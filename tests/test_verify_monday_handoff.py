from __future__ import annotations

from autoresearch_tradebot.mt5.verify_monday_handoff import build_handoff_report


def test_build_handoff_report_all_exist() -> None:
    report = build_handoff_report()
    assert report["all_exist"] is True
    assert report["checks"]["tier1_preset"]["exists"] is True
    assert report["checks"]["tier2_preset"]["exists"] is True
    assert report["checks"]["tier3_preset"]["exists"] is True
