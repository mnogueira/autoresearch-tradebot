from __future__ import annotations

import json
from dataclasses import asdict, replace

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management, session_filter, session_winner_params
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_core_horizon_followups_20260329")


def _combine_filters(*filters):
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    base_params = session_winner_params()
    management = ManagementConfig(min_minutes_between_entries=25)
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    variants = [
        ("tier2a_baseline", base_params),
        ("tier2a_atr14", replace(base_params, ATR_Length=14)),
        ("tier2a_atr26", replace(base_params, ATR_Length=26)),
        ("tier2a_contractlookback3", replace(base_params, NumDaysToConsiderPreviousContractMARange=3)),
        ("tier2a_contractlookback8", replace(base_params, NumDaysToConsiderPreviousContractMARange=8)),
        (
            "tier2a_atr14_contractlookback3",
            replace(base_params, ATR_Length=14, NumDaysToConsiderPreviousContractMARange=3),
        ),
        (
            "tier2a_atr26_contractlookback8",
            replace(base_params, ATR_Length=26, NumDaysToConsiderPreviousContractMARange=8),
        ),
    ]

    rows = []
    for name, params in variants:
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        rows.append(
            {
                "name": name,
                "metrics": metrics,
                **_risk_block(trades, trade_dates),
                "params": {
                    "management": asdict(management),
                    "roc_agreement_bars": 5,
                    "ATR_Length": int(params.ATR_Length),
                    "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
                    "RetracementLevel": float(params.RetracementLevel),
                    "FilterAsPercOfContractMARange": float(params.FilterAsPercOfContractMARange),
                },
            }
        )

    rows.sort(
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row["batch_rank"] = rank

    summary = {
        "notes": [
            "This batch checks whether the remaining core horizon knobs still contain meaningful improvement on Tier 2A.",
            "If these stay close to baseline, the current signal family is likely near a genuine local ceiling rather than just a partially tuned one.",
        ],
        "variants_ranked": rows,
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
