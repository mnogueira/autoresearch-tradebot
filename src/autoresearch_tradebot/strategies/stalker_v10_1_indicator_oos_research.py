from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_indicator_oos_research")


@dataclass(frozen=True)
class IndicatorConfig:
    name: str
    family: str
    trend_mode: str = "off"
    trend_window: int = 15
    trend_min: float = 0.0
    volume_mode: str = "off"
    volume_window: int = 15
    volume_min: float = 0.0
    relvol_mode: str = "off"
    relvol_lookback: int = 20
    relvol_min: float = 0.0


def mode_flags(mode: str) -> tuple[bool, bool]:
    normalized = str(mode).strip().lower()
    if normalized == "long":
        return True, False
    if normalized == "short":
        return False, True
    if normalized == "both":
        return True, True
    return False, False


def params_from_config(baseline: V101Params, config: IndicatorConfig) -> V101Params:
    trend_longs, trend_shorts = mode_flags(config.trend_mode)
    volume_longs, volume_shorts = mode_flags(config.volume_mode)
    relvol_longs, relvol_shorts = mode_flags(config.relvol_mode)
    return replace(
        baseline,
        TrendEfficiencyWindowMinutes=int(config.trend_window),
        ApplyTrendEfficiencyFilterToLongs=trend_longs,
        ApplyTrendEfficiencyFilterToShorts=trend_shorts,
        MinDirectionalTrendEfficiency15m=float(config.trend_min),
        VolumeWindowMinutes=int(config.volume_window),
        ApplyVolumeFilterToLongs=volume_longs,
        ApplyVolumeFilterToShorts=volume_shorts,
        MinSignalVolumeWindowSum=float(config.volume_min),
        RelativeVolumeLookbackDays=int(config.relvol_lookback),
        ApplyRelativeVolumeFilterToLongs=relvol_longs,
        ApplyRelativeVolumeFilterToShorts=relvol_shorts,
        MinRelativeVolumeAtTime=float(config.relvol_min),
    )


def baseline_config() -> IndicatorConfig:
    return IndicatorConfig(name="baseline", family="baseline")


def build_single_configs() -> list[IndicatorConfig]:
    configs: list[IndicatorConfig] = []

    trend_thresholds = [0.0, 0.15, 0.25, 0.333333, 0.4, 0.5, 0.6]
    for mode in ("long", "short", "both"):
        for window in (10, 15, 20, 25, 30):
            for threshold in trend_thresholds:
                configs.append(
                    IndicatorConfig(
                        name=f"trend__{mode}__w{window}__ge_{threshold:.6f}",
                        family="trend",
                        trend_mode=mode,
                        trend_window=window,
                        trend_min=threshold,
                    )
                )

    volume_thresholds = [25_000.0, 30_000.0, 35_000.0, 40_000.0, 45_000.0, 50_000.0, 55_000.0]
    for mode in ("long", "short", "both"):
        for window in (10, 15, 20, 25, 30):
            for threshold in volume_thresholds:
                configs.append(
                    IndicatorConfig(
                        name=f"volume__{mode}__w{window}__ge_{int(threshold)}",
                        family="volume",
                        volume_mode=mode,
                        volume_window=window,
                        volume_min=threshold,
                    )
                )

    relvol_thresholds = [0.85, 0.95, 1.05, 1.15, 1.25, 1.35]
    for mode in ("long", "short", "both"):
        for lookback in (10, 20, 30, 40, 60):
            for threshold in relvol_thresholds:
                configs.append(
                    IndicatorConfig(
                        name=f"relvol__{mode}__lb{lookback}__ge_{threshold:.2f}",
                        family="relvol",
                        relvol_mode=mode,
                        relvol_lookback=lookback,
                        relvol_min=threshold,
                    )
                )

    return configs


def combine_configs(
    trend: IndicatorConfig | None,
    volume: IndicatorConfig | None,
    relvol: IndicatorConfig | None,
) -> IndicatorConfig:
    parts = [
        config.name
        for config in (trend, volume, relvol)
        if config is not None and config.family in {"trend", "volume", "relvol"}
    ]
    return IndicatorConfig(
        name="combo__" + "__".join(parts),
        family="combo",
        trend_mode=trend.trend_mode if trend is not None else "off",
        trend_window=trend.trend_window if trend is not None else 15,
        trend_min=trend.trend_min if trend is not None else 0.0,
        volume_mode=volume.volume_mode if volume is not None else "off",
        volume_window=volume.volume_window if volume is not None else 15,
        volume_min=volume.volume_min if volume is not None else 0.0,
        relvol_mode=relvol.relvol_mode if relvol is not None else "off",
        relvol_lookback=relvol.relvol_lookback if relvol is not None else 20,
        relvol_min=relvol.relvol_min if relvol is not None else 0.0,
    )


def build_combo_configs(
    top_trend: list[IndicatorConfig],
    top_volume: list[IndicatorConfig],
    top_relvol: list[IndicatorConfig],
) -> list[IndicatorConfig]:
    combos: list[IndicatorConfig] = []
    seen: set[IndicatorConfig] = set()

    for trend in top_trend:
        for volume in top_volume:
            config = combine_configs(trend, volume, None)
            if config not in seen:
                seen.add(config)
                combos.append(config)

    for trend in top_trend:
        for relvol in top_relvol:
            config = combine_configs(trend, None, relvol)
            if config not in seen:
                seen.add(config)
                combos.append(config)

    for volume in top_volume:
        for relvol in top_relvol:
            config = combine_configs(None, volume, relvol)
            if config not in seen:
                seen.add(config)
                combos.append(config)

    for trend in top_trend:
        for volume in top_volume:
            for relvol in top_relvol:
                config = combine_configs(trend, volume, relvol)
                if config not in seen:
                    seen.add(config)
                    combos.append(config)

    return combos


def build_anchored_walkforward_splits(trade_dates: pd.Index, folds: int) -> list[dict[str, Any]]:
    partitions = [pd.Index(part) for part in np.array_split(trade_dates, folds) if len(part) > 0]
    splits: list[dict[str, Any]] = []
    for fold_number in range(1, len(partitions)):
        train_dates = pd.Index(np.concatenate([partitions[idx].to_numpy() for idx in range(fold_number)]))
        test_dates = partitions[fold_number]
        splits.append(
            {
                "fold": fold_number,
                "train_dates": train_dates,
                "test_dates": test_dates,
            }
        )
    return splits


def evaluate_config(
    dataset: V10Dataset,
    baseline: V101Params,
    config: IndicatorConfig,
    trade_dates: pd.Index,
    train_dates: pd.Index,
    test_dates: pd.Index,
    walkforward_splits: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    params = params_from_config(baseline, config)
    trades_df, full_metrics = run_backtest(dataset, params, trade_dates)
    if not trades_df.empty:
        trades_df = trades_df.copy()
        trades_df["session_date"] = pd.to_datetime(trades_df["session_date"]).dt.normalize()

    train_date_set = set(pd.to_datetime(train_dates).normalize())
    test_date_set = set(pd.to_datetime(test_dates).normalize())

    train_trades = trades_df[trades_df["session_date"].isin(train_date_set)].copy() if not trades_df.empty else trades_df
    test_trades = trades_df[trades_df["session_date"].isin(test_date_set)].copy() if not trades_df.empty else trades_df

    train_metrics = calculate_metrics(train_trades, train_dates)
    test_metrics = calculate_metrics(test_trades, test_dates)

    walkforward_rows: list[dict[str, Any]] = []
    for split in walkforward_splits:
        wf_test_dates = split["test_dates"]
        wf_test_date_set = set(pd.to_datetime(wf_test_dates).normalize())
        wf_trades = trades_df[trades_df["session_date"].isin(wf_test_date_set)].copy() if not trades_df.empty else trades_df
        wf_metrics = calculate_metrics(wf_trades, wf_test_dates)
        walkforward_rows.append(
            {
                "name": config.name,
                "family": config.family,
                "fold": int(split["fold"]),
                "start_date": pd.Timestamp(wf_test_dates[0]).date().isoformat(),
                "end_date": pd.Timestamp(wf_test_dates[-1]).date().isoformat(),
                **wf_metrics,
            }
        )

    summary_row = {
        "name": config.name,
        "family": config.family,
        "config": json.dumps(asdict(config), ensure_ascii=True, sort_keys=True),
        "params": json.dumps(asdict(params), ensure_ascii=True, sort_keys=True),
    }
    for prefix, metrics in (
        ("all", full_metrics),
        ("train", train_metrics),
        ("test", test_metrics),
    ):
        for key, value in metrics.items():
            summary_row[f"{prefix}_{key}"] = value
    return summary_row, walkforward_rows


def select_top_family_configs(results_df: pd.DataFrame, top_k: int) -> dict[str, list[IndicatorConfig]]:
    selected: dict[str, list[IndicatorConfig]] = {}
    for family in ("trend", "volume", "relvol"):
        family_df = results_df[results_df["family"] == family].copy()
        family_df = family_df.sort_values(
            ["train_on_tester_value", "train_avg_profit_brl", "train_profit_factor", "train_net_profit_brl"],
            ascending=[False, False, False, False],
        )
        top_configs = family_df.head(top_k)["config"].tolist()
        selected[family] = [IndicatorConfig(**json.loads(config_json)) for config_json in top_configs]
    return selected


def add_baseline_deltas(results_df: pd.DataFrame) -> pd.DataFrame:
    baseline_row = results_df.loc[results_df["name"] == "baseline"].iloc[0]
    for prefix in ("train", "test", "all"):
        results_df[f"{prefix}_net_delta"] = results_df[f"{prefix}_net_profit_brl"] - float(
            baseline_row[f"{prefix}_net_profit_brl"]
        )
        results_df[f"{prefix}_avg_delta"] = results_df[f"{prefix}_avg_profit_brl"] - float(
            baseline_row[f"{prefix}_avg_profit_brl"]
        )
        results_df[f"{prefix}_pf_delta"] = results_df[f"{prefix}_profit_factor"] - float(
            baseline_row[f"{prefix}_profit_factor"]
        )
        results_df[f"{prefix}_dd_delta"] = results_df[f"{prefix}_max_drawdown_pct"] - float(
            baseline_row[f"{prefix}_max_drawdown_pct"]
        )
        results_df[f"{prefix}_on_tester_delta"] = results_df[f"{prefix}_on_tester_value"] - float(
            baseline_row[f"{prefix}_on_tester_value"]
        )
    return results_df


def summarize_walkforward(
    walkforward_df: pd.DataFrame,
    baseline_name: str,
    candidate_names: list[str],
) -> pd.DataFrame:
    baseline_folds = walkforward_df[walkforward_df["name"] == baseline_name].copy()
    rows: list[dict[str, Any]] = []
    for name in candidate_names:
        candidate_folds = walkforward_df[walkforward_df["name"] == name].copy()
        if candidate_folds.empty:
            continue
        merged = candidate_folds.merge(
            baseline_folds[
                [
                    "fold",
                    "net_profit_brl",
                    "avg_profit_brl",
                    "profit_factor",
                    "max_drawdown_pct",
                    "on_tester_value",
                ]
            ].rename(
                columns={
                    "net_profit_brl": "baseline_net_profit_brl",
                    "avg_profit_brl": "baseline_avg_profit_brl",
                    "profit_factor": "baseline_profit_factor",
                    "max_drawdown_pct": "baseline_max_drawdown_pct",
                    "on_tester_value": "baseline_on_tester_value",
                }
            ),
            on="fold",
            how="left",
        )
        rows.append(
            {
                "name": name,
                "folds": int(len(merged)),
                "positive_folds": int((merged["net_profit_brl"] > 0.0).sum()),
                "wins_vs_baseline_net": int((merged["net_profit_brl"] > merged["baseline_net_profit_brl"]).sum()),
                "wins_vs_baseline_pf": int((merged["profit_factor"] > merged["baseline_profit_factor"]).sum()),
                "mean_net_profit_brl": float(merged["net_profit_brl"].mean()),
                "mean_avg_profit_brl": float(merged["avg_profit_brl"].mean()),
                "mean_profit_factor": float(merged["profit_factor"].mean()),
                "mean_max_drawdown_pct": float(merged["max_drawdown_pct"].mean()),
                "mean_on_tester_value": float(merged["on_tester_value"].mean()),
            }
        )
    return pd.DataFrame(rows)


def find_robust_winners(
    candidates_df: pd.DataFrame,
    walkforward_summary_df: pd.DataFrame,
) -> pd.DataFrame:
    merged = candidates_df.merge(walkforward_summary_df, on="name", how="left")
    required_fold_wins = np.ceil(merged["folds"].fillna(0).astype(float) / 2.0)
    robust = merged[
        (merged["name"] != "baseline")
        & (merged["test_net_delta"] > 0.0)
        & (merged["test_avg_delta"] > 0.0)
        & (merged["test_pf_delta"] > 0.0)
        & (merged["test_dd_delta"] <= 0.0)
        & (merged["wins_vs_baseline_net"] >= required_fold_wins)
        & (merged["positive_folds"] >= required_fold_wins)
    ].copy()
    return robust.sort_values(
        ["test_on_tester_value", "test_net_profit_brl", "test_profit_factor"],
        ascending=[False, False, False],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Systematic OOS indicator research for WDO Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--walkforward-folds", type=int, default=6)
    parser.add_argument("--top-k-per-family", type=int, default=4)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(args.data_path or locate_data_file())
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, args.train_ratio)
    walkforward_splits = build_anchored_walkforward_splits(trade_dates, args.walkforward_folds)

    baseline = V101Params()
    baseline_row, baseline_walkforward = evaluate_config(
        dataset=dataset,
        baseline=baseline,
        config=baseline_config(),
        trade_dates=trade_dates,
        train_dates=train_dates,
        test_dates=test_dates,
        walkforward_splits=walkforward_splits,
    )

    single_configs = build_single_configs()
    single_rows = [baseline_row]
    walkforward_rows = list(baseline_walkforward)
    for config in single_configs:
        row, wf_rows = evaluate_config(
            dataset=dataset,
            baseline=baseline,
            config=config,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            walkforward_splits=walkforward_splits,
        )
        single_rows.append(row)
        walkforward_rows.extend(wf_rows)

    single_df = add_baseline_deltas(pd.DataFrame(single_rows))
    top_by_family = select_top_family_configs(single_df, args.top_k_per_family)
    combo_configs = build_combo_configs(
        top_trend=top_by_family["trend"],
        top_volume=top_by_family["volume"],
        top_relvol=top_by_family["relvol"],
    )

    combo_rows: list[dict[str, Any]] = []
    for config in combo_configs:
        row, wf_rows = evaluate_config(
            dataset=dataset,
            baseline=baseline,
            config=config,
            trade_dates=trade_dates,
            train_dates=train_dates,
            test_dates=test_dates,
            walkforward_splits=walkforward_splits,
        )
        combo_rows.append(row)
        walkforward_rows.extend(wf_rows)

    combo_df = add_baseline_deltas(pd.DataFrame([baseline_row] + combo_rows))
    all_candidates_df = (
        pd.concat([single_df, combo_df[combo_df["name"] != "baseline"]], ignore_index=True)
        .sort_values(
            ["test_on_tester_value", "test_net_profit_brl", "test_profit_factor"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
    )

    walkforward_df = pd.DataFrame(walkforward_rows)
    top_candidate_names = all_candidates_df["name"].tolist()
    walkforward_summary_df = summarize_walkforward(walkforward_df, "baseline", top_candidate_names)
    robust_df = find_robust_winners(all_candidates_df, walkforward_summary_df)

    family_best_rows: list[dict[str, Any]] = []
    for family in ("trend", "volume", "relvol", "combo"):
        family_df = all_candidates_df[all_candidates_df["family"] == family].copy()
        if family_df.empty:
            continue
        family_df = family_df.sort_values(
            ["train_on_tester_value", "train_avg_profit_brl", "train_profit_factor"],
            ascending=[False, False, False],
        )
        family_best_rows.append(family_df.iloc[0].to_dict())
    family_best_df = pd.DataFrame(family_best_rows)

    recommended_row = robust_df.iloc[0].to_dict() if not robust_df.empty else baseline_row
    summary = {
        "data_source": str(dataset.bars_m1.attrs.get("source_path", "")),
        "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
        "baseline": baseline_row,
        "single_indicator_count": int(len(single_df) - 1),
        "combo_indicator_count": int(len(combo_df) - 1),
        "family_best": family_best_df.to_dict(orient="records"),
        "top_holdout_candidates": all_candidates_df.head(15).to_dict(orient="records"),
        "robust_winners": robust_df.head(10).to_dict(orient="records"),
        "recommended": recommended_row,
    }

    with open(args.output_dir / "summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    single_df.to_csv(args.output_dir / "single_indicator_results.csv", index=False)
    combo_df.to_csv(args.output_dir / "combo_results.csv", index=False)
    all_candidates_df.to_csv(args.output_dir / "all_candidates_ranked.csv", index=False)
    family_best_df.to_csv(args.output_dir / "family_best.csv", index=False)
    walkforward_df.to_csv(args.output_dir / "walkforward_results.csv", index=False)
    walkforward_summary_df.to_csv(args.output_dir / "walkforward_summary.csv", index=False)
    robust_df.to_csv(args.output_dir / "robust_winners.csv", index=False)

    print("BASELINE")
    print(json.dumps(baseline_row, indent=2))
    print("\nFAMILY_BEST")
    if not family_best_df.empty:
        print(
            family_best_df[
                [
                    "family",
                    "name",
                    "train_on_tester_value",
                    "test_net_profit_brl",
                    "test_avg_profit_brl",
                    "test_profit_factor",
                    "test_max_drawdown_pct",
                    "test_net_delta",
                    "test_pf_delta",
                    "test_dd_delta",
                ]
            ].to_string(index=False)
        )
    print("\nROBUST_WINNERS")
    if robust_df.empty:
        print("None")
    else:
        print(
            robust_df[
                [
                    "family",
                    "name",
                    "test_net_profit_brl",
                    "test_avg_profit_brl",
                    "test_profit_factor",
                    "test_max_drawdown_pct",
                    "test_net_delta",
                    "test_pf_delta",
                    "test_dd_delta",
                    "wins_vs_baseline_net",
                    "positive_folds",
                ]
            ].to_string(index=False)
        )
    print("\nOUTPUT_DIR", args.output_dir)


if __name__ == "__main__":
    main()
