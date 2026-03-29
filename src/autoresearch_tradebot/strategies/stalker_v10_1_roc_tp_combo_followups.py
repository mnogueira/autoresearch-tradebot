from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
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
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_roc_tp_combo_followups_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
    comparison_tier: str = "exact",
    params: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "rule": rule,
        "comparison_tier": comparison_tier,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
    }
    if params is not None:
        payload["params"] = params
    if extra is not None:
        payload.update(extra)
    return payload


def _leaderboard_row(variant: dict[str, Any], family: str, artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family=family,
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant.get("params"),
    )
    row["comparison_tier"] = str(variant.get("comparison_tier", "exact"))
    row["screening_method"] = "roc_tp_combo_followup"
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
        empty_stats = {"mean": 0.0, "median": 0.0, "p25": 0.0, "p75": 0.0, "min": 0.0, "max": 0.0}
        return pd.DataFrame(), empty_metrics, empty_stats

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


def _make_roc_filter(dataset: V10Dataset, window_bars: int) -> Callable[[dict[str, Any]], bool]:
    bars = dataset.bars_m1
    session_key = bars["session_date"]
    close_values = bars["Close"]
    roc_values = close_values.groupby(session_key).transform(lambda series: series.pct_change(int(window_bars)))
    roc_array = roc_values.to_numpy(dtype=float)

    def _allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        roc_value = float(roc_array[idx])
        if not np.isfinite(roc_value):
            return False
        direction = int(context["direction"])
        return roc_value > 0.0 if direction == 1 else roc_value < 0.0

    return _allow


def _daily_atr_tp_scale(
    dataset: V10Dataset,
    atr_length: int,
    lookback_sessions: int,
    min_scale: float,
    max_scale: float,
) -> tuple[np.ndarray, dict[str, float]]:
    bars = dataset.bars_m1
    session_dates = pd.to_datetime(bars["session_date"]).dt.normalize()
    atr_series = pd.Series(dataset.get_atr_current(int(atr_length)), index=bars.index, dtype=float)
    daily_atr = atr_series.groupby(session_dates).first().astype(float)
    daily_reference = daily_atr.shift(1).rolling(int(lookback_sessions), min_periods=5).mean()
    daily_scale = (daily_atr / daily_reference).replace([np.inf, -np.inf], np.nan).clip(float(min_scale), float(max_scale))
    daily_scale = daily_scale.fillna(1.0)
    scale_lookup = daily_scale.to_dict()
    scale_array = session_dates.map(scale_lookup).astype(float).to_numpy()
    scale_stats = {
        "mean": round(float(daily_scale.mean()), 4),
        "median": round(float(daily_scale.median()), 4),
        "p25": round(float(daily_scale.quantile(0.25)), 4),
        "p75": round(float(daily_scale.quantile(0.75)), 4),
        "min": round(float(daily_scale.min()), 4),
        "max": round(float(daily_scale.max()), 4),
    }
    return scale_array, scale_stats


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    tier2_management = ManagementConfig(min_minutes_between_entries=25)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)
    time_widened_management = ManagementConfig(
        min_minutes_between_entries=25,
        max_bars_in_trade=150,
        widen_stop_after_bars=30,
        widened_sl_atr_mult=1.20,
    )

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
    tp_scale_array, tp_scale_stats = _daily_atr_tp_scale(
        dataset=dataset,
        atr_length=int(params.ATR_Length),
        lookback_sessions=20,
        min_scale=0.75,
        max_scale=1.50,
    )

    results: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    reference_specs = [
        (
            "tier2_cooldown_25m_reference",
            "Current Tier 2 exact production candidate: session winner + 25 minute cooldown.",
            params,
            base_filter,
            tier2_management,
            None,
            "exact",
        ),
        (
            "tier3_cooldown_25m_maxhold150_reference",
            "Current Tier 3 exact production candidate: session winner + 25 minute cooldown + 150 M1 bar max hold.",
            params,
            base_filter,
            tier3_management,
            None,
            "exact",
        ),
    ]

    trade_store: dict[str, pd.DataFrame] = {}
    context_store: dict[str, dict[str, Any]] = {}

    for name, rule, variant_params, entry_filter, management, tp_scale, comparison_tier in reference_specs:
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=variant_params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
            tp_scale_override=tp_scale,
        )
        trade_store[name] = trades
        context_store[name] = {
            "params": variant_params,
            "entry_filter": entry_filter,
            "management": management,
            "tp_scale_override": tp_scale,
        }
        variant = _variant_payload(
            name=name,
            rule=rule,
            trades=trades,
            metrics=metrics,
            trade_dates=trade_dates,
            comparison_tier=comparison_tier,
            params={
                "entry_hours": [10, 11, 12, 14],
                "management": asdict(management),
                "SL_ATRMultiplier": float(variant_params.SL_ATRMultiplier),
                "TP_ATRMultiplier": float(variant_params.TP_ATRMultiplier),
            },
        )
        results.append(variant)
        leaderboard_rows.append(_leaderboard_row(variant, "stalker_v10_1_roc_tp_combo", summary_path))

    roc_params = replace(
        params,
        ApplyTrendEfficiencyFilterToLongs=False,
        ApplyTrendEfficiencyFilterToShorts=False,
    )
    for window_bars in (5, 10, 20):
        roc_filter = _combine_filters(base_filter, _make_roc_filter(dataset, window_bars))
        for tier_name, management in (("tier2", tier2_management), ("tier3", tier3_management)):
            name = f"{tier_name}_roc{window_bars}_directional"
            rule = (
                f"Replace trend-efficiency with directional ROC({window_bars}) sign while keeping "
                f"the current session, timing, and management rules for {tier_name}."
            )
            trades, metrics = run_backtest_with_management(
                dataset=dataset,
                params=roc_params,
                trade_dates=trade_dates,
                entry_filter=roc_filter,
                management=management,
            )
            variant = _variant_payload(
                name=name,
                rule=rule,
                trades=trades,
                metrics=metrics,
                trade_dates=trade_dates,
                comparison_tier="exact",
                params={
                    "signal_family": f"ROC({window_bars}) directional",
                    "entry_hours": [10, 11, 12, 14],
                    "management": asdict(management),
                    "SL_ATRMultiplier": float(roc_params.SL_ATRMultiplier),
                    "TP_ATRMultiplier": float(roc_params.TP_ATRMultiplier),
                },
            )
            results.append(variant)
            leaderboard_rows.append(_leaderboard_row(variant, "stalker_v10_1_roc_tp_combo", summary_path))

    adaptive_tp_trades, adaptive_tp_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=tier3_management,
        tp_scale_override=tp_scale_array,
    )
    adaptive_tp_variant = _variant_payload(
        name="tier3_dynamic_tp_atr_ratio_20d",
        rule=(
            "Tier 3 with TP scaled by current daily ATR divided by the prior 20-session average ATR, "
            "clipped to 0.75x through 1.50x."
        ),
        trades=adaptive_tp_trades,
        metrics=adaptive_tp_metrics,
        trade_dates=trade_dates,
        comparison_tier="exact",
        params={
            "tp_scale_method": "current_daily_atr / prior_20_session_avg_atr",
            "tp_scale_clip": [0.75, 1.50],
            "management": asdict(tier3_management),
        },
        extra={"tp_scale_stats": tp_scale_stats},
    )
    results.append(adaptive_tp_variant)
    leaderboard_rows.append(_leaderboard_row(adaptive_tp_variant, "stalker_v10_1_roc_tp_combo", summary_path))

    time_widened_trades, time_widened_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=time_widened_management,
    )
    time_widened_variant = _variant_payload(
        name="tier3_time_widened_stop",
        rule="Tier 3 plus the time-widened stop that relaxes from 0.84 ATR to 1.20 ATR after 30 M1 bars.",
        trades=time_widened_trades,
        metrics=time_widened_metrics,
        trade_dates=trade_dates,
        comparison_tier="exact",
        params={"management": asdict(time_widened_management)},
    )
    results.append(time_widened_variant)
    leaderboard_rows.append(_leaderboard_row(time_widened_variant, "stalker_v10_1_roc_tp_combo", summary_path))

    confidence_trades, confidence_metrics, confidence_stats = _apply_confidence_overlay(
        trades=trade_store["tier3_cooldown_25m_maxhold150_reference"],
        signal_strength_lookup=signal_strength_lookup,
        baseline_strength=baseline_strength,
        trade_dates=trade_dates,
    )
    confidence_variant = _variant_payload(
        name="tier3_confidence_weighted_overlay",
        rule="Research-only confidence-weighted sizing overlay on Tier 3 using absolute trend-efficiency strength.",
        trades=confidence_trades,
        metrics=confidence_metrics,
        trade_dates=trade_dates,
        comparison_tier="analysis",
        params={"size_multiplier_clip": [0.5, 1.5]},
        extra={"multiplier_stats": confidence_stats},
    )
    results.append(confidence_variant)
    leaderboard_rows.append(_leaderboard_row(confidence_variant, "stalker_v10_1_roc_tp_combo", summary_path))

    confidence_widened_trades, confidence_widened_metrics, confidence_widened_stats = _apply_confidence_overlay(
        trades=time_widened_trades,
        signal_strength_lookup=signal_strength_lookup,
        baseline_strength=baseline_strength,
        trade_dates=trade_dates,
    )
    confidence_widened_variant = _variant_payload(
        name="tier3_time_widened_confidence_overlay",
        rule=(
            "Research-only combination of the two most promising overlays: Tier 3 with time-widened stop "
            "plus confidence-weighted sizing."
        ),
        trades=confidence_widened_trades,
        metrics=confidence_widened_metrics,
        trade_dates=trade_dates,
        comparison_tier="analysis",
        params={"size_multiplier_clip": [0.5, 1.5], "management": asdict(time_widened_management)},
        extra={"multiplier_stats": confidence_widened_stats},
    )
    results.append(confidence_widened_variant)
    leaderboard_rows.append(_leaderboard_row(confidence_widened_variant, "stalker_v10_1_roc_tp_combo", summary_path))

    ranked = sorted(
        results,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["batch_rank"] = rank

    summary = {
        "variants": ranked,
        "notes": [
            "This batch tests a simpler ROC-family signal on the current 25m cooldown frontier, rather than on the older 30m baseline.",
            "Adaptive TP is implemented exactly by scaling the base TP ATR multiplier with current daily ATR relative to the prior 20-session average ATR, clipped to 0.75x through 1.50x.",
            "The combined promising-ideas variant remains research-only because confidence-weighted sizing assumes fractional scaling from a 1-contract baseline.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
