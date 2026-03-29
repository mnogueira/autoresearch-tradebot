from __future__ import annotations

import json
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
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
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_fine_cooldown_momentum_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _result_block(
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
    note: str,
) -> dict[str, Any]:
    return {
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "note": note,
    }


def _recent_metrics(trades: pd.DataFrame, trade_dates: pd.Index, recent_dates: pd.Index) -> dict[str, Any]:
    if trades.empty:
        recent_trades = trades
    else:
        session_dates = pd.to_datetime(trades["session_date"]).dt.normalize()
        recent_index = pd.Index(pd.to_datetime(recent_dates))
        recent_trades = trades.loc[session_dates.isin(recent_index)].reset_index(drop=True)
    metrics = calculate_metrics(recent_trades, pd.Index(pd.to_datetime(recent_dates)))
    return {
        "metrics": metrics,
        **_risk_block(recent_trades, pd.Index(pd.to_datetime(recent_dates))),
    }


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _increasing_directional_strength_filter(
    dataset: V10Dataset,
    window_minutes: int,
    consecutive_bars: int,
) -> Callable[[dict[str, Any]], bool]:
    strength_cache = _ensure_signal_strength_cache(
        dataset,
        trend_window=int(window_minutes),
        volume_window=30,
        relative_volume_lookback=20,
    )
    raw_values = np.asarray(strength_cache["trend_efficiency_raw"], dtype=float)

    def _allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        direction = int(context["direction"])
        bars = int(consecutive_bars)
        start = idx - bars + 1
        if start < 0:
            return False
        recent = raw_values[start : idx + 1]
        if recent.shape[0] != bars or not np.isfinite(recent).all():
            return False
        directional_recent = recent * float(direction)
        return bool(np.all(np.diff(directional_recent) > 0.0))

    return _allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    recent_dates = dataset.trade_dates[-30:]

    fine_cooldown_results: list[dict[str, Any]] = []
    fine_cooldown_trade_map: dict[int, pd.DataFrame] = {}
    for minutes in (15, 18, 20, 22, 25):
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(
                min_minutes_between_entries=int(minutes),
                max_bars_in_trade=120,
            ),
        )
        fine_cooldown_trade_map[int(minutes)] = trades
        fine_cooldown_results.append(
            {
                "cooldown_minutes": int(minutes),
                "metrics": metrics,
                **_risk_block(trades, dataset.trade_dates),
                "recent_30d": _recent_metrics(trades, dataset.trade_dates, recent_dates),
            }
        )

    fine_cooldown_ranked = sorted(
        fine_cooldown_results,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["metrics"]["profit_factor"]),
            float(row["metrics"]["net_profit_brl"]),
            -float(row["metrics"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )

    momentum_results: dict[str, Any] = {}
    for bars in (2, 3):
        momentum_filter = _increasing_directional_strength_filter(
            dataset=dataset,
            window_minutes=int(params.TrendEfficiencyWindowMinutes),
            consecutive_bars=int(bars),
        )
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=_combine_filters(base_filter, momentum_filter),
            management=ManagementConfig(
                min_minutes_between_entries=25,
                max_bars_in_trade=120,
            ),
        )
        momentum_results[f"increasing_{bars}_bars"] = {
            "metrics": metrics,
            **_risk_block(trades, dataset.trade_dates),
            "recent_30d": _recent_metrics(trades, dataset.trade_dates, recent_dates),
            "note": f"Require directional trend-efficiency to be strictly increasing across the last {bars} bars.",
        }

    recent_comparison = {
        "cooldown_25_maxhold120": _recent_metrics(
            fine_cooldown_trade_map[25],
            dataset.trade_dates,
            recent_dates,
        ),
    }

    trades_30, metrics_30 = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
        ),
    )
    recent_comparison["cooldown_30_maxhold120"] = _recent_metrics(trades_30, dataset.trade_dates, recent_dates)
    recent_comparison["cooldown_30_maxhold120"]["full_sample"] = {
        "metrics": metrics_30,
        **_risk_block(trades_30, dataset.trade_dates),
    }

    summary = {
        "fine_cooldown_sweep_with_maxhold": fine_cooldown_ranked,
        "signal_momentum_followups": momentum_results,
        "recent_30d_comparison": recent_comparison,
        "notes": [
            "This sweep refines the cooldown search specifically on top of the max-hold production line.",
            "Signal momentum is evaluated as a binary gate with 2-bar and 3-bar strengthening checks.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
