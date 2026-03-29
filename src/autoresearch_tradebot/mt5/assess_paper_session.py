from __future__ import annotations

import argparse
import json
from pathlib import Path


def assess_snapshot(
    snapshot: dict,
    *,
    max_spread_ticks: float | None = None,
    mt5_errors: bool = False,
    consecutive_losing_days: int | None = None,
    completed_sessions: int | None = None,
    current_tier: str | None = None,
) -> dict:
    rolling_pf_30d = float(snapshot["rolling_profit_factor"]["30d"])
    current_dd_pct = float(snapshot["drawdown"]["current_pct"])
    p90_dd_pct = float(snapshot["historical_drawdown_distribution_pct"]["p90_pct"])
    p95_dd_pct = float(snapshot["historical_drawdown_distribution_pct"]["p95_pct"])

    spread_red = max_spread_ticks is not None and max_spread_ticks > 2.0
    spread_yellow = max_spread_ticks is not None and max_spread_ticks == 2.0
    dd_red = current_dd_pct > p95_dd_pct
    dd_yellow = p90_dd_pct < current_dd_pct <= p95_dd_pct
    pf_red = rolling_pf_30d < 1.0
    pf_yellow = 1.0 <= rolling_pf_30d <= 1.2
    losing_red = consecutive_losing_days is not None and consecutive_losing_days >= 5

    if spread_red or dd_red or pf_red or mt5_errors or losing_red:
        status = "red"
    elif spread_yellow or dd_yellow or pf_yellow:
        status = "yellow"
    else:
        status = "green"

    notes: list[str] = []
    if spread_red:
        notes.append("Spread is above the documented 2-tick hard limit.")
    elif spread_yellow:
        notes.append("Spread is at the degraded 2-tick limit.")
    if pf_red:
        notes.append("Rolling 30-day PF is below 1.0.")
    elif pf_yellow:
        notes.append("Rolling 30-day PF is between 1.0 and 1.2.")
    if dd_red:
        notes.append("Current drawdown is above the historical p95 drawdown.")
    elif dd_yellow:
        notes.append("Current drawdown is between the historical p90 and p95 bands.")
    if mt5_errors:
        notes.append("MT5 execution errors were reported.")
    if losing_red:
        notes.append("Consecutive losing-day stop rule is triggered.")

    promotion_eligible = (
        status == "green"
        and completed_sessions is not None
        and completed_sessions >= 5
        and (current_tier or "").lower() in {"tier 1", "tier1", "tier 2", "tier2", "tier 2a", "tier2a"}
    )
    pause_recommended = status == "red"

    return {
        "status": status,
        "promotion_eligible": promotion_eligible,
        "pause_recommended": pause_recommended,
        "rolling_profit_factor_30d": rolling_pf_30d,
        "current_drawdown_pct": current_dd_pct,
        "historical_drawdown_p90_pct": p90_dd_pct,
        "historical_drawdown_p95_pct": p95_dd_pct,
        "max_spread_ticks": max_spread_ticks,
        "mt5_errors": mt5_errors,
        "consecutive_losing_days": consecutive_losing_days,
        "completed_sessions": completed_sessions,
        "current_tier": current_tier,
        "notes": notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Assess MT5 paper-session health from a monitoring snapshot.")
    parser.add_argument("--snapshot", required=True, type=Path, help="Path to monitoring_snapshot.json.")
    parser.add_argument("--out", type=Path, help="Optional output path for the assessment JSON.")
    parser.add_argument("--max-spread-ticks", type=float, help="Maximum observed spread for the session.")
    parser.add_argument("--mt5-errors", action="store_true", help="Set if MT5 execution errors were observed.")
    parser.add_argument("--consecutive-losing-days", type=int, help="Current consecutive losing-day count.")
    parser.add_argument("--completed-sessions", type=int, help="Completed paper sessions on the current tier.")
    parser.add_argument("--current-tier", type=str, help="Current tier label, e.g. 'Tier 1'.")
    args = parser.parse_args()

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    assessment = assess_snapshot(
        snapshot,
        max_spread_ticks=args.max_spread_ticks,
        mt5_errors=bool(args.mt5_errors),
        consecutive_losing_days=args.consecutive_losing_days,
        completed_sessions=args.completed_sessions,
        current_tier=args.current_tier,
    )

    payload = json.dumps(assessment, indent=2)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
