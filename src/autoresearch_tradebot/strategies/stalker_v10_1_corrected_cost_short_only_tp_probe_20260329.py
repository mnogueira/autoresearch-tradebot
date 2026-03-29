from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block, _variant_payload
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_short_only_tp_probe_20260329")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    base_params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        AllowFriday=False,
    )
    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])
    base_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
    )

    def _short_only(context) -> bool:
        return int(context.get("direction", 0)) == -1

    entry_filter = _combine_filters(base_filter, _short_only)
    management = ManagementConfig(min_minutes_between_entries=60)

    ranked_variants: list[dict] = []
    best_name = ""
    best_score = float("-inf")
    best_trades = pd.DataFrame()

    for tp_multiplier in (0.42, 0.48, 0.54, 0.60):
        params = replace(base_params, TP_ATRMultiplier=tp_multiplier)
        trades, _ = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        payload = _variant_payload(
            name=f"tier2a_corrected_no_roc_no_maxhold_sl1p0_tp{str(tp_multiplier).replace('.', 'p')}_cd60_skipfriday_skiplast1_short_only",
            rule=f"Short-only corrected-cost branch with TP {tp_multiplier:.2f}.",
            trades=trades,
            trade_dates=trade_dates,
            params={
                "params": asdict(params),
                "management": asdict(management),
                "direction": "short_only",
            },
        )
        ranked_variants.append(payload)
        score = float(payload["sortino_weighted_composite"])
        if score > best_score:
            best_score = score
            best_name = payload["name"]
            best_trades = trades

    ranked_variants.sort(
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked_variants, start=1):
        row["batch_rank"] = rank

    summary = {
        "ranked_variants": ranked_variants,
        "best_variant_walkforward_70_30": {
            "variant_name": best_name,
            "train": _subset_block(best_trades, train_dates),
            "test": _subset_block(best_trades, test_dates),
        },
        "best_variant_recent_windows": {
            "variant_name": best_name,
            "recent_60d": _subset_block(best_trades, recent_60),
            "recent_30d": _subset_block(best_trades, recent_30),
            "recent_10d": _subset_block(best_trades, recent_10),
        },
        "notes": [
            "Short-side corrected-cost TP sweep after direction diagnostics showed the short sleeve is the stronger honest branch.",
            "Goal: test whether the short sleeve wants wider reward than the balanced corrected-cost survivor.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
