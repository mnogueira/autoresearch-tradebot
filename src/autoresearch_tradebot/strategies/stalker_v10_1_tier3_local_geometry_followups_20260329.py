from __future__ import annotations

import json
from dataclasses import asdict, replace

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_roc_fine_followups_20260329 import _leaderboard_row
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_tier3_local_geometry_followups_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    trades, metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    summary = {
        "variant_name": "tier3_atr10_contractlookback2_roc5",
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": {
            "management": asdict(management),
            "roc_agreement_bars": 5,
            "ATR_Length": int(params.ATR_Length),
            "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
        },
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_variant = {
        "name": "tier3_roc5_atr10_contractlookback2_maxhold150",
        "rule": "Strengthened Tier 3: 25m cooldown + 150m max-hold + ROC(5) agreement + ATR_Length 10 + contract lookback 2.",
        "metrics": metrics,
        "risk_adjusted_metrics": summary["risk_adjusted_metrics"],
        "sortino_weighted_composite": summary["sortino_weighted_composite"],
        "params": summary["params"],
    }
    row = _leaderboard_row(leaderboard_variant, summary_path)
    row["family"] = "stalker_v10_1_tier3_local_geometry_followup"
    row["screening_method"] = "tier3_local_geometry_followup"
    row["comparison_tier"] = "research_exact"
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
