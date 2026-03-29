from __future__ import annotations

import json
from dataclasses import asdict, replace

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management, session_filter, session_winner_params
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_core_horizon_local_followups_20260329")


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

    variants = [("tier2a_horizon_reference", replace(base_params, ATR_Length=14, NumDaysToConsiderPreviousContractMARange=3))]
    for atr_length in (10, 12, 14, 16):
        for contract_lookback in (2, 3, 4):
            name = f"tier2a_atr{atr_length}_contractlookback{contract_lookback}"
            params = replace(base_params, ATR_Length=atr_length, NumDaysToConsiderPreviousContractMARange=contract_lookback)
            if name == "tier2a_atr14_contractlookback3":
                continue
            variants.append((name, params))

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
            "This batch refines locally around the new ATR14/lookback3 Tier 2A optimum.",
            "If the best local result lands on an edge again, the family may still contain some shorter-horizon room, but it should be treated skeptically until validated.",
        ],
        "variants_ranked": rows,
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
