from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .export_tester_trade_log import deals_to_trade_log, daily_pnl_from_trades, parse_deals


def _profit_factor_from_pnl(values: pd.Series) -> float:
    wins = float(values[values > 0.0].sum())
    losses = float(values[values < 0.0].abs().sum())
    if losses > 0.0:
        return wins / losses
    if wins > 0.0:
        return float("inf")
    return 0.0


def build_snapshot(
    trades: pd.DataFrame,
    initial_balance_brl: float,
    session_date: str | None = None,
) -> dict[str, object]:
    trades = trades.copy()
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    trades["exit_time"] = pd.to_datetime(trades["exit_time"])
    trades["session_date"] = pd.to_datetime(trades["session_date"])
    daily = daily_pnl_from_trades(trades, initial_balance_brl=initial_balance_brl)
    daily["session_date"] = pd.to_datetime(daily["session_date"])
    asof_session = (
        pd.Timestamp(session_date).normalize()
        if session_date is not None
        else pd.Timestamp(daily["session_date"].max()).normalize()
    )
    today_trades = trades.loc[trades["session_date"].dt.normalize().eq(asof_session)].copy()

    equity = daily["equity_brl"].astype(float)
    peaks = equity.cummax()
    drawdown_brl = peaks - equity
    drawdown_pct = (drawdown_brl / peaks.where(peaks != 0.0, 1.0)) * 100.0

    recent_5 = daily.tail(5)
    recent_20 = daily.tail(20)
    recent_30 = daily.tail(30)
    total_trades = int(len(trades))
    trading_days = int(daily["session_date"].nunique())

    dd_distribution = drawdown_pct.fillna(0.0)
    dd_summary = {
        "p50_pct": round(float(dd_distribution.quantile(0.50)), 2) if not dd_distribution.empty else 0.0,
        "p90_pct": round(float(dd_distribution.quantile(0.90)), 2) if not dd_distribution.empty else 0.0,
        "p95_pct": round(float(dd_distribution.quantile(0.95)), 2) if not dd_distribution.empty else 0.0,
        "max_pct": round(float(dd_distribution.max()), 2) if not dd_distribution.empty else 0.0,
    }

    return {
        "asof_session_date": asof_session.date().isoformat(),
        "last_trade_time": str(trades["exit_time"].max()),
        "total_trades": total_trades,
        "trading_days": trading_days,
        "expected_trades_per_day": round(total_trades / trading_days, 4) if trading_days else 0.0,
        "latest_daily_pnl_brl": round(float(daily["pnl_brl"].iloc[-1]), 2) if not daily.empty else 0.0,
        "today": {
            "pnl_brl": round(float(today_trades["pnl_brl"].sum()), 2) if not today_trades.empty else 0.0,
            "trades": int(len(today_trades)),
            "win_rate": round(float((today_trades["pnl_brl"].astype(float) > 0.0).mean()), 4) if not today_trades.empty else 0.0,
        },
        "rolling_pnl_brl": {
            "5d": round(float(recent_5["pnl_brl"].sum()), 2),
            "20d": round(float(recent_20["pnl_brl"].sum()), 2),
            "30d": round(float(recent_30["pnl_brl"].sum()), 2),
        },
        "rolling_profit_factor": {
            "5d": round(float(_profit_factor_from_pnl(recent_5["pnl_brl"])), 4),
            "20d": round(float(_profit_factor_from_pnl(recent_20["pnl_brl"])), 4),
            "30d": round(float(_profit_factor_from_pnl(recent_30["pnl_brl"])), 4),
            "60d": round(float(_profit_factor_from_pnl(daily.tail(60)["pnl_brl"])), 4),
        },
        "drawdown": {
            "current_brl": round(float(drawdown_brl.iloc[-1]), 2) if not drawdown_brl.empty else 0.0,
            "current_pct": round(float(drawdown_pct.iloc[-1]), 2) if not drawdown_pct.empty else 0.0,
            "max_brl": round(float(drawdown_brl.max()), 2) if not drawdown_brl.empty else 0.0,
            "max_pct": round(float(drawdown_pct.max()), 2) if not drawdown_pct.empty else 0.0,
        },
        "historical_drawdown_distribution_pct": dd_summary,
        "last_10_daily_rows": [
            {
                "session_date": pd.Timestamp(row.session_date).date().isoformat(),
                "trades": int(row.trades),
                "pnl_brl": round(float(row.pnl_brl), 2),
                "equity_brl": round(float(row.equity_brl), 2),
            }
            for row in daily.tail(10).itertuples(index=False)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a lightweight MT5 monitoring snapshot JSON from a tester report or trade log.")
    parser.add_argument("--report", type=Path, help="Path to an MT5 tester HTML report.")
    parser.add_argument("--trade-log", type=Path, help="Path to a previously exported trade_log.csv.")
    parser.add_argument("--out", required=True, type=Path, help="Output path for the monitoring JSON snapshot.")
    parser.add_argument("--initial-balance", type=float, default=10_000.0, help="Initial balance used to reconstruct equity.")
    parser.add_argument("--session-date", type=str, help="Session date to treat as 'today' in YYYY-MM-DD format. Defaults to the latest session in the trade log.")
    args = parser.parse_args()

    if args.trade_log is not None:
        trades = pd.read_csv(args.trade_log)
    elif args.report is not None:
        trades = deals_to_trade_log(parse_deals(args.report))
    else:
        raise SystemExit("Provide either --trade-log or --report.")

    snapshot = build_snapshot(
        trades,
        initial_balance_brl=float(args.initial_balance),
        session_date=args.session_date,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
