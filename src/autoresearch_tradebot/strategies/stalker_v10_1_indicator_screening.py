from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator

from ..common.paths import artifact_output_dir
from .stalker_v10_1_strength_research import perf_by_split
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_indicator_screening")


def robust_baseline_params() -> V101Params:
    return V101Params(
        TrendEfficiencyWindowMinutes=15,
        ApplyTrendEfficiencyFilterToLongs=True,
        ApplyTrendEfficiencyFilterToShorts=False,
        MinDirectionalTrendEfficiency15m=0.333333,
        VolumeWindowMinutes=30,
        ApplyVolumeFilterToLongs=False,
        ApplyVolumeFilterToShorts=True,
        MinSignalVolumeWindowSum=30000.0,
    )


def attach_bar_features(dataset: V10Dataset) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    bars["session_date"] = bars.index.normalize()
    bars["entry_hour"] = bars.index.hour

    for period in (10, 20, 30):
        bars[f"atr_current_{period}"] = dataset.get_atr_current(period)

    rsi14 = RSIIndicator(close=bars["Close"], window=14).rsi()
    prev_close = bars["Close"].shift(1)
    prev_rsi = rsi14.shift(1)
    bars["rsi14"] = rsi14

    for lookback in (5, 10, 15):
        bars[f"price_delta_lb{lookback}"] = prev_close - bars["Close"].shift(lookback + 1)
        bars[f"rsi_delta_lb{lookback}"] = prev_rsi - rsi14.shift(lookback + 1)

    return bars[
        [
            "session_date",
            "entry_hour",
            "atr_current_10",
            "atr_current_20",
            "atr_current_30",
            "rsi14",
            "price_delta_lb5",
            "price_delta_lb10",
            "price_delta_lb15",
            "rsi_delta_lb5",
            "rsi_delta_lb10",
            "rsi_delta_lb15",
        ]
    ].copy()


def quantile_thresholds(series: pd.Series, probs: list[float]) -> list[float]:
    clean = series.dropna()
    if clean.empty:
        return []
    return sorted({round(float(clean.quantile(prob)), 6) for prob in probs})


def normalize_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    normalized = trades_df.copy()
    normalized["session_date"] = pd.to_datetime(normalized["session_date"]).dt.normalize()
    normalized["signal_time"] = pd.to_datetime(normalized["signal_time"])
    normalized["signal_bar_time"] = normalized["signal_time"].dt.floor("min")
    normalized["entry_hour"] = normalized["signal_time"].dt.hour
    return normalized


def evaluate_candidate(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    train_dates: set[pd.Timestamp],
    test_dates: set[pd.Timestamp],
    name: str,
    family: str,
    config: dict[str, Any],
    allow_entry: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    trades_df, _ = run_backtest(dataset, params, trade_dates, entry_filter=allow_entry)
    trades_df = normalize_trades(trades_df)
    result: dict[str, Any] = {"name": name, "family": family, "config": config}
    for prefix, values in perf_by_split(trades_df, train_dates, test_dates).items():
        for key, value in values.items():
            result[f"{prefix}_{key}"] = value
    return result


def atr_candidate_specs(baseline_trade_features: pd.DataFrame, train_dates: set[pd.Timestamp]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    train_mask = baseline_trade_features["session_date"].isin(train_dates)
    for period in (10, 20, 30):
        column = f"signal_atr_current_{period}"
        thresholds = quantile_thresholds(
            baseline_trade_features.loc[train_mask, column],
            probs=[0.20, 0.35, 0.50, 0.65, 0.80],
        )
        for threshold in thresholds:
            specs.append(
                {
                    "name": f"atr_min_p{period}_ge_{threshold:g}",
                    "family": "atr_volatility",
                    "config": {"period": period, "mode": "min", "threshold": float(threshold)},
                }
            )
        for threshold in thresholds[-3:]:
            specs.append(
                {
                    "name": f"atr_max_p{period}_le_{threshold:g}",
                    "family": "atr_volatility",
                    "config": {"period": period, "mode": "max", "threshold": float(threshold)},
                }
            )
    return specs


def rsi_divergence_specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for lookback in (5, 10, 15):
        for min_delta in (0.0, 2.5, 5.0):
            specs.append(
                {
                    "name": f"rsi_div_lb{lookback}_delta_{min_delta:g}",
                    "family": "rsi_divergence",
                    "config": {"lookback": lookback, "min_rsi_delta": float(min_delta)},
                }
            )
    return specs


def time_window_specs() -> list[dict[str, Any]]:
    windows = [
        (10, 14),
        (11, 15),
        (10, 13),
        (11, 14),
        (12, 15),
        (10, 12),
    ]
    return [
        {
            "name": f"time_window_{start}_{end}",
            "family": "time_of_day",
            "config": {"start_hour": start, "end_hour": end},
        }
        for start, end in windows
    ]


def build_allow_entry(feature_frame: pd.DataFrame, spec: dict[str, Any]) -> Callable[[dict[str, Any]], bool]:
    family = spec["family"]
    config = spec["config"]

    atr_arrays = {
        10: feature_frame["atr_current_10"].to_numpy(dtype=float),
        20: feature_frame["atr_current_20"].to_numpy(dtype=float),
        30: feature_frame["atr_current_30"].to_numpy(dtype=float),
    }
    price_delta_arrays = {
        5: feature_frame["price_delta_lb5"].to_numpy(dtype=float),
        10: feature_frame["price_delta_lb10"].to_numpy(dtype=float),
        15: feature_frame["price_delta_lb15"].to_numpy(dtype=float),
    }
    rsi_delta_arrays = {
        5: feature_frame["rsi_delta_lb5"].to_numpy(dtype=float),
        10: feature_frame["rsi_delta_lb10"].to_numpy(dtype=float),
        15: feature_frame["rsi_delta_lb15"].to_numpy(dtype=float),
    }

    def allow_entry(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        direction = int(context["direction"])

        if family == "atr_volatility":
            value = atr_arrays[int(config["period"])][idx]
            if not np.isfinite(value):
                return False
            threshold = float(config["threshold"])
            if config["mode"] == "min":
                return value >= threshold
            return value <= threshold

        if family == "rsi_divergence":
            lookback = int(config["lookback"])
            min_delta = float(config["min_rsi_delta"])
            price_delta = price_delta_arrays[lookback][idx]
            rsi_delta = rsi_delta_arrays[lookback][idx]
            if not np.isfinite(price_delta) or not np.isfinite(rsi_delta):
                return False
            if direction == 1:
                return price_delta < 0.0 and rsi_delta >= min_delta
            return price_delta > 0.0 and rsi_delta <= -min_delta

        if family == "time_of_day":
            hour = int(context["entry_hour"])
            return int(config["start_hour"]) <= hour <= int(config["end_hour"])

        return True

    return allow_entry


def build_hourly_analysis(trades_df: pd.DataFrame, train_dates: set[pd.Timestamp], test_dates: set[pd.Timestamp]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hour, group in trades_df.groupby("entry_hour"):
        row = {"entry_hour": int(hour)}
        for prefix, date_set in (("train", train_dates), ("test", test_dates), ("all", train_dates | test_dates)):
            scoped = group[group["session_date"].isin(date_set)].copy()
            pnl = scoped["pnl_brl"].astype(float) if not scoped.empty else pd.Series(dtype=float)
            gross_profit = float(pnl[pnl > 0.0].sum())
            gross_loss = float(-pnl[pnl < 0.0].sum())
            row[f"{prefix}_trades"] = int(len(scoped))
            row[f"{prefix}_net_profit_brl"] = float(pnl.sum())
            row[f"{prefix}_avg_profit_brl"] = float(pnl.mean()) if len(pnl) else 0.0
            row[f"{prefix}_profit_factor"] = float(gross_profit / gross_loss) if gross_loss > 0.0 else float("inf")
            row[f"{prefix}_win_rate"] = float((pnl > 0.0).mean()) if len(pnl) else 0.0
        rows.append(row)
    return sorted(rows, key=lambda item: item["entry_hour"])


def write_time_preset(output_dir: Path, start_hour: int, end_hour: int) -> str:
    preset_dir = output_dir / "prepared_presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    preset_path = preset_dir / f"WDO Stalker Strategy v10.1 Time Window {start_hour}-{end_hour} GPT 5.4.set"
    contents = f"""\
; prepared from Python screening on top of the robust v10.1 baseline
ContractsPerTrade=1.0||1.0||0.100000||10.000000||N
FilterAsPercOfContractMARange=0.3||0.3||0.030000||3.000000||N
NumDaysToConsiderPreviousContractMARange=5||5||1||50||N
RetracementLevel=0.25||0.25||0.025000||2.500000||N
EntryStart_Hour={start_hour}||{start_hour}||1||100||N
EntryStart_Minute=0||0||1||10||N
LastEntry_Hour={end_hour}||{end_hour}||1||150||N
LastEntry_Minute=0||0||1||10||N
AllowMonday=true||false||0||true||N
AllowTuesday=true||false||0||true||N
AllowWednesday=true||false||0||true||N
AllowThursday=true||false||0||true||N
AllowFriday=true||false||0||true||N
TrendEfficiencyWindowMinutes=15||15||1||60||N
ApplyTrendEfficiencyFilterToLongs=true||false||0||true||N
ApplyTrendEfficiencyFilterToShorts=false||false||0||true||N
MinDirectionalTrendEfficiency15m=0.333333||0.333333||0.033333||3.333330||N
VolumeWindowMinutes=30||30||1||120||N
ApplyVolumeFilterToLongs=false||false||0||true||N
ApplyVolumeFilterToShorts=true||false||0||true||N
MinSignalVolumeWindowSum=30000.0||30000.0||3000.000000||300000.000000||N
RelativeVolumeLookbackDays=20||20||1||120||N
ApplyRelativeVolumeFilterToLongs=false||false||0||true||N
ApplyRelativeVolumeFilterToShorts=false||false||0||true||N
MinRelativeVolumeAtTime=0.0||0.0||0.050000||5.000000||N
SL_ATRMultiplier=0.78||0.78||0.078000||7.800000||N
TP_ATRMultiplier=0.36||0.36||0.036000||3.600000||N
ATRTimeFrame=15||0||0||49153||N
ATR_Length=20||20||1||200||N
MarketClose_Hour=18||18||1||180||N
MarketClose_Minute=0||0||1||10||N
MinutesBeforeMarketCloseToClosePositions=5||5||1||50||N
"""
    preset_path.write_text(contents, encoding="utf-8")
    return str(preset_path.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen next-indicator candidates for Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(args.data_path or locate_data_file())
    params = robust_baseline_params()
    trade_dates = dataset.trade_dates
    train_dates_idx, test_dates_idx = split_dates(trade_dates, args.train_ratio)
    train_dates = set(pd.Timestamp(date).normalize() for date in train_dates_idx)
    test_dates = set(pd.Timestamp(date).normalize() for date in test_dates_idx)

    feature_frame = attach_bar_features(dataset)
    baseline_trades, baseline_metrics = run_backtest(dataset, params, trade_dates)
    baseline_trades = normalize_trades(baseline_trades)
    baseline_trade_features = baseline_trades.join(feature_frame.add_prefix("signal_"), on="signal_bar_time")

    baseline_result = {"name": "robust_baseline", "family": "baseline", "config": {}}
    for prefix, values in perf_by_split(baseline_trades, train_dates, test_dates).items():
        for key, value in values.items():
            baseline_result[f"{prefix}_{key}"] = value

    screening_specs = atr_candidate_specs(baseline_trade_features, train_dates)
    screening_specs.extend(rsi_divergence_specs())
    screening_specs.extend(time_window_specs())

    results = [baseline_result]
    for spec in screening_specs:
        result = evaluate_candidate(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            name=str(spec["name"]),
            family=str(spec["family"]),
            config=dict(spec["config"]),
            allow_entry=build_allow_entry(feature_frame, spec),
        )
        results.append(result)

    results_df = pd.DataFrame(results)
    baseline_test_pf = float(results_df.loc[results_df["name"] == "robust_baseline", "test_profit_factor"].iloc[0])
    baseline_test_net = float(results_df.loc[results_df["name"] == "robust_baseline", "test_net_profit_brl"].iloc[0])
    baseline_test_dd = float(results_df.loc[results_df["name"] == "robust_baseline", "test_max_drawdown_pct"].iloc[0])
    results_df["test_pf_delta"] = results_df["test_profit_factor"] - baseline_test_pf
    results_df["test_net_delta"] = results_df["test_net_profit_brl"] - baseline_test_net
    results_df["test_dd_delta"] = results_df["test_max_drawdown_pct"] - baseline_test_dd
    ranked_df = results_df.sort_values(
        ["test_pf_delta", "test_net_delta", "test_dd_delta"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    hourly_analysis = build_hourly_analysis(baseline_trades, train_dates, test_dates)

    top_by_family: dict[str, dict[str, Any]] = {}
    for family in ("atr_volatility", "rsi_divergence", "time_of_day"):
        family_df = ranked_df[ranked_df["family"] == family]
        if not family_df.empty:
            top_by_family[family] = family_df.iloc[0].to_dict()

    promising_candidates: list[dict[str, Any]] = []
    for row in ranked_df.itertuples(index=False):
        if row.family == "baseline":
            continue
        if float(row.test_pf_delta) <= 0.0:
            continue
        candidate = {
            "name": row.name,
            "family": row.family,
            "config": row.config,
            "test_profit_factor": row.test_profit_factor,
            "test_pf_delta": row.test_pf_delta,
            "test_net_profit_brl": row.test_net_profit_brl,
            "test_net_delta": row.test_net_delta,
            "test_max_drawdown_pct": row.test_max_drawdown_pct,
            "test_dd_delta": row.test_dd_delta,
            "mt5_ready": row.family == "time_of_day",
        }
        if row.family == "time_of_day":
            candidate["prepared_preset"] = write_time_preset(
                args.output_dir,
                int(row.config["start_hour"]),
                int(row.config["end_hour"]),
            )
        promising_candidates.append(candidate)

    summary = {
        "baseline_params": params.__dict__,
        "baseline_metrics": baseline_metrics,
        "train_start": pd.Timestamp(train_dates_idx[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates_idx[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates_idx[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates_idx[-1]).date().isoformat(),
        "library_availability": {"ta": True, "talib": False, "pandas_ta": False},
        "top_by_family": top_by_family,
        "overall_top_candidates": ranked_df.head(12).to_dict(orient="records"),
        "promising_candidates": promising_candidates,
        "hourly_analysis": hourly_analysis,
    }

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.output_dir / "screen_results.json").write_text(ranked_df.to_json(orient="records", indent=2), encoding="utf-8")
    (args.output_dir / "hourly_analysis.json").write_text(json.dumps(hourly_analysis, indent=2), encoding="utf-8")
    (args.output_dir / "promising_mt5_candidates.json").write_text(
        json.dumps(promising_candidates, indent=2),
        encoding="utf-8",
    )
    ranked_df.to_csv(args.output_dir / "screen_results.csv", index=False)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
