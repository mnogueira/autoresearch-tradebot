from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator

from ..common.paths import ARTIFACTS_DIR, MT5_TESTER_PROFILES_DIR, artifact_output_dir
from .stalker_v10_1_optimization_screening import render_preset, robust_baseline_params
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_followup_screening")
DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"


def normalize_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    frame = trades_df.copy()
    if frame.empty:
        return frame
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.normalize()
    frame["signal_time"] = pd.to_datetime(frame["signal_time"])
    frame["signal_bar_time"] = frame["signal_time"].dt.floor("min")
    return frame


def metric_bundle(
    trades_df: pd.DataFrame,
    train_dates: pd.Index,
    test_dates: pd.Index,
) -> dict[str, Any]:
    normalized = normalize_trades(trades_df)
    train_index = pd.Index(pd.to_datetime(train_dates))
    test_index = pd.Index(pd.to_datetime(test_dates))
    all_index = pd.Index(train_index.tolist() + test_index.tolist())
    if normalized.empty:
        train_df = normalized
        test_df = normalized
    else:
        train_df = normalized[normalized["session_date"].isin(train_index)]
        test_df = normalized[normalized["session_date"].isin(test_index)]
    return {
        "all": calculate_metrics(normalized, all_index),
        "train": calculate_metrics(train_df, train_index),
        "test": calculate_metrics(test_df, test_index),
    }


def run_candidate(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    train_dates: pd.Index,
    test_dates: pd.Index,
    entry_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    trades_df, _ = run_backtest(dataset, params, trade_dates, entry_filter=entry_filter)
    return normalize_trades(trades_df), metric_bundle(trades_df, train_dates, test_dates)


def result_record(
    *,
    name: str,
    family: str,
    config: dict[str, Any],
    metrics: dict[str, Any],
    mt5_ready: bool,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "family": family,
        "config": config,
        "metrics": metrics,
        "mt5_ready": mt5_ready,
        "notes": notes,
    }


def make_atr_range_filter(atr_values: np.ndarray, min_value: float, max_value: float) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        value = float(atr_values[idx])
        return bool(np.isfinite(value) and float(min_value) <= value <= float(max_value))

    return allow


def build_rsi_divergence_arrays(dataset: V10Dataset) -> dict[int, dict[str, np.ndarray]]:
    bars = dataset.bars_m1
    rsi14 = RSIIndicator(close=bars["Close"], window=14).rsi()
    prev_close = bars["Close"].shift(1)
    prev_rsi = rsi14.shift(1)

    arrays: dict[int, dict[str, np.ndarray]] = {}
    for lookback in (5, 10, 15):
        arrays[lookback] = {
            "price_delta": (prev_close - bars["Close"].shift(lookback + 1)).to_numpy(dtype=float),
            "rsi_delta": (prev_rsi - rsi14.shift(lookback + 1)).to_numpy(dtype=float),
        }
    return arrays


def make_rsi_divergence_filter(
    price_delta: np.ndarray,
    rsi_delta: np.ndarray,
    min_delta: float,
) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        price_value = float(price_delta[idx])
        rsi_value = float(rsi_delta[idx])
        if not np.isfinite(price_value) or not np.isfinite(rsi_value):
            return False
        direction = int(context["direction"])
        if direction == 1:
            return bool(price_value < 0.0 and rsi_value >= float(min_delta))
        return bool(price_value > 0.0 and rsi_value <= -float(min_delta))

    return allow


def atr_iqr_thresholds(
    dataset: V10Dataset,
    baseline_trades: pd.DataFrame,
    train_dates: pd.Index,
    period: int,
) -> tuple[float, float]:
    bars = dataset.bars_m1.copy()
    bars["atr_value"] = dataset.get_atr_current(period)
    signal_sample = normalize_trades(baseline_trades)[["session_date", "signal_bar_time"]].copy()
    signal_sample = signal_sample.join(
        bars[["atr_value"]].rename_axis("signal_bar_time"),
        on="signal_bar_time",
    )
    train_index = pd.Index(pd.to_datetime(train_dates))
    sample = signal_sample.loc[signal_sample["session_date"].isin(train_index), "atr_value"].dropna()
    return float(sample.quantile(0.25)), float(sample.quantile(0.75))


def build_leaderboard_rows(
    existing_rows: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    baseline_test: dict[str, Any],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {str(row["name"]): dict(row) for row in existing_rows if "name" in row}

    for record in new_records:
        test_metrics = record["metrics"]["test"]
        merged[record["name"]] = {
            "name": record["name"],
            "family": record["family"],
            "test_net_profit_brl": test_metrics["net_profit_brl"],
            "test_profit_factor": test_metrics["profit_factor"],
            "test_max_drawdown_pct": test_metrics["max_drawdown_pct"],
            "test_win_rate": test_metrics["win_rate"],
            "test_on_tester_value": test_metrics["on_tester_value"],
            "delta_vs_baseline_test_net": test_metrics["net_profit_brl"] - baseline_test["net_profit_brl"],
            "delta_vs_baseline_test_pf": test_metrics["profit_factor"] - baseline_test["profit_factor"],
            "delta_vs_baseline_test_dd": test_metrics["max_drawdown_pct"] - baseline_test["max_drawdown_pct"],
            "mt5_ready": bool(record["mt5_ready"]),
            "notes": record.get("notes", ""),
        }

    rows = list(merged.values())
    rows.sort(
        key=lambda row: (
            float(row.get("test_on_tester_value", 0.0)),
            float(row.get("test_profit_factor", 0.0)),
            float(row.get("test_net_profit_brl", 0.0)),
            -float(row.get("test_max_drawdown_pct", 0.0)),
        ),
        reverse=True,
    )
    return rows


def params_for_mt5_candidate(name: str) -> V101Params | None:
    params = robust_baseline_params()

    if name == "robust_combo_baseline":
        return params
    if name == "exclude_last_30m":
        params.LastEntry_Hour = 14
        params.LastEntry_Minute = 30
        return params
    if name == "relvol_short_lb40_ge_0.5":
        params.RelativeVolumeLookbackDays = 40
        params.ApplyRelativeVolumeFilterToShorts = True
        params.MinRelativeVolumeAtTime = 0.5
        return params
    if name == "relvol_short_lb40_ge_1":
        params.RelativeVolumeLookbackDays = 40
        params.ApplyRelativeVolumeFilterToShorts = True
        params.MinRelativeVolumeAtTime = 1.0
        return params
    if name == "exclude_first_30m":
        params.EntryStart_Hour = 10
        params.EntryStart_Minute = 30
        return params
    if name == "exclude_last_30m_plus_relvol_short_lb40_ge_0.5":
        params.LastEntry_Hour = 14
        params.LastEntry_Minute = 30
        params.RelativeVolumeLookbackDays = 40
        params.ApplyRelativeVolumeFilterToShorts = True
        params.MinRelativeVolumeAtTime = 0.5
        return params
    return None


def preset_filename(name: str) -> str:
    safe_name = name.replace(".", "p")
    return f"WDO Stalker Strategy v10.1 {safe_name} GPT 5.4.set"


def write_top_presets(leaderboard: list[dict[str, Any]], top_n: int) -> list[dict[str, Any]]:
    MT5_TESTER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for row in leaderboard:
        if len(written) >= int(top_n):
            break
        params = params_for_mt5_candidate(str(row["name"]))
        if params is None:
            continue
        path = MT5_TESTER_PROFILES_DIR / preset_filename(str(row["name"]))
        path.write_text(render_preset(asdict(params)), encoding="utf-8")
        written.append(
            {
                "name": str(row["name"]),
                "path": str(path.resolve()),
            }
        )
    return written


def load_existing_leaderboard(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def main() -> None:
    parser = argparse.ArgumentParser(description="Follow-up Python screening for Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--leaderboard-path", type=Path, default=DEFAULT_LEADERBOARD_PATH)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--top-presets", type=int, default=3)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    data_path = locate_data_file(args.data_path)
    dataset = V10Dataset.from_disk(data_path)
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, args.train_ratio)

    baseline = robust_baseline_params()
    baseline_trades, baseline_metrics = run_candidate(
        dataset=dataset,
        params=baseline,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
    )

    records: list[dict[str, Any]] = [
        result_record(
            name="robust_combo_baseline",
            family="baseline",
            config=asdict(baseline),
            metrics=baseline_metrics,
            mt5_ready=True,
            notes="Current robust combo baseline used for deltas",
        )
    ]

    relvol_combo = V101Params(
        **{
            **asdict(baseline),
            "LastEntry_Hour": 14,
            "LastEntry_Minute": 30,
            "RelativeVolumeLookbackDays": 40,
            "ApplyRelativeVolumeFilterToShorts": True,
            "MinRelativeVolumeAtTime": 0.5,
        }
    )
    _, relvol_combo_metrics = run_candidate(
        dataset=dataset,
        params=relvol_combo,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
    )
    records.append(
        result_record(
            name="exclude_last_30m_plus_relvol_short_lb40_ge_0.5",
            family="combo",
            config={
                "time_filter": "exclude_last_30m",
                "relative_volume": {
                    "apply_side": "short",
                    "lookback_days": 40,
                    "threshold": 0.5,
                },
            },
            metrics=relvol_combo_metrics,
            mt5_ready=True,
            notes="Robust baseline plus the best single time filter and the best single relative-volume filter",
        )
    )

    atr_min, atr_max = atr_iqr_thresholds(dataset, baseline_trades, train_dates, period=20)
    atr_combo = V101Params(
        **{
            **asdict(baseline),
            "LastEntry_Hour": 14,
            "LastEntry_Minute": 30,
        }
    )
    _, atr_combo_metrics = run_candidate(
        dataset=dataset,
        params=atr_combo,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
        entry_filter=make_atr_range_filter(dataset.get_atr_current(20), atr_min, atr_max),
    )
    records.append(
        result_record(
            name="exclude_last_30m_plus_atr_20_iqr",
            family="combo",
            config={
                "time_filter": "exclude_last_30m",
                "atr_filter": {
                    "period": 20,
                    "mode": "train_iqr_range",
                    "min_atr": atr_min,
                    "max_atr": atr_max,
                },
            },
            metrics=atr_combo_metrics,
            mt5_ready=False,
            notes="Requires MT5 EA ATR-filter support before host-side validation",
        )
    )

    rsi_arrays = build_rsi_divergence_arrays(dataset)
    for lookback, arrays in rsi_arrays.items():
        for min_delta in (0.0, 2.5, 5.0):
            _, rsi_metrics = run_candidate(
                dataset=dataset,
                params=baseline,
                trade_dates=trade_dates,
                train_dates=train_dates,
                test_dates=test_dates,
                entry_filter=make_rsi_divergence_filter(
                    arrays["price_delta"],
                    arrays["rsi_delta"],
                    min_delta,
                ),
            )
            records.append(
                result_record(
                    name=f"baseline_plus_rsi_div_lb{lookback}_delta_{min_delta:g}",
                    family="rsi_divergence",
                    config={
                        "lookback": int(lookback),
                        "min_rsi_delta": float(min_delta),
                        "period": 14,
                    },
                    metrics=rsi_metrics,
                    mt5_ready=False,
                    notes="Integrated backtest using RSI-vs-price divergence confirmation on the signal bar",
                )
            )

    existing_leaderboard = load_existing_leaderboard(args.leaderboard_path)
    leaderboard = build_leaderboard_rows(existing_leaderboard, records, baseline_metrics["test"])
    written_presets = write_top_presets(leaderboard, args.top_presets)

    summary = {
        "data_source": str(data_path),
        "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
        "baseline_test_metrics": baseline_metrics["test"],
        "new_records": records[1:],
        "top_overall": leaderboard[:15],
        "written_presets": written_presets,
    }

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.output_dir / "candidate_results.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    args.leaderboard_path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
