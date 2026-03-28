from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import V101Params, _ensure_signal_strength_cache, run_backtest
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_optimization_screening")
PRESET_DIR = Path(r"C:\Dev\autoresearch-tradebot\mt5\profiles\tester")


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    family: str
    config: dict[str, Any]
    mt5_supported: bool = False


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


def perf(trades_df: pd.DataFrame) -> dict[str, float]:
    pnl = trades_df["pnl_brl"].astype(float) if not trades_df.empty else pd.Series(dtype=float)
    gross_profit = float(pnl[pnl > 0.0].sum())
    gross_loss = float(-pnl[pnl < 0.0].sum())
    equity = 10_000.0 + pnl.cumsum()
    max_dd_pct = 0.0
    if not equity.empty:
        rolling_peak = equity.cummax()
        drawdown = (equity - rolling_peak) / rolling_peak
        max_dd_pct = float(-drawdown.min() * 100.0)
    return {
        "trades": int(len(trades_df)),
        "net_profit_brl": float(pnl.sum()),
        "avg_profit_brl": float(pnl.mean()) if len(pnl) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss > 0.0 else float("inf"),
        "win_rate": float((pnl > 0.0).mean()) if len(pnl) else 0.0,
        "max_drawdown_pct": max_dd_pct,
    }


def perf_by_split(
    trades_df: pd.DataFrame,
    train_dates: set[pd.Timestamp],
    test_dates: set[pd.Timestamp],
) -> dict[str, Any]:
    train_df = trades_df[trades_df["session_date"].isin(train_dates)].copy()
    test_df = trades_df[trades_df["session_date"].isin(test_dates)].copy()
    return {
        "all": perf(trades_df),
        "train": perf(train_df),
        "test": perf(test_df),
    }


def normalize_trade_dates(trades_df: pd.DataFrame) -> pd.DataFrame:
    frame = trades_df.copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["signal_time"] = pd.to_datetime(frame["signal_time"])
    frame["entry_time"] = pd.to_datetime(frame["entry_time"])
    frame["exit_time"] = pd.to_datetime(frame["exit_time"])
    frame["entry_hour"] = frame["signal_time"].dt.hour
    return frame


def safe_float(value: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return float(value)


def evaluate_candidate(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    train_dates: set[pd.Timestamp],
    test_dates: set[pd.Timestamp],
    spec: CandidateSpec,
    entry_filter: Callable[[dict[str, Any]], bool] | None,
) -> dict[str, Any]:
    trades_df, _ = run_backtest(dataset, params, trade_dates, entry_filter=entry_filter)
    trades_df = normalize_trade_dates(trades_df)
    result = {
        "name": spec.name,
        "family": spec.family,
        "config": spec.config,
        "mt5_supported": bool(spec.mt5_supported),
    }
    for prefix, values in perf_by_split(trades_df, train_dates, test_dates).items():
        for key, value in values.items():
            result[f"{prefix}_{key}"] = safe_float(value)
    return result


def make_relative_volume_filter(
    dataset: V10Dataset,
    params: V101Params,
    lookback_days: int,
    threshold: float,
    apply_side: str,
) -> Callable[[dict[str, Any]], bool]:
    cache = _ensure_signal_strength_cache(
        dataset=dataset,
        trend_window=int(params.TrendEfficiencyWindowMinutes),
        volume_window=int(params.VolumeWindowMinutes),
        relative_volume_lookback=int(lookback_days),
    )
    relvol = cache["relative_volume"]

    def allow(context: dict[str, Any]) -> bool:
        direction = int(context["direction"])
        if apply_side == "long" and direction != 1:
            return True
        if apply_side == "short" and direction != -1:
            return True
        idx = int(context["dataset_index"])
        value = float(relvol[idx])
        return bool(np.isfinite(value) and value >= float(threshold))

    return allow


def make_atr_range_filter(
    atr_array: np.ndarray,
    min_value: float,
    max_value: float,
) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        value = float(atr_array[idx])
        return bool(np.isfinite(value) and value >= float(min_value) and value <= float(max_value))

    return allow


def make_rsi_confirmation_filter(
    rsi_array: np.ndarray,
    threshold: float,
) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        value = float(rsi_array[idx])
        if not np.isfinite(value):
            return False
        direction = int(context["direction"])
        if direction == 1:
            return value >= float(threshold)
        return value <= float(100.0 - threshold)

    return allow


def make_time_window_filter(
    start_hour: int,
    end_hour: int,
) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        hour = int(context["entry_hour"])
        return int(start_hour) <= hour <= int(end_hour)

    return allow


def quantiles_from_signal_bars(
    signal_feature_frame: pd.DataFrame,
    train_dates: set[pd.Timestamp],
    column: str,
    probs: list[float],
) -> list[float]:
    sample = signal_feature_frame.loc[
        signal_feature_frame["session_date"].isin(train_dates),
        column,
    ].dropna()
    if sample.empty:
        return []
    return sorted({round(float(sample.quantile(prob)), 6) for prob in probs})


def build_signal_feature_frame(
    dataset: V10Dataset,
    baseline_trades: pd.DataFrame,
) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    bars["atr_10"] = dataset.get_atr_current(10)
    bars["atr_14"] = dataset.get_atr_current(14)
    bars["atr_20"] = dataset.get_atr_current(20)

    rsi7 = RSIIndicator(close=bars["Close"], window=7).rsi()
    rsi14 = RSIIndicator(close=bars["Close"], window=14).rsi()
    bars["rsi_7_prev"] = rsi7.shift(1)
    bars["rsi_14_prev"] = rsi14.shift(1)
    bars["entry_hour"] = bars.index.hour
    bars["signal_bar_time"] = bars.index.floor("min")

    signal_frame = normalize_trade_dates(baseline_trades)[["session_date", "signal_time", "entry_hour"]].copy()
    signal_frame["signal_bar_time"] = signal_frame["signal_time"].dt.floor("min")
    joined = signal_frame.join(
        bars[
            [
                "signal_bar_time",
                "atr_10",
                "atr_14",
                "atr_20",
                "rsi_7_prev",
                "rsi_14_prev",
            ]
        ].set_index("signal_bar_time"),
        on="signal_bar_time",
    )
    return joined


def analyze_hours(trades_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for hour, hour_df in trades_df.groupby("entry_hour", sort=True):
        metrics = perf(hour_df)
        rows.append(
            {
                "entry_hour": int(hour),
                **metrics,
            }
        )
    return pd.DataFrame(rows).sort_values("entry_hour").reset_index(drop=True)


def set_line(name: str, value: Any) -> str:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
        return f"{name}={rendered}||false||0||true||N"
    if isinstance(value, int):
        return f"{name}={value}||{value}||1||1000||N"
    if isinstance(value, float):
        return f"{name}={value:.6f}||{value:.6f}||0.050000||100000.000000||N"
    return f"{name}={value}"


def render_preset(params: dict[str, Any]) -> str:
    lines = [
        "; generated by stalker_v10_1_optimization_screening.py",
        "; Position Sizing",
        set_line("ContractsPerTrade", params["ContractsPerTrade"]),
        "; Filter",
        set_line("FilterAsPercOfContractMARange", params["FilterAsPercOfContractMARange"]),
        set_line("NumDaysToConsiderPreviousContractMARange", params["NumDaysToConsiderPreviousContractMARange"]),
        "; Open Signal",
        set_line("RetracementLevel", params["RetracementLevel"]),
        "; Entry Filters",
        set_line("EntryStart_Hour", params["EntryStart_Hour"]),
        set_line("EntryStart_Minute", params["EntryStart_Minute"]),
        set_line("LastEntry_Hour", params["LastEntry_Hour"]),
        set_line("LastEntry_Minute", params["LastEntry_Minute"]),
        set_line("SkipWednesday", params["SkipWednesday"]),
        set_line("SkipShortWednesday", params.get("SkipShortWednesday", False)),
        set_line("SkipHour13", params["SkipHour13"]),
        set_line("SkipHour14", params.get("SkipHour14", False)),
        set_line("AllowMonday", params["AllowMonday"]),
        set_line("AllowTuesday", params["AllowTuesday"]),
        set_line("AllowWednesday", params["AllowWednesday"]),
        set_line("AllowThursday", params["AllowThursday"]),
        set_line("AllowFriday", params["AllowFriday"]),
        "; Signal Strength Filters",
        set_line("TrendEfficiencyWindowMinutes", params["TrendEfficiencyWindowMinutes"]),
        set_line("ApplyTrendEfficiencyFilterToLongs", params["ApplyTrendEfficiencyFilterToLongs"]),
        set_line("ApplyTrendEfficiencyFilterToShorts", params["ApplyTrendEfficiencyFilterToShorts"]),
        set_line("MinDirectionalTrendEfficiency15m", params["MinDirectionalTrendEfficiency15m"]),
        set_line("VolumeWindowMinutes", params["VolumeWindowMinutes"]),
        set_line("ApplyVolumeFilterToLongs", params["ApplyVolumeFilterToLongs"]),
        set_line("ApplyVolumeFilterToShorts", params["ApplyVolumeFilterToShorts"]),
        set_line("MinSignalVolumeWindowSum", params["MinSignalVolumeWindowSum"]),
        set_line("RelativeVolumeLookbackDays", params["RelativeVolumeLookbackDays"]),
        set_line("ApplyRelativeVolumeFilterToLongs", params["ApplyRelativeVolumeFilterToLongs"]),
        set_line("ApplyRelativeVolumeFilterToShorts", params["ApplyRelativeVolumeFilterToShorts"]),
        set_line("MinRelativeVolumeAtTime", params["MinRelativeVolumeAtTime"]),
        "; Risk Management",
        set_line("SL_ATRMultiplier", params["SL_ATRMultiplier"]),
        set_line("TP_ATRMultiplier", params["TP_ATRMultiplier"]),
        set_line("ATRTimeFrame", params["ATRTimeFrame"]),
        set_line("ATR_Length", params["ATR_Length"]),
        "; Market Info",
        set_line("MarketClose_Hour", params["MarketClose_Hour"]),
        set_line("MarketClose_Minute", params["MarketClose_Minute"]),
        set_line("MinutesBeforeMarketCloseToClosePositions", params["MinutesBeforeMarketCloseToClosePositions"]),
        "",
    ]
    return "\n".join(lines)


def build_mt5_preset_params(
    baseline: V101Params,
    spec: CandidateSpec,
) -> dict[str, Any] | None:
    params = asdict(baseline)
    if spec.family == "relative_volume":
        side = str(spec.config["apply_side"])
        params["RelativeVolumeLookbackDays"] = int(spec.config["lookback_days"])
        params["ApplyRelativeVolumeFilterToLongs"] = side in {"long", "both"}
        params["ApplyRelativeVolumeFilterToShorts"] = side in {"short", "both"}
        params["MinRelativeVolumeAtTime"] = float(spec.config["threshold"])
        return params
    if spec.family == "time_of_day":
        params["EntryStart_Hour"] = int(spec.config["start_hour"])
        params["LastEntry_Hour"] = int(spec.config["end_hour"])
        return params
    return None


def write_supported_presets(
    baseline: V101Params,
    candidates: list[dict[str, Any]],
    preset_dir: Path,
    top_n: int,
) -> list[dict[str, Any]]:
    preset_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for row in candidates:
        if len(written) >= top_n:
            break
        if not bool(row.get("mt5_supported")):
            continue
        spec = CandidateSpec(
            name=str(row["name"]),
            family=str(row["family"]),
            config=dict(row["config"]),
            mt5_supported=True,
        )
        preset_params = build_mt5_preset_params(baseline, spec)
        if preset_params is None:
            continue
        preset_name = f"WDO Stalker Strategy v10.1 {spec.name} GPT 5.4.set"
        if preset_name in seen_names:
            continue
        preset_path = preset_dir / preset_name
        preset_path.write_text(render_preset(preset_params), encoding="utf-8")
        seen_names.add(preset_name)
        written.append(
            {
                "name": spec.name,
                "family": spec.family,
                "path": str(preset_path.resolve()),
            }
        )
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Systematic Python screening for Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--top-presets", type=int, default=5)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(args.data_path or locate_data_file())
    baseline = robust_baseline_params()
    trade_dates = dataset.trade_dates
    train_dates_idx, test_dates_idx = split_dates(trade_dates, args.train_ratio)
    train_dates = set(pd.Timestamp(date).normalize() for date in train_dates_idx)
    test_dates = set(pd.Timestamp(date).normalize() for date in test_dates_idx)

    baseline_trades, _ = run_backtest(dataset, baseline, trade_dates)
    baseline_trades = normalize_trade_dates(baseline_trades)
    baseline_metrics = perf_by_split(baseline_trades, train_dates, test_dates)
    signal_feature_frame = build_signal_feature_frame(dataset, baseline_trades)
    hourly_df = analyze_hours(baseline_trades)

    results: list[dict[str, Any]] = []
    results.append(
        {
            "name": "baseline_robust_combo",
            "family": "baseline",
            "config": asdict(baseline),
            "mt5_supported": True,
            **{f"{prefix}_{key}": safe_float(value) for prefix, values in baseline_metrics.items() for key, value in values.items()},
        }
    )

    # Relative-volume variations layered on the robust baseline.
    for apply_side in ("short", "both"):
        for lookback_days in (20, 40, 60):
            for threshold in (0.75, 0.85, 0.95):
                spec = CandidateSpec(
                    name=f"relvol_{apply_side}_lb{lookback_days}_ge_{threshold:.2f}".replace(".", "_"),
                    family="relative_volume",
                    config={
                        "apply_side": apply_side,
                        "lookback_days": int(lookback_days),
                        "threshold": float(threshold),
                    },
                    mt5_supported=True,
                )
                result = evaluate_candidate(
                    dataset=dataset,
                    params=baseline,
                    trade_dates=trade_dates,
                    train_dates=train_dates,
                    test_dates=test_dates,
                    spec=spec,
                    entry_filter=make_relative_volume_filter(dataset, baseline, lookback_days, threshold, apply_side),
                )
                results.append(result)

    # ATR volatility: keep entries only when ATR is inside a train-derived "normal" band.
    bars = dataset.bars_m1
    atr_arrays = {
        10: dataset.get_atr_current(10),
        14: dataset.get_atr_current(14),
        20: dataset.get_atr_current(20),
    }
    atr_signal_sample = signal_feature_frame.copy()
    atr_quantile_bands = ((0.20, 0.80), (0.25, 0.75), (0.30, 0.70))
    for period, column in ((10, "atr_10"), (14, "atr_14"), (20, "atr_20")):
        sample = atr_signal_sample.loc[atr_signal_sample["session_date"].isin(train_dates), column].dropna()
        if sample.empty:
            continue
        atr_array = atr_arrays[period]
        for low_q, high_q in atr_quantile_bands:
            min_value = float(sample.quantile(low_q))
            max_value = float(sample.quantile(high_q))
            spec = CandidateSpec(
                name=f"atr_normal_p{period}_q{int(low_q*100)}_{int(high_q*100)}",
                family="atr_volatility",
                config={
                    "period": int(period),
                    "min_atr": min_value,
                    "max_atr": max_value,
                    "low_quantile": float(low_q),
                    "high_quantile": float(high_q),
                },
                mt5_supported=False,
            )
            results.append(
                evaluate_candidate(
                    dataset=dataset,
                    params=baseline,
                    trade_dates=trade_dates,
                    train_dates=train_dates,
                    test_dates=test_dates,
                    spec=spec,
                    entry_filter=make_atr_range_filter(atr_array, min_value, max_value),
                )
            )

    # RSI directional confirmation.
    rsi_arrays = {
        7: bars["Close"].pipe(lambda s: RSIIndicator(close=s, window=7).rsi().shift(1)).to_numpy(dtype=float),
        14: bars["Close"].pipe(lambda s: RSIIndicator(close=s, window=14).rsi().shift(1)).to_numpy(dtype=float),
    }
    for period, rsi_array in rsi_arrays.items():
        for threshold in (50.0, 55.0, 60.0):
            spec = CandidateSpec(
                name=f"rsi_confirm_p{period}_thr{int(threshold)}",
                family="rsi_confirmation",
                config={
                    "period": int(period),
                    "threshold": float(threshold),
                },
                mt5_supported=False,
            )
            results.append(
                evaluate_candidate(
                    dataset=dataset,
                    params=baseline,
                    trade_dates=trade_dates,
                    train_dates=train_dates,
                    test_dates=test_dates,
                    spec=spec,
                    entry_filter=make_rsi_confirmation_filter(rsi_array, threshold),
                )
            )

    # Time-of-day: evaluate all contiguous windows inside the current 10-15 range.
    for start_hour in range(10, 16):
        for end_hour in range(start_hour, 16):
            if start_hour == 10 and end_hour == 15:
                continue
            if (end_hour - start_hour) < 1:
                continue
            spec = CandidateSpec(
                name=f"time_window_{start_hour}_{end_hour}",
                family="time_of_day",
                config={
                    "start_hour": int(start_hour),
                    "end_hour": int(end_hour),
                },
                mt5_supported=True,
            )
            results.append(
                evaluate_candidate(
                    dataset=dataset,
                    params=baseline,
                    trade_dates=trade_dates,
                    train_dates=train_dates,
                    test_dates=test_dates,
                    spec=spec,
                    entry_filter=make_time_window_filter(start_hour, end_hour),
                )
            )

    results_df = pd.DataFrame(results)
    base_row = results_df.loc[results_df["name"] == "baseline_robust_combo"].iloc[0]
    for prefix in ("all", "train", "test"):
        results_df[f"{prefix}_pf_delta"] = results_df[f"{prefix}_profit_factor"] - float(base_row[f"{prefix}_profit_factor"])
        results_df[f"{prefix}_net_delta"] = results_df[f"{prefix}_net_profit_brl"] - float(base_row[f"{prefix}_net_profit_brl"])
        results_df[f"{prefix}_dd_delta"] = results_df[f"{prefix}_max_drawdown_pct"] - float(base_row[f"{prefix}_max_drawdown_pct"])

    ranked_df = results_df.sort_values(
        ["test_pf_delta", "test_net_delta", "test_dd_delta"],
        ascending=[False, False, True],
    ).reset_index(drop=True)

    top_by_family = {
        family: ranked_df[ranked_df["family"] == family].head(5).to_dict(orient="records")
        for family in ranked_df["family"].unique()
    }
    supported_candidates = ranked_df[
        (ranked_df["family"] != "baseline") & ranked_df["mt5_supported"]
    ].to_dict(orient="records")
    written_presets = write_supported_presets(
        baseline=baseline,
        candidates=supported_candidates,
        preset_dir=PRESET_DIR,
        top_n=args.top_presets,
    )

    summary = {
        "data_source": str(dataset.bars_m1.attrs.get("source_path", "")),
        "baseline_name": "baseline_robust_combo",
        "baseline_params": asdict(baseline),
        "baseline_metrics": {
            prefix: {key: safe_float(value) for key, value in values.items()}
            for prefix, values in baseline_metrics.items()
        },
        "train_start": pd.Timestamp(train_dates_idx[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates_idx[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates_idx[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates_idx[-1]).date().isoformat(),
        "library_availability": {
            "ta": True,
            "talib": False,
            "pandas_ta": False,
        },
        "top_overall": ranked_df.head(20).to_dict(orient="records"),
        "top_by_family": top_by_family,
        "written_presets": written_presets,
    }

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.output_dir / "candidate_results.json").write_text(
        json.dumps(ranked_df.to_dict(orient="records"), indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "hourly_analysis.json").write_text(
        json.dumps(hourly_df.to_dict(orient="records"), indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
