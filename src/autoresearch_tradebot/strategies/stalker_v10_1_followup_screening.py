from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from ta.momentum import ROCIndicator, RSIIndicator
from ta.trend import ADXIndicator
from ta.volatility import BollingerBands

from ..common.paths import ARTIFACTS_DIR, MT5_TESTER_PROFILES_DIR, artifact_output_dir
from .stalker_v10_1_optimization_screening import render_preset, robust_baseline_params
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_followup_screening")
DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"
DEFAULT_LOSS_ANALYSIS_DIR = ARTIFACTS_DIR / "outputs" / "stalker_v10_1_mt5_loss_analysis"


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


def make_weekday_exclusion_filter(excluded_weekdays: set[int]) -> Callable[[dict[str, Any]], bool]:
    excluded = {int(value) for value in excluded_weekdays}

    def allow(context: dict[str, Any]) -> bool:
        return int(context["weekday"]) not in excluded

    return allow


def make_entry_hour_exclusion_filter(excluded_hours: set[int]) -> Callable[[dict[str, Any]], bool]:
    excluded = {int(value) for value in excluded_hours}

    def allow(context: dict[str, Any]) -> bool:
        return int(context["entry_hour"]) not in excluded

    return allow


def combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool]:
    active_filters = [candidate for candidate in filters if candidate is not None]

    def allow(context: dict[str, Any]) -> bool:
        return all(bool(candidate(context)) for candidate in active_filters)

    return allow


def make_value_range_filter(values: np.ndarray, min_value: float, max_value: float) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        value = float(values[idx])
        return bool(np.isfinite(value) and float(min_value) <= value <= float(max_value))

    return allow


def make_min_value_filter(values: np.ndarray, min_value: float) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        value = float(values[idx])
        return bool(np.isfinite(value) and value >= float(min_value))

    return allow


def signal_array_quantiles(
    dataset: V10Dataset,
    baseline_trades: pd.DataFrame,
    train_dates: pd.Index,
    values: np.ndarray,
    probs: tuple[float, ...],
) -> list[float]:
    lookup = pd.DataFrame(
        {
            "signal_bar_time": dataset.bars_m1.index.floor("min"),
            "value": values,
        }
    ).set_index("signal_bar_time")
    signal_sample = normalize_trades(baseline_trades)[["session_date", "signal_bar_time"]].copy()
    signal_sample = signal_sample.join(lookup, on="signal_bar_time")
    train_index = pd.Index(pd.to_datetime(train_dates))
    sample = signal_sample.loc[signal_sample["session_date"].isin(train_index), "value"].dropna()
    if sample.empty:
        return []
    return [float(sample.quantile(prob)) for prob in probs]


def build_bollinger_width_array(dataset: V10Dataset, window: int = 20, window_dev: float = 2.0) -> np.ndarray:
    indicator = BollingerBands(
        close=dataset.bars_m1["Close"],
        window=int(window),
        window_dev=float(window_dev),
    )
    return indicator.bollinger_wband().shift(1).to_numpy(dtype=float)


def build_adx_array(dataset: V10Dataset, window: int = 14) -> np.ndarray:
    indicator = ADXIndicator(
        high=dataset.bars_m1["High"],
        low=dataset.bars_m1["Low"],
        close=dataset.bars_m1["Close"],
        window=int(window),
    )
    return indicator.adx().shift(1).to_numpy(dtype=float)


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


def build_momentum_divergence_arrays(dataset: V10Dataset) -> dict[tuple[int, int], dict[str, np.ndarray]]:
    bars = dataset.bars_m1
    prev_close = bars["Close"].shift(1)

    arrays: dict[tuple[int, int], dict[str, np.ndarray]] = {}
    for roc_window in (5, 10):
        roc = ROCIndicator(close=bars["Close"], window=roc_window).roc().shift(1)
        for lookback in (5, 10):
            arrays[(roc_window, lookback)] = {
                "price_delta": (prev_close - bars["Close"].shift(lookback + 1)).to_numpy(dtype=float),
                "momentum_delta": (roc - roc.shift(lookback + 1)).to_numpy(dtype=float),
            }
    return arrays


def make_momentum_divergence_filter(
    price_delta: np.ndarray,
    momentum_delta: np.ndarray,
    min_delta: float,
) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        price_value = float(price_delta[idx])
        momentum_value = float(momentum_delta[idx])
        if not np.isfinite(price_value) or not np.isfinite(momentum_value):
            return False
        direction = int(context["direction"])
        if direction == 1:
            return bool(price_value < 0.0 and momentum_value >= float(min_delta))
        return bool(price_value > 0.0 and momentum_value <= -float(min_delta))

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


def load_pattern_analysis(loss_analysis_dir: Path) -> dict[str, Any]:
    weekday_path = loss_analysis_dir / "weekday_summary.csv"
    hour_path = loss_analysis_dir / "entry_hour_summary.csv"
    vwap_path = loss_analysis_dir / "signal_dir_vwap_dev_bins.csv"
    ema_path = loss_analysis_dir / "signal_dir_ema50_dev_bins.csv"
    if not weekday_path.exists() or not hour_path.exists():
        return {}

    weekday_df = pd.read_csv(weekday_path)
    hour_df = pd.read_csv(hour_path)
    vwap_df = pd.read_csv(vwap_path) if vwap_path.exists() else pd.DataFrame()
    ema_df = pd.read_csv(ema_path) if ema_path.exists() else pd.DataFrame()

    best_weekday = weekday_df.sort_values(["pf", "net"], ascending=False).iloc[0].to_dict()
    worst_weekday = weekday_df.sort_values(["pf", "net"], ascending=[True, True]).iloc[0].to_dict()
    meaningful_hours = hour_df.loc[hour_df["trades"] >= 50].copy()
    best_hour_source = meaningful_hours if not meaningful_hours.empty else hour_df
    worst_hour_source = meaningful_hours if not meaningful_hours.empty else hour_df
    best_hour = best_hour_source.sort_values(["pf", "net"], ascending=False).iloc[0].to_dict()
    worst_hour = worst_hour_source.sort_values(["pf", "net"], ascending=[True, True]).iloc[0].to_dict()

    notes = [
        (
            f"Weekday edge: best={best_weekday['weekday']} PF {float(best_weekday['pf']):.3f}, "
            f"worst={worst_weekday['weekday']} PF {float(worst_weekday['pf']):.3f}"
        ),
        (
            f"Entry-hour edge: best={int(best_hour['entry_hour'])}:00 PF {float(best_hour['pf']):.3f}, "
            f"worst={int(worst_hour['entry_hour'])}:00 PF {float(worst_hour['pf']):.3f}"
        ),
    ]
    if not vwap_df.empty:
        best_vwap = vwap_df.sort_values(["pf", "net"], ascending=False).iloc[0].to_dict()
        notes.append(f"VWAP deviation sweet spot: {best_vwap['bin']} with PF {float(best_vwap['pf']):.3f}")
    if not ema_df.empty:
        best_ema = ema_df.sort_values(["pf", "net"], ascending=False).iloc[0].to_dict()
        notes.append(f"EMA50 deviation sweet spot: {best_ema['bin']} with PF {float(best_ema['pf']):.3f}")

    return {
        "best_weekday": best_weekday,
        "worst_weekday": worst_weekday,
        "best_entry_hour": best_hour,
        "worst_entry_hour": worst_hour,
        "notes": notes,
    }


def attach_analysis_notes(leaderboard: list[dict[str, Any]], pattern_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    notes = pattern_analysis.get("notes", []) if pattern_analysis else []
    if not notes:
        return leaderboard
    for row in leaderboard:
        row["analysis_notes"] = notes
    return leaderboard


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
            "beats_baseline": bool(
                test_metrics["net_profit_brl"] >= baseline_test["net_profit_brl"]
                and test_metrics["profit_factor"] >= baseline_test["profit_factor"]
                and test_metrics["max_drawdown_pct"] <= baseline_test["max_drawdown_pct"]
            ),
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
    payload = asdict(robust_baseline_params())

    if name == "robust_combo_baseline":
        return V101Params(**payload)
    if name == "robust_relvol_short_lb20_ge_0.85":
        payload["RelativeVolumeLookbackDays"] = 20
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 0.85
        return V101Params(**payload)
    if name == "robust_relvol_short_lb40_ge_0.95":
        payload["RelativeVolumeLookbackDays"] = 40
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 0.95
        return V101Params(**payload)
    if name == "robust_relvol_both_lb20_ge_0.85":
        payload["RelativeVolumeLookbackDays"] = 20
        payload["ApplyRelativeVolumeFilterToLongs"] = True
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 0.85
        return V101Params(**payload)
    if name == "exclude_last_30m":
        payload["LastEntry_Hour"] = 14
        payload["LastEntry_Minute"] = 30
        return V101Params(**payload)
    if name == "relvol_short_lb40_ge_0.5":
        payload["RelativeVolumeLookbackDays"] = 40
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 0.5
        return V101Params(**payload)
    if name == "relvol_short_lb40_ge_1":
        payload["RelativeVolumeLookbackDays"] = 40
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 1.0
        return V101Params(**payload)
    if name == "exclude_first_30m":
        payload["EntryStart_Hour"] = 10
        payload["EntryStart_Minute"] = 30
        return V101Params(**payload)
    if name == "exclude_wednesday":
        payload["AllowWednesday"] = False
        return V101Params(**payload)
    if name == "robust_no_wednesday":
        payload["AllowWednesday"] = False
        return V101Params(**payload)
    if name == "robust_no_wednesday_plus_relvol_short_lb20_ge_0.85":
        payload["AllowWednesday"] = False
        payload["RelativeVolumeLookbackDays"] = 20
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 0.85
        return V101Params(**payload)
    if name == "exclude_last_30m_plus_exclude_wednesday":
        payload["AllowWednesday"] = False
        payload["LastEntry_Hour"] = 14
        payload["LastEntry_Minute"] = 30
        return V101Params(**payload)
    if name == "exclude_last_30m_plus_relvol_short_lb40_ge_0.5":
        payload["LastEntry_Hour"] = 14
        payload["LastEntry_Minute"] = 30
        payload["RelativeVolumeLookbackDays"] = 40
        payload["ApplyRelativeVolumeFilterToShorts"] = True
        payload["MinRelativeVolumeAtTime"] = 0.5
        return V101Params(**payload)
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


def select_mt5_winners(
    leaderboard: list[dict[str, Any]],
    baseline_test: dict[str, Any],
) -> list[dict[str, Any]]:
    winners: list[dict[str, Any]] = []
    baseline_net = float(baseline_test["net_profit_brl"])
    baseline_pf = float(baseline_test["profit_factor"])
    baseline_dd = float(baseline_test["max_drawdown_pct"])
    for row in leaderboard:
        if not bool(row.get("mt5_ready")):
            continue
        if str(row.get("name", "")) == "robust_combo_baseline":
            continue
        row_net = float(row.get("test_net_profit_brl", 0.0))
        row_pf = float(row.get("test_profit_factor", 0.0))
        row_dd = float(row.get("test_max_drawdown_pct", 0.0))
        if row_net >= baseline_net and row_pf >= baseline_pf and row_dd <= baseline_dd:
            winners.append(row)
    return winners


def main() -> None:
    parser = argparse.ArgumentParser(description="Follow-up Python screening for Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--leaderboard-path", type=Path, default=DEFAULT_LEADERBOARD_PATH)
    parser.add_argument("--loss-analysis-dir", type=Path, default=DEFAULT_LOSS_ANALYSIS_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--top-presets", type=int, default=3)
    parser.add_argument("--last-months", type=int, default=0)
    parser.add_argument("--include-rsi-grid", action="store_true")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    data_path = locate_data_file(args.data_path)
    dataset = V10Dataset.from_disk(data_path)
    trade_dates = dataset.trade_dates
    if int(args.last_months) > 0:
        cutoff = pd.Timestamp(trade_dates.max()) - pd.DateOffset(months=int(args.last_months))
        trade_dates = trade_dates[trade_dates >= cutoff.normalize()]
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

    exclude_wednesday = V101Params(
        **{
            **asdict(baseline),
            "AllowWednesday": False,
        }
    )
    _, exclude_wednesday_metrics = run_candidate(
        dataset=dataset,
        params=exclude_wednesday,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
    )
    records.append(
        result_record(
            name="exclude_wednesday",
            family="timing_filter",
            config={"exclude_weekdays": ["Wednesday"]},
            metrics=exclude_wednesday_metrics,
            mt5_ready=True,
            notes="Direct weekday filter based on MT5 loss analysis showing Wednesday as the weakest day",
        )
    )

    exclude_hour_13_filter = make_entry_hour_exclusion_filter({13})
    _, exclude_hour_13_metrics = run_candidate(
        dataset=dataset,
        params=baseline,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
        entry_filter=exclude_hour_13_filter,
    )
    records.append(
        result_record(
            name="exclude_entry_hour_13",
            family="timing_filter",
            config={"exclude_entry_hours": [13]},
            metrics=exclude_hour_13_metrics,
            mt5_ready=False,
            notes="Screen-only filter from the MT5 analysis, which showed 13:00 as the weakest hour",
        )
    )

    exclude_last_30m_plus_exclude_wednesday = V101Params(
        **{
            **asdict(baseline),
            "AllowWednesday": False,
            "LastEntry_Hour": 14,
            "LastEntry_Minute": 30,
        }
    )
    _, exclude_last_30m_plus_exclude_wednesday_metrics = run_candidate(
        dataset=dataset,
        params=exclude_last_30m_plus_exclude_wednesday,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
    )
    records.append(
        result_record(
            name="exclude_last_30m_plus_exclude_wednesday",
            family="combo",
            config={
                "exclude_weekdays": ["Wednesday"],
                "time_filter": "exclude_last_30m",
            },
            metrics=exclude_last_30m_plus_exclude_wednesday_metrics,
            mt5_ready=True,
            notes="MT5-ready combination of the earlier late-session trim and the weak-Wednesday filter",
        )
    )

    exclude_wednesday_hour_13_last_30m = V101Params(
        **{
            **asdict(baseline),
            "AllowWednesday": False,
            "LastEntry_Hour": 14,
            "LastEntry_Minute": 30,
        }
    )
    _, exclude_wednesday_hour_13_last_30m_metrics = run_candidate(
        dataset=dataset,
        params=exclude_wednesday_hour_13_last_30m,
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
        entry_filter=exclude_hour_13_filter,
    )
    records.append(
        result_record(
            name="exclude_wednesday_plus_exclude_hour_13_plus_exclude_last_30m",
            family="combo",
            config={
                "exclude_weekdays": ["Wednesday"],
                "exclude_entry_hours": [13],
                "time_filter": "exclude_last_30m",
            },
            metrics=exclude_wednesday_hour_13_last_30m_metrics,
            mt5_ready=False,
            notes="Full timing stack using the two weak pockets plus the earlier last-30m trim",
        )
    )

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

    bb_width_values = build_bollinger_width_array(dataset, window=20, window_dev=2.0)
    bb_quantiles = signal_array_quantiles(dataset, baseline_trades, train_dates, bb_width_values, (0.25, 0.75))
    if len(bb_quantiles) == 2:
        _, bb_metrics = run_candidate(
            dataset=dataset,
            params=baseline,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            entry_filter=make_value_range_filter(
                bb_width_values,
                bb_quantiles[0],
                bb_quantiles[1],
            ),
        )
        records.append(
            result_record(
                name="baseline_plus_bb_width_20_train_iqr",
                family="bollinger_band_width",
                config={
                    "window": 20,
                    "window_dev": 2.0,
                    "mode": "train_iqr_range",
                    "min_width": bb_quantiles[0],
                    "max_width": bb_quantiles[1],
                },
                metrics=bb_metrics,
                mt5_ready=False,
                notes="Bollinger-band width filter to keep entries in the baseline volatility regime",
            )
        )

    adx_values = build_adx_array(dataset, window=14)
    adx_thresholds = signal_array_quantiles(dataset, baseline_trades, train_dates, adx_values, (0.5,))
    if len(adx_thresholds) == 1:
        _, adx_metrics = run_candidate(
            dataset=dataset,
            params=baseline,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            entry_filter=make_min_value_filter(adx_values, adx_thresholds[0]),
        )
        records.append(
            result_record(
                name="baseline_plus_adx_14_ge_train_median",
                family="adx_trend_strength",
                config={
                    "window": 14,
                    "mode": "train_median_min",
                    "min_adx": adx_thresholds[0],
                },
                metrics=adx_metrics,
                mt5_ready=False,
                notes="ADX trend-strength confirmation using the train-set median as the minimum threshold",
            )
        )

    if args.include_rsi_grid:
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

    momentum_arrays = build_momentum_divergence_arrays(dataset)
    momentum_key = (10, 10)
    if momentum_key in momentum_arrays:
        arrays = momentum_arrays[momentum_key]
        _, momentum_metrics = run_candidate(
            dataset=dataset,
            params=baseline,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            entry_filter=make_momentum_divergence_filter(
                arrays["price_delta"],
                arrays["momentum_delta"],
                0.0,
            ),
        )
        records.append(
            result_record(
                name="baseline_plus_momdiv_roc10_lb10_delta0",
                family="momentum_divergence",
                config={
                    "roc_window": 10,
                    "lookback": 10,
                    "min_momentum_delta": 0.0,
                },
                metrics=momentum_metrics,
                mt5_ready=False,
                notes="Price-vs-ROC divergence confirmation on the signal bar",
            )
        )

    existing_leaderboard = load_existing_leaderboard(args.leaderboard_path)
    leaderboard = build_leaderboard_rows(existing_leaderboard, records, baseline_metrics["test"])
    pattern_analysis = load_pattern_analysis(args.loss_analysis_dir)
    leaderboard = attach_analysis_notes(leaderboard, pattern_analysis)
    mt5_winners = select_mt5_winners(leaderboard, baseline_metrics["test"])
    written_presets = write_top_presets(mt5_winners, max(int(args.top_presets), len(mt5_winners)))

    summary = {
        "data_source": str(data_path),
        "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
        "baseline_test_metrics": baseline_metrics["test"],
        "new_records": records[1:],
        "pattern_analysis": pattern_analysis,
        "top_overall": leaderboard[:15],
        "mt5_winners": mt5_winners,
        "written_presets": written_presets,
    }

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (args.output_dir / "candidate_results.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    (args.output_dir / "pattern_analysis.json").write_text(json.dumps(pattern_analysis, indent=2), encoding="utf-8")
    args.leaderboard_path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
