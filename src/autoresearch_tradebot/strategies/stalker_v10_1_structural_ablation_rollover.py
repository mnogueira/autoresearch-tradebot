from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_followups import (
    combine_entry_filters,
    regime_day_filter,
    split_trade_dates_by_adx,
)
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_structural_ablation_rollover_20260328")


def impact_vs_reference(reference: dict[str, float], candidate: dict[str, float]) -> dict[str, float]:
    return {
        "net_profit_brl_delta": round(float(candidate["net_profit_brl"]) - float(reference["net_profit_brl"]), 2),
        "profit_factor_delta": round(float(candidate["profit_factor"]) - float(reference["profit_factor"]), 4),
        "max_drawdown_pct_delta": round(
            float(candidate["max_drawdown_pct"]) - float(reference["max_drawdown_pct"]),
            2,
        ),
        "win_rate_delta": round(float(candidate["win_rate"]) - float(reference["win_rate"]), 4),
        "total_trades_delta": int(candidate["total_trades"]) - int(reference["total_trades"]),
        "on_tester_value_delta": round(
            float(candidate["on_tester_value"]) - float(reference["on_tester_value"]),
            6,
        ),
    }


def filter_trades_to_dates(trades: pd.DataFrame, trade_dates: pd.Index) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    date_set = set(pd.to_datetime(trade_dates).normalize())
    session_dates = pd.to_datetime(trades["session_date"]).dt.normalize()
    return trades.loc[session_dates.isin(date_set)].copy()


def contract_rollover_buckets(dataset: V10Dataset) -> pd.DataFrame:
    daily = dataset.daily.copy()
    daily["contract_length"] = daily.groupby("contract_id")["contract_day_number"].transform("max")
    daily["contract_days_to_end"] = daily["contract_length"] - daily["contract_day_number"]
    daily["rollover_bucket"] = np.select(
        [
            daily["contract_day_number"] <= 3,
            daily["contract_days_to_end"] <= 2,
        ],
        [
            "first_3_contract_days",
            "last_3_contract_days",
        ],
        default="mid_contract_days",
    )
    return daily


def bucket_metrics_from_reference(
    reference_trades: pd.DataFrame,
    daily_buckets: pd.DataFrame,
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for bucket_name in ("first_3_contract_days", "mid_contract_days", "last_3_contract_days"):
        bucket_dates = pd.Index(daily_buckets.index[daily_buckets["rollover_bucket"] == bucket_name])
        bucket_trades = filter_trades_to_dates(reference_trades, bucket_dates)
        results[bucket_name] = {
            "trade_dates_count": int(len(bucket_dates)),
            "metrics": calculate_metrics(bucket_trades, bucket_dates),
        }
    return results


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    production_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=production_management,
    )

    trend_dates, _, _ = split_trade_dates_by_adx(dataset, threshold=25.0)
    trend_day_set = {pd.Timestamp(value).date().isoformat() for value in trend_dates}
    trend_entry_filter = combine_entry_filters(base_filter, regime_day_filter(trend_day_set))

    trend_cooldown_only_trades, trend_cooldown_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=trend_entry_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    trend_cooldown_maxhold_trades, trend_cooldown_maxhold_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=trend_entry_filter,
        management=production_management,
    )

    ablations = {
        "remove_session_filter": run_backtest_with_management(
            dataset=dataset,
            params=base_params,
            trade_dates=dataset.trade_dates,
            entry_filter=None,
            management=production_management,
        )[1],
        "remove_cooldown": run_backtest_with_management(
            dataset=dataset,
            params=base_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(max_bars_in_trade=120),
        )[1],
        "remove_max_hold": run_backtest_with_management(
            dataset=dataset,
            params=base_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(min_minutes_between_entries=30),
        )[1],
        "remove_skip_short_wednesday": run_backtest_with_management(
            dataset=dataset,
            params=replace(base_params, SkipShortWednesday=False),
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=production_management,
        )[1],
        "remove_skip_short_hour13": run_backtest_with_management(
            dataset=dataset,
            params=replace(base_params, SkipShortHour13=False),
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=production_management,
        )[1],
    }

    rollover_daily = contract_rollover_buckets(dataset)
    non_rollover_dates = pd.Index(rollover_daily.index[rollover_daily["rollover_bucket"] != "last_3_contract_days"])
    non_rollover_day_set = {pd.Timestamp(value).date().isoformat() for value in non_rollover_dates}
    rollover_filter_trades, rollover_filter_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(non_rollover_day_set)),
        management=production_management,
    )
    rollover_summary = bucket_metrics_from_reference(reference_trades, rollover_daily)

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown_30m_maxhold_120m1bars",
            "metrics": reference_metrics,
        },
        "trend_day_regime_variants_full_sample": {
            "trend_day_definition": "prior-day daily ADX(14) > 25",
            "session_plus_cooldown_30m_no_maxhold": {
                "metrics": trend_cooldown_only_metrics,
                "impact_vs_reference": impact_vs_reference(reference_metrics, trend_cooldown_only_metrics),
            },
            "session_plus_cooldown_30m_plus_maxhold_120m1bars": {
                "metrics": trend_cooldown_maxhold_metrics,
                "impact_vs_reference": impact_vs_reference(reference_metrics, trend_cooldown_maxhold_metrics),
            },
        },
        "ablation_study": {
            key: {
                "metrics": value,
                "impact_vs_reference": impact_vs_reference(reference_metrics, value),
            }
            for key, value in ablations.items()
        },
        "rollover_period_analysis": {
            "bucket_definition": "Contract month proxy using the first 3 trading days, last 3 trading days, and the middle of each monthly contract bucket.",
            "contract_summary": {
                "num_contract_months": int(rollover_daily["contract_id"].nunique()),
                "avg_contract_length_days": round(float(rollover_daily["contract_length"].mean()), 2),
            },
            "skip_last_3_contract_days_variant": {
                "metrics": rollover_filter_metrics,
                "impact_vs_reference": impact_vs_reference(reference_metrics, rollover_filter_metrics),
            },
            "bucket_metrics": rollover_summary,
        },
        "notes": [
            "The ablation study removes one component at a time from the current exact production candidate while leaving the rest of the stack unchanged.",
            "The skip-short-13h ablation is expected to be close to a no-op in the exact harness because the explicit session-hour gate already excludes the full 13:00 hour.",
            "The ADX regime variants are run over the full sample and simply stand aside on non-trend days, so they are directly comparable to the main exact candidate.",
            "The rollover analysis uses the dataset's monthly contract proxy and evaluates the reference trade tape by first, middle, and last contract-day buckets.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_trendday_adx25_cooldown30_fullsample",
            family="session_regime_gate",
            metrics=trend_cooldown_only_metrics,
            notes="Full-sample exact variant that trades only on prior-day daily ADX>25 days, using the session winner with a 30-minute cooldown and no max hold.",
            artifact=summary_path,
            params={
                "use_prior_day_adx_gate": True,
                "min_prior_day_adx": 25.0,
                "min_minutes_between_entries": 30,
                "max_bars_in_trade": None,
            },
        ),
        candidate_row(
            name="session_winner_trendday_adx25_cooldown30_maxhold120_fullsample",
            family="session_regime_gate",
            metrics=trend_cooldown_maxhold_metrics,
            notes="Full-sample exact variant that trades only on prior-day daily ADX>25 days, using the session winner with a 30-minute cooldown and a 120 M1-bar max hold.",
            artifact=summary_path,
            params={
                "use_prior_day_adx_gate": True,
                "min_prior_day_adx": 25.0,
                "min_minutes_between_entries": 30,
                "max_bars_in_trade": 120,
            },
        ),
        candidate_row(
            name="session_winner_cooldown30_maxhold120_skip_last3_contractdays",
            family="session_rollover_filter",
            metrics=rollover_filter_metrics,
            notes="Full-sample exact variant that keeps the production stack but stands down in the last 3 trading days of each monthly contract bucket.",
            artifact=summary_path,
            params={
                "skip_last_contract_days": 3,
                "min_minutes_between_entries": 30,
                "max_bars_in_trade": 120,
            },
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
