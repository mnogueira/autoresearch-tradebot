from __future__ import annotations

import json
from dataclasses import replace

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_wider_sl_followups_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    base_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    wider_sl_results: list[dict[str, object]] = []
    metrics_by_sl: dict[float, dict[str, object]] = {}
    for sl_multiplier in (1.00, 1.20):
        sl_params = replace(base_params, SL_ATRMultiplier=float(sl_multiplier), TP_ATRMultiplier=0.30)
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=sl_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=base_management,
        )
        metrics_by_sl[float(sl_multiplier)] = metrics
        wider_sl_results.append(
            {
                "sl_atr_multiplier": float(sl_multiplier),
                "tp_atr_multiplier": 0.30,
                "metrics": metrics,
            }
        )

    widened_management = ManagementConfig(
        min_minutes_between_entries=30,
        max_bars_in_trade=120,
        widen_stop_after_bars=30,
        widened_sl_atr_mult=1.20,
    )
    _, time_widened_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=widened_management,
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
        "reference_metrics": reference_metrics,
        "wider_sl_variants": wider_sl_results,
        "time_weighted_stop_variant": {
            "rule": "Start at SL 0.84 ATR and widen the stop to 1.20 ATR after 30 M1 bars if the trade is still open.",
            "metrics": time_widened_metrics,
        },
        "notes": [
            "All variants keep the current exact production structure: session hours 10/11/12/14, 30-minute cooldown, and 120 M1-bar max hold.",
            "The wider-SL pass only changes the ATR-based stop multiplier while keeping TP fixed at 0.30 ATR.",
            "The time-weighted stop variant starts with the current 0.84 ATR stop and only widens after 30 bars if the trade survives that long.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_sl1p00_tp0p30",
            family="session_stop_extension",
            metrics=metrics_by_sl[1.00],
            notes="Exact session+cooldown+120m max-hold leader with a wider 1.00 ATR stop and the same 0.30 ATR target.",
            artifact=summary_path,
            params={"sl_atr_multiplier": 1.00, "tp_atr_multiplier": 0.30, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_sl1p20_tp0p30",
            family="session_stop_extension",
            metrics=metrics_by_sl[1.20],
            notes="Exact session+cooldown+120m max-hold leader with a wider 1.20 ATR stop and the same 0.30 ATR target.",
            artifact=summary_path,
            params={"sl_atr_multiplier": 1.20, "tp_atr_multiplier": 0.30, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_sl0p84_widen_to_1p20_after_30bars",
            family="session_stop_extension",
            metrics=time_widened_metrics,
            notes="Exact session+cooldown+120m max-hold leader with a 0.84 ATR stop that widens to 1.20 ATR after 30 M1 bars.",
            artifact=summary_path,
            params={"sl_atr_multiplier": 0.84, "tp_atr_multiplier": 0.30, "widen_stop_after_bars": 30, "widened_sl_atr_mult": 1.20, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
