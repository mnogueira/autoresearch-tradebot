from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_followup_screening import build_session_vwap_prev_array
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import POINT_VALUE_BRL, V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_vwap_risk_cooldown_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _vwap_direction_filter(dataset: V10Dataset, vwap_prev: pd.Series) -> Callable[[dict[str, Any]], bool]:
    previous_close = dataset.bars_m1.groupby("session_date")["Close"].shift(1)
    close_values = previous_close.to_numpy(dtype=float)
    vwap_values = pd.Series(vwap_prev).to_numpy(dtype=float)

    def _filter(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        direction = int(context["direction"])
        close_value = float(close_values[idx])
        vwap_value = float(vwap_values[idx])
        if pd.isna(close_value) or pd.isna(vwap_value):
            return False
        if direction == 1:
            return close_value > vwap_value
        if direction == -1:
            return close_value < vwap_value
        return False

    return _filter


def _recent_winrate_overlay(
    trades: pd.DataFrame,
    trade_dates: pd.Index,
    lookback_trades: int = 20,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    if trades.empty:
        empty_metrics = calculate_metrics(pd.DataFrame(), trade_dates)
        return pd.DataFrame(), empty_metrics, {
            "lookback_trades": int(lookback_trades),
            "avg_size_multiplier": 0.0,
            "full_size_share": 0.0,
            "half_size_share": 0.0,
            "skip_share": 0.0,
        }

    frame = trades.copy()
    frame["entry_time"] = pd.to_datetime(frame["entry_time"])
    frame = frame.sort_values("entry_time").reset_index(drop=True)

    sizes: list[float] = []
    wins = frame["pnl_brl"].astype(float) > 0.0
    for idx in range(len(frame)):
        if idx < int(lookback_trades):
            sizes.append(1.0)
            continue
        trailing_winrate = float(wins.iloc[idx - int(lookback_trades) : idx].mean())
        if trailing_winrate > 0.80:
            sizes.append(1.0)
        elif trailing_winrate >= 0.60:
            sizes.append(0.5)
        else:
            sizes.append(0.0)

    frame["size_multiplier"] = sizes
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["size_multiplier"]
    frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["size_multiplier"]
    frame = frame.loc[frame["size_multiplier"] > 0.0].reset_index(drop=True)
    metrics = calculate_metrics(frame, trade_dates)
    stats = {
        "lookback_trades": int(lookback_trades),
        "avg_size_multiplier": round(float(pd.Series(sizes).mean()), 4),
        "full_size_share": round(float((pd.Series(sizes) == 1.0).mean()), 4),
        "half_size_share": round(float((pd.Series(sizes) == 0.5).mean()), 4),
        "skip_share": round(float((pd.Series(sizes) == 0.0).mean()), 4),
    }
    return frame, metrics, stats


def _result_block(trades: pd.DataFrame, metrics: dict[str, Any], trade_dates: pd.Index, note: str) -> dict[str, Any]:
    return {
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "note": note,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )

    vwap_prev = pd.Series(build_session_vwap_prev_array(dataset), index=dataset.bars_m1.index)
    vwap_filter = _vwap_direction_filter(dataset, vwap_prev)
    vwap_trades, vwap_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(base_filter, vwap_filter),
        management=ManagementConfig(min_minutes_between_entries=30),
    )

    overlay_trades, overlay_metrics, overlay_stats = _recent_winrate_overlay(
        trades=reference_trades,
        trade_dates=dataset.trade_dates,
        lookback_trades=20,
    )

    cooldown_results: list[dict[str, Any]] = []
    for minutes in (15, 20, 25, 30, 35, 40):
        cooldown_trades, cooldown_metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(min_minutes_between_entries=int(minutes)),
        )
        cooldown_results.append(
            {
                "cooldown_minutes": int(minutes),
                "metrics": cooldown_metrics,
                **_risk_block(cooldown_trades, dataset.trade_dates),
            }
        )

    cooldown_ranked = sorted(
        cooldown_results,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["metrics"]["profit_factor"]),
            float(row["metrics"]["net_profit_brl"]),
            -float(row["metrics"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )

    summary = {
        "reference_tier2_cooldown_only": _result_block(
            reference_trades,
            reference_metrics,
            dataset.trade_dates,
            "Session winner + 30-minute cooldown only.",
        ),
        "trend_efficiency_plus_vwap_confirmation": _result_block(
            vwap_trades,
            vwap_metrics,
            dataset.trade_dates,
            "Require the previous close to be above session VWAP for longs and below session VWAP for shorts.",
        ),
        "adaptive_recent_winrate_scaling": {
            "metrics": overlay_metrics,
            **_risk_block(overlay_trades, dataset.trade_dates),
            "stats": overlay_stats,
            "note": "Research-only overlay: last 20 closed trades decide whether the next trade is full size, half size, or skipped.",
        },
        "cooldown_duration_sweep": cooldown_ranked,
        "notes": [
            "VWAP confirmation is an exact every-tick rerun on top of the Tier 2 session winner.",
            "Adaptive win-rate sizing is analysis-only because it assumes fractional down-scaling from a 1-contract baseline.",
            "Cooldown durations are ranked by the same Sortino-weighted composite used across the rest of the sprint.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
