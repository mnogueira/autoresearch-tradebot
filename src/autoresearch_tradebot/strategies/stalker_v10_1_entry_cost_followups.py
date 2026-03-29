from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_entry_cost_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _volume_weight_overlay(
    trades: pd.DataFrame,
    dataset: V10Dataset,
    signal_strength_cache: dict[str, np.ndarray],
) -> tuple[pd.DataFrame, dict[str, object]]:
    if trades.empty:
        return trades.copy(), _risk_block(trades, dataset.trade_dates)

    timestamp_to_index = pd.Series(np.arange(len(dataset.bars_m1), dtype=int), index=dataset.bars_m1.index)
    relative_volume = signal_strength_cache["relative_volume"]
    overlay_trades = trades.copy()
    overlay_trades["signal_time"] = pd.to_datetime(overlay_trades["signal_time"])
    signal_indices = timestamp_to_index.reindex(overlay_trades["signal_time"]).to_numpy(dtype=float)
    size_multiplier = np.ones(len(overlay_trades), dtype=float)
    valid = np.isfinite(signal_indices)
    relvol_values = np.ones(len(overlay_trades), dtype=float)
    relvol_values[valid] = relative_volume[signal_indices[valid].astype(int)]
    size_multiplier[relvol_values < 1.0] = 0.5
    overlay_trades["relative_volume_at_signal"] = relvol_values
    overlay_trades["size_multiplier"] = size_multiplier
    overlay_trades["pnl_brl"] = overlay_trades["pnl_brl"].astype(float) * size_multiplier
    overlay_trades["pnl_points"] = overlay_trades["pnl_points"].astype(float) * size_multiplier
    metrics = calculate_metrics(overlay_trades, dataset.trade_dates)
    return overlay_trades, {"metrics": metrics, **_risk_block(overlay_trades, dataset.trade_dates)}


def _run_exact(
    dataset: V10Dataset,
    management: ManagementConfig,
    label: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    trades, metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=management,
    )
    return trades, {"label": label, "management": management.__dict__, "metrics": metrics, **_risk_block(trades, dataset.trade_dates)}


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    signal_strength_cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=15,
        volume_window=30,
        relative_volume_lookback=10,
    )

    reference_trades, reference_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=30),
        "session_cooldown_reference",
    )
    smart_pullback_1_trades, smart_pullback_1_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=30, micro_pullback_ticks=1, micro_pullback_max_wait_bars=3),
        "micro_pullback_1tick_3bars",
    )
    smart_pullback_2_trades, smart_pullback_2_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=30, micro_pullback_ticks=2, micro_pullback_max_wait_bars=3),
        "micro_pullback_2ticks_3bars",
    )
    doubled_cost_trades, doubled_cost_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=30, round_trip_cost_multiplier=2.0),
        "commission_doubled_proxy",
    )
    zero_cost_trades, zero_cost_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=30, round_trip_cost_multiplier=0.0),
        "no_commission_proxy",
    )
    cooldown_45_trades, cooldown_45_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=45),
        "cooldown_45m",
    )
    cooldown_60_trades, cooldown_60_result = _run_exact(
        dataset,
        ManagementConfig(min_minutes_between_entries=60),
        "cooldown_60m",
    )
    confirm_2bars_trades, confirm_2bars_result = _run_exact(
        dataset,
        ManagementConfig(
            min_minutes_between_entries=30,
            confirmation_candle_required=True,
            confirmation_wait_bars=1,
            confirmation_consecutive_bars=2,
        ),
        "confirmation_2_consecutive_bars",
    )
    volume_weighted_trades, volume_weighted_result = _volume_weight_overlay(
        trades=reference_trades,
        dataset=dataset,
        signal_strength_cache=signal_strength_cache,
    )

    summary = {
        "reference_session_cooldown": reference_result,
        "smart_entry_pullback_1tick_3bars": smart_pullback_1_result,
        "smart_entry_pullback_2ticks_3bars": smart_pullback_2_result,
        "commission_doubled_proxy": doubled_cost_result,
        "no_commission_proxy": zero_cost_result,
        "cooldown_45m_followup": cooldown_45_result,
        "cooldown_60m_followup": cooldown_60_result,
        "two_bar_confirmation_followup": confirm_2bars_result,
        "volume_weighted_entry_overlay": {
            **volume_weighted_result,
            "rule": "Research-only sizing overlay: full size when relative volume at signal >= 1.0, half size otherwise.",
            "mean_size_multiplier": round(float(volume_weighted_trades["size_multiplier"].mean()), 4) if not volume_weighted_trades.empty else 0.0,
            "share_half_size": round(float((volume_weighted_trades["size_multiplier"] < 1.0).mean()), 4) if not volume_weighted_trades.empty else 0.0,
        },
        "notes": [
            "Commission tests use a conservative round-trip-cost multiplier proxy on the existing flat round-trip cost constant.",
            "Smart-entry micro-pullback variants improve the pending-entry price by 1-2 ticks and require fill within the next 3 bars.",
            "The two-bar confirmation waits for two consecutive completed M15 bars to close in the signal direction before entry.",
            "The volume-weighted entry overlay is research-only because it assumes fractional sizing from the exact trade list.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_cooldown_smart_entry_pullback_1tick",
            family="session_entry_timing",
            metrics=smart_pullback_1_result["metrics"],
            notes="Exact session+cooldown with a 1-tick better entry price required within 3 bars after the signal.",
            artifact=summary_path,
            params={"micro_pullback_ticks": 1, "micro_pullback_max_wait_bars": 3, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_smart_entry_pullback_2ticks",
            family="session_entry_timing",
            metrics=smart_pullback_2_result["metrics"],
            notes="Exact session+cooldown with a 2-tick better entry price required within 3 bars after the signal.",
            artifact=summary_path,
            params={"micro_pullback_ticks": 2, "micro_pullback_max_wait_bars": 3, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_cost_x2_proxy",
            family="session_cost_stress",
            metrics=doubled_cost_result["metrics"],
            notes="Exact session+cooldown with the flat round-trip cost doubled as a conservative higher-fee proxy.",
            artifact=summary_path,
            params={"round_trip_cost_multiplier": 2.0, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_cost_x0_proxy",
            family="session_cost_stress",
            metrics=zero_cost_result["metrics"],
            notes="Exact session+cooldown with zero round-trip cost to estimate the theoretical cost-free ceiling.",
            artifact=summary_path,
            params={"round_trip_cost_multiplier": 0.0, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_45m_followup",
            family="session_trade_cooldown",
            metrics=cooldown_45_result["metrics"],
            notes="Exact session winner with a 45-minute cooldown between filled entries.",
            artifact=summary_path,
            params={"min_minutes_between_entries": 45},
        ),
        candidate_row(
            name="session_cooldown_60m_followup",
            family="session_trade_cooldown",
            metrics=cooldown_60_result["metrics"],
            notes="Exact session winner with a 60-minute cooldown between filled entries.",
            artifact=summary_path,
            params={"min_minutes_between_entries": 60},
        ),
        candidate_row(
            name="session_cooldown_confirmation_2bars",
            family="session_confirmation_entry",
            metrics=confirm_2bars_result["metrics"],
            notes="Exact session+cooldown requiring two consecutive completed M15 bars to close in the signal direction before entry.",
            artifact=summary_path,
            params={"confirmation_wait_bars": 1, "confirmation_consecutive_bars": 2, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_cooldown_volume_weighted_overlay",
            family="session_position_sizing",
            metrics=volume_weighted_result["metrics"],
            notes="Research-only overlay: full size when relative volume >= 1.0, half size otherwise.",
            artifact=summary_path,
            params={"relative_volume_threshold": 1.0, "size_high_relvol": 1.0, "size_low_relvol": 0.5},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
