from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_structure_followups_20260328")
GAP_REFERENCE_PATH = Path(
    "artifacts/outputs/stalker_v10_1_session_signal_followups_20260328/summary.json"
)


def combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool]:
    active = [candidate for candidate in filters if candidate is not None]

    def allow(context: dict[str, Any]) -> bool:
        return all(bool(candidate(context)) for candidate in active)

    return allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    cooldown_management = ManagementConfig(min_minutes_between_entries=30)

    strength_cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(params.RelativeVolumeLookbackDays),
    )
    bars = dataset.bars_m1
    session_key = bars["session_date"]
    trend_eff = pd.Series(strength_cache["trend_efficiency_raw"], index=bars.index)
    roc10 = bars["Close"].groupby(session_key).transform(lambda series: series.pct_change(10))

    trend_q75 = trend_eff.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(50, min_periods=20).quantile(0.75)
    )
    trend_q25 = trend_eff.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(50, min_periods=20).quantile(0.25)
    )
    trend_mean = trend_eff.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(50, min_periods=20).mean()
    )
    trend_std = trend_eff.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(50, min_periods=20).std()
    )
    roc_mean = roc10.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(50, min_periods=20).mean()
    )
    roc_std = roc10.groupby(session_key).transform(
        lambda series: series.shift(1).rolling(50, min_periods=20).std()
    )

    trend_array = trend_eff.to_numpy(dtype=float)
    trend_q75_array = trend_q75.to_numpy(dtype=float)
    trend_q25_array = trend_q25.to_numpy(dtype=float)
    trend_z_array = ((trend_eff - trend_mean) / trend_std.replace(0.0, np.nan)).to_numpy(dtype=float)
    roc_z_array = ((roc10 - roc_mean) / roc_std.replace(0.0, np.nan)).to_numpy(dtype=float)

    def rolling_strength_filter(context: dict[str, Any]) -> bool:
        index = int(context["dataset_index"])
        direction = int(context["direction"])
        value = float(trend_array[index])
        if direction == 1:
            threshold = float(trend_q75_array[index])
            return bool(np.isfinite(value) and np.isfinite(threshold) and value >= threshold)
        threshold = float(trend_q25_array[index])
        return bool(np.isfinite(value) and np.isfinite(threshold) and value <= threshold)

    def composite_filter(context: dict[str, Any]) -> bool:
        index = int(context["dataset_index"])
        direction = int(context["direction"])
        trend_component = float(trend_z_array[index])
        roc_component = float(roc_z_array[index])
        if not np.isfinite(trend_component) or not np.isfinite(roc_component):
            return False
        score = (0.7 * trend_component) + (0.3 * roc_component)
        directional_score = score if direction == 1 else -score
        return bool(directional_score > 0.5)

    def tue_to_thu_filter(context: dict[str, Any]) -> bool:
        return int(context["weekday"]) in {1, 2, 3}

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_management,
    )

    def subset_metrics(frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return calculate_metrics(pd.DataFrame(), pd.Index([]))
        dates = pd.Index(sorted(pd.to_datetime(frame["session_date"]).dt.normalize().unique()))
        return calculate_metrics(frame.copy(), dates)

    trade_dates = pd.to_datetime(reference_trades["session_date"]).dt.normalize()
    tue_thu_trade_metrics = subset_metrics(reference_trades.loc[trade_dates.dt.dayofweek.isin([1, 2, 3])])
    mon_fri_trade_metrics = subset_metrics(reference_trades.loc[trade_dates.dt.dayofweek.isin([0, 4])])

    gap_reference: dict[str, Any] | None = None
    if GAP_REFERENCE_PATH.exists():
        gap_payload = json.loads(GAP_REFERENCE_PATH.read_text(encoding="utf-8"))
        gap_reference = gap_payload.get("session_open_gap_practical_10h15_start")

    leaderboard_rows: list[dict[str, Any]] = []

    strength_filter = combine_filters(base_filter, rolling_strength_filter)
    _, strength_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=strength_filter,
        management=cooldown_management,
    )
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_strength_gt_rolling75",
            family="session_signal_strength",
            metrics=strength_metrics,
            notes=(
                "Exact session+cooldown winner with directional trend-efficiency strength gating "
                "against the rolling 50-bar 75th/25th percentile."
            ),
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"trend_strength_history_bars": 50, "percentile": 0.75, "min_minutes_between_entries": 30},
        )
    )

    composite_entry_filter = combine_filters(base_filter, composite_filter)
    _, composite_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=composite_entry_filter,
        management=cooldown_management,
    )
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_composite_te_roc",
            family="session_composite_signal",
            metrics=composite_metrics,
            notes="Exact session+cooldown winner with weighted composite score: 0.7 trend-efficiency z + 0.3 ROC10 z.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"trend_weight": 0.7, "roc_weight": 0.3, "score_threshold": 0.5, "history_bars": 50},
        )
    )

    tue_thu_filter = combine_filters(base_filter, tue_to_thu_filter)
    _, tue_thu_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=tue_thu_filter,
        management=cooldown_management,
    )
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_tue_to_thu_only",
            family="session_weekday_filter",
            metrics=tue_thu_metrics,
            notes="Exact session+cooldown winner restricted to Tuesday through Thursday.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"allowed_weekdays": [1, 2, 3], "min_minutes_between_entries": 30},
        )
    )

    _, max_time_45_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=45),
    )
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_time_exit_45m1bars",
            family="session_time_exit",
            metrics=max_time_45_metrics,
            notes="Exact session+cooldown winner with a hard exit after 45 M1 bars.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"max_bars_in_trade": 45, "engine_bar_size": "M1"},
        )
    )

    _, max_time_660_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=660),
    )
    leaderboard_rows.append(
        candidate_row(
            name="session_winner_cooldown_30m_time_exit_660m1bars",
            family="session_time_exit",
            metrics=max_time_660_metrics,
            notes="Exact session+cooldown winner with a hard exit after 660 M1 bars, roughly equivalent to 11 hours of M15 time.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={"max_bars_in_trade": 660, "engine_bar_size": "M1", "approx_m15_hours": 11},
        )
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m",
        "reference_metrics": reference_metrics,
        "trend_strength_rolling_50bar_percentile": {
            "rule": "Require long signals to exceed the rolling 50-bar 75th percentile of trend efficiency and short signals to be below the rolling 25th percentile.",
            "metrics": strength_metrics,
        },
        "composite_signal_trend_eff_roc10": {
            "rule": "Directional score = 0.7 * z(trend_eff_15 over rolling 50) + 0.3 * z(ROC10 over rolling 50); require score > 0.5 in trade direction.",
            "metrics": composite_metrics,
        },
        "weekday_trade_subset_analysis": {
            "tuesday_through_thursday_trade_subset": tue_thu_trade_metrics,
            "monday_and_friday_trade_subset": mon_fri_trade_metrics,
            "exact_tuesday_through_thursday_only_variant": tue_thu_metrics,
        },
        "max_open_time_filters": {
            "45_m1_bars": {
                "interpretation": "Literal exact-engine test of 45 bars, which equals 45 minutes because the every-tick parity engine advances on M1 bars.",
                "metrics": max_time_45_metrics,
            },
            "660_m1_bars": {
                "interpretation": "Approximate translation of 11 hours of M15 holding time into the exact M1 execution engine.",
                "metrics": max_time_660_metrics,
            },
        },
        "prior_gap_reference": gap_reference,
        "notes": [
            "The user-requested 09:15 start remains a structural no-op because the current session winner does not allow entries before 10:00; the saved prior gap reference is the 10:15 practical analog inside the allowed session.",
            "Tuesday-Thursday vs Monday/Friday is reported both as a trade-subset analysis and as a clean exact backtest variant.",
            "The literal 45-bar max-open-time request is tested exactly as 45 M1 bars, and a separate 660-bar proxy is included to reflect the M15-time intuition.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
