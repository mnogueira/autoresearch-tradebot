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

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_close_weekly_followups_20260328")


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

    close_30m_params = replace(
        base_params,
        MinutesBeforeMarketCloseToClosePositions=30,
    )
    _, close_30m_metrics = run_backtest_with_management(
        dataset=dataset,
        params=close_30m_params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    weekly_caps: list[dict[str, object]] = []
    weekly_metrics_by_cap: dict[float, dict[str, object]] = {}
    for weekly_cap in (300.0, 500.0):
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=base_params,
            trade_dates=dataset.trade_dates,
            entry_filter=base_filter,
            management=ManagementConfig(
                min_minutes_between_entries=30,
                max_bars_in_trade=120,
                max_weekly_profit_brl=float(weekly_cap),
            ),
        )
        weekly_metrics_by_cap[float(weekly_cap)] = metrics
        weekly_caps.append(
            {
                "max_weekly_profit_brl": float(weekly_cap),
                "metrics": metrics,
            }
        )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
        "reference_metrics": reference_metrics,
        "market_close_avoidance": {
            "rule": "Close any open position 30 minutes before the session cutoff instead of letting it run later in the day.",
            "metrics": close_30m_metrics,
        },
        "weekly_profit_caps": {
            "assumption_note": "The request text rendered as `R00`; this pass tests R$300 and R$500 per-contract weekly profit caps as practical guardrails.",
            "variants": weekly_caps,
        },
        "notes": [
            "All variants keep the same production structure: session hours 10/11/12/14, 30-minute cooldown, 120 M1-bar max hold, and SL 0.84 / TP 0.30.",
            "The market-close variant only changes `MinutesBeforeMarketCloseToClosePositions` to 30.",
            "The weekly-cap variants stop opening new trades for the rest of the ISO week once realized weekly PnL reaches the configured cap.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_close_30m_before_market_close",
            family="session_time_exit",
            metrics=close_30m_metrics,
            notes="Exact production candidate with a 30-minute market-close exit buffer.",
            artifact=summary_path,
            params={"minutes_before_market_close_to_close_positions": 30, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_weekly_cap_300",
            family="session_profit_cap",
            metrics=weekly_metrics_by_cap[300.0],
            notes="Exact production candidate with a R$300 weekly profit cap per contract.",
            artifact=summary_path,
            params={"max_weekly_profit_brl": 300.0, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_weekly_cap_500",
            family="session_profit_cap",
            metrics=weekly_metrics_by_cap[500.0],
            notes="Exact production candidate with a R$500 weekly profit cap per contract.",
            artifact=summary_path,
            params={"max_weekly_profit_brl": 500.0, "min_minutes_between_entries": 30, "max_bars_in_trade": 120},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
