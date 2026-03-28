from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_confidence_weekday_followups import _allowed_weekdays_filter, _combine_filters
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_max_quality_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_metrics,
        "sortino_weighted_composite": _composite_score(risk_metrics),
    }


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
    comparison_tier: str = "exact",
) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "comparison_tier": comparison_tier,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
    }


def _leaderboard_row(
    variant: dict[str, Any],
    family: str,
    notes: str,
    artifact: Path,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family=family,
        metrics=dict(variant["metrics"]),
        notes=notes,
        artifact=artifact,
        params=params,
    )
    row["comparison_tier"] = str(variant.get("comparison_tier", "exact"))
    row["screening_method"] = "max_quality_followup"
    risk_metrics = dict(variant.get("risk_adjusted_metrics", {}))
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant.get("sortino_weighted_composite")
    return row


def _apply_confidence_overlay(
    trades: pd.DataFrame,
    signal_strength_lookup: pd.Series,
    baseline_strength: float,
    trade_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, float]]:
    if trades.empty:
        empty_metrics = calculate_metrics(pd.DataFrame(), trade_dates)
        return pd.DataFrame(), empty_metrics, {"mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0, "min": 0.0, "max": 0.0}

    frame = trades.copy()
    frame["signal_time"] = pd.to_datetime(frame["signal_time"])
    strengths = (
        signal_strength_lookup.reindex(frame["signal_time"].dt.floor("min"))
        .fillna(baseline_strength)
        .abs()
        .astype(float)
        .to_numpy()
    )
    multipliers = np.clip(strengths / max(float(baseline_strength), 1e-6), 0.5, 1.5)
    frame["signal_strength_abs"] = strengths
    frame["size_multiplier"] = multipliers
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["size_multiplier"]
    frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["size_multiplier"]
    metrics = calculate_metrics(frame, trade_dates)
    stats = {
        "mean": round(float(frame["size_multiplier"].mean()), 4),
        "median": round(float(frame["size_multiplier"].median()), 4),
        "p25": round(float(frame["size_multiplier"].quantile(0.25)), 4),
        "p75": round(float(frame["size_multiplier"].quantile(0.75)), 4),
        "min": round(float(frame["size_multiplier"].min()), 4),
        "max": round(float(frame["size_multiplier"].max()), 4),
    }
    return frame, metrics, stats


def _run_exact_variant(
    dataset: V10Dataset,
    params,
    trade_dates: pd.Index,
    entry_filter: Callable[[dict[str, Any]], bool] | None,
    management: ManagementConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    trade_dates = dataset.trade_dates
    entry_filter = session_filter({10, 11, 12, 14})
    mon_wed_thu_filter = _combine_filters(entry_filter, _allowed_weekdays_filter({0, 2, 3}))
    baseline_strength = float(params.MinDirectionalTrendEfficiency15m)
    strength_cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(params.RelativeVolumeLookbackDays),
    )
    signal_strength_lookup = pd.Series(
        strength_cache["trend_efficiency_raw"],
        index=dataset.bars_m1.index.floor("min"),
    )

    reference_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)
    time_widened_management = ManagementConfig(
        min_minutes_between_entries=30,
        max_bars_in_trade=120,
        widen_stop_after_bars=30,
        widened_sl_atr_mult=1.20,
    )

    exact_specs = [
        (
            "session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
            "Reference production candidate.",
            entry_filter,
            reference_management,
        ),
        (
            "session_winner_cooldown_30m_maxhold120_timewidened",
            "Production candidate plus time-widened stop: 0.84 ATR widening to 1.20 ATR after 30 M1 bars.",
            entry_filter,
            time_widened_management,
        ),
        (
            "session_winner_cooldown_30m_maxhold120_mon_wed_thu_only",
            "Production candidate on Monday, Wednesday, and Thursday only.",
            mon_wed_thu_filter,
            reference_management,
        ),
        (
            "session_winner_cooldown_30m_maxhold120_mon_wed_thu_timewidened",
            "Production candidate on Monday, Wednesday, and Thursday only, plus time-widened stop.",
            mon_wed_thu_filter,
            time_widened_management,
        ),
    ]

    exact_results: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    exact_trade_map: dict[str, pd.DataFrame] = {}
    exact_context_map: dict[str, dict[str, Any]] = {}

    for name, rule, variant_filter, management in exact_specs:
        trades, metrics = _run_exact_variant(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=variant_filter,
            management=management,
        )
        exact_trade_map[name] = trades
        exact_context_map[name] = {"entry_filter": variant_filter, "management": management}
        variant = _variant_payload(
            name=name,
            rule=rule,
            trades=trades,
            metrics=metrics,
            trade_dates=trade_dates,
            comparison_tier="exact",
        )
        exact_results.append(variant)
        leaderboard_rows.append(
            _leaderboard_row(
                variant=variant,
                family="stalker_v10_1_session_execution",
                notes=rule,
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={
                    "entry_hours": [10, 11, 12, 14],
                    "management": asdict(management),
                    "allowed_weekdays": [0, 2, 3] if "mon_wed_thu" in name else [0, 1, 2, 3, 4],
                    "SL_ATRMultiplier": float(params.SL_ATRMultiplier),
                    "TP_ATRMultiplier": float(params.TP_ATRMultiplier),
                },
            )
        )

    overlay_results: list[dict[str, Any]] = []
    for exact_variant in exact_results:
        overlay_trades, overlay_metrics, multiplier_stats = _apply_confidence_overlay(
            trades=exact_trade_map[exact_variant["name"]],
            signal_strength_lookup=signal_strength_lookup,
            baseline_strength=baseline_strength,
            trade_dates=trade_dates,
        )
        overlay_variant = _variant_payload(
            name=f"{exact_variant['name']}_confidence_overlay",
            rule=f"{exact_variant['rule']} Research-only confidence-weighted sizing overlay from trend-efficiency strength.",
            trades=overlay_trades,
            metrics=overlay_metrics,
            trade_dates=trade_dates,
            comparison_tier="analysis",
        )
        overlay_variant["multiplier_stats"] = multiplier_stats
        overlay_results.append(overlay_variant)
        leaderboard_rows.append(
            _leaderboard_row(
                variant=overlay_variant,
                family="stalker_v10_1_session_execution",
                notes=f"{exact_variant['rule']} Research-only confidence-weighted sizing overlay.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={
                    "base_variant": exact_variant["name"],
                    "overlay": "confidence_weighted",
                    "multiplier_stats": multiplier_stats,
                },
            )
        )

    all_variants = exact_results + overlay_results
    best_variant = max(all_variants, key=lambda item: float(item["sortino_weighted_composite"]))
    best_base_name = str(best_variant["name"]).replace("_confidence_overlay", "")
    best_context = exact_context_map[best_base_name]
    train_dates, test_dates = split_dates(trade_dates, 0.7)

    train_trades, train_metrics = _run_exact_variant(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=best_context["entry_filter"],
        management=best_context["management"],
    )
    test_trades, test_metrics = _run_exact_variant(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=best_context["entry_filter"],
        management=best_context["management"],
    )

    if str(best_variant["name"]).endswith("_confidence_overlay"):
        train_trades, train_metrics, _ = _apply_confidence_overlay(
            trades=train_trades,
            signal_strength_lookup=signal_strength_lookup,
            baseline_strength=baseline_strength,
            trade_dates=train_dates,
        )
        test_trades, test_metrics, _ = _apply_confidence_overlay(
            trades=test_trades,
            signal_strength_lookup=signal_strength_lookup,
            baseline_strength=baseline_strength,
            trade_dates=test_dates,
        )

    summary = {
        "exact_variants": exact_results,
        "analysis_variants": overlay_results,
        "best_composite_variant_walkforward_70_30": {
            "variant_name": best_variant["name"],
            "variant_rule": best_variant["rule"],
            "comparison_tier": best_variant["comparison_tier"],
            "train_metrics": train_metrics,
            "test_metrics": test_metrics,
            "train_risk_adjusted": _risk_block(train_trades, train_dates),
            "test_risk_adjusted": _risk_block(test_trades, test_dates),
        },
        "notes": [
            "This batch tries to squeeze the composite score higher by combining the strongest research-only lever, confidence-weighted sizing, with the strongest exact quality variants.",
            "Confidence overlays remain analysis-only because they assume fractional sizing from a 1-contract baseline.",
            "The time-widened stop variant uses the previously identified 0.84 ATR stop that relaxes to 1.20 ATR after 30 M1 bars.",
            "The walk-forward block is run on the single best composite-scoring variant from this batch, whether exact or analysis-only.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
