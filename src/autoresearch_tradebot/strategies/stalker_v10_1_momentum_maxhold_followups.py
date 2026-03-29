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
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_momentum_maxhold_followups_20260328")


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


def _increasing_directional_strength_filter(dataset: V10Dataset, window_minutes: int) -> Callable[[dict[str, Any]], bool]:
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
        if idx < 2:
            return False
        recent = raw_values[idx - 2 : idx + 1]
        if recent.shape[0] != 3 or not np.isfinite(recent).all():
            return False
        directional_recent = recent * float(direction)
        return bool(
            directional_recent[0] < directional_recent[1] < directional_recent[2]
        )

    return _allow


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    cooldown_25_trades, cooldown_25_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=25),
    )

    cooldown_25_maxhold_trades, cooldown_25_maxhold_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=120),
    )

    cooldown_30_maxhold_trades, cooldown_30_maxhold_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    momentum_filter = _increasing_directional_strength_filter(
        dataset=dataset,
        window_minutes=int(params.TrendEfficiencyWindowMinutes),
    )
    momentum_trades, momentum_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(base_filter, momentum_filter),
        management=ManagementConfig(min_minutes_between_entries=25),
    )

    summary = {
        "cooldown_25_reference": _result_block(
            cooldown_25_trades,
            cooldown_25_metrics,
            dataset.trade_dates,
            "Session winner with the new 25-minute cooldown sweep winner.",
        ),
        "cooldown_25_plus_maxhold120": _result_block(
            cooldown_25_maxhold_trades,
            cooldown_25_maxhold_metrics,
            dataset.trade_dates,
            "Same exact line, but with the 120-minute max-hold layered onto the 25-minute cooldown.",
        ),
        "cooldown_30_plus_maxhold120_reference": _result_block(
            cooldown_30_maxhold_trades,
            cooldown_30_maxhold_metrics,
            dataset.trade_dates,
            "Prior exact Tier 3 reference using the 30-minute cooldown and 120-minute max-hold.",
        ),
        "signal_momentum_last_3_bars": _result_block(
            momentum_trades,
            momentum_metrics,
            dataset.trade_dates,
            "Require the directional trend-efficiency value to be strictly increasing across the last three bars.",
        ),
        "notes": [
            "The 20-minute cooldown was already evaluated in the earlier sweep and came back below the 25-minute winner.",
            "Signal momentum is tested as a binary gate on top of the new 25-minute cooldown winner.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
