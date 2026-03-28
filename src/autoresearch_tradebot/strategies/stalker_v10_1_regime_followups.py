from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_session_macro_followups import compute_adx
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_regime_followups_20260328")


def daily_ohlc_from_bars(dataset: V10Dataset) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    return (
        bars.assign(session_date=pd.to_datetime(bars["session_date"]).dt.normalize())
        .groupby("session_date")
        .agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    )


def split_trade_dates_by_adx(dataset: V10Dataset, threshold: float = 25.0) -> tuple[pd.Index, pd.Index, pd.Series]:
    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_adx = compute_adx(daily_ohlc, period=14).shift(1)
    normalized_trade_dates = pd.to_datetime(dataset.trade_dates).normalize()
    regime_values = daily_adx.reindex(normalized_trade_dates).fillna(0.0)
    trend_mask = regime_values > float(threshold)
    trend_dates = dataset.trade_dates[trend_mask.to_numpy()]
    range_dates = dataset.trade_dates[(~trend_mask).to_numpy()]
    return trend_dates, range_dates, daily_adx


def combine_entry_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]

    def _allow(context):
        return all(bool(candidate(context)) for candidate in active)

    return _allow


def regime_day_filter(day_set: set[str]):
    def _allow(context):
        session_date = pd.Timestamp(context["session_date"]).date().isoformat()
        return session_date in day_set

    return _allow


def combine_runs(trades_list: list[pd.DataFrame], trade_dates: pd.Index) -> tuple[pd.DataFrame, dict[str, float]]:
    frames = [frame.copy() for frame in trades_list if not frame.empty]
    if frames:
        combined = pd.concat(frames, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    else:
        combined = pd.DataFrame()
    return combined, calculate_metrics(combined, trade_dates)


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    trend_dates, range_dates, _ = split_trade_dates_by_adx(dataset, threshold=25.0)
    trend_day_set = {pd.Timestamp(value).date().isoformat() for value in trend_dates}
    range_day_set = {pd.Timestamp(value).date().isoformat() for value in range_dates}

    trend_session_only_trades, trend_session_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(trend_day_set)),
        management=ManagementConfig(),
    )
    trend_session_only_metrics = calculate_metrics(trend_session_only_trades, trend_dates)
    trend_production_trades, trend_production_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(trend_day_set)),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    trend_production_metrics = calculate_metrics(trend_production_trades, trend_dates)
    range_session_only_trades, range_session_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(range_day_set)),
        management=ManagementConfig(),
    )
    range_session_only_metrics = calculate_metrics(range_session_only_trades, range_dates)
    range_production_trades, range_production_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(range_day_set)),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    range_production_metrics = calculate_metrics(range_production_trades, range_dates)

    adaptive_cooldown_trend_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(trend_day_set)),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    adaptive_cooldown_range_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(range_day_set)),
        management=ManagementConfig(min_minutes_between_entries=15, max_bars_in_trade=120),
    )
    _, adaptive_cooldown_metrics = combine_runs(
        [adaptive_cooldown_trend_trades, adaptive_cooldown_range_trades],
        dataset.trade_dates,
    )

    regime_switch_trend_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(trend_day_set)),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    regime_switch_range_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_entry_filters(base_filter, regime_day_filter(range_day_set)),
        management=ManagementConfig(),
    )
    _, regime_switch_metrics = combine_runs(
        [regime_switch_trend_trades, regime_switch_range_trades],
        dataset.trade_dates,
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "regime_split_counts": {
            "trend_days_adx_gt_25": int(len(trend_dates)),
            "range_days_adx_lte_25_or_nan": int(len(range_dates)),
        },
        "trend_days_comparison": {
            "session_only": trend_session_only_metrics,
            "session_plus_cooldown_30m_plus_maxhold_120m1bars": trend_production_metrics,
        },
        "range_days_comparison": {
            "session_only": range_session_only_metrics,
            "session_plus_cooldown_30m_plus_maxhold_120m1bars": range_production_metrics,
        },
        "adaptive_cooldown_full_sample": {
            "rule": "Use 30-minute cooldown on ADX>25 days and 15-minute cooldown on ADX<=25 days, always keeping the 120-bar max hold.",
            "metrics": adaptive_cooldown_metrics,
        },
        "regime_switch_full_sample": {
            "rule": "Use session-only on ADX<=25 days, and session + 30-minute cooldown + 120-bar max hold on ADX>25 days.",
            "metrics": regime_switch_metrics,
        },
        "notes": [
            "ADX is computed on daily WDO and shifted by one day, so the regime decision only uses information known before the session opens.",
            "The range bucket includes the early warm-up days where daily ADX is not yet available; these are treated conservatively as non-trending days.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_adaptive_cooldown_adx25_full",
            family="session_regime_adaptive_cooldown",
            metrics=adaptive_cooldown_metrics,
            notes="Exact session winner with prior-day daily ADX regime adaptation: 30m cooldown on ADX>25 days, 15m cooldown on ADX<=25 days, always keeping the 120 M1-bar max hold.",
            artifact=summary_path,
            params={
                "trend_day_adx_threshold": 25.0,
                "cooldown_minutes_trend_days": 30,
                "cooldown_minutes_range_days": 15,
                "max_bars_in_trade": 120,
            },
        ),
        candidate_row(
            name="session_winner_regime_switch_adx25_full",
            family="session_regime_switch",
            metrics=regime_switch_metrics,
            notes="Exact session winner using session-only on prior-day ADX<=25 days and session+30m cooldown+120 M1-bar max hold on prior-day ADX>25 days.",
            artifact=summary_path,
            params={
                "trend_day_adx_threshold": 25.0,
                "trend_day_management": "cooldown_30m_plus_maxhold_120",
                "range_day_management": "session_only",
            },
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
