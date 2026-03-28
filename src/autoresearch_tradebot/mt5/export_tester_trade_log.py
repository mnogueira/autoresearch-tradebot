from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


DEAL_ROW_PATTERN = re.compile(
    r'<tr bgcolor="#(?:FFFFFF|F7F7F7)" align=right>'
    r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
    r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
    r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>"
)


def _money_to_float(raw: str) -> float:
    cleaned = raw.replace(" ", "").replace("\xa0", "").strip()
    if cleaned == "":
        return 0.0
    return float(cleaned)


def parse_deals(report_path: Path) -> pd.DataFrame:
    text = report_path.read_text(encoding="utf-16")
    rows: list[dict[str, object]] = []
    for match in DEAL_ROW_PATTERN.finditer(text):
        time_raw, deal, symbol, type_raw, direction, volume, price, order, commission, swap, profit, balance, comment = match.groups()
        if symbol != "WDO$N":
            continue
        rows.append(
            {
                "time": pd.to_datetime(time_raw, format="%Y.%m.%d %H:%M:%S"),
                "deal": int(deal),
                "symbol": symbol,
                "type": type_raw,
                "direction_flag": direction,
                "volume": float(volume) if volume else 0.0,
                "price": _money_to_float(price),
                "order": int(order) if order else 0,
                "commission": _money_to_float(commission),
                "swap": _money_to_float(swap),
                "profit": _money_to_float(profit),
                "balance": _money_to_float(balance),
                "comment": comment,
            }
        )
    deals = pd.DataFrame(rows)
    if deals.empty:
        raise ValueError(f"No WDO deals found in {report_path}")
    return deals.sort_values(["time", "deal"]).reset_index(drop=True)


def deals_to_trade_log(deals: pd.DataFrame) -> pd.DataFrame:
    trades: list[dict[str, object]] = []
    active_trade: dict[str, object] | None = None
    for row in deals.itertuples(index=False):
        if row.direction_flag == "in":
            active_trade = {
                "entry_time": row.time,
                "entry_deal": int(row.deal),
                "direction": "long" if row.type == "buy" else "short",
                "entry_price": float(row.price),
                "volume": float(row.volume),
                "entry_comment": row.comment,
            }
            continue
        if row.direction_flag != "out" or active_trade is None:
            continue
        trades.append(
            {
                "session_date": pd.Timestamp(row.time).date().isoformat(),
                "entry_time": active_trade["entry_time"],
                "exit_time": row.time,
                "direction": active_trade["direction"],
                "entry_price": active_trade["entry_price"],
                "exit_price": float(row.price),
                "volume": active_trade["volume"],
                "pnl_brl": float(row.profit),
                "balance_after_brl": float(row.balance),
                "entry_comment": active_trade["entry_comment"],
                "exit_comment": row.comment,
            }
        )
        active_trade = None
    trade_log = pd.DataFrame(trades)
    if trade_log.empty:
        raise ValueError("No closed trades were reconstructed from the MT5 deals log.")
    return trade_log


def daily_pnl_from_trades(trades: pd.DataFrame, initial_balance_brl: float = 10_000.0) -> pd.DataFrame:
    daily = (
        trades.assign(session_date=pd.to_datetime(trades["session_date"]))
        .groupby("session_date")
        .agg(
            trades=("pnl_brl", "size"),
            pnl_brl=("pnl_brl", "sum"),
        )
        .reset_index()
    )
    daily["cumulative_pnl_brl"] = daily["pnl_brl"].cumsum()
    daily["equity_brl"] = initial_balance_brl + daily["cumulative_pnl_brl"]
    daily["session_date"] = daily["session_date"].dt.date.astype(str)
    return daily


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MT5 tester trades and daily PnL from an HTML report.")
    parser.add_argument("--report", required=True, type=Path, help="Path to the MT5 tester HTML report.")
    parser.add_argument("--trades-out", required=True, type=Path, help="Output CSV path for the per-trade log.")
    parser.add_argument("--daily-out", required=True, type=Path, help="Output CSV path for the daily PnL log.")
    args = parser.parse_args()

    deals = parse_deals(args.report)
    trades = deals_to_trade_log(deals)
    daily = daily_pnl_from_trades(trades)

    args.trades_out.parent.mkdir(parents=True, exist_ok=True)
    args.daily_out.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(args.trades_out, index=False)
    daily.to_csv(args.daily_out, index=False)

    print(f"Exported {len(trades)} trades to {args.trades_out}")
    print(f"Exported {len(daily)} daily rows to {args.daily_out}")


if __name__ == "__main__":
    main()
