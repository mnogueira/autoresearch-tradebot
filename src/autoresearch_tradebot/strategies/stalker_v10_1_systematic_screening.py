from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_systematic_screening")
DEFAULT_LEADERBOARD_PATH = artifact_output_dir("..", "leaderboard.json")


def robust_base_params() -> V101Params:
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


def rawbest_core_params() -> V101Params:
    return V101Params(
        TrendEfficiencyWindowMinutes=15,
        ApplyTrendEfficiencyFilterToLongs=True,
        ApplyTrendEfficiencyFilterToShorts=True,
        MinDirectionalTrendEfficiency15m=0.333333,
        VolumeWindowMinutes=15,
        ApplyVolumeFilterToLongs=True,
        ApplyVolumeFilterToShorts=False,
        MinSignalVolumeWindowSum=50000.0,
    )


def split_metric_bundle(
    trades_df: pd.DataFrame,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> dict[str, Any]:
    if trades_df.empty:
        train_df = trades_df
        test_df = trades_df
    else:
        enriched = trades_df.assign(session_date=pd.to_datetime(trades_df["session_date"]).dt.normalize())
        train_df = enriched[enriched["session_date"].isin(pd.Index(pd.to_datetime(train_dates)))]
        test_df = enriched[enriched["session_date"].isin(pd.Index(pd.to_datetime(test_dates)))]

    return {
        "all": calculate_metrics(trades_df, pd.Index(pd.to_datetime(train_dates).tolist() + pd.to_datetime(test_dates).tolist())),
        "train": calculate_metrics(train_df, train_dates),
        "test": calculate_metrics(test_df, test_dates),
    }


def metric_record(
    *,
    family: str,
    name: str,
    screening_method: str,
    mt5_ready: bool,
    params: dict[str, Any] | None,
    spec: dict[str, Any] | None,
    metrics: dict[str, Any],
    notes: str = "",
    preset_name: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "family": family,
        "name": name,
        "screening_method": screening_method,
        "mt5_ready": bool(mt5_ready),
        "params": params,
        "spec": spec,
        "notes": notes,
    }
    if preset_name is not None:
        record["preset_name"] = preset_name
    for prefix, values in metrics.items():
        for key, value in values.items():
            record[f"{prefix}_{key}"] = value
    return record


def quantile_values(series: pd.Series, probs: list[float]) -> list[float]:
    clean = series.dropna().astype(float)
    if clean.empty:
        return []
    return sorted({round(float(clean.quantile(prob)), 6) for prob in probs})


def rolling_session_sum(values: pd.Series, session_key: pd.Series, window: int) -> pd.Series:
    min_periods = max(3, min(int(window), 10))
    return values.groupby(session_key).transform(
        lambda series: series.rolling(int(window), min_periods=min_periods).sum()
    )


def rolling_same_minute_mean(values: pd.Series, minute_of_day: pd.Index, lookback: int) -> pd.Series:
    min_periods = max(3, min(int(lookback), 10))
    return values.groupby(minute_of_day).transform(
        lambda series: series.rolling(int(lookback), min_periods=min_periods).mean().shift(1)
    )


def build_indicator_frame(dataset: V10Dataset, base_params: V101Params) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    session_key = bars["session_date"]
    minute_of_day = pd.Index((bars.index.hour * 60) + bars.index.minute)

    frame = pd.DataFrame(index=bars.index)
    frame["session_date"] = bars["session_date"]
    frame["entry_hour"] = bars.index.hour
    frame["minute_of_day"] = minute_of_day
    frame["signal_range"] = dataset.get_signal_range(
        base_params.FilterAsPercOfContractMARange,
        base_params.NumDaysToConsiderPreviousContractMARange,
    )

    for period in (10, 14, 20, 30):
        atr_values = dataset.get_atr_current(period)
        frame[f"atr_{period}"] = atr_values
        frame[f"atr_to_range_{period}"] = atr_values / frame["signal_range"].replace(0.0, np.nan)

    prev_close = bars.groupby("session_date")["Close"].shift(1)
    rsi_prev = RSIIndicator(close=bars["Close"], window=14).rsi().groupby(session_key).shift(1)
    frame["rsi_14_prev"] = rsi_prev
    frame["prev_close"] = prev_close

    atr_norm = frame["atr_20"].replace(0.0, np.nan)
    for lookback in (5, 10, 15):
        price_move = prev_close - bars.groupby("session_date")["Close"].shift(lookback + 1)
        rsi_move = rsi_prev - rsi_prev.groupby(session_key).shift(lookback)
        frame[f"rsi_divergence_proxy_{lookback}"] = (rsi_move / 10.0) - (price_move / atr_norm)

    volume_prev = bars.groupby("session_date")["Volume"].shift(1)
    for volume_window in (15, 30):
        signal_volume_sum = rolling_session_sum(volume_prev, session_key, volume_window)
        for lookback in (20, 40, 60):
            expected_same_time = rolling_same_minute_mean(signal_volume_sum, minute_of_day, lookback)
            frame[f"relvol_v{volume_window}_lb{lookback}"] = signal_volume_sum / expected_same_time.replace(
                0.0, np.nan
            )

    return frame


def attach_signal_features(trades_df: pd.DataFrame, indicator_frame: pd.DataFrame) -> pd.DataFrame:
    enriched = trades_df.copy()
    enriched["session_date"] = pd.to_datetime(enriched["session_date"]).dt.normalize()
    enriched["signal_time"] = pd.to_datetime(enriched["signal_time"])
    enriched["signal_bar_time"] = enriched["signal_time"].dt.floor("min")
    enriched["direction_sign"] = np.where(enriched["direction"].eq("long"), 1.0, -1.0)
    enriched["entry_hour"] = enriched["signal_time"].dt.hour
    enriched = enriched.join(indicator_frame.add_prefix("signal_"), on="signal_bar_time")
    return enriched


def keep_mask_metrics(
    trades_df: pd.DataFrame,
    keep_mask: pd.Series,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> dict[str, Any]:
    kept = trades_df[keep_mask.fillna(False)].copy()
    return split_metric_bundle(kept, train_dates, test_dates)


def run_parameter_candidate(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    trades_df, _ = run_backtest(dataset, params, trade_dates)
    return trades_df, split_metric_bundle(trades_df, train_dates, test_dates)


def run_relative_volume_screen(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    baseline_params = robust_base_params()
    _, baseline_metrics = run_parameter_candidate(dataset, baseline_params, trade_dates, train_dates, test_dates)
    results.append(
        metric_record(
            family="relative_volume",
            name="baseline_robust",
            screening_method="integrated_backtest",
            mt5_ready=True,
            params=asdict(baseline_params),
            spec={"core": "robust"},
            metrics=baseline_metrics,
            notes="Current best MT5-facing robust combo baseline",
            preset_name="WDO Stalker Strategy v10.1 EffVol Robust GPT 5.4",
        )
    )

    candidate_cores = [
        ("robust", robust_base_params(), ["short", "both"]),
        ("rawbest", rawbest_core_params(), ["short"]),
    ]
    thresholds = [0.75, 0.85, 0.95, 1.05]
    lookbacks = [20, 40, 60]

    for core_name, core_params, modes in candidate_cores:
        for mode in modes:
            for lookback in lookbacks:
                for threshold in thresholds:
                    relvol_longs = mode in {"long", "both"}
                    relvol_shorts = mode in {"short", "both"}
                    params = V101Params(
                        **{
                            **asdict(core_params),
                            "RelativeVolumeLookbackDays": int(lookback),
                            "ApplyRelativeVolumeFilterToLongs": bool(relvol_longs),
                            "ApplyRelativeVolumeFilterToShorts": bool(relvol_shorts),
                            "MinRelativeVolumeAtTime": float(threshold),
                        }
                    )
                    _, metrics = run_parameter_candidate(dataset, params, trade_dates, train_dates, test_dates)
                    results.append(
                        metric_record(
                            family="relative_volume",
                            name=f"{core_name}_relvol_{mode}_lb{lookback}_ge_{threshold:g}",
                            screening_method="integrated_backtest",
                            mt5_ready=True,
                            params=asdict(params),
                            spec={"core": core_name, "mode": mode, "lookback": lookback, "threshold": threshold},
                            metrics=metrics,
                            notes="Relative volume variation on top of a fixed core parameter set",
                        )
                    )
    return results


def run_atr_screen(
    trade_features: pd.DataFrame,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    train_mask = trade_features["session_date"].isin(pd.Index(pd.to_datetime(train_dates)))
    for period in (10, 14, 20, 30):
        column = f"signal_atr_to_range_{period}"
        train_series = trade_features.loc[train_mask, column]
        thresholds = quantile_values(train_series, probs=[0.25, 0.50, 0.75])
        for mode in ("ge", "le"):
            for threshold in thresholds:
                if mode == "ge":
                    keep_mask = trade_features[column] >= threshold
                else:
                    keep_mask = trade_features[column] <= threshold
                metrics = keep_mask_metrics(trade_features, keep_mask, train_dates, test_dates)
                results.append(
                    metric_record(
                        family="atr_volatility",
                        name=f"atr_ratio_p{period}_{mode}_{threshold:g}",
                        screening_method="trade_mask_prescreen",
                        mt5_ready=False,
                        params=None,
                        spec={"period": period, "mode": mode, "threshold": threshold, "column": column},
                        metrics=metrics,
                        notes="Python-side prescreen on baseline trades; MT5 EA support not added yet",
                    )
                )
        summary_rows.append(
            {
                "period": period,
                "train_mean": round(float(train_series.mean()), 6),
                "train_median": round(float(train_series.median()), 6),
                "train_p25": round(float(train_series.quantile(0.25)), 6),
                "train_p75": round(float(train_series.quantile(0.75)), 6),
            }
        )
    return results, summary_rows


def run_rsi_divergence_screen(
    trade_features: pd.DataFrame,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    train_mask = trade_features["session_date"].isin(pd.Index(pd.to_datetime(train_dates)))

    for lookback in (5, 10, 15):
        column = f"signal_rsi_divergence_proxy_{lookback}"
        thresholds = quantile_values(trade_features.loc[train_mask, column], probs=[0.65, 0.75, 0.85])
        for threshold in thresholds:
            keep_mask = trade_features[column] >= threshold
            metrics = keep_mask_metrics(trade_features, keep_mask, train_dates, test_dates)
            results.append(
                metric_record(
                    family="rsi_divergence",
                    name=f"rsi_div_proxy_lb{lookback}_ge_{threshold:g}",
                    screening_method="trade_mask_prescreen",
                    mt5_ready=False,
                    params=None,
                    spec={"lookback": lookback, "threshold": threshold, "column": column},
                    metrics=metrics,
                    notes="RSI divergence proxy prescreen using RSI-vs-price disagreement",
                )
            )
    return results


def run_time_of_day_screen(
    dataset: V10Dataset,
    trade_dates: pd.Index,
    train_dates: pd.Index,
    test_dates: pd.Index,
    baseline_trades: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []

    enriched = baseline_trades.copy()
    enriched["signal_time"] = pd.to_datetime(enriched["signal_time"])
    enriched["session_date"] = pd.to_datetime(enriched["session_date"]).dt.normalize()
    enriched["entry_hour"] = enriched["signal_time"].dt.hour

    hourly_rows: list[dict[str, Any]] = []
    for hour in sorted(enriched["entry_hour"].dropna().unique()):
        subset = enriched[enriched["entry_hour"] == hour].copy()
        hourly_rows.append(
            {
                "entry_hour": int(hour),
                "all": calculate_metrics(subset, trade_dates),
                "train": calculate_metrics(subset[subset["session_date"].isin(pd.Index(pd.to_datetime(train_dates)))], train_dates),
                "test": calculate_metrics(subset[subset["session_date"].isin(pd.Index(pd.to_datetime(test_dates)))], test_dates),
            }
        )

    baseline_params = robust_base_params()
    for start_hour in range(10, 16):
        for end_hour in range(start_hour, 16):
            params = V101Params(
                **{
                    **asdict(baseline_params),
                    "EntryStart_Hour": int(start_hour),
                    "EntryStart_Minute": 0,
                    "LastEntry_Hour": int(end_hour),
                    "LastEntry_Minute": 0,
                }
            )
            _, metrics = run_parameter_candidate(dataset, params, trade_dates, train_dates, test_dates)
            results.append(
                metric_record(
                    family="time_of_day",
                    name=f"time_window_{start_hour:02d}00_{end_hour:02d}00",
                    screening_method="integrated_backtest",
                    mt5_ready=True,
                    params=asdict(params),
                    spec={"start_hour": start_hour, "end_hour": end_hour},
                    metrics=metrics,
                    notes="Contiguous entry-window optimization on top of the robust combo",
                )
            )
    return results, hourly_rows


def leaderboard_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        quality_tier = 2 if record["screening_method"] == "integrated_backtest" else 1
        rows.append(
            {
                "family": record["family"],
                "name": record["name"],
                "screening_method": record["screening_method"],
                "quality_tier": quality_tier,
                "mt5_ready": record["mt5_ready"],
                "preset_name": record.get("preset_name"),
                "test_total_trades": record.get("test_total_trades", 0),
                "test_net_profit_brl": record.get("test_net_profit_brl", 0.0),
                "test_profit_factor": record.get("test_profit_factor", 0.0),
                "test_on_tester_value": record.get("test_on_tester_value", 0.0),
                "test_max_drawdown_pct": record.get("test_max_drawdown_pct", 0.0),
                "test_win_rate": record.get("test_win_rate", 0.0),
                "notes": record.get("notes", ""),
            }
        )

    rows.sort(
        key=lambda row: (
            row["quality_tier"],
            row["mt5_ready"],
            row["test_on_tester_value"],
            row["test_profit_factor"],
            row["test_net_profit_brl"],
            -row["test_max_drawdown_pct"],
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Systematic Python-side screening for WDO Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--leaderboard-path", type=Path, default=DEFAULT_LEADERBOARD_PATH)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    data_path = locate_data_file(args.data_path)
    dataset = V10Dataset.from_disk(data_path)
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, args.train_ratio)

    base_params = robust_base_params()
    baseline_trades, baseline_metrics = run_parameter_candidate(dataset, base_params, trade_dates, train_dates, test_dates)
    baseline_record = metric_record(
        family="baseline",
        name="robust_base",
        screening_method="integrated_backtest",
        mt5_ready=True,
        params=asdict(base_params),
        spec={"core": "robust"},
        metrics=baseline_metrics,
        notes="Current robust Stalker v10.1 leader",
        preset_name="WDO Stalker Strategy v10.1 EffVol Robust GPT 5.4",
    )

    indicator_frame = build_indicator_frame(dataset, base_params)
    trade_features = attach_signal_features(baseline_trades, indicator_frame)

    relvol_results = run_relative_volume_screen(dataset, trade_dates, train_dates, test_dates)
    atr_results, atr_summary = run_atr_screen(trade_features, train_dates, test_dates)
    rsi_results = run_rsi_divergence_screen(trade_features, train_dates, test_dates)
    time_results, hourly_rows = run_time_of_day_screen(
        dataset=dataset,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
        baseline_trades=baseline_trades,
    )

    all_records = [baseline_record, *relvol_results, *atr_results, *rsi_results, *time_results]
    leaderboard = leaderboard_rows(all_records)

    dump_json(args.output_dir / "baseline_summary.json", baseline_record)
    dump_json(args.output_dir / "relative_volume_results.json", relvol_results)
    dump_json(args.output_dir / "atr_volatility_results.json", {"summary": atr_summary, "results": atr_results})
    dump_json(args.output_dir / "rsi_divergence_results.json", rsi_results)
    dump_json(args.output_dir / "time_of_day_results.json", {"hourly_analysis": hourly_rows, "window_results": time_results})
    dump_json(
        args.output_dir / "summary.json",
        {
            "data_source": str(data_path),
            "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
            "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
            "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
            "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
            "baseline": baseline_record,
            "top_overall": leaderboard[:15],
        },
    )
    dump_json(args.leaderboard_path, leaderboard)

    print(json.dumps({"output_dir": str(args.output_dir), "leaderboard_path": str(args.leaderboard_path)}, indent=2))


if __name__ == "__main__":
    main()
