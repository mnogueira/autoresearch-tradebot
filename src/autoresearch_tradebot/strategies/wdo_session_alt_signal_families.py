from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_python import POINT_VALUE_BRL, ROUND_TRIP_COST_BRL, V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_wdo_alt_session_signal_families_20260328")


def allowed_entry_time(timestamp: pd.Timestamp) -> bool:
    return timestamp.weekday() < 5 and timestamp.hour in {10, 11, 12, 14}


def prepare_bars(dataset: V10Dataset) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    bars["session_date"] = bars["session_date"].astype("datetime64[ns]")
    bars["spread_price"] = bars["Spread"].astype(float) * 0.001
    bars["atr20"] = dataset.get_atr_current(20)

    m15_close = bars["Close"].resample("15min").last()
    m15_ema5 = m15_close.ewm(span=5, adjust=False).mean()
    m15_ema21 = m15_close.ewm(span=21, adjust=False).mean()
    m15_cross_up = (m15_ema5 > m15_ema21) & (m15_ema5.shift(1) <= m15_ema21.shift(1))
    m15_cross_dn = (m15_ema5 < m15_ema21) & (m15_ema5.shift(1) >= m15_ema21.shift(1))
    bars["m15_ema5"] = m15_ema5.reindex(bars.index, method="ffill")
    bars["m15_ema21"] = m15_ema21.reindex(bars.index, method="ffill")
    bars["m15_cross_up"] = m15_cross_up.reindex(bars.index, method="ffill").fillna(False)
    bars["m15_cross_dn"] = m15_cross_dn.reindex(bars.index, method="ffill").fillna(False)

    close = bars["Close"]
    mean20 = close.rolling(20, min_periods=20).mean()
    std20 = close.rolling(20, min_periods=20).std(ddof=0)
    bars["bb_mid"] = mean20
    bars["bb_upper"] = mean20 + (2.0 * std20)
    bars["bb_lower"] = mean20 - (2.0 * std20)
    return bars


def append_trade(trades: list[dict[str, object]], session_date: pd.Timestamp, direction: int, entry_time: pd.Timestamp, exit_time: pd.Timestamp, entry_price: float, exit_price: float, stop_price: float, target_price: float, exit_reason: str) -> None:
    pnl_points = (exit_price - entry_price) * float(direction)
    pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
    trades.append(
        {
            "session_date": session_date.date().isoformat(),
            "signal_time": str(entry_time),
            "entry_time": str(entry_time),
            "exit_time": str(exit_time),
            "direction": "long" if direction == 1 else "short",
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "stop_price": round(stop_price, 2),
            "target_price": round(target_price, 2),
            "pnl_points": round(pnl_points, 2),
            "pnl_brl": round(float(pnl_brl), 2),
            "exit_reason": exit_reason,
        }
    )


def run_market_entry_strategy(
    bars: pd.DataFrame,
    trade_dates: pd.Index,
    *,
    name: str,
    long_signal: pd.Series,
    short_signal: pd.Series,
    sl_mult: float = 0.84,
    tp_mult: float = 0.30,
) -> dict[str, object]:
    trades: list[dict[str, object]] = []
    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    entry_time = pd.NaT
    current_session = None

    rows = bars.reset_index().rename(columns={"time": "timestamp"})
    for idx in range(1, len(rows)):
        row = rows.iloc[idx]
        timestamp = pd.Timestamp(row["timestamp"])
        session_date = pd.Timestamp(row["session_date"])
        if current_session is None:
            current_session = session_date
        if session_date != current_session:
            if position != 0:
                exit_price = float(row["Open"]) if position == -1 else float(row["Open"])
                append_trade(trades, current_session, position, entry_time, timestamp, entry_price, exit_price, stop_price, target_price, "forced_day_change")
                position = 0
            current_session = session_date

        if position != 0:
            high_price = float(row["High"])
            low_price = float(row["Low"])
            exit_price = None
            exit_reason = None
            if position == 1:
                if low_price <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                elif high_price >= target_price:
                    exit_price = target_price
                    exit_reason = "take_profit"
            else:
                if high_price >= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop_loss"
                elif low_price <= target_price:
                    exit_price = target_price
                    exit_reason = "take_profit"
            if exit_price is not None:
                append_trade(trades, session_date, position, entry_time, timestamp, entry_price, exit_price, stop_price, target_price, str(exit_reason))
                position = 0
                continue

        if position != 0 or not allowed_entry_time(timestamp):
            continue

        atr_value = float(row["atr20"]) if pd.notna(row["atr20"]) else np.nan
        if not np.isfinite(atr_value) or atr_value <= 0.0:
            continue

        if bool(long_signal.iloc[idx - 1]):
            entry_price = float(row["Open"] + row["spread_price"])
            stop_price = entry_price - (atr_value * sl_mult)
            target_price = entry_price + (atr_value * tp_mult)
            entry_time = timestamp
            position = 1
        elif bool(short_signal.iloc[idx - 1]):
            entry_price = float(row["Open"])
            stop_price = entry_price + (atr_value * sl_mult)
            target_price = entry_price - (atr_value * tp_mult)
            entry_time = timestamp
            position = -1

    trades_df = pd.DataFrame(trades)
    metrics = calculate_metrics(trades_df, trade_dates)
    return {"name": name, "metrics": metrics}


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    bars = prepare_bars(dataset)

    ema_results = []
    for sl_mult, tp_mult in [(0.60, 0.24), (0.84, 0.30), (1.08, 0.42), (0.84, 0.42), (0.60, 0.30)]:
        ema_results.append(
            run_market_entry_strategy(
                bars,
                dataset.trade_dates,
                name=f"ema_5_21_crossover_session_entry_sl{str(sl_mult).replace('.', 'p')}_tp{str(tp_mult).replace('.', 'p')}",
                long_signal=bars["m15_cross_up"],
                short_signal=bars["m15_cross_dn"],
                sl_mult=sl_mult,
                tp_mult=tp_mult,
            )
        )
    ema_result = max(ema_results, key=lambda item: float(item["metrics"]["on_tester_value"]))

    boll_long = (bars["Close"].shift(1) <= bars["bb_lower"].shift(1)) & (bars["Close"].shift(1) > bars["m15_ema21"].shift(1))
    boll_short = (bars["Close"].shift(1) >= bars["bb_upper"].shift(1)) & (bars["Close"].shift(1) < bars["m15_ema21"].shift(1))
    boll_result = run_market_entry_strategy(
        bars,
        dataset.trade_dates,
        name="bollinger_mean_reversion_with_trend_session_entry",
        long_signal=boll_long.fillna(False),
        short_signal=boll_short.fillna(False),
    )

    summary = {
        "notes": [
            "These are lightweight bar-based prototype screens, not MT5 parity backtests.",
            "They are meant to answer whether alternate signal families deserve more engineering time.",
        ],
        "results": ema_results + [boll_result],
        "best_ema_variant": ema_result,
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
