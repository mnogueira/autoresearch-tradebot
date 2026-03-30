from __future__ import annotations

import json
from dataclasses import asdict

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_corrected_cost_combo_volume_ema_hourmap_20260329 import _m15_state_filter
from .stalker_v10_1_corrected_cost_structural_followups_20260329 import _build_combo_filter, _build_params
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block, _variant_payload
from .stalker_v10_1_session_execution_refinement import ManagementConfig, run_backtest_with_management
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_recent_analysis_20260329")


def _build_m5_ema20_state(dataset: V10Dataset) -> pd.Series:
    m5 = (
        dataset.bars_m1[["Close"]]
        .resample("5min")
        .agg({"Close": "last"})
        .dropna()
    )
    ema20 = m5["Close"].ewm(span=20, adjust=False).mean()
    state = pd.Series(0, index=m5.index, dtype=int)
    state.loc[m5["Close"] > ema20] = 1
    state.loc[m5["Close"] < ema20] = -1
    state = state.shift(1).fillna(0).astype(int)
    return state.reindex(pd.DatetimeIndex(dataset.bars_m1.index), method="ffill").fillna(0).astype(int)


def _duration_minutes(trades: pd.DataFrame) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    entry = pd.to_datetime(trades["entry_time"])
    exit_ = pd.to_datetime(trades["exit_time"])
    return (exit_ - entry).dt.total_seconds() / 60.0


def _simple_bucket(trades: pd.DataFrame) -> dict[str, object]:
    if trades.empty:
        return {
            "total_trades": 0,
            "net_profit_brl": 0.0,
            "avg_profit_brl": 0.0,
            "win_rate": 0.0,
            "avg_duration_min": 0.0,
            "median_duration_min": 0.0,
        }
    durations = _duration_minutes(trades)
    wins = float((trades["pnl_brl"] > 0).mean())
    return {
        "total_trades": int(len(trades)),
        "net_profit_brl": float(trades["pnl_brl"].sum()),
        "avg_profit_brl": float(trades["pnl_brl"].mean()),
        "win_rate": round(wins, 4),
        "avg_duration_min": round(float(durations.mean()), 2),
        "median_duration_min": round(float(durations.median()), 2),
    }


def _group_summary(trades: pd.DataFrame, group_col: str) -> list[dict[str, object]]:
    if trades.empty:
        return []
    frame = trades.copy()
    frame["duration_min"] = _duration_minutes(frame)
    rows: list[dict[str, object]] = []
    for group_value, group in frame.groupby(group_col, sort=True):
        rows.append(
            {
                group_col: group_value if not isinstance(group_value, pd.Timestamp) else group_value.strftime("%Y-%m-%d"),
                "total_trades": int(len(group)),
                "net_profit_brl": round(float(group["pnl_brl"].sum()), 2),
                "avg_profit_brl": round(float(group["pnl_brl"].mean()), 2),
                "win_rate": round(float((group["pnl_brl"] > 0).mean()), 4),
                "avg_duration_min": round(float(group["duration_min"].mean()), 2),
            }
        )
    return rows


def _group_summary_multi(trades: pd.DataFrame, group_cols: list[str]) -> list[dict[str, object]]:
    if trades.empty:
        return []
    frame = trades.copy()
    frame["duration_min"] = _duration_minutes(frame)
    rows: list[dict[str, object]] = []
    for group_values, group in frame.groupby(group_cols, sort=True):
        if not isinstance(group_values, tuple):
            group_values = (group_values,)
        row = {
            key: value if not isinstance(value, pd.Timestamp) else value.strftime("%Y-%m-%d")
            for key, value in zip(group_cols, group_values, strict=True)
        }
        row.update(
            {
                "total_trades": int(len(group)),
                "net_profit_brl": round(float(group["pnl_brl"].sum()), 2),
                "avg_profit_brl": round(float(group["pnl_brl"].mean()), 2),
                "win_rate": round(float((group["pnl_brl"] > 0).mean()), 4),
                "avg_duration_min": round(float(group["duration_min"].mean()), 2),
            }
        )
        rows.append(row)
    return rows


def _recent_trade_breakdown(trades: pd.DataFrame) -> dict[str, object]:
    frame = trades.copy()
    frame["entry_hour"] = pd.to_datetime(frame["entry_time"]).dt.hour
    frame["direction"] = frame["direction"].astype(str)
    winners = frame.loc[frame["pnl_brl"] > 0].reset_index(drop=True)
    losers = frame.loc[frame["pnl_brl"] <= 0].reset_index(drop=True)
    return {
        "overall": _simple_bucket(frame),
        "winners": _simple_bucket(winners),
        "losers": _simple_bucket(losers),
        "by_direction": _group_summary(frame, "direction"),
        "by_hour": _group_summary(frame, "entry_hour"),
        "winner_hours": _group_summary(winners, "entry_hour"),
        "loser_hours": _group_summary(losers, "entry_hour"),
        "direction_hour_grid": _group_summary_multi(frame, ["direction", "entry_hour"]),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = _build_params()
    management = ManagementConfig(min_minutes_between_entries=60)
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_3m_dates = trade_dates[trade_dates >= pd.Timestamp("2026-01-01")]
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    combo_filter = _build_combo_filter(dataset)
    combo_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=combo_filter,
        management=management,
    )

    m5_state = _build_m5_ema20_state(dataset)
    m5_filter = _m15_state_filter(m5_state)
    m5_confirm_filter = lambda context: combo_filter(context) and m5_filter(context)
    m5_confirm_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=m5_confirm_filter,
        management=management,
    )

    recent_3m_trades = combo_trades.loc[
        combo_trades["session_date"].isin(pd.Index(recent_3m_dates).strftime("%Y-%m-%d"))
    ].reset_index(drop=True)
    recent_3m_trades.to_csv(OUTPUT_DIR / "recent_3m_combo_trades.csv", index=False)

    summary = {
        "combo_reference": _variant_payload(
            name="tier2a_corrected_no_roc_no_maxhold_sl1p0_tp0p48_cd60_skipfriday_skiplast1_prune_longs_topatr33_shorts_10_11_12",
            rule="Corrected-cost stacked combo reference.",
            trades=combo_trades,
            trade_dates=trade_dates,
            params={"params": asdict(params), "management": asdict(management)},
        ),
        "recent_3m_combo": {
            **_subset_block(combo_trades, recent_3m_dates),
            "trade_breakdown": _recent_trade_breakdown(recent_3m_trades),
        },
        "m5_ema20_confirmation": {
            "variant": _variant_payload(
                name="tier2a_corrected_combo_m5_ema20_confirmation",
                rule="Corrected-cost stacked combo plus prior completed M5 close above EMA20 for longs and below EMA20 for shorts.",
                trades=m5_confirm_trades,
                trade_dates=trade_dates,
                params={"params": asdict(params), "management": asdict(management)},
            ),
            "walkforward_70_30": {
                "train": _subset_block(m5_confirm_trades, train_dates),
                "test": _subset_block(m5_confirm_trades, test_dates),
            },
            "recent_windows": {
                "recent_3m": _subset_block(m5_confirm_trades, recent_3m_dates),
                "recent_60d": _subset_block(m5_confirm_trades, recent_60),
                "recent_30d": _subset_block(m5_confirm_trades, recent_30),
                "recent_10d": _subset_block(m5_confirm_trades, recent_10),
            },
        },
        "notes": [
            "Recent-window anatomy for the corrected-cost stacked combo.",
            "Also checks whether a lightweight M5 EMA20 confirmation layer improves the M1 combo.",
        ],
    }

    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
