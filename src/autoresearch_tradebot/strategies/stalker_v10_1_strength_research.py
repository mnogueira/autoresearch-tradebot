from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_strength_research")


@dataclass(frozen=True)
class FilterSpec:
    name: str
    apply_side: str = "all"
    min_strength_score: float | None = None
    min_dir_ret_15: float | None = None
    min_open_impulse: float | None = None
    min_trend_efficiency_15: float | None = None
    min_cum_volume_rel: float | None = None
    min_range_vs_filter: float | None = None
    max_trade_number: int | None = None


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


def apply_rank_from_train(values: pd.Series, train_values: pd.Series) -> pd.Series:
    reference = np.sort(train_values.dropna().to_numpy(dtype=float))
    if len(reference) == 0:
        return pd.Series(0.5, index=values.index, dtype=float)

    query = values.to_numpy(dtype=float, copy=True)
    ranks = np.searchsorted(reference, query, side="right") / len(reference)
    output = pd.Series(ranks, index=values.index, dtype=float)
    output[values.isna()] = 0.5
    return output.clip(0.0, 1.0)


def quantile_candidates(series: pd.Series, probs: list[float]) -> list[float]:
    clean = series.dropna()
    if clean.empty:
        return []
    thresholds = [float(clean.quantile(prob)) for prob in probs]
    return sorted({round(value, 6) for value in thresholds})


def build_strength_frame(dataset: V10Dataset, params: V101Params) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    session_key = bars["session_date"]
    minute_of_day = (bars.index.hour * 60) + bars.index.minute
    bars["minute_of_day"] = minute_of_day
    bars["session_open"] = bars.groupby("session_date")["Open"].transform("first")
    bars["prev_close"] = bars.groupby("session_date")["Close"].shift(1)

    for window in (5, 15, 30):
        lookback = window + 1
        bars[f"ret_{window}_raw"] = (
            bars.groupby("session_date")["Close"].shift(1)
            - bars.groupby("session_date")["Close"].shift(lookback)
        )

    bars["open_impulse_raw"] = bars["prev_close"] - bars["session_open"]

    ret_prev = bars.groupby("session_date")["Close"].diff().groupby(session_key).shift(1)
    abs_ret_prev = ret_prev.abs()
    pos_sq_prev = ret_prev.clip(lower=0.0).pow(2)
    neg_sq_prev = (-ret_prev.clip(upper=0.0)).pow(2)

    bars["realized_abs_15"] = (
        abs_ret_prev.groupby(session_key).transform(lambda series: series.rolling(15, min_periods=10).sum())
    )
    up_semivar_15 = pos_sq_prev.groupby(session_key).transform(
        lambda series: series.rolling(15, min_periods=10).sum()
    )
    down_semivar_15 = neg_sq_prev.groupby(session_key).transform(
        lambda series: series.rolling(15, min_periods=10).sum()
    )
    total_semivar = up_semivar_15 + down_semivar_15
    bars["semivar_bias_15"] = np.where(
        total_semivar > 0.0,
        (up_semivar_15 - down_semivar_15) / total_semivar,
        np.nan,
    )
    bars["trend_efficiency_15"] = bars["ret_15_raw"] / bars["realized_abs_15"].replace(0.0, np.nan)

    bars["signal_range"] = dataset.get_signal_range(
        params.FilterAsPercOfContractMARange,
        params.NumDaysToConsiderPreviousContractMARange,
    )
    bars["range_vs_filter"] = (
        (bars["day_high_current"] - bars["day_low_current"]) / bars["signal_range"].replace(0.0, np.nan)
    )

    bars["cum_volume_prev"] = bars.groupby("session_date")["Volume"].cumsum().groupby(session_key).shift(1)
    bars["expected_cum_volume_prev"] = bars.groupby("minute_of_day")["cum_volume_prev"].transform(
        lambda series: series.rolling(60, min_periods=20).mean().shift(1)
    )
    bars["cum_volume_rel"] = bars["cum_volume_prev"] / bars["expected_cum_volume_prev"].replace(0.0, np.nan)

    columns = [
        "ret_5_raw",
        "ret_15_raw",
        "ret_30_raw",
        "open_impulse_raw",
        "realized_abs_15",
        "semivar_bias_15",
        "trend_efficiency_15",
        "signal_range",
        "range_vs_filter",
        "cum_volume_prev",
        "cum_volume_rel",
    ]
    return bars[columns].copy()


def attach_trade_features(
    trades_df: pd.DataFrame,
    strength_frame: pd.DataFrame,
    train_dates: set[pd.Timestamp],
) -> pd.DataFrame:
    enriched = trades_df.copy()
    enriched["session_date"] = pd.to_datetime(enriched["session_date"]).dt.normalize()
    enriched["signal_time"] = pd.to_datetime(enriched["signal_time"])
    enriched["entry_time"] = pd.to_datetime(enriched["entry_time"])
    enriched["exit_time"] = pd.to_datetime(enriched["exit_time"])
    enriched["direction_sign"] = np.where(enriched["direction"].eq("long"), 1.0, -1.0)
    enriched["signal_bar_time"] = enriched["signal_time"].dt.floor("min")
    enriched["trade_seq_day"] = enriched.groupby("session_date").cumcount() + 1
    enriched = enriched.join(strength_frame.add_prefix("signal_"), on="signal_bar_time")

    enriched["signal_dir_ret_15"] = enriched["direction_sign"] * enriched["signal_ret_15_raw"]
    enriched["signal_dir_ret_30"] = enriched["direction_sign"] * enriched["signal_ret_30_raw"]
    enriched["signal_open_impulse"] = enriched["direction_sign"] * enriched["signal_open_impulse_raw"]
    enriched["signal_dir_trend_efficiency_15"] = (
        enriched["direction_sign"] * enriched["signal_trend_efficiency_15"]
    )
    enriched["signal_semivar_align"] = enriched["direction_sign"] * enriched["signal_semivar_bias_15"]

    train_mask = enriched["session_date"].isin(train_dates)
    components: list[tuple[str, float]] = [
        ("signal_dir_ret_15", 0.30),
        ("signal_open_impulse", 0.25),
        ("signal_dir_trend_efficiency_15", 0.20),
        ("signal_cum_volume_rel", 0.15),
        ("signal_range_vs_filter", 0.10),
    ]
    score = pd.Series(0.0, index=enriched.index, dtype=float)
    total_weight = 0.0
    for column, weight in components:
        score += apply_rank_from_train(enriched[column], enriched.loc[train_mask, column]) * weight
        total_weight += weight
    enriched["strength_score"] = score / total_weight
    return enriched


def evaluate_trade_mask(
    trades_df: pd.DataFrame,
    keep_mask: pd.Series,
    train_dates: set[pd.Timestamp],
    test_dates: set[pd.Timestamp],
) -> dict[str, Any]:
    kept = trades_df[keep_mask.fillna(False)].copy()
    removed = trades_df[~keep_mask.fillna(False)].copy()
    metrics = perf_by_split(kept, train_dates, test_dates)
    result: dict[str, Any] = {
        "kept_trades": int(len(kept)),
        "removed_trades": int(len(removed)),
        "removed_net_profit_brl": float(removed["pnl_brl"].sum()),
    }
    for prefix, values in metrics.items():
        for key, value in values.items():
            result[f"{prefix}_{key}"] = value
    return result


def build_filter_callback(
    strength_frame: pd.DataFrame,
    spec: FilterSpec,
):
    arrays = {
        "long_strength_score": strength_frame["long_strength_score"].to_numpy(dtype=float),
        "short_strength_score": strength_frame["short_strength_score"].to_numpy(dtype=float),
        "ret_15_raw": strength_frame["ret_15_raw"].to_numpy(dtype=float),
        "open_impulse_raw": strength_frame["open_impulse_raw"].to_numpy(dtype=float),
        "trend_efficiency_15_raw": strength_frame["trend_efficiency_15"].to_numpy(dtype=float),
        "cum_volume_rel": strength_frame["cum_volume_rel"].to_numpy(dtype=float),
        "range_vs_filter": strength_frame["range_vs_filter"].to_numpy(dtype=float),
    }

    def allow_entry(context: dict[str, Any]) -> bool:
        direction = int(context["direction"])
        if spec.apply_side == "long" and direction != 1:
            return True
        if spec.apply_side == "short" and direction != -1:
            return True

        idx = int(context["dataset_index"])
        if spec.max_trade_number is not None and int(context["next_trade_number"]) > int(spec.max_trade_number):
            return False

        checks = [
            (
                "strength_score",
                spec.min_strength_score,
                arrays["long_strength_score"][idx] if direction == 1 else arrays["short_strength_score"][idx],
            ),
            ("dir_ret_15", spec.min_dir_ret_15, direction * arrays["ret_15_raw"][idx]),
            ("open_impulse", spec.min_open_impulse, direction * arrays["open_impulse_raw"][idx]),
            (
                "trend_efficiency_15",
                spec.min_trend_efficiency_15,
                direction * arrays["trend_efficiency_15_raw"][idx],
            ),
            ("cum_volume_rel", spec.min_cum_volume_rel, arrays["cum_volume_rel"][idx]),
            ("range_vs_filter", spec.min_range_vs_filter, arrays["range_vs_filter"][idx]),
        ]
        for _key, threshold, value in checks:
            if threshold is None:
                continue
            if not np.isfinite(value) or value < float(threshold):
                return False
        return True

    return allow_entry


def integrated_backtest_result(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    train_dates: set[pd.Timestamp],
    test_dates: set[pd.Timestamp],
    strength_frame: pd.DataFrame,
    spec: FilterSpec,
) -> dict[str, Any]:
    entry_filter = build_filter_callback(strength_frame, spec) if spec.name != "baseline" else None
    trades_df, _ = run_backtest(dataset, params, trade_dates, entry_filter=entry_filter)
    trades_df["session_date"] = pd.to_datetime(trades_df["session_date"]).dt.normalize()
    result = {"name": spec.name, "spec": asdict(spec)}
    for prefix, values in perf_by_split(trades_df, train_dates, test_dates).items():
        for key, value in values.items():
            result[f"{prefix}_{key}"] = value
    return result


def build_walkforward_splits(trade_dates: pd.Index, folds: int) -> list[pd.Index]:
    if folds <= 1 or len(trade_dates) == 0:
        return [trade_dates]
    partitions = np.array_split(np.arange(len(trade_dates)), folds)
    return [trade_dates[partition] for partition in partitions if len(partition) > 0]


def walkforward_result(
    dataset: V10Dataset,
    params: V101Params,
    strength_frame: pd.DataFrame,
    spec: FilterSpec,
    trade_dates: pd.Index,
    folds: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    entry_filter = build_filter_callback(strength_frame, spec) if spec.name != "baseline" else None
    for fold_number, fold_dates in enumerate(build_walkforward_splits(trade_dates, folds), start=1):
        trades_df, _ = run_backtest(dataset, params, fold_dates, entry_filter=entry_filter)
        metrics = perf(trades_df)
        rows.append(
            {
                "name": spec.name,
                "fold": fold_number,
                "start_date": pd.Timestamp(fold_dates[0]).date().isoformat(),
                "end_date": pd.Timestamp(fold_dates[-1]).date().isoformat(),
                **metrics,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Research strength filters for WDO Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--walkforward-folds", type=int, default=6)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(args.data_path or locate_data_file())
    params = V101Params()
    trade_dates = dataset.trade_dates
    train_dates_idx, test_dates_idx = split_dates(trade_dates, args.train_ratio)
    train_dates = set(pd.Timestamp(date).normalize() for date in train_dates_idx)
    test_dates = set(pd.Timestamp(date).normalize() for date in test_dates_idx)

    strength_frame = build_strength_frame(dataset, params)
    base_trades, base_metrics = run_backtest(dataset, params, trade_dates)
    trade_features = attach_trade_features(base_trades, strength_frame, train_dates)
    train_trade_mask = trade_features["session_date"].isin(train_dates)
    strength_frame["long_strength_score"] = (
        apply_rank_from_train(
            strength_frame["ret_15_raw"],
            trade_features.loc[train_trade_mask, "signal_dir_ret_15"],
        )
        * 0.30
        + apply_rank_from_train(
            strength_frame["open_impulse_raw"],
            trade_features.loc[train_trade_mask, "signal_open_impulse"],
        )
        * 0.25
        + apply_rank_from_train(
            strength_frame["trend_efficiency_15"],
            trade_features.loc[train_trade_mask, "signal_dir_trend_efficiency_15"],
        )
        * 0.20
        + apply_rank_from_train(
            strength_frame["cum_volume_rel"],
            trade_features.loc[train_trade_mask, "signal_cum_volume_rel"],
        )
        * 0.15
        + apply_rank_from_train(
            strength_frame["range_vs_filter"],
            trade_features.loc[train_trade_mask, "signal_range_vs_filter"],
        )
        * 0.10
    )
    strength_frame["short_strength_score"] = (
        apply_rank_from_train(
            -strength_frame["ret_15_raw"],
            trade_features.loc[train_trade_mask, "signal_dir_ret_15"],
        )
        * 0.30
        + apply_rank_from_train(
            -strength_frame["open_impulse_raw"],
            trade_features.loc[train_trade_mask, "signal_open_impulse"],
        )
        * 0.25
        + apply_rank_from_train(
            -strength_frame["trend_efficiency_15"],
            trade_features.loc[train_trade_mask, "signal_dir_trend_efficiency_15"],
        )
        * 0.20
        + apply_rank_from_train(
            strength_frame["cum_volume_rel"],
            trade_features.loc[train_trade_mask, "signal_cum_volume_rel"],
        )
        * 0.15
        + apply_rank_from_train(
            strength_frame["range_vs_filter"],
            trade_features.loc[train_trade_mask, "signal_range_vs_filter"],
        )
        * 0.10
    )

    prescreen_rows: list[dict[str, Any]] = []
    baseline_row = evaluate_trade_mask(
        trade_features,
        pd.Series(True, index=trade_features.index),
        train_dates,
        test_dates,
    )
    baseline_row["name"] = "baseline_keep_all"
    prescreen_rows.append(baseline_row)

    candidate_feature_defs = [
        ("long_only_dir_ret_15", "signal_dir_ret_15", "long"),
        ("all_dir_ret_15", "signal_dir_ret_15", "all"),
        ("long_only_open_impulse", "signal_open_impulse", "long"),
        ("all_open_impulse", "signal_open_impulse", "all"),
        ("long_only_trend_efficiency", "signal_dir_trend_efficiency_15", "long"),
        ("all_trend_efficiency", "signal_dir_trend_efficiency_15", "all"),
        ("long_only_cum_volume_rel", "signal_cum_volume_rel", "long"),
        ("all_cum_volume_rel", "signal_cum_volume_rel", "all"),
        ("all_range_vs_filter", "signal_range_vs_filter", "all"),
        ("long_only_strength_score", "strength_score", "long"),
        ("all_strength_score", "strength_score", "all"),
    ]

    for candidate_name, column, side in candidate_feature_defs:
        base_mask = pd.Series(True, index=trade_features.index)
        if side == "long":
            selector = trade_features["direction"].eq("long")
        elif side == "short":
            selector = trade_features["direction"].eq("short")
        else:
            selector = pd.Series(True, index=trade_features.index)

        thresholds = quantile_candidates(
            trade_features.loc[trade_features["session_date"].isin(train_dates) & selector, column],
            probs=[0.20, 0.35, 0.50, 0.65],
        )
        for threshold in thresholds:
            mask = base_mask.copy()
            mask.loc[selector] = trade_features.loc[selector, column] >= threshold
            row = evaluate_trade_mask(trade_features, mask, train_dates, test_dates)
            row["name"] = f"{candidate_name}_ge_{threshold:g}"
            row["column"] = column
            row["threshold"] = float(threshold)
            row["side"] = side
            prescreen_rows.append(row)

    seq_benchmark = evaluate_trade_mask(
        trade_features,
        ~(
            trade_features["direction"].eq("long")
            & trade_features["trade_seq_day"].eq(2)
        ),
        train_dates,
        test_dates,
    )
    seq_benchmark["name"] = "benchmark_skip_long_seq2"
    prescreen_rows.append(seq_benchmark)

    prescreen_df = pd.DataFrame(prescreen_rows)
    baseline_test_pf = float(
        prescreen_df.loc[prescreen_df["name"] == "baseline_keep_all", "test_profit_factor"].iloc[0]
    )
    baseline_test_avg = float(
        prescreen_df.loc[prescreen_df["name"] == "baseline_keep_all", "test_avg_profit_brl"].iloc[0]
    )
    prescreen_df["test_pf_delta"] = prescreen_df["test_profit_factor"] - baseline_test_pf
    prescreen_df["test_avg_delta"] = prescreen_df["test_avg_profit_brl"] - baseline_test_avg
    prescreen_df = prescreen_df.sort_values(
        ["test_pf_delta", "test_avg_delta", "test_net_profit_brl"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    integrated_specs = [
        FilterSpec(name="baseline"),
    ]

    top_strength_candidates = prescreen_df[
        prescreen_df["name"].str.contains("strength|dir_ret|open_impulse|trend_efficiency|cum_volume", case=False)
    ].head(6)

    for row in top_strength_candidates.itertuples(index=False):
        if row.name == "baseline_keep_all":
            continue
        spec = FilterSpec(
            name=str(row.name),
            apply_side=str(getattr(row, "side", "all")),
            min_strength_score=float(row.threshold) if "strength_score" in str(getattr(row, "column", "")) else None,
            min_dir_ret_15=float(row.threshold) if "dir_ret_15" in str(getattr(row, "column", "")) else None,
            min_open_impulse=float(row.threshold) if "open_impulse" in str(getattr(row, "column", "")) else None,
            min_trend_efficiency_15=(
                float(row.threshold) if "trend_efficiency" in str(getattr(row, "column", "")) else None
            ),
            min_cum_volume_rel=float(row.threshold) if "cum_volume_rel" in str(getattr(row, "column", "")) else None,
        )
        if spec not in integrated_specs:
            integrated_specs.append(spec)
        if len(integrated_specs) >= 6:
            break

    integrated_rows = [
        integrated_backtest_result(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            strength_frame=strength_frame,
            spec=spec,
        )
        for spec in integrated_specs
    ]
    integrated_df = pd.DataFrame(integrated_rows)
    base_integrated = integrated_df.loc[integrated_df["name"] == "baseline"].iloc[0]
    integrated_df["test_pf_delta"] = integrated_df["test_profit_factor"] - float(base_integrated["test_profit_factor"])
    integrated_df["test_avg_delta"] = integrated_df["test_avg_profit_brl"] - float(base_integrated["test_avg_profit_brl"])
    integrated_df["test_net_delta"] = integrated_df["test_net_profit_brl"] - float(base_integrated["test_net_profit_brl"])
    integrated_df = integrated_df.sort_values(
        ["test_pf_delta", "test_avg_delta", "test_net_delta"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    walkforward_frames = [
        walkforward_result(
            dataset=dataset,
            params=params,
            strength_frame=strength_frame,
            spec=spec,
            trade_dates=trade_dates,
            folds=args.walkforward_folds,
        )
        for spec in integrated_specs
    ]
    walkforward_df = pd.concat(walkforward_frames, ignore_index=True)

    recommended = integrated_df.iloc[0].to_dict()
    summary = {
        "data_source": str(dataset.bars_m1.attrs.get("source_path", "")),
        "baseline_metrics": base_metrics,
        "train_start": pd.Timestamp(train_dates_idx[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates_idx[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates_idx[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates_idx[-1]).date().isoformat(),
        "top_prescreen_candidates": prescreen_df.head(12).to_dict(orient="records"),
        "integrated_candidates": integrated_df.to_dict(orient="records"),
        "recommended_candidate": recommended,
    }

    with open(args.output_dir / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    trade_features.to_csv(args.output_dir / "baseline_trade_strength_features.csv", index=False)
    prescreen_df.to_csv(args.output_dir / "prescreen_results.csv", index=False)
    integrated_df.to_csv(args.output_dir / "integrated_results.csv", index=False)
    walkforward_df.to_csv(args.output_dir / "walkforward_results.csv", index=False)

    print("BASELINE", json.dumps(base_metrics, indent=2))
    print("\nTOP PRESCREEN")
    print(
        prescreen_df[
            [
                "name",
                "kept_trades",
                "removed_trades",
                "test_net_profit_brl",
                "test_avg_profit_brl",
                "test_profit_factor",
                "test_win_rate",
                "test_pf_delta",
                "test_avg_delta",
            ]
        ]
        .head(12)
        .to_string(index=False)
    )
    print("\nINTEGRATED")
    print(
        integrated_df[
            [
                "name",
                "test_trades",
                "test_net_profit_brl",
                "test_avg_profit_brl",
                "test_profit_factor",
                "test_win_rate",
                "test_max_drawdown_pct",
                "test_pf_delta",
                "test_avg_delta",
                "test_net_delta",
            ]
        ].to_string(index=False)
    )
    print("\nOUTPUT_DIR", args.output_dir)


if __name__ == "__main__":
    main()
