from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from ..common.paths import DATA_DIR, artifact_output_dir


POINT_VALUE_BRL = 10.0
ROUND_TRIP_COST_BRL = 4.0
TICK_SIZE = 0.5
OUTPUT_DIR = artifact_output_dir("wdo_offline_opening_range_breakout_20260330")
M5_PATH = DATA_DIR / "wdo_m5_2021_2026.parquet"
M15_PATH = DATA_DIR / "wdo_m15_2021_2026.parquet"


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    signal_fn: Callable[[pd.DataFrame], pd.Series]
    entry_start_hour: int
    entry_start_minute: int
    last_entry_hour: int
    last_entry_minute: int
    force_flat_hour: int
    force_flat_minute: int
    target_mult: float


def _spec_dict(spec: StrategySpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    return data


def _round_to_tick(value: float) -> float:
    return round(float(value) / TICK_SIZE) * TICK_SIZE


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _load_frame(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path).copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["timestamp_brt"] = df["timestamp_utc"].dt.tz_convert("America/Sao_Paulo")
    df = df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "Volume",
            "spread": "Spread",
            "real_volume": "RealVolume",
        }
    ).set_index("timestamp_brt")
    return df[["timestamp_utc", "Open", "High", "Low", "Close", "Volume", "Spread", "RealVolume"]].copy()


def _build_feature_frame(m5: pd.DataFrame, m15: pd.DataFrame) -> pd.DataFrame:
    frame = m5.copy()
    frame["session_date"] = frame.index.normalize()
    frame["entry_hour"] = frame.index.hour
    frame["entry_minute"] = frame.index.minute

    m15_feat = m15.copy()
    m15_feat["ema8_m15"] = _ema(m15_feat["Close"], 8)
    m15_feat["ema21_m15"] = _ema(m15_feat["Close"], 21)
    frame["ema8_m15"] = m15_feat["ema8_m15"].reindex(frame.index, method="ffill")
    frame["ema21_m15"] = m15_feat["ema21_m15"].reindex(frame.index, method="ffill")

    return frame


def _add_orb_levels(frame: pd.DataFrame, range_minutes: int) -> pd.DataFrame:
    enriched = frame.copy()
    start = 9 * 60
    end = start + range_minutes
    minute_of_day = enriched["entry_hour"] * 60 + enriched["entry_minute"]
    orb_mask = minute_of_day.ge(start) & minute_of_day.lt(end)
    orb = (
        enriched.loc[orb_mask]
        .groupby("session_date")
        .agg(orb_high=("High", "max"), orb_low=("Low", "min"))
    )
    orb["orb_range"] = orb["orb_high"] - orb["orb_low"]
    enriched = enriched.join(orb, on="session_date")
    return enriched


def _signal_orb(frame: pd.DataFrame, range_minutes: int, use_ema_confirm: bool) -> pd.Series:
    enriched = frame if {"orb_high", "orb_low", "orb_range"}.issubset(frame.columns) else _add_orb_levels(frame, range_minutes)
    signal = pd.Series(0, index=enriched.index, dtype=int)
    minutes = enriched["entry_hour"] * 60 + enriched["entry_minute"]
    start_minute = 9 * 60 + range_minutes
    tradable = minutes.ge(start_minute) & minutes.le(14 * 60)
    range_ready = enriched["orb_range"].notna() & (enriched["orb_range"] > 0.0)
    long_break = tradable & range_ready & (enriched["Close"] > enriched["orb_high"]) & (enriched["Close"].shift(1) <= enriched["orb_high"].shift(1))
    short_break = tradable & range_ready & (enriched["Close"] < enriched["orb_low"]) & (enriched["Close"].shift(1) >= enriched["orb_low"].shift(1))
    if use_ema_confirm:
        long_break &= enriched["ema8_m15"] > enriched["ema21_m15"]
        short_break &= enriched["ema8_m15"] < enriched["ema21_m15"]
    signal.loc[long_break] = 1
    signal.loc[short_break] = -1
    return signal


def _calc_metrics(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, float | int | str]:
    if len(trade_dates) == 0:
        return {"trading_days": 0, "total_trades": 0, "win_rate": 0.0, "net_profit_brl": 0.0, "profit_factor": 0.0, "max_drawdown_pct": 0.0}
    if trades.empty:
        return {
            "start_date": pd.Timestamp(trade_dates[0]).date().isoformat(),
            "end_date": pd.Timestamp(trade_dates[-1]).date().isoformat(),
            "trading_days": int(len(trade_dates)),
            "total_trades": 0,
            "win_rate": 0.0,
            "net_profit_brl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "avg_profit_brl": 0.0,
        }
    pnl = trades["pnl_brl"].astype(float)
    wins = pnl[pnl > 0.0]
    losses = pnl[pnl < 0.0]
    gross_profit = float(wins.sum())
    gross_loss = float(losses.abs().sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    normalized_trade_dates = pd.Index(pd.to_datetime(trade_dates).tz_localize(None).normalize())
    daily = (
        trades.assign(session_date=pd.to_datetime(trades["session_date"]).dt.tz_localize(None))
        .groupby("session_date")["pnl_brl"]
        .sum()
        .reindex(normalized_trade_dates, fill_value=0.0)
    )
    equity = 10_000.0 + daily.cumsum()
    peaks = equity.cummax()
    dd = ((peaks - equity) / peaks.replace(0.0, np.nan) * 100.0).max()
    return {
        "start_date": pd.Timestamp(trade_dates[0]).date().isoformat(),
        "end_date": pd.Timestamp(trade_dates[-1]).date().isoformat(),
        "trading_days": int(len(trade_dates)),
        "total_trades": int(len(trades)),
        "win_rate": round(float((pnl > 0.0).mean()), 4),
        "net_profit_brl": round(float(pnl.sum()), 2),
        "profit_factor": round(float(pf), 4) if np.isfinite(pf) else float("inf"),
        "max_drawdown_pct": round(float(dd), 2),
        "avg_profit_brl": round(float(pnl.mean()), 2),
    }


def _walkforward_1y_3m(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    normalized_trade_dates = pd.Index(pd.to_datetime(trade_dates).tz_localize(None).normalize())
    months = pd.Index(sorted(normalized_trade_dates.to_period("M").unique()))
    train_months = 12
    test_months = 3
    folds: list[dict[str, object]] = []
    for i in range(train_months, len(months) - test_months + 1, test_months):
        train = set(months[i - train_months : i])
        test = set(months[i : i + test_months])
        train_dates = pd.Index([d for d in normalized_trade_dates if d.to_period("M") in train])
        test_dates = pd.Index([d for d in normalized_trade_dates if d.to_period("M") in test])
        train_subset = trades.loc[trades["session_date"].isin(train_dates.strftime("%Y-%m-%d"))].reset_index(drop=True)
        test_subset = trades.loc[trades["session_date"].isin(test_dates.strftime("%Y-%m-%d"))].reset_index(drop=True)
        test_metrics = _calc_metrics(test_subset, test_dates)
        folds.append(
            {
                "train_months": [str(x) for x in sorted(train)],
                "test_months": [str(x) for x in sorted(test)],
                "train_metrics": _calc_metrics(train_subset, train_dates),
                "test_metrics": test_metrics,
                "pass": bool(test_metrics["net_profit_brl"] > 0 and float(test_metrics["profit_factor"]) > 1.0),
            }
        )
    return {"total_folds": len(folds), "passed_folds": int(sum(1 for f in folds if f["pass"])), "folds": folds}


def _backtest(frame: pd.DataFrame, spec: StrategySpec, range_minutes: int) -> pd.DataFrame:
    enriched = _add_orb_levels(frame, range_minutes)
    signal = spec.signal_fn(enriched).fillna(0).astype(int)
    cutoff = spec.force_flat_hour * 60 + spec.force_flat_minute
    last_entry_cutoff = spec.last_entry_hour * 60 + spec.last_entry_minute
    trades: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    position: dict[str, object] | None = None
    traded_days: set[pd.Timestamp] = set()
    idx = enriched.index

    for i in range(len(enriched)):
        ts = idx[i]
        bar = enriched.iloc[i]
        minute_of_day = ts.hour * 60 + ts.minute
        session_date = ts.normalize()

        if position is not None:
            current_open = _round_to_tick(float(bar["Open"]))
            current_high = _round_to_tick(float(bar["High"]))
            current_low = _round_to_tick(float(bar["Low"]))
            direction = int(position["direction"])
            stop_price = float(position["stop_price"])
            target_price = float(position["target_price"])
            exit_price = None
            exit_reason = None

            if minute_of_day >= cutoff:
                exit_price, exit_reason = current_open, "time_cutoff"
            elif direction == 1:
                if current_open <= stop_price:
                    exit_price, exit_reason = current_open, "stop_gap_open"
                elif current_open >= target_price:
                    exit_price, exit_reason = current_open, "target_gap_open"
                elif current_low <= stop_price and current_high >= target_price:
                    exit_price, exit_reason = stop_price, "ambiguous_stop_first"
                elif current_low <= stop_price:
                    exit_price, exit_reason = stop_price, "stop_loss"
                elif current_high >= target_price:
                    exit_price, exit_reason = target_price, "take_profit"
            else:
                if current_open >= stop_price:
                    exit_price, exit_reason = current_open, "stop_gap_open"
                elif current_open <= target_price:
                    exit_price, exit_reason = current_open, "target_gap_open"
                elif current_high >= stop_price and current_low <= target_price:
                    exit_price, exit_reason = stop_price, "ambiguous_stop_first"
                elif current_high >= stop_price:
                    exit_price, exit_reason = stop_price, "stop_loss"
                elif current_low <= target_price:
                    exit_price, exit_reason = target_price, "take_profit"

            if exit_price is not None:
                pnl_points = (float(exit_price) - float(position["entry_price"])) * direction
                trades.append(
                    {
                        "session_date": pd.Timestamp(position["session_date"]).date().isoformat(),
                        "entry_time": str(position["entry_time"]),
                        "exit_time": str(ts),
                        "direction": "long" if direction == 1 else "short",
                        "entry_price": float(position["entry_price"]),
                        "exit_price": float(exit_price),
                        "pnl_points": round(pnl_points, 3),
                        "pnl_brl": round((pnl_points * POINT_VALUE_BRL) - ROUND_TRIP_COST_BRL, 2),
                        "exit_reason": exit_reason,
                    }
                )
                position = None

        if position is None and pending is not None:
            entry_price = _round_to_tick(float(bar["Open"]))
            position = {
                "session_date": pending["session_date"],
                "entry_time": ts,
                "direction": pending["direction"],
                "entry_price": entry_price,
                "stop_price": pending["stop_price"],
                "target_price": pending["target_price"],
            }
            pending = None

        if position is None and pending is None and i < len(enriched) - 1:
            if session_date in traded_days:
                continue
            if minute_of_day < spec.entry_start_hour * 60 + spec.entry_start_minute or minute_of_day > last_entry_cutoff:
                continue
            direction = int(signal.iloc[i])
            if direction == 0:
                continue
            orb_high = float(bar["orb_high"]) if pd.notna(bar["orb_high"]) else np.nan
            orb_low = float(bar["orb_low"]) if pd.notna(bar["orb_low"]) else np.nan
            orb_range = float(bar["orb_range"]) if pd.notna(bar["orb_range"]) else np.nan
            if not np.isfinite(orb_range) or orb_range <= 0.0:
                continue
            next_open = _round_to_tick(float(enriched.iloc[i + 1]["Open"]))
            if direction == 1:
                stop_price = _round_to_tick(orb_low)
                target_price = _round_to_tick(next_open + spec.target_mult * orb_range)
            else:
                stop_price = _round_to_tick(orb_high)
                target_price = _round_to_tick(next_open - spec.target_mult * orb_range)
            pending = {
                "session_date": session_date,
                "direction": direction,
                "stop_price": stop_price,
                "target_price": target_price,
            }
            traded_days.add(session_date)

    return pd.DataFrame(trades)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    m5 = _load_frame(M5_PATH)
    m15 = _load_frame(M15_PATH)
    frame = _build_feature_frame(m5, m15)
    frame = frame.loc[
        (frame.index >= pd.Timestamp("2022-09-01", tz="America/Sao_Paulo"))
        & (frame.index <= pd.Timestamp("2026-03-29 23:59:59", tz="America/Sao_Paulo"))
    ].copy()
    trade_dates = pd.Index(sorted(frame.index.tz_localize(None).normalize().unique()))

    specs = [
        StrategySpec(
            name="orb15_tp10_ema_on",
            description="15m opening range breakout, TP 1.0x range, M15 EMA confirmation on.",
            signal_fn=lambda f: _signal_orb(f, 15, True),
            entry_start_hour=9,
            entry_start_minute=15,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=1.0,
        ),
        StrategySpec(
            name="orb15_tp15_ema_on",
            description="15m opening range breakout, TP 1.5x range, M15 EMA confirmation on.",
            signal_fn=lambda f: _signal_orb(f, 15, True),
            entry_start_hour=9,
            entry_start_minute=15,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=1.5,
        ),
        StrategySpec(
            name="orb15_tp20_ema_on",
            description="15m opening range breakout, TP 2.0x range, M15 EMA confirmation on.",
            signal_fn=lambda f: _signal_orb(f, 15, True),
            entry_start_hour=9,
            entry_start_minute=15,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=2.0,
        ),
        StrategySpec(
            name="orb15_tp10_ema_off",
            description="15m opening range breakout, TP 1.0x range, no EMA confirmation.",
            signal_fn=lambda f: _signal_orb(f, 15, False),
            entry_start_hour=9,
            entry_start_minute=15,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=1.0,
        ),
        StrategySpec(
            name="orb30_tp10_ema_on",
            description="30m opening range breakout, TP 1.0x range, M15 EMA confirmation on.",
            signal_fn=lambda f: _signal_orb(f, 30, True),
            entry_start_hour=9,
            entry_start_minute=30,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=1.0,
        ),
        StrategySpec(
            name="orb30_tp15_ema_on",
            description="30m opening range breakout, TP 1.5x range, M15 EMA confirmation on.",
            signal_fn=lambda f: _signal_orb(f, 30, True),
            entry_start_hour=9,
            entry_start_minute=30,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=1.5,
        ),
        StrategySpec(
            name="orb30_tp10_ema_off",
            description="30m opening range breakout, TP 1.0x range, no EMA confirmation.",
            signal_fn=lambda f: _signal_orb(f, 30, False),
            entry_start_hour=9,
            entry_start_minute=30,
            last_entry_hour=14,
            last_entry_minute=0,
            force_flat_hour=14,
            force_flat_minute=0,
            target_mult=1.0,
        ),
    ]

    ranked_rows: list[dict[str, object]] = []
    detailed: list[dict[str, object]] = []

    for spec in specs:
        range_minutes = 15 if "orb15" in spec.name else 30
        trades = _backtest(frame, spec, range_minutes)
        metrics = _calc_metrics(trades, trade_dates)
        walkforward = _walkforward_1y_3m(trades, trade_dates)
        ranked_rows.append(
            {
                "name": spec.name,
                "net_profit_brl": metrics["net_profit_brl"],
                "profit_factor": metrics["profit_factor"],
                "max_drawdown_pct": metrics["max_drawdown_pct"],
                "total_trades": metrics["total_trades"],
                "wf_passed_folds": walkforward["passed_folds"],
                "wf_total_folds": walkforward["total_folds"],
            }
        )
        detailed.append(
            {
                "name": spec.name,
                "description": spec.description,
                "params": _spec_dict(spec),
                "metrics": metrics,
                "walkforward_1y_train_3m_test": walkforward,
            }
        )
        trades.to_csv(OUTPUT_DIR / f"{spec.name}_trades.csv", index=False)
        partial_ranked = sorted(
            ranked_rows,
            key=lambda row: (
                float(row["profit_factor"]) if row["profit_factor"] != float("inf") else 999.0,
                -float(row["max_drawdown_pct"]),
                float(row["net_profit_brl"]),
            ),
            reverse=True,
        )
        promising = [row for row in partial_ranked if float(row["profit_factor"]) > 1.3 and float(row["max_drawdown_pct"]) < 15.0]
        (OUTPUT_DIR / "summary.json").write_text(
            json.dumps(
                {
                    "dataset": {
                        "m5_path": str(M5_PATH.resolve()),
                        "m15_path": str(M15_PATH.resolve()),
                        "start": str(frame.index.min()),
                        "end": str(frame.index.max()),
                        "trading_days": int(len(trade_dates)),
                    },
                    "cost_model": {
                        "round_trip_cost_brl": ROUND_TRIP_COST_BRL,
                        "tick_size": TICK_SIZE,
                        "point_value_brl": POINT_VALUE_BRL,
                    },
                    "ranked_variants": partial_ranked,
                    "promising_variants": promising,
                    "variants": detailed,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
