from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import session_winner_params
from .stalker_v10_python import POINT_VALUE_BRL, calculate_metrics

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_microstructure_entry_followups_20260328")
RAW_DATA_PATH = Path(r"c:\Dev\autoresearch-tradebot\data\wdo_m1_mt5_2021_2026.parquet")
REFERENCE_TRADES_PATH = (
    Path(r"c:\Dev\autoresearch-tradebot\artifacts\outputs")
    / "stalker_v10_1_session_deployment_followups_20260328"
    / "cooldown_session_trades.csv"
)
PRICE_TICK_SIZE = 0.5


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _direction_sign(direction: pd.Series) -> pd.Series:
    return direction.map({"long": 1.0, "short": -1.0}).astype(float)


def _reprice_trades(
    trades: pd.DataFrame,
    new_entry_prices: pd.Series,
    new_entry_times: pd.Series,
) -> pd.DataFrame:
    repriced = trades.copy()
    direction_sign = _direction_sign(repriced["direction"])
    entry_delta_points = direction_sign * (repriced["entry_price"].astype(float) - new_entry_prices.astype(float))
    contracts = float(session_winner_params().ContractsPerTrade)
    repriced["entry_price"] = new_entry_prices.astype(float)
    repriced["entry_time"] = pd.to_datetime(new_entry_times)
    repriced["pnl_points"] = repriced["pnl_points"].astype(float) + entry_delta_points.astype(float)
    repriced["pnl_brl"] = repriced["pnl_brl"].astype(float) + (
        entry_delta_points.astype(float) * float(POINT_VALUE_BRL) * contracts
    )
    return repriced


def _variant_block(
    trades: pd.DataFrame,
    trade_dates: pd.Index,
    kept_mask: pd.Series,
    new_entry_prices: pd.Series,
    new_entry_times: pd.Series,
    assumption: str,
) -> dict[str, Any]:
    filtered = trades.loc[kept_mask].copy().reset_index(drop=True)
    if filtered.empty:
        metrics = calculate_metrics(pd.DataFrame(), trade_dates)
        return {
            "metrics": metrics,
            **_risk_block(pd.DataFrame(), trade_dates),
            "kept_trades": 0,
            "skipped_trades": int((~kept_mask).sum()),
            "keep_rate": 0.0,
            "assumption": assumption,
        }
    repriced = _reprice_trades(
        filtered,
        new_entry_prices.loc[kept_mask].reset_index(drop=True),
        new_entry_times.loc[kept_mask].reset_index(drop=True),
    )
    metrics = calculate_metrics(repriced, trade_dates)
    return {
        "metrics": metrics,
        **_risk_block(repriced, trade_dates),
        "kept_trades": int(len(repriced)),
        "skipped_trades": int((~kept_mask).sum()),
        "keep_rate": round(float(kept_mask.mean()), 4),
        "assumption": assumption,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_bars = pd.read_parquet(RAW_DATA_PATH)[["Open", "Close"]].copy()
    raw_bars.index = pd.to_datetime(raw_bars.index)
    trade_dates = pd.Index(raw_bars.index.normalize().unique())

    trades = pd.read_csv(
        REFERENCE_TRADES_PATH,
        parse_dates=["signal_time", "entry_time", "exit_time"],
    )
    trades["entry_price"] = trades["entry_price"].astype(float)
    trades["pnl_points"] = trades["pnl_points"].astype(float)
    trades["pnl_brl"] = trades["pnl_brl"].astype(float)

    signal_close = raw_bars["Close"].reindex(pd.DatetimeIndex(trades["signal_time"])).astype(float).reset_index(drop=True)
    next_open_time = pd.to_datetime(trades["signal_time"]) + pd.Timedelta(minutes=1)
    next_open = raw_bars["Open"].reindex(pd.DatetimeIndex(next_open_time)).astype(float).reset_index(drop=True)
    direction_sign = _direction_sign(trades["direction"]).reset_index(drop=True)

    valid_next_open = next_open.notna() & signal_close.notna()
    favorable_next_open = valid_next_open & (
        ((direction_sign > 0) & (next_open <= signal_close))
        | ((direction_sign < 0) & (next_open >= signal_close))
    )

    desired_limit_price = signal_close - (direction_sign * PRICE_TICK_SIZE)
    improved_limit_fill = valid_next_open & (
        ((direction_sign > 0) & (next_open <= desired_limit_price))
        | ((direction_sign < 0) & (next_open >= desired_limit_price))
    )

    reference_metrics = calculate_metrics(trades, trade_dates)
    improvement_ticks = direction_sign * ((signal_close - next_open) / PRICE_TICK_SIZE)

    patience_block = _variant_block(
        trades=trades,
        trade_dates=trade_dates,
        kept_mask=favorable_next_open,
        new_entry_prices=next_open,
        new_entry_times=next_open_time,
        assumption=(
            "Research-only overlay: if the next M1 open is no worse than the signal bar close, wait and enter there; "
            "otherwise skip the trade."
        ),
    )
    limit_block = _variant_block(
        trades=trades,
        trade_dates=trade_dates,
        kept_mask=improved_limit_fill,
        new_entry_prices=desired_limit_price,
        new_entry_times=next_open_time,
        assumption=(
            "Research-only overlay: place a limit one WDO tick better than the signal bar close and only keep trades "
            "where the next M1 open is already at or beyond that improved price."
        ),
    )

    diagnostics = {
        "reference_trade_count": int(len(trades)),
        "share_with_observed_next_open": round(float(valid_next_open.mean()), 4),
        "share_next_open_non_worse_than_signal_close": round(float(favorable_next_open.mean()), 4),
        "share_next_open_one_tick_better_than_signal_close": round(float(improved_limit_fill.mean()), 4),
        "mean_next_open_improvement_ticks": round(float(improvement_ticks[valid_next_open].mean()), 4),
        "median_next_open_improvement_ticks": round(float(improvement_ticks[valid_next_open].median()), 4),
    }

    summary = {
        "reference_tier2_cooldown_only": {
            "metrics": reference_metrics,
            **_risk_block(trades, trade_dates),
        },
        "next_open_patience_filter": patience_block,
        "next_open_one_tick_limit_proxy": limit_block,
        "diagnostics": diagnostics,
        "notes": [
            "These are post-trade microstructure overlays on top of the exact Tier 2 trade tape, not a full exact-engine rerun with changed stop/target paths.",
            "The patience filter measures whether waiting one minute without paying up would have improved entry quality.",
            "The one-tick limit proxy is deliberately conservative: it only counts trades where the next M1 open is already at or beyond the improved limit price.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
