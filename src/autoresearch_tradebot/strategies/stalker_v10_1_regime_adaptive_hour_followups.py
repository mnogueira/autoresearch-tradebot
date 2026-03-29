from __future__ import annotations

import json
from typing import Any, Callable

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_followups import combine_runs, combine_entry_filters, regime_day_filter, split_trade_dates_by_adx
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
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_regime_adaptive_hour_followups_20260329")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _build_adaptive_hour_map(
    reference_trades: pd.DataFrame,
    trade_dates: pd.Index,
    base_hours: set[int],
    lookback_days: int,
) -> tuple[dict[str, set[int]], dict[str, Any]]:
    frame = reference_trades.copy()
    if frame.empty:
        allow_map = {
            pd.Timestamp(value).date().isoformat(): set(base_hours)
            for value in pd.to_datetime(trade_dates)
        }
        return allow_map, {
            "lookback_days": int(lookback_days),
            "average_allowed_hours_per_day": float(len(base_hours)),
            "days_with_any_skip": 0,
            "days_forced_back_to_base": 0,
        }

    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["entry_hour"] = pd.to_datetime(frame["entry_time"]).dt.hour.astype(int)
    hourly = (
        frame.groupby(["session_date", "entry_hour"])["pnl_brl"]
        .sum()
        .unstack(fill_value=0.0)
        .reindex(columns=sorted(base_hours), fill_value=0.0)
    )
    normalized_dates = pd.DatetimeIndex(pd.to_datetime(trade_dates)).normalize()
    hourly = hourly.reindex(normalized_dates, fill_value=0.0)

    allow_map: dict[str, set[int]] = {}
    allowed_count: list[int] = []
    skipped_days = 0
    forced_full_reset_days = 0

    for idx, session_date in enumerate(normalized_dates):
        if idx < int(lookback_days):
            allowed = set(base_hours)
        else:
            trailing = hourly.iloc[idx - int(lookback_days) : idx].sum(axis=0)
            allowed = {int(hour) for hour in base_hours if float(trailing.get(hour, 0.0)) >= 0.0}
            if len(allowed) < len(base_hours):
                skipped_days += 1
            if not allowed:
                allowed = set(base_hours)
                forced_full_reset_days += 1

        allow_map[pd.Timestamp(session_date).date().isoformat()] = allowed
        allowed_count.append(len(allowed))

    stats = {
        "lookback_days": int(lookback_days),
        "average_allowed_hours_per_day": round(float(pd.Series(allowed_count).mean()), 4),
        "days_with_any_skip": int(skipped_days),
        "days_forced_back_to_base": int(forced_full_reset_days),
    }
    return allow_map, stats


def _adaptive_hour_filter(allow_map: dict[str, set[int]], base_hours: set[int]) -> Callable[[dict[str, Any]], bool]:
    fallback = set(base_hours)

    def _allow(context: dict[str, Any]) -> bool:
        session_key = pd.Timestamp(context["session_date"]).date().isoformat()
        allowed_hours = allow_map.get(session_key, fallback)
        return int(context["entry_hour"]) in allowed_hours

    return _allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_hours = {10, 11, 12, 14}
    base_filter = session_filter(base_hours)

    tier2_management = ManagementConfig(min_minutes_between_entries=25)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2_trades, tier2_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=tier2_management,
    )
    tier3_trades, tier3_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=tier3_management,
    )

    trend_dates, range_dates, _ = split_trade_dates_by_adx(dataset, threshold=25.0)
    trend_day_set = {pd.Timestamp(value).date().isoformat() for value in trend_dates}
    range_day_set = {pd.Timestamp(value).date().isoformat() for value in range_dates}

    trend_tier3_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(trend_day_set)),
        management=tier3_management,
    )
    range_tier2_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(range_day_set)),
        management=tier2_management,
    )
    regime_switch_trades, regime_switch_metrics = combine_runs(
        [trend_tier3_trades, range_tier2_trades],
        dataset.trade_dates,
    )

    adaptive_hour_map, adaptive_stats = _build_adaptive_hour_map(
        reference_trades=tier2_trades,
        trade_dates=dataset.trade_dates,
        base_hours=base_hours,
        lookback_days=10,
    )
    adaptive_filter = _adaptive_hour_filter(adaptive_hour_map, base_hours)
    adaptive_hour_trades, adaptive_hour_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, adaptive_filter),
        management=tier2_management,
    )

    summary = {
        "reference_tier2_cooldown_25m": {
            "metrics": tier2_metrics,
            **_risk_block(tier2_trades, dataset.trade_dates),
        },
        "reference_tier3_cooldown_25m_maxhold_150m1": {
            "metrics": tier3_metrics,
            **_risk_block(tier3_trades, dataset.trade_dates),
        },
        "regime_switch_tier2_range_tier3_trend": {
            "rule": "Use Tier 2 on prior-day ADX <= 25 days and Tier 3 on prior-day ADX > 25 days.",
            "trend_day_count": int(len(trend_dates)),
            "range_day_count": int(len(range_dates)),
            "metrics": regime_switch_metrics,
            **_risk_block(regime_switch_trades, dataset.trade_dates),
        },
        "dynamic_session_hours_from_trailing_10d_hour_pnl": {
            "rule": "Start from hours 10/11/12/14, then skip any hour whose prior 10-trading-day Tier 2 PnL is negative.",
            "metrics": adaptive_hour_metrics,
            **_risk_block(adaptive_hour_trades, dataset.trade_dates),
            "adaptive_hour_stats": adaptive_stats,
        },
        "notes": [
            "The regime switch is exact at the day level because positions are flattened by session end, so Tier 2 and Tier 3 can be combined safely across disjoint day sets.",
            "The adaptive hour schedule is an exact rerun under a precomputed day-by-day hour map derived from the baseline Tier 2 trade tape.",
            "That adaptive hour overlay should be treated as a research follow-up, not as a Monday default, because its schedule is keyed off prior realized hour PnL from the baseline strategy.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
