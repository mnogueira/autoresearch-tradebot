from __future__ import annotations

import json
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_handoff_report() -> dict:
    root = _repo_root()
    checks = {
        "ea_source": root / "mt5/experts/custom/WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5",
        "tier1_preset": root / "mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 GPT 5.4.set",
        "tier2_preset": root / "mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m GPT 5.4.set",
        "tier2a_preset": root / "mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m ROC5 Agreement GPT 5.4.set",
        "tier2b_preset": root / "mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m ROC5 TrendSwitch ADX25 GPT 5.4.set",
        "advanced_regime_preset": root / "mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m ROC5 TrendSwitch ADX25 GPT 5.4.set",
        "tier3_preset": root / "mt5/profiles/tester/WDO Stalker Strategy v10.1 Surgical SLTP sl0p84 tp0p3 Skip Hour13 All Sides Cooldown 25m MaxHold150m GPT 5.4.set",
        "executive_summary": root / "docs/mt5-monday-executive-summary-2026-03-28.md",
        "monday_checklist": root / "docs/mt5-monday-morning-checklist-2026-03-30.md",
        "paper_playbook": root / "docs/mt5-paper-trading-playbook-2026-03-28.md",
        "comparison_doc": root / "docs/stalker-v10-1-production-comparison-2026-03-28.md",
        "frontier_doc": root / "docs/research-frontier-2026-03-28.md",
        "tier1_artifact": root / "artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json",
        "tier2_artifact": root / "artifacts/outputs/stalker_v10_1_vwap_risk_cooldown_followups_20260328/summary.json",
        "tier2a_artifact": root / "artifacts/outputs/stalker_v10_1_roc_agreement_tier2_validation_20260329/summary.json",
        "tier2b_artifact": root / "artifacts/outputs/stalker_v10_1_regime_roc_fine_followups_20260329/summary.json",
        "advanced_regime_artifact": root / "artifacts/outputs/stalker_v10_1_regime_tier3_roc_followups_20260329/summary.json",
        "tier3_artifact": root / "artifacts/outputs/stalker_v10_1_maxhold_sweep_followups_20260328/summary.json",
    }

    results = {
        "repo_root": str(root),
        "checks": {
            name: {
                "path": str(path),
                "exists": path.exists(),
            }
            for name, path in checks.items()
        },
    }
    results["all_exist"] = all(item["exists"] for item in results["checks"].values())
    return results


def main() -> None:
    results = build_handoff_report()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
