from __future__ import annotations

from autoresearch_tradebot.mt5.assess_paper_session import assess_snapshot


def _snapshot(rolling_pf_30d: float, current_dd_pct: float, p90: float = 4.0, p95: float = 5.0) -> dict:
    return {
        "rolling_profit_factor": {"30d": rolling_pf_30d},
        "drawdown": {"current_pct": current_dd_pct},
        "historical_drawdown_distribution_pct": {"p90_pct": p90, "p95_pct": p95},
    }


def test_assess_snapshot_green_and_promotion_ready() -> None:
    result = assess_snapshot(
        _snapshot(rolling_pf_30d=1.35, current_dd_pct=2.0),
        max_spread_ticks=1.0,
        mt5_errors=False,
        consecutive_losing_days=0,
        completed_sessions=5,
        current_tier="Tier 1",
    )
    assert result["status"] == "green"
    assert result["promotion_eligible"] is True
    assert result["pause_recommended"] is False


def test_assess_snapshot_yellow_on_degraded_spread() -> None:
    result = assess_snapshot(
        _snapshot(rolling_pf_30d=1.1, current_dd_pct=4.5),
        max_spread_ticks=2.0,
        mt5_errors=False,
        consecutive_losing_days=1,
        completed_sessions=3,
        current_tier="Tier 1",
    )
    assert result["status"] == "yellow"
    assert result["promotion_eligible"] is False
    assert result["pause_recommended"] is False


def test_assess_snapshot_red_on_cost_and_drawdown_break() -> None:
    result = assess_snapshot(
        _snapshot(rolling_pf_30d=0.95, current_dd_pct=5.5),
        max_spread_ticks=3.0,
        mt5_errors=True,
        consecutive_losing_days=5,
        completed_sessions=6,
        current_tier="Tier 2",
    )
    assert result["status"] == "red"
    assert result["promotion_eligible"] is False
    assert result["pause_recommended"] is True
