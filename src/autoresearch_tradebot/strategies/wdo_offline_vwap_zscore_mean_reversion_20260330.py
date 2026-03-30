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
OUTPUT_DIR = artifact_output_dir("wdo_offline_vwap_zscore_mean_reversion_20260330")
M5_PATH = DATA_DIR / "wdo_m5_2021_2026.parquet"
M15_PATH = DATA_DIR / "wdo_m15_2021_2026.parquet"


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    signal_fn: Callable[[pd.DataFrame], pd.Series]
    stop_atr_mult: float
    entry_start_hour: int
    last_entry_hour: int
    last_entry_minute: int = 55
    force_flat_hour: int = 17
    force_flat_minute: int = 50
    max_hold_bars: int | None = None


def _spec_dict(spec: StrategySpec) -> dict[str, object]:
    data = asdict(spec)
    data.pop("signal_fn", None)
    return data


def _round_to_tick(value: float) -> float:
    return round(float(value) / TICK_SIZE) * TICK_SIZE


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _atr(frame: pd.DataFrame, period: int) -> pd.Series:
    prev_close = frame["Close"].shift(1)
    tr = pd.concat(
        [
            frame["High"] - frame["Low"],
            (frame["High"] - prev_close).abs(),
            (frame["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _session_vwap(frame: pd.DataFrame) -> pd.Series:
    typical = (frame["High"] + frame["Low"] + frame["Close"]) / 3.0
    value = typical * frame["Volume"].replace(0.0, np.nan)
    session = frame.index.normalize()
    cum_value = value.groupby(session).cumsum()
    cum_volume = frame["Volume"].replace(0.0, np.nan).groupby(session).cumsum()
    return (cum_value / cum_volume).ffill()


def _session_rolling_std(series: pd.Series, window: int) -> pd.Series:
    return series.groupby(series.index.normalize()).transform(
        lambda s: s.rolling(window, min_periods=max(6, window // 2)).std()
    )


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
    frame["atr14_m5"] = _atr(frame, 14)
    frame["session_vwap"] = _session_vwap(frame)
    frame["vwap_dist"] = frame["Close"] - frame["session_vwap"]
    frame["vwap_std12"] = _session_rolling_std(frame["vwap_dist"], 12)
    frame["vwap_std24"] = _session_rolling_std(frame["vwap_dist"], 24)
    frame["vwap_z12"] = frame["vwap_dist"] / frame["vwap_std12"].replace(0.0, np.nan)
    frame["vwap_z24"] = frame["vwap_dist"] / frame["vwap_std24"].replace(0.0, np.nan)
    frame["vol_avg12"] = frame["Volume"].rolling(12, min_periods=6).mean()
    frame["spread_ticks"] = (frame["Spread"] * 0.001) / TICK_SIZE

    m15_feat = m15.copy()
    m15_feat["ema20_m15"] = _ema(m15_feat["Close"], 20)
    m15_feat["ema50_m15"] = _ema(m15_feat["Close"], 50)
    m15_feat["atr14_m15"] = _atr(m15_feat, 14)
    frame["ema20_m15"] = m15_feat["ema20_m15"].reindex(frame.index, method="ffill")
    frame["ema50_m15"] = m15_feat["ema50_m15"].reindex(frame.index, method="ffill")
    frame["atr14_m15"] = m15_feat["atr14_m15"].reindex(frame.index, method="ffill")
    frame["trend_gap_ratio"] = (frame["ema20_m15"] - frame["ema50_m15"]).abs() / frame["atr14_m15"].replace(0.0, np.nan)

    daily = frame.groupby("session_date").agg(day_high=("High", "max"), day_low=("Low", "min"), close=("Close", "last"))
    daily["atr14_day"] = _atr(
        daily.rename(columns={"day_high": "High", "day_low": "Low", "close": "Close"})[["High", "Low", "Close"]],
        14,
    )
    daily["atr14_prior"] = daily["atr14_day"].shift(1)
    daily["atr20_mean_prior"] = daily["atr14_prior"].rolling(20, min_periods=10).mean()
    frame["daily_atr14_prior"] = frame["session_date"].map(daily["atr14_prior"])
    frame["daily_atr20_mean_prior"] = frame["session_date"].map(daily["atr20_mean_prior"])
    frame["low_vol_day"] = frame["daily_atr14_prior"] <= frame["daily_atr20_mean_prior"]
    return frame


def _signal_zscore(frame: pd.DataFrame, z_col: str, threshold: float, require_flat_m15: bool, hours: tuple[int, int]) -> pd.Series:
    afternoon = frame["entry_hour"].between(hours[0], hours[1])
    flat = (frame["trend_gap_ratio"] <= 0.35) if require_flat_m15 else True
    long_signal = afternoon & frame["low_vol_day"] & flat & (frame[z_col] <= -threshold)
    short_signal = afternoon & frame["low_vol_day"] & flat & (frame[z_col] >= threshold)
    signal = pd.Series(0, index=frame.index, dtype=int)
    signal.loc[long_signal] = 1
    signal.loc[short_signal] = -1
    return signal


def _signal_zscore_volume(frame: pd.DataFrame, z_col: str, threshold: float, hours: tuple[int, int]) -> pd.Series:
    signal = _signal_zscore(frame, z_col, threshold, True, hours)
    vol_gate = frame["Volume"] <= (1.25 * frame["vol_avg12"])
    return signal.where(vol_gate, 0)


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


def _backtest(frame: pd.DataFrame, spec: StrategySpec) -> pd.DataFrame:
    signal = spec.signal_fn(frame).fillna(0).astype(int)
    cutoff = spec.force_flat_hour * 60 + spec.force_flat_minute
    last_entry_cutoff = spec.last_entry_hour * 60 + spec.last_entry_minute
    trades: list[dict[str, object]] = []
    pending: dict[str, object] | None = None
    position: dict[str, object] | None = None
    idx = frame.index

    for i in range(len(frame)):
        ts = idx[i]
        bar = frame.iloc[i]
        minute_of_day = ts.hour * 60 + ts.minute

        if position is not None:
            current_open = _round_to_tick(float(bar["Open"]))
            current_high = _round_to_tick(float(bar["High"]))
            current_low = _round_to_tick(float(bar["Low"]))
            exit_price = None
            exit_reason = None

            direction = int(position["direction"])
            stop_price = float(position["stop_price"])
            target_price = float(position["target_price"])
            if minute_of_day >= cutoff:
                exit_price = current_open
                exit_reason = "time_cutoff"
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
                    exit_price, exit_reason = target_price, "vwap_revert"
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
                    exit_price, exit_reason = target_price, "vwap_revert"

            if exit_price is None and spec.max_hold_bars is not None and i - int(position["entry_index"]) >= spec.max_hold_bars:
                exit_price = _round_to_tick(float(bar["Close"]))
                exit_reason = "max_hold"

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
                "entry_index": i,
                "direction": pending["direction"],
                "entry_price": entry_price,
                "stop_price": pending["stop_price"],
                "target_price": pending["target_price"],
            }
            pending = None

        if position is None and pending is None and i < len(frame) - 1:
            if minute_of_day < spec.entry_start_hour * 60 or minute_of_day > last_entry_cutoff:
                continue
            direction = int(signal.iloc[i])
            if direction == 0:
                continue
            atr_value = float(bar["atr14_m5"]) if pd.notna(bar["atr14_m5"]) else np.nan
            if not np.isfinite(atr_value) or atr_value <= 0.0:
                continue
            next_open = _round_to_tick(float(frame.iloc[i + 1]["Open"]))
            target_price = _round_to_tick(float(bar["session_vwap"]))
            if direction == 1:
                stop_price = _round_to_tick(next_open - (spec.stop_atr_mult * atr_value))
                if target_price <= next_open:
                    continue
            else:
                stop_price = _round_to_tick(next_open + (spec.stop_atr_mult * atr_value))
                if target_price >= next_open:
                    continue
            pending = {
                "session_date": ts.normalize(),
                "direction": direction,
                "stop_price": stop_price,
                "target_price": target_price,
            }

    return pd.DataFrame(trades)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    m5 = _load_frame(M5_PATH)
    m15 = _load_frame(M15_PATH)
    frame = _build_feature_frame(m5, m15)
    frame = frame.loc[(frame.index >= pd.Timestamp("2022-09-01", tz="America/Sao_Paulo")) & (frame.index <= pd.Timestamp("2026-03-29 23:59:59", tz="America/Sao_Paulo"))].copy()
    trade_dates = pd.Index(sorted(frame.index.tz_localize(None).normalize().unique()))

    specs = [
        StrategySpec(
            name="vwap_z24_afternoon_z20",
            description="Afternoon low-vol VWAP mean reversion, z24 threshold 2.0, flat M15 filter.",
            signal_fn=lambda f: _signal_zscore(f, "vwap_z24", 2.0, True, (14, 16)),
            stop_atr_mult=1.0,
            entry_start_hour=14,
            last_entry_hour=16,
            max_hold_bars=12,
        ),
        StrategySpec(
            name="vwap_z24_afternoon_z25",
            description="Afternoon low-vol VWAP mean reversion, z24 threshold 2.5, flat M15 filter.",
            signal_fn=lambda f: _signal_zscore(f, "vwap_z24", 2.5, True, (14, 16)),
            stop_atr_mult=1.0,
            entry_start_hour=14,
            last_entry_hour=16,
            max_hold_bars=12,
        ),
        StrategySpec(
            name="vwap_z12_afternoon_z20",
            description="Afternoon low-vol VWAP mean reversion, z12 threshold 2.0, flat M15 filter.",
            signal_fn=lambda f: _signal_zscore(f, "vwap_z12", 2.0, True, (14, 16)),
            stop_atr_mult=1.0,
            entry_start_hour=14,
            last_entry_hour=16,
            max_hold_bars=8,
        ),
        StrategySpec(
            name="vwap_z12_afternoon_z20_noflat",
            description="Afternoon low-vol VWAP mean reversion, z12 threshold 2.0, no flat-trend filter.",
            signal_fn=lambda f: _signal_zscore(f, "vwap_z12", 2.0, False, (14, 16)),
            stop_atr_mult=1.0,
            entry_start_hour=14,
            last_entry_hour=16,
            max_hold_bars=8,
        ),
        StrategySpec(
            name="vwap_z12_late_z20",
            description="Late-session low-vol VWAP mean reversion, z12 threshold 2.0.",
            signal_fn=lambda f: _signal_zscore(f, "vwap_z12", 2.0, True, (15, 17)),
            stop_atr_mult=1.0,
            entry_start_hour=15,
            last_entry_hour=17,
            last_entry_minute=0,
            max_hold_bars=8,
        ),
        StrategySpec(
            name="vwap_z24_afternoon_z20_volume",
            description="Afternoon VWAP z-score mean reversion plus anti-chase volume gate.",
            signal_fn=lambda f: _signal_zscore_volume(f, "vwap_z24", 2.0, (14, 16)),
            stop_atr_mult=1.0,
            entry_start_hour=14,
            last_entry_hour=16,
            max_hold_bars=12,
        ),
    ]

    ranked_rows: list[dict[str, object]] = []
    detailed: list[dict[str, object]] = []

    for spec in specs:
        trades = _backtest(frame, spec)
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
