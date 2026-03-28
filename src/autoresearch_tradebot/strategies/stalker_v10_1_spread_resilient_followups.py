from __future__ import annotations

import json
from dataclasses import replace

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import _composite_score, _daily_pnl_from_trades, _risk_adjusted_metrics
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_spread_resilient_followups_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = replace(session_winner_params(), TP_ATRMultiplier=0.48)
    management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120, fixed_spread_ticks=3)
    trades, metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=session_filter({10, 11, 12, 14}),
        management=management,
    )
    risk = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, dataset.trade_dates))
    summary = {
        "variant": "session winner + 30m cooldown + 120 M1 max-hold + TP 0.48 under fixed 3-tick spread",
        "metrics": metrics,
        "risk_adjusted_metrics": {
            "sortino_ratio": float(risk["sortino_ratio"]),
            "calmar_ratio": float(risk["calmar_ratio"]),
            "omega_ratio": float(risk["omega_ratio"]),
            "sortino_weighted_composite": float(_composite_score(risk)),
        },
        "notes": [
            "This is a research-only hostile-spread follow-up.",
            "It slightly improves on the cooldown-only TP 0.48 variant at fixed 3 ticks, but the edge is still too thin for production promotion.",
        ],
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
