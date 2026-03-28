from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common.paths import ARTIFACTS_DIR, artifact_output_dir
from .stalker_v10_1_python import run_backtest
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_risk_adjusted_evaluation_20260328")
INITIAL_EQUITY_BRL = 10_000.0
TRADING_DAYS_PER_YEAR = 252.0


def _money_to_float(raw: str) -> float:
    cleaned = raw.replace(" ", "").replace("\xa0", "").strip()
    if cleaned == "":
        return 0.0
    return float(cleaned)


def _daily_pnl_from_trades(trades_df: pd.DataFrame, trade_dates: pd.Index) -> pd.Series:
    if trades_df.empty:
        return pd.Series(0.0, index=pd.to_datetime(trade_dates), dtype=float)
    return (
        trades_df.assign(session_date=pd.to_datetime(trades_df["session_date"]))
        .groupby("session_date")["pnl_brl"]
        .sum()
        .reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0)
        .astype(float)
    )


def _daily_pnl_from_mt5_report(report_path: Path, trade_dates: pd.Index) -> pd.Series:
    pattern = re.compile(
        r'<tr bgcolor="#(?:FFFFFF|F7F7F7)" align=right>'
        r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
        r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td>"
        r"<td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td><td>([^<]*)</td></tr>"
    )
    rows: list[dict[str, Any]] = []
    text = report_path.read_text(encoding="utf-16")
    for match in pattern.finditer(text):
        time_raw, deal, symbol, type_raw, direction, volume, price, order, commission, swap, profit, balance, comment = match.groups()
        if symbol != "WDO$N":
            continue
        rows.append(
            {
                "time": pd.to_datetime(time_raw, format="%Y.%m.%d %H:%M:%S"),
                "deal": int(deal),
                "symbol": symbol,
                "type": type_raw,
                "direction": direction,
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
    deals_df = pd.DataFrame(rows)
    if deals_df.empty:
        return pd.Series(0.0, index=pd.to_datetime(trade_dates), dtype=float)
    closed_deals = deals_df.loc[deals_df["direction"].eq("out")].copy()
    closed_deals["session_date"] = closed_deals["time"].dt.normalize()
    return (
        closed_deals.groupby("session_date")["profit"]
        .sum()
        .reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0)
        .astype(float)
    )


def _risk_adjusted_metrics(daily_pnl: pd.Series) -> dict[str, float]:
    daily_returns = daily_pnl.astype(float) / INITIAL_EQUITY_BRL
    mean_daily = float(daily_returns.mean())
    negative_returns = daily_returns[daily_returns < 0.0]
    downside_rms = float(np.sqrt(np.mean(np.square(negative_returns)))) if len(negative_returns) else 0.0
    if downside_rms > 0.0:
        sortino = (mean_daily / downside_rms) * math.sqrt(TRADING_DAYS_PER_YEAR)
    elif mean_daily > 0.0:
        sortino = float("inf")
    else:
        sortino = 0.0

    equity = INITIAL_EQUITY_BRL + daily_pnl.cumsum()
    peaks = equity.cummax()
    drawdowns = (peaks - equity) / peaks.replace(0.0, np.nan)
    max_drawdown = float(drawdowns.max()) if len(drawdowns) else 0.0
    if len(daily_returns) > 0 and equity.iloc[-1] > 0.0:
        annual_return = float((equity.iloc[-1] / INITIAL_EQUITY_BRL) ** (TRADING_DAYS_PER_YEAR / len(daily_returns)) - 1.0)
    else:
        annual_return = 0.0
    calmar = (annual_return / max_drawdown) if max_drawdown > 0.0 else float("inf")

    positive_sum = float(daily_returns[daily_returns > 0.0].sum())
    negative_sum = float((-daily_returns[daily_returns < 0.0]).sum())
    omega = (positive_sum / negative_sum) if negative_sum > 0.0 else float("inf")

    return {
        "sortino_ratio": round(float(sortino), 4) if np.isfinite(sortino) else float("inf"),
        "calmar_ratio": round(float(calmar), 4) if np.isfinite(calmar) else float("inf"),
        "omega_ratio": round(float(omega), 4) if np.isfinite(omega) else float("inf"),
        "annual_return_pct": round(float(annual_return * 100.0), 2),
        "max_drawdown_frac": round(float(max_drawdown), 6),
    }


def _composite_score(risk_metrics: dict[str, float]) -> float:
    sortino = float(risk_metrics["sortino_ratio"])
    calmar = float(risk_metrics["calmar_ratio"])
    omega = float(risk_metrics["omega_ratio"])
    return round((0.5 * sortino) + (0.3 * calmar) + (0.2 * omega), 4)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    base_params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    session_trades, session_metrics = run_backtest(dataset, base_params, trade_dates, entry_filter=base_filter)
    maxhold_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)
    maxhold_trades, maxhold_metrics = run_backtest_with_management(
        dataset=dataset,
        params=base_params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=maxhold_management,
    )

    cooldown_trades_path = (
        ARTIFACTS_DIR
        / "outputs"
        / "stalker_v10_1_session_deployment_followups_20260328"
        / "cooldown_session_trades.csv"
    )
    cooldown_trades = pd.read_csv(cooldown_trades_path)

    mt5_summary_path = (
        ARTIFACTS_DIR
        / "outputs"
        / "mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328"
        / "summary.json"
    )
    mt5_report_path = (
        ARTIFACTS_DIR
        / "outputs"
        / "mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328"
        / "mt5_model_0_report.html"
    )
    mt5_summary = _load_json(mt5_summary_path)
    mt5_trade_dates = trade_dates[
        (pd.to_datetime(trade_dates) >= pd.Timestamp("2021-03-22"))
        & (pd.to_datetime(trade_dates) <= pd.Timestamp("2026-03-20"))
    ]

    candidates = [
        {
            "name": "base_mt5_validated",
            "label": "Baseline, MT5-validated `sl0p84/tp0p30`",
            "family": "mt5_validated",
            "headline_metrics": {
                "net_profit_brl": float(mt5_summary["mt5_report"]["net_profit_brl"]),
                "profit_factor": float(mt5_summary["mt5_report"]["profit_factor"]),
                "max_drawdown_pct": float(mt5_summary["mt5_report"]["max_drawdown_pct"]),
                "win_rate_pct": float(mt5_summary["mt5_report"]["win_rate_pct"]),
                "total_trades": int(mt5_summary["mt5_report"]["total_trades"]),
            },
            "daily_pnl": _daily_pnl_from_mt5_report(mt5_report_path, mt5_trade_dates),
            "source_artifact": str(mt5_summary_path.resolve()),
        },
        {
            "name": "session_winner_exact",
            "label": "Session winner",
            "family": "exact_python",
            "headline_metrics": {
                "net_profit_brl": float(session_metrics["net_profit_brl"]),
                "profit_factor": float(session_metrics["profit_factor"]),
                "max_drawdown_pct": float(session_metrics["max_drawdown_pct"]),
                "win_rate_pct": round(float(session_metrics["win_rate"]) * 100.0, 2),
                "total_trades": int(session_metrics["total_trades"]),
            },
            "daily_pnl": _daily_pnl_from_trades(session_trades, trade_dates),
            "source_artifact": str(
                (ARTIFACTS_DIR / "outputs" / "stalker_v10_1_session_refinement_20260328" / "summary.json").resolve()
            ),
        },
        {
            "name": "cooldown_only_exact",
            "label": "Minimal moderate, session winner + cooldown",
            "family": "exact_python",
            "headline_metrics": {
                "net_profit_brl": 14085.0,
                "profit_factor": 1.4825,
                "max_drawdown_pct": 3.30,
                "win_rate_pct": 80.55,
                "total_trades": 1568,
            },
            "daily_pnl": _daily_pnl_from_trades(cooldown_trades, trade_dates),
            "source_artifact": str(
                (ARTIFACTS_DIR / "outputs" / "stalker_v10_1_session_deployment_followups_20260328" / "summary.json").resolve()
            ),
        },
        {
            "name": "cooldown_maxhold_exact",
            "label": "Max-hold v2, session winner + cooldown + `120` M1-bar max hold",
            "family": "exact_python",
            "headline_metrics": {
                "net_profit_brl": float(maxhold_metrics["net_profit_brl"]),
                "profit_factor": float(maxhold_metrics["profit_factor"]),
                "max_drawdown_pct": float(maxhold_metrics["max_drawdown_pct"]),
                "win_rate_pct": round(float(maxhold_metrics["win_rate"]) * 100.0, 2),
                "total_trades": int(maxhold_metrics["total_trades"]),
            },
            "daily_pnl": _daily_pnl_from_trades(maxhold_trades, trade_dates),
            "source_artifact": str(
                (ARTIFACTS_DIR / "outputs" / "stalker_v10_1_session_maxhold_followups_20260328" / "summary.json").resolve()
            ),
        },
    ]

    results: list[dict[str, Any]] = []
    for candidate in candidates:
        risk_metrics = _risk_adjusted_metrics(candidate["daily_pnl"])
        results.append(
            {
                "name": candidate["name"],
                "label": candidate["label"],
                "family": candidate["family"],
                "headline_metrics": candidate["headline_metrics"],
                "risk_adjusted_metrics": risk_metrics,
                "sortino_weighted_composite": _composite_score(risk_metrics),
                "source_artifact": candidate["source_artifact"],
            }
        )

    ranked = sorted(
        results,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["headline_metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for index, row in enumerate(ranked, start=1):
        row["composite_rank"] = index

    summary = {
        "methodology": {
            "daily_series_basis": "Daily PnL, normalized to a R$10,000 starting equity to match the repo's drawdown convention.",
            "sortino_ratio": "Annualized mean daily return divided by downside RMS of negative daily returns.",
            "calmar_ratio": "CAGR divided by maximum equity drawdown fraction.",
            "omega_ratio": "Sum of positive daily returns divided by absolute sum of negative daily returns, threshold 0%.",
            "sortino_weighted_composite": "0.50 * Sortino + 0.30 * Calmar + 0.20 * Omega.",
            "notes": [
                "The MT5 base candidate uses the actual Every Tick HTML deals ledger, aggregated to daily PnL.",
                "The exact Python candidates use the exact every-tick engine trade ledger, aggregated to daily PnL.",
                "The cooldown-only variant is included because it is the recommended Tier 2 operator configuration.",
            ],
        },
        "ranked_candidates": ranked,
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
