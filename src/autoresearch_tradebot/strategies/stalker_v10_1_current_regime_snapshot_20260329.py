from __future__ import annotations

import json
from pathlib import Path

from ..common.paths import artifact_output_dir

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_current_regime_snapshot_20260329")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tier2a = _load(root / "artifacts/outputs/stalker_v10_1_roc_agreement_tier2_validation_20260329/summary.json")
    tier2b = _load(root / "artifacts/outputs/stalker_v10_1_regime_roc_fine_followups_20260329/summary.json")
    tier3 = _load(root / "artifacts/outputs/stalker_v10_1_maxhold150_walkforward_20260328/summary.json")
    advanced = _load(root / "artifacts/outputs/stalker_v10_1_regime_tier3_roc_followups_20260329/summary.json")

    tier2b_variant = next(v for v in tier2b["variants"] if v["name"] == "tier2_range_tier2a_trend_switch")

    summary = {
        "tier2": {
            "name": "cooldown_25m_only",
            "full_sample": {
                "net_profit_brl": 14350.0,
                "profit_factor": 1.4749,
                "max_drawdown_pct": 3.30,
                "sortino_weighted_composite": 3.1158,
            },
            "recent_60d": {
                "net_profit_brl": 30.0,
                "profit_factor": 1.0157,
                "max_drawdown_pct": 5.62,
                "sortino_weighted_composite": 0.3133,
            },
            "walkforward_test": {
                "net_profit_brl": 3175.0,
                "profit_factor": 1.3662,
                "max_drawdown_pct": 4.29,
                "sortino_weighted_composite": 2.5061,
            },
        },
        "tier2a": {
            "name": tier2a["variant_name"],
            "full_sample": {
                **tier2a["full_sample"]["metrics"],
                "sortino_weighted_composite": tier2a["full_sample"]["sortino_weighted_composite"],
            },
            "recent_60d": {
                **tier2a["recent_60d"]["metrics"],
                "sortino_weighted_composite": tier2a["recent_60d"]["sortino_weighted_composite"],
            },
            "walkforward_test": {
                **tier2a["walkforward_70_30"]["test_metrics"],
                "sortino_weighted_composite": tier2a["walkforward_70_30"]["test_risk"]["sortino_weighted_composite"],
            },
        },
        "tier2b": {
            "name": "tier2_range_tier2a_trend_switch",
            "full_sample": {
                **tier2b_variant["metrics"],
                "sortino_weighted_composite": tier2b_variant["sortino_weighted_composite"],
            },
            "recent_60d": {
                **tier2b["best_variant_recent_60d"]["metrics"],
                "sortino_weighted_composite": tier2b["best_variant_recent_60d"]["sortino_weighted_composite"],
            },
            "walkforward_test": {
                **tier2b["best_variant_walkforward_70_30"]["test_metrics"],
                "sortino_weighted_composite": tier2b["best_variant_walkforward_70_30"]["test_risk"]["sortino_weighted_composite"],
            },
        },
        "tier3": {
            "name": tier3["variant"],
            "full_sample": {
                "net_profit_brl": 14420.0,
                "profit_factor": 1.4784,
                "max_drawdown_pct": 3.28,
                "sortino_weighted_composite": 3.1340,
            },
            "recent_60d": {
                "net_profit_brl": 30.0,
                "profit_factor": 1.0157,
                "max_drawdown_pct": 5.62,
                "sortino_weighted_composite": 0.3133,
            },
            "walkforward_test": {
                **tier3["test"]["metrics"],
                "sortino_weighted_composite": tier3["test"]["sortino_weighted_composite"],
            },
        },
        "advanced_regime": {
            "name": advanced["variant"]["name"],
            "full_sample": {
                **advanced["variant"]["metrics"],
                "sortino_weighted_composite": advanced["variant"]["sortino_weighted_composite"],
            },
            "recent_60d": {
                **advanced["recent_60d"]["metrics"],
                "sortino_weighted_composite": advanced["recent_60d"]["sortino_weighted_composite"],
            },
            "walkforward_test": {
                **advanced["walkforward_70_30"]["test_metrics"],
                "sortino_weighted_composite": advanced["walkforward_70_30"]["test_risk"]["sortino_weighted_composite"],
            },
        },
        "notes": [
            "This compact snapshot keeps the latest full-sample, recent-60d, and walk-forward test readouts for the exact upgrade tiers in one place.",
            "It exists to support Monday operations, not to create a new promotion path.",
        ],
    }

    output_path = DEFAULT_OUTPUT_DIR / "summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
