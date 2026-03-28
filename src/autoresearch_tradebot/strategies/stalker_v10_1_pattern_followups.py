from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..common.paths import ARTIFACTS_DIR, MT5_TESTER_PROFILES_DIR, artifact_output_dir
from .stalker_v10_1_followup_screening import (
    attach_analysis_notes,
    build_directional_deviation_array,
    build_leaderboard_rows,
    build_prev_m15_ema50_array,
    build_session_vwap_prev_array,
    combine_filters,
    load_existing_leaderboard,
    load_pattern_analysis,
    make_directional_value_range_filter,
    normalize_trades,
)
from .stalker_v10_1_optimization_screening import render_preset, robust_baseline_params
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"
DEFAULT_LOSS_ANALYSIS_DIR = ARTIFACTS_DIR / "outputs" / "stalker_v10_1_mt5_loss_analysis"
DEFAULT_HOLDOUT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_skip_short_hour13_holdout_20260328")
DEFAULT_DEVIATION_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_directional_deviation_holdout_20260328")
HOLDOUT_SPLIT_RATIO = 0.70

SKIP_SHORT_HOUR13_PRESET = (
    MT5_TESTER_PROFILES_DIR / "WDO Stalker Strategy v10.1 Robust Skip Short Hour 13 GPT 5.4.set"
)
DIRECTIONAL_TIMING_PRESET = (
    MT5_TESTER_PROFILES_DIR
    / "WDO Stalker Strategy v10.1 Robust Skip Short Wednesday Short Hour 13 Last30m GPT 5.4.set"
)


def run_candidate(
    dataset: V10Dataset,
    params: V101Params,
    trade_dates: pd.Index,
    entry_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    trades_df, _ = run_backtest(dataset, params, trade_dates, entry_filter=entry_filter)
    normalized = normalize_trades(trades_df)
    return normalized, calculate_metrics(normalized, trade_dates)


def result_record(
    *,
    name: str,
    family: str,
    metrics: dict[str, Any],
    mt5_ready: bool,
    notes: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "family": family,
        "metrics": {"test": metrics},
        "mt5_ready": mt5_ready,
        "notes": notes,
    }


def refresh_ranks(leaderboard: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for rank, row in enumerate(leaderboard, start=1):
        row["rank"] = rank
    return leaderboard


def update_row_metadata(leaderboard: list[dict[str, Any]], name: str, **extra: Any) -> None:
    for row in leaderboard:
        if str(row.get("name")) == name:
            row.update(extra)
            return


def write_preset(path: Path, params: V101Params) -> None:
    path.write_text(render_preset(asdict(params)), encoding="utf-8")


def robust_params() -> V101Params:
    return robust_baseline_params()


def skip_short_hour13_params() -> V101Params:
    payload = asdict(robust_baseline_params())
    payload["SkipShortHour13"] = True
    return V101Params(**payload)


def directional_timing_params() -> V101Params:
    payload = asdict(robust_baseline_params())
    payload["LastEntry_Hour"] = 14
    payload["LastEntry_Minute"] = 30
    payload["SkipShortWednesday"] = True
    payload["SkipShortHour13"] = True
    return V101Params(**payload)


def holdout_dates(dataset: V10Dataset) -> tuple[pd.Index, pd.Index]:
    return split_dates(dataset.trade_dates, HOLDOUT_SPLIT_RATIO)


def run_skip_short_hour13_holdout(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(args.data_path))
    train_dates, test_dates = holdout_dates(dataset)

    baseline_params = robust_params()
    candidate_params = skip_short_hour13_params()
    _, baseline_metrics = run_candidate(dataset, baseline_params, test_dates)
    _, candidate_metrics = run_candidate(dataset, candidate_params, test_dates)

    write_preset(SKIP_SHORT_HOUR13_PRESET, candidate_params)

    summary = {
        "data_source": str(locate_data_file(args.data_path)),
        "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
        "robust_baseline_test": baseline_metrics,
        "skip_short_hour13_test": candidate_metrics,
        "delta_vs_baseline_test": {
            "net_profit_brl": float(candidate_metrics["net_profit_brl"] - baseline_metrics["net_profit_brl"]),
            "profit_factor": float(candidate_metrics["profit_factor"] - baseline_metrics["profit_factor"]),
            "max_drawdown_pct": float(candidate_metrics["max_drawdown_pct"] - baseline_metrics["max_drawdown_pct"]),
            "win_rate": float(candidate_metrics["win_rate"] - baseline_metrics["win_rate"]),
            "on_tester_value": float(candidate_metrics["on_tester_value"] - baseline_metrics["on_tester_value"]),
        },
        "preset_path": str(SKIP_SHORT_HOUR13_PRESET.resolve()),
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard = load_existing_leaderboard(args.leaderboard_path)
    leaderboard = build_leaderboard_rows(
        leaderboard,
        [
            result_record(
                name="robust_skip_short_hour13_holdout",
                family="directional_timing_holdout",
                metrics=candidate_metrics,
                mt5_ready=True,
                notes="Holdout-only test of blocking short entries during the 13:00 hour.",
            )
        ],
        baseline_metrics,
    )
    pattern_analysis = load_pattern_analysis(args.loss_analysis_dir)
    leaderboard = attach_analysis_notes(leaderboard, pattern_analysis)
    update_row_metadata(
        leaderboard,
        "robust_skip_short_hour13_holdout",
        screening_method="integrated_backtest_holdout",
        preset_name="WDO Stalker Strategy v10.1 Robust Skip Short Hour 13 GPT 5.4",
        preset_path=str(SKIP_SHORT_HOUR13_PRESET.resolve()),
        source_artifact=str(summary_path.resolve()),
    )
    refresh_ranks(leaderboard)
    args.leaderboard_path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
    return summary


def run_directional_deviation_holdouts(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(args.data_path))
    train_dates, test_dates = holdout_dates(dataset)

    baseline_params = robust_params()
    reference_params = directional_timing_params()

    _, baseline_metrics = run_candidate(dataset, baseline_params, test_dates)
    _, reference_metrics = run_candidate(dataset, reference_params, test_dates)

    vwap_directional = build_directional_deviation_array(dataset, build_session_vwap_prev_array(dataset))
    ema50_directional = build_directional_deviation_array(dataset, build_prev_m15_ema50_array(dataset))

    candidates = [
        (
            "robust_skip_short_wednesday_short_hour13_last30m_plus_vwap_sweetspot_holdout",
            "directional_deviation_holdout",
            {"min_directional_vwap_dev_pts": 17.336, "max_directional_vwap_dev_pts": 22.117},
            make_directional_value_range_filter(vwap_directional, 17.336, 22.117),
            "Holdout test of the directional timing winner plus the trade-tape VWAP sweet spot.",
        ),
        (
            "robust_skip_short_wednesday_short_hour13_last30m_plus_ema50_sweetspot_holdout",
            "directional_deviation_holdout",
            {"min_directional_ema50_dev_pts": 2.091, "max_directional_ema50_dev_pts": 12.423},
            make_directional_value_range_filter(ema50_directional, 2.091, 12.423),
            "Holdout test of the directional timing winner plus the trade-tape EMA50 sweet spot.",
        ),
        (
            "robust_skip_short_wednesday_short_hour13_last30m_plus_vwap_ema_sweetspots_holdout",
            "directional_deviation_holdout",
            {
                "min_directional_vwap_dev_pts": 17.336,
                "max_directional_vwap_dev_pts": 22.117,
                "min_directional_ema50_dev_pts": 2.091,
                "max_directional_ema50_dev_pts": 12.423,
            },
            combine_filters(
                make_directional_value_range_filter(vwap_directional, 17.336, 22.117),
                make_directional_value_range_filter(ema50_directional, 2.091, 12.423),
            ),
            "Holdout test of the directional timing winner plus both tape-derived price-location sweet spots.",
        ),
    ]

    records = [
        result_record(
            name="robust_skip_short_wednesday_short_hour13_last30m_holdout",
            family="directional_timing_holdout",
            metrics=reference_metrics,
            mt5_ready=True,
            notes="Holdout-only test of the strongest directional timing stack.",
        )
    ]

    run_results: list[dict[str, Any]] = []
    for name, family, config, entry_filter, notes in candidates:
        _, metrics = run_candidate(dataset, reference_params, test_dates, entry_filter=entry_filter)
        run_results.append(
            {
                "name": name,
                "family": family,
                "config": config,
                "metrics": metrics,
                "notes": notes,
                "delta_vs_reference_test": {
                    "net_profit_brl": float(metrics["net_profit_brl"] - reference_metrics["net_profit_brl"]),
                    "profit_factor": float(metrics["profit_factor"] - reference_metrics["profit_factor"]),
                    "max_drawdown_pct": float(metrics["max_drawdown_pct"] - reference_metrics["max_drawdown_pct"]),
                    "win_rate": float(metrics["win_rate"] - reference_metrics["win_rate"]),
                    "on_tester_value": float(metrics["on_tester_value"] - reference_metrics["on_tester_value"]),
                },
            }
        )
        records.append(
            result_record(
                name=name,
                family=family,
                metrics=metrics,
                mt5_ready=False,
                notes=notes,
            )
        )

    summary = {
        "data_source": str(locate_data_file(args.data_path)),
        "train_start": pd.Timestamp(train_dates[0]).date().isoformat(),
        "train_end": pd.Timestamp(train_dates[-1]).date().isoformat(),
        "test_start": pd.Timestamp(test_dates[0]).date().isoformat(),
        "test_end": pd.Timestamp(test_dates[-1]).date().isoformat(),
        "robust_baseline_test": baseline_metrics,
        "directional_timing_reference_test": reference_metrics,
        "new_records": run_results,
        "reference_preset_path": str(DIRECTIONAL_TIMING_PRESET.resolve()),
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard = load_existing_leaderboard(args.leaderboard_path)
    leaderboard = build_leaderboard_rows(leaderboard, records, baseline_metrics)
    pattern_analysis = load_pattern_analysis(args.loss_analysis_dir)
    leaderboard = attach_analysis_notes(leaderboard, pattern_analysis)
    update_row_metadata(
        leaderboard,
        "robust_skip_short_wednesday_short_hour13_last30m_holdout",
        screening_method="integrated_backtest_holdout",
        preset_name="WDO Stalker Strategy v10.1 Robust Skip Short Wednesday Short Hour 13 Last30m GPT 5.4",
        preset_path=str(DIRECTIONAL_TIMING_PRESET.resolve()),
        source_artifact=str(summary_path.resolve()),
    )
    for candidate in run_results:
        update_row_metadata(
            leaderboard,
            candidate["name"],
            screening_method="integrated_backtest_holdout",
            source_artifact=str(summary_path.resolve()),
        )
    refresh_ranks(leaderboard)
    args.leaderboard_path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Focused Stalker v10.1 pattern follow-ups.")
    parser.add_argument(
        "--task",
        choices=("skip_short_hour13_holdout", "directional_deviation_holdouts"),
        required=True,
    )
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--leaderboard-path", type=Path, default=DEFAULT_LEADERBOARD_PATH)
    parser.add_argument("--loss-analysis-dir", type=Path, default=DEFAULT_LOSS_ANALYSIS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.output_dir is None:
        args.output_dir = (
            DEFAULT_HOLDOUT_OUTPUT_DIR
            if args.task == "skip_short_hour13_holdout"
            else DEFAULT_DEVIATION_OUTPUT_DIR
        )

    if args.task == "skip_short_hour13_holdout":
        summary = run_skip_short_hour13_holdout(args)
    else:
        summary = run_directional_deviation_holdouts(args)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
