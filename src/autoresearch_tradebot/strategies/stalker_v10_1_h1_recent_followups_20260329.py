from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from ..common.wdo_data import locate_wdo_bar_file
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import (
    BIG_NUMBER,
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    TradeRecord,
    V10Dataset,
    calculate_metrics,
    locate_data_file,
    round_to_tick,
    standardize_m1_columns,
)

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_h1_recent_followups_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _load_h1_bars() -> pd.DataFrame:
    path = locate_wdo_bar_file("1h", extra_candidates=[Path("data") / "wdo_h1.parquet"])
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path).copy()
    else:
        frame = pd.read_parquet(path).copy()
    if "time" in frame.columns:
        frame["time"] = pd.to_datetime(frame["time"])
        frame = frame.set_index("time")
    frame = standardize_m1_columns(frame)
    frame = frame.sort_index()
    frame["session_date"] = frame.index.normalize()
    frame["spread_price"] = frame["Spread"].astype(float) * 0.001 if "Spread" in frame.columns else 0.5
    return frame[["Open", "High", "Low", "Close", "Volume", "spread_price", "session_date"]].copy()


def _build_h1_reference(bars: pd.DataFrame) -> pd.DataFrame:
    daily = bars.groupby("session_date").agg(
        day_high=("High", "max"),
        day_low=("Low", "min"),
    )
    daily["range_points"] = daily["day_high"] - daily["day_low"]
    daily["contract_id"] = daily.index.to_period("M").astype(str)
    previous_contract_mean = daily.groupby("contract_id")["range_points"].mean().sort_index().shift(1)
    daily["previous_contract_average"] = daily["contract_id"].map(previous_contract_mean)

    high = bars["High"].astype(float)
    low = bars["Low"].astype(float)
    close = bars["Close"].astype(float)
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # 5 H1 bars ~= original 20 x 15m ATR horizon.
    bars["atr_h1_proxy"] = tr.ewm(alpha=(1.0 / 5.0), adjust=False, min_periods=5).mean()

    close_diff = close.diff()
    trend_window = 4
    bars["trend_eff_h1_proxy"] = (close - close.shift(trend_window)) / close_diff.abs().rolling(
        trend_window, min_periods=trend_window
    ).sum()
    bars["previous_contract_average"] = bars["session_date"].map(daily["previous_contract_average"])
    return bars


def _allowed_entry_hour(timestamp: pd.Timestamp) -> bool:
    return timestamp.weekday() < 5 and timestamp.hour in {10, 11, 12, 14}


def _append_trade(
    trades: list[TradeRecord],
    *,
    session_date: pd.Timestamp,
    signal_time: pd.Timestamp,
    entry_time: pd.Timestamp,
    exit_time: pd.Timestamp,
    direction: int,
    entry_price: float,
    exit_price: float,
    stop_price: float,
    target_price: float,
    fill_reason: str,
    exit_reason: str,
) -> None:
    pnl_points = (float(exit_price) - float(entry_price)) * float(direction)
    pnl_brl = (pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL
    trades.append(
        TradeRecord(
            session_date=session_date.date().isoformat(),
            signal_time=str(signal_time),
            entry_time=str(entry_time),
            exit_time=str(exit_time),
            direction="long" if direction == 1 else "short",
            entry_price=round(float(entry_price), 2),
            exit_price=round(float(exit_price), 2),
            stop_price=round(float(stop_price), 2),
            target_price=round(float(target_price), 2),
            pnl_points=round(float(pnl_points), 2),
            pnl_brl=round(float(pnl_brl), 2),
            fill_reason=fill_reason,
            exit_reason=exit_reason,
        )
    )


def run_h1_proxy_strategy(
    bars: pd.DataFrame,
    *,
    max_bars_in_trade: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    params = session_winner_params()
    trade_dates = pd.Index(sorted(pd.to_datetime(bars["session_date"]).unique()))
    trades: list[TradeRecord] = []

    current_session: pd.Timestamp | None = None
    session_high = 0.0
    session_low = BIG_NUMBER
    previous_high = 0.0
    previous_low = BIG_NUMBER
    last_row: pd.Series | None = None

    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    entry_time = pd.NaT
    signal_time = pd.NaT
    entry_session_date = pd.NaT
    entry_bar_number = 0
    pending_order: dict[str, Any] | None = None

    rows = bars.reset_index()
    timestamp_column = rows.columns[0]
    rows = rows.rename(columns={timestamp_column: "timestamp"})
    for row_index, row in rows.iterrows():
        timestamp = pd.Timestamp(row["timestamp"])
        session_date = pd.Timestamp(row["session_date"])
        spread_price = float(row["spread_price"])

        if current_session is None or session_date != current_session:
            if position != 0 and last_row is not None:
                forced_exit_price = float(last_row["Close"]) if position == 1 else float(last_row["Close"]) + float(last_row["spread_price"])
                _append_trade(
                    trades,
                    session_date=current_session,
                    signal_time=signal_time,
                    entry_time=entry_time,
                    exit_time=pd.Timestamp(last_row["timestamp"]),
                    direction=position,
                    entry_price=entry_price,
                    exit_price=forced_exit_price,
                    stop_price=stop_price,
                    target_price=target_price,
                    fill_reason="h1_proxy_limit",
                    exit_reason="forced_day_change",
                )
                position = 0
            current_session = session_date
            session_high = float(row["Open"])
            session_low = float(row["Open"])
            previous_high = 0.0
            previous_low = BIG_NUMBER
            pending_order = None

        if position != 0:
            exit_price: float | None = None
            exit_reason: str | None = None
            high_price = float(row["High"])
            low_price = float(row["Low"])
            ask_high = high_price + spread_price
            ask_low = low_price + spread_price

            if position == 1:
                if low_price <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                elif high_price >= target_price:
                    exit_price = target_price
                    exit_reason = "take_profit"
            else:
                if ask_high >= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                elif ask_low <= target_price:
                    exit_price = target_price
                    exit_reason = "take_profit"

            if exit_price is None and max_bars_in_trade is not None and (int(row_index) - entry_bar_number) >= int(max_bars_in_trade):
                exit_price = float(row["Open"]) if position == 1 else float(row["Open"]) + spread_price
                exit_reason = "max_hold"

            if exit_price is not None and exit_reason is not None:
                _append_trade(
                    trades,
                    session_date=session_date,
                    signal_time=signal_time,
                    entry_time=entry_time,
                    exit_time=timestamp,
                    direction=position,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    stop_price=stop_price,
                    target_price=target_price,
                    fill_reason="h1_proxy_limit",
                    exit_reason=exit_reason,
                )
                position = 0
                pending_order = None

        if position == 0 and pending_order is not None:
            if not _allowed_entry_hour(timestamp):
                pending_order = None
            else:
                limit_price = float(pending_order["limit_price"])
                if int(pending_order["direction"]) == 1 and float(row["Low"]) <= limit_price:
                    entry_price = limit_price + spread_price
                    stop_price = float(pending_order["stop_price"]) + spread_price
                    target_price = float(pending_order["target_price"]) + spread_price
                    entry_time = timestamp
                    signal_time = pd.Timestamp(pending_order["signal_time"])
                    entry_session_date = session_date
                    entry_bar_number = int(row_index)
                    position = 1
                    pending_order = None
                elif int(pending_order["direction"]) == -1 and float(row["High"]) >= limit_price:
                    entry_price = limit_price
                    stop_price = float(pending_order["stop_price"])
                    target_price = float(pending_order["target_price"])
                    entry_time = timestamp
                    signal_time = pd.Timestamp(pending_order["signal_time"])
                    entry_session_date = session_date
                    entry_bar_number = int(row_index)
                    position = -1
                    pending_order = None

        current_day_high = max(session_high, float(row["High"]))
        current_day_low = min(session_low, float(row["Low"]))
        current_day_range = current_day_high - current_day_low
        contract_range_filter_value = float(row["previous_contract_average"]) * float(params.FilterAsPercOfContractMARange)
        atr_value = float(row["atr_h1_proxy"])
        trend_eff_value = float(row["trend_eff_h1_proxy"])

        if position == 0 and _allowed_entry_hour(timestamp):
            if (
                current_day_range > 0.0
                and np.isfinite(contract_range_filter_value)
                and contract_range_filter_value > 0.0
                and current_day_range >= contract_range_filter_value
                and np.isfinite(atr_value)
                and atr_value > 0.0
            ):
                if float(row["High"]) > previous_high and np.isfinite(trend_eff_value) and trend_eff_value >= float(params.MinDirectionalTrendEfficiency15m):
                    base_price = round_to_tick(current_day_high - (current_day_range * float(params.RetracementLevel)))
                    pending_order = {
                        "direction": 1,
                        "limit_price": float(base_price),
                        "stop_price": round_to_tick(base_price - (atr_value * float(params.SL_ATRMultiplier))),
                        "target_price": round_to_tick(base_price + (atr_value * float(params.TP_ATRMultiplier))),
                        "signal_time": timestamp,
                    }
                elif (
                    float(row["Low"]) < previous_low
                    and not (timestamp.weekday() == 2)
                    and float(row["Volume"]) >= float(params.MinSignalVolumeWindowSum)
                ):
                    base_price = round_to_tick(current_day_low + (current_day_range * float(params.RetracementLevel)))
                    pending_order = {
                        "direction": -1,
                        "limit_price": float(base_price),
                        "stop_price": round_to_tick(base_price + (atr_value * float(params.SL_ATRMultiplier))),
                        "target_price": round_to_tick(base_price - (atr_value * float(params.TP_ATRMultiplier))),
                        "signal_time": timestamp,
                    }

        session_high = current_day_high
        session_low = current_day_low
        previous_high = max(previous_high, float(row["High"]))
        previous_low = min(previous_low, float(row["Low"]))
        last_row = row

    if position != 0 and last_row is not None:
        final_exit_price = float(last_row["Close"]) if position == 1 else float(last_row["Close"]) + float(last_row["spread_price"])
        _append_trade(
            trades,
            session_date=entry_session_date if pd.notna(entry_session_date) else pd.Timestamp(last_row["session_date"]),
            signal_time=signal_time,
            entry_time=entry_time,
            exit_time=pd.Timestamp(last_row["timestamp"]),
            direction=position,
            entry_price=entry_price,
            exit_price=final_exit_price,
            stop_price=stop_price,
            target_price=target_price,
            fill_reason="h1_proxy_limit",
            exit_reason="forced_end_of_sample",
        )

    trades_df = pd.DataFrame([trade.__dict__ for trade in trades])
    metrics = calculate_metrics(trades_df, trade_dates)
    return trades_df, metrics


def _last_trades_payload(name: str, trades: pd.DataFrame, full_metrics: dict[str, Any]) -> dict[str, Any]:
    tail = trades.tail(5).copy()
    if tail.empty:
        return {"name": name, "last_5_trades": [], "recent_5_trade_metrics": {}, "full_sample_metrics": full_metrics}
    recent_dates = pd.Index(pd.to_datetime(tail["session_date"]).dt.normalize().unique())
    recent_metrics = calculate_metrics(tail, recent_dates)
    return {
        "name": name,
        "last_5_trades": tail[
            [
                "session_date",
                "signal_time",
                "entry_time",
                "exit_time",
                "direction",
                "entry_price",
                "exit_price",
                "pnl_brl",
                "fill_reason",
                "exit_reason",
            ]
        ].to_dict(orient="records"),
        "recent_5_trade_metrics": recent_metrics,
        "full_sample_metrics": full_metrics,
        "deltas_vs_full_sample": {
            "win_rate_delta": round(float(recent_metrics["win_rate"]) - float(full_metrics["win_rate"]), 4),
            "avg_profit_brl_delta": round(float(recent_metrics["avg_profit_brl"]) - float(full_metrics["avg_profit_brl"]), 2),
            "profit_factor_delta": round(float(recent_metrics["profit_factor"]) - float(full_metrics["profit_factor"]), 4),
        },
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    tier1_filter = session_filter({10, 11, 12, 13, 14})
    tier2_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    tier2a_filter = _combine_filters(tier2_filter, roc5_filter)

    tier1_trades, tier1_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=tier1_filter,
        management=ManagementConfig(),
    )
    tier2a_trades, tier2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=tier2a_filter,
        management=ManagementConfig(min_minutes_between_entries=25),
    )

    h1_bars = _build_h1_reference(_load_h1_bars())
    h1_trades, h1_metrics = run_h1_proxy_strategy(h1_bars, max_bars_in_trade=None)
    h1_maxhold_trades, h1_maxhold_metrics = run_h1_proxy_strategy(h1_bars, max_bars_in_trade=3)

    summary = {
        "paper_forward_last_5_trades": {
            "tier1_exact_analog_monday_default": _last_trades_payload("tier1_exact_analog_monday_default", tier1_trades, tier1_metrics),
            "tier2a_exact_upgrade_candidate": _last_trades_payload("tier2a_exact_upgrade_candidate", tier2a_trades, tier2a_metrics),
        },
        "h1_proxy_variants": {
            "h1_core_proxy": {
                "metrics": h1_metrics,
                **_risk_block(h1_trades, pd.Index(sorted(pd.to_datetime(h1_bars["session_date"]).unique()))),
                "notes": "Bar-based H1 proxy of the v10.1 retracement family using H1 bars, 4-bar H1 trend efficiency, 5-bar H1 ATR, session hours, and the same 0.25 retracement logic.",
            },
            "h1_core_proxy_maxhold3bars": {
                "metrics": h1_maxhold_metrics,
                **_risk_block(h1_maxhold_trades, pd.Index(sorted(pd.to_datetime(h1_bars["session_date"]).unique()))),
                "notes": "Same H1 proxy with a 3-bar max-hold to mimic the 150-minute hold cap in the current Tier 3 line.",
            },
        },
        "notes": [
            "The H1 section is a bar-based proxy, not an exact every-tick translation. It is meant to answer whether the signal family is even directionally viable on a slower timeframe.",
            "The paper-forward section uses the exact M1 engine and simply reports the most recent five realized trades from the selected lines.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tier1_trades.tail(5).to_csv(DEFAULT_OUTPUT_DIR / "tier1_last5_trades.csv", index=False)
    tier2a_trades.tail(5).to_csv(DEFAULT_OUTPUT_DIR / "tier2a_last5_trades.csv", index=False)
    h1_trades.to_csv(DEFAULT_OUTPUT_DIR / "h1_core_proxy_trades.csv", index=False)
    h1_maxhold_trades.to_csv(DEFAULT_OUTPUT_DIR / "h1_core_proxy_maxhold3bars_trades.csv", index=False)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
