from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.paths import ARTIFACTS_DIR, artifact_output_dir
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_python import run_backtest
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_trade_sharpe_smoothing_20260328")


def _rolling_trade_sharpe(trades: pd.DataFrame, window: int = 20) -> dict[str, float]:
    pnl = trades["pnl_brl"].astype(float)
    rolling = pnl.rolling(window=int(window), min_periods=int(window))
    sharpe = (rolling.mean() / rolling.std(ddof=0).replace(0.0, np.nan)) * np.sqrt(float(window))
    sharpe = sharpe.replace([np.inf, -np.inf], np.nan).dropna()
    if sharpe.empty:
        return {
            "window": int(window),
            "median": 0.0,
            "p25": 0.0,
            "minimum": 0.0,
            "pct_positive_windows": 0.0,
            "num_windows": 0,
        }
    return {
        "window": int(window),
        "median": round(float(sharpe.median()), 4),
        "p25": round(float(sharpe.quantile(0.25)), 4),
        "minimum": round(float(sharpe.min()), 4),
        "pct_positive_windows": round(float((sharpe > 0.0).mean()), 4),
        "num_windows": int(len(sharpe)),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})

    session_trades, _ = run_backtest(dataset, params, dataset.trade_dates, entry_filter=entry_filter)
    cooldown_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    maxhold_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    time_widened_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            widen_stop_after_bars=30,
            widened_sl_atr_mult=1.20,
        ),
    )
    weekly_cap_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            max_weekly_profit_brl=300.0,
        ),
    )

    mt5_trade_log = (
        ARTIFACTS_DIR
        / "outputs"
        / "mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328"
        / "trade_log.csv"
    )
    mt5_trades = pd.read_csv(mt5_trade_log) if mt5_trade_log.exists() else pd.DataFrame(columns=["pnl_brl"])

    candidates = [
        ("tier1_mt5_base", mt5_trades),
        ("session_winner", session_trades),
        ("cooldown_only", cooldown_trades),
        ("maxhold_v2", maxhold_trades),
        ("time_widened_stop", time_widened_trades),
        ("weekly_cap_300", weekly_cap_trades),
    ]
    rows = [
        {
            "name": name,
            "rolling_20_trade_sharpe": _rolling_trade_sharpe(trades, window=20),
        }
        for name, trades in candidates
    ]
    rows.sort(
        key=lambda row: (
            float(row["rolling_20_trade_sharpe"]["median"]),
            float(row["rolling_20_trade_sharpe"]["pct_positive_windows"]),
        ),
        reverse=True,
    )

    summary = {
        "method": "Rolling 20-trade Sharpe on realized trade PnL, using population std within each 20-trade window.",
        "ranked_variants": rows,
    }
    output_path = DEFAULT_OUTPUT_DIR / "summary.json"
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
