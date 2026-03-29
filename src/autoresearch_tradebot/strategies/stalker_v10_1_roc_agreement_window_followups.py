from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _variant_payload
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_roc_agreement_window_followups_20260329")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    tier2_management = ManagementConfig(min_minutes_between_entries=25)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    variants: list[dict[str, object]] = []

    for window_bars in (5, 10, 20):
        roc_filter = lambda context, bf=base_filter, rf=_make_roc_filter(dataset, window_bars): bool(bf(context) and rf(context))
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=roc_filter,
            management=tier2_management,
        )
        variant = _variant_payload(
            name=f"tier2_trend_efficiency_plus_roc{window_bars}_agreement",
            rule=f"Keep trend-efficiency and require directional ROC({window_bars}) agreement on Tier 2.",
            trades=trades,
            metrics=metrics,
            trade_dates=trade_dates,
            params={"management": asdict(tier2_management), "roc_agreement_bars": window_bars},
        )
        variants.append(variant)

    ranked = sorted(
        variants,
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
            "This batch isolates ROC agreement window length on the current Tier 2 structure.",
            "It answers whether ROC(5) was actually best or just the first tested agreement lookback.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
