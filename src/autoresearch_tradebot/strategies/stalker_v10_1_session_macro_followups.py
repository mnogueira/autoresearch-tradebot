from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_macro_followups_20260328")
DEPLOYMENT_REFERENCE_PATH = Path(
    "artifacts/outputs/stalker_v10_1_session_deployment_followups_20260328/summary.json"
)


def combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool]:
    active = [candidate for candidate in filters if candidate is not None]

    def allow(context: dict[str, Any]) -> bool:
        return all(bool(candidate(context)) for candidate in active)

    return allow


def flatten_close_series(frame: pd.DataFrame) -> pd.Series:
    if isinstance(frame.columns, pd.MultiIndex):
        close_frame = frame.xs("Close", axis=1, level=0)
        return close_frame.iloc[:, 0].astype(float)
    if "Close" in frame.columns:
        return frame["Close"].astype(float)
    raise KeyError("Could not locate Close column in daily dataset.")


def compute_adx(daily_ohlc: pd.DataFrame, period: int = 14) -> pd.Series:
    high = daily_ohlc["High"].astype(float)
    low = daily_ohlc["Low"].astype(float)
    close = daily_ohlc["Close"].astype(float)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0.0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0.0), 0.0)

    tr = pd.concat(
        [
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    alpha = 1.0 / float(period)
    atr = tr.ewm(alpha=alpha, adjust=False).mean()
    plus_dm_smoothed = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    minus_dm_smoothed = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    plus_di = 100.0 * plus_dm_smoothed / atr.replace(0.0, np.nan)
    minus_di = 100.0 * minus_dm_smoothed / atr.replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False).mean()


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    cooldown_management = ManagementConfig(min_minutes_between_entries=30)

    bars = dataset.bars_m1.copy()
    daily_wdo = (
        bars.assign(session_date=pd.to_datetime(bars["session_date"]).dt.normalize())
        .groupby("session_date")
        .agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    )
    daily_adx = compute_adx(daily_wdo, period=14).shift(1)

    dxy_frame = pd.read_parquet("data/dxy_daily.parquet")
    dxy_close = flatten_close_series(dxy_frame)
    dxy_close.index = pd.to_datetime(dxy_close.index).normalize()

    wdo_returns = daily_wdo["Close"].astype(float).pct_change()
    dxy_returns = dxy_close.pct_change()
    aligned_returns = pd.concat(
        [
            wdo_returns.rename("wdo_ret"),
            dxy_returns.rename("dxy_ret"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    rolling_corr = aligned_returns["wdo_ret"].rolling(20, min_periods=15).corr(aligned_returns["dxy_ret"]).shift(1)

    def daily_adx_filter(context: dict[str, Any]) -> bool:
        session = pd.Timestamp(context["session_date"]).normalize()
        value = float(daily_adx.get(session, np.nan))
        return bool(np.isfinite(value) and value > 25.0)

    def dxy_corr_filter(context: dict[str, Any]) -> bool:
        session = pd.Timestamp(context["session_date"]).normalize()
        value = float(rolling_corr.get(session, np.nan))
        return bool(np.isfinite(value) and value > 0.7)

    _, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=cooldown_management,
    )

    _, adx_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, daily_adx_filter),
        management=cooldown_management,
    )

    _, dxy_corr_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=combine_filters(base_filter, dxy_corr_filter),
        management=cooldown_management,
    )

    _, max_120_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    walkforward_70_30: dict[str, Any] | None = None
    if DEPLOYMENT_REFERENCE_PATH.exists():
        payload = json.loads(DEPLOYMENT_REFERENCE_PATH.read_text(encoding="utf-8"))
        walkforward_70_30 = payload.get("walkforward_70_30")

    summary = {
        "reference_variant": "session_winner_cooldown_30m",
        "reference_metrics": reference_metrics,
        "daily_adx_trending_only": {
            "rule": "Use prior-day ADX(14) on daily WDO; only allow entries when ADX > 25.",
            "metrics": adx_metrics,
        },
        "dxy_correlation_filter": {
            "rule": "Use prior-day rolling 20-session correlation between daily WDO returns and daily DXY returns; only allow entries when correlation > 0.70.",
            "metrics": dxy_corr_metrics,
        },
        "max_position_duration_120_m1_bars": {
            "rule": "Combine the 30-minute cooldown with a hard exit after 120 M1 bars.",
            "metrics": max_120_metrics,
        },
        "existing_walkforward_70_30": walkforward_70_30,
        "notes": [
            "The daily ADX filter uses only information known as of the prior completed daily candle.",
            "The DXY correlation filter is constrained by DXY daily data availability, which begins later than the WDO sample.",
            "The walk-forward section is reused from the existing cooldown deployment follow-up artifact because it already tests the exact same reference strategy on a clean 70/30 split.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_daily_adx_gt_25",
            family="session_daily_regime",
            metrics=adx_metrics,
            notes="Exact session+cooldown winner filtered by prior-day daily ADX(14) > 25.",
            artifact=summary_path,
            params={"daily_adx_period": 14, "daily_adx_threshold": 25.0, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_dxy_corr_gt_0p7",
            family="session_macro_correlation",
            metrics=dxy_corr_metrics,
            notes="Exact session+cooldown winner filtered by prior-day 20-session rolling WDO/DXY correlation > 0.70.",
            artifact=summary_path,
            params={"correlation_window_days": 20, "correlation_threshold": 0.7, "min_minutes_between_entries": 30},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_time_exit_120m1bars",
            family="session_time_exit",
            metrics=max_120_metrics,
            notes="Exact session+cooldown winner with a hard exit after 120 M1 bars.",
            artifact=summary_path,
            params={"max_bars_in_trade": 120, "engine_bar_size": "M1"},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
