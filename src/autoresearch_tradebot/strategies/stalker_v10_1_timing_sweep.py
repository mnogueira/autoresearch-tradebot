from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..common.paths import ARTIFACTS_DIR, MT5_TESTER_PROFILES_DIR, artifact_output_dir
from .stalker_v10_1_optimization_screening import render_preset, robust_baseline_params
from .stalker_v10_1_python import V101Params, run_backtest
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_timing_sweep")
DEFAULT_LEADERBOARD_PATH = ARTIFACTS_DIR / "leaderboard.json"


def make_hour_exclusion_filter(excluded_hours: set[int]) -> Callable[[dict[str, Any]], bool]:
    blocked = {int(hour) for hour in excluded_hours}

    def allow(context: dict[str, Any]) -> bool:
        return int(context["entry_hour"]) not in blocked

    return allow


def make_friday_afternoon_filter(start_hour: int = 13) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        weekday = int(context["weekday"])
        entry_hour = int(context["entry_hour"])
        return not (weekday == 4 and entry_hour >= int(start_hour))

    return allow


def candidate_specs(baseline: V101Params) -> list[dict[str, Any]]:
    payload = asdict(baseline)
    relvol_payload = {
        **payload,
        "RelativeVolumeLookbackDays": 20,
        "ApplyRelativeVolumeFilterToShorts": True,
        "MinRelativeVolumeAtTime": 0.85,
    }
    return [
        {
            "name": "robust_timing_baseline_full",
            "params": baseline,
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Full-period robust timing reference.",
            "preset_name": None,
        },
        {
            "name": "robust_skip_wednesday_full",
            "params": V101Params(**{**payload, "SkipWednesday": True}),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Wednesday only.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Skip Wednesday GPT 5.4",
        },
        {
            "name": "robust_skip_hour_13_full",
            "params": V101Params(**{**payload, "SkipHour13": True}),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip entries during the 13:00 hour only.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Skip Hour 13 GPT 5.4",
        },
        {
            "name": "robust_skip_wednesday_hour_13_full",
            "params": V101Params(**{**payload, "SkipWednesday": True, "SkipHour13": True}),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Wednesday and the 13:00 hour.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Timing Edge GPT 5.4",
        },
        {
            "name": "robust_skip_wednesday_hours_13_14_full",
            "params": V101Params(
                **{
                    **payload,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                    "SkipHour14": True,
                }
            ),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Wednesday and the 13:00-14:59 window.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Skip Wednesday 13-14 GPT 5.4",
        },
        {
            "name": "robust_skip_tuesday_wednesday_hour_13_full",
            "params": V101Params(
                **{
                    **payload,
                    "AllowTuesday": False,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                }
            ),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Tuesday, Wednesday, and the 13:00 hour.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Skip Tuesday Wednesday Hour 13 GPT 5.4",
        },
        {
            "name": "robust_skip_friday_afternoon_full",
            "params": baseline,
            "entry_filter": make_friday_afternoon_filter(13),
            "mt5_ready": False,
            "notes": "Skip Friday entries at 13:00 or later.",
            "preset_name": None,
        },
        {
            "name": "robust_skip_wednesday_hour_13_relvol_short_lb20_ge_0.85_full",
            "params": V101Params(
                **{
                    **relvol_payload,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                }
            ),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Wednesday plus 13:00, then add the best short-side relative-volume confirmation.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Timing RelVol Edge GPT 5.4",
        },
        {
            "name": "robust_skip_wednesday_hours_13_14_relvol_short_lb20_ge_0.85_full",
            "params": V101Params(
                **{
                    **relvol_payload,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                    "SkipHour14": True,
                }
            ),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Wednesday plus the 13:00-14:59 window, then add the best short-side relative-volume confirmation.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Timing RelVol 13-14 GPT 5.4",
        },
        {
            "name": "robust_skip_friday_afternoon_relvol_short_lb20_ge_0.85_full",
            "params": V101Params(**relvol_payload),
            "entry_filter": make_friday_afternoon_filter(13),
            "mt5_ready": False,
            "notes": "Skip Friday afternoon, then add the best short-side relative-volume confirmation.",
            "preset_name": None,
        },
        {
            "name": "robust_skip_wednesday_hour_13_plus_last_30m_full",
            "params": V101Params(
                **{
                    **payload,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                    "LastEntry_Hour": 14,
                    "LastEntry_Minute": 30,
                }
            ),
            "entry_filter": None,
            "mt5_ready": True,
            "notes": "Skip Wednesday, skip the 13:00 hour, and stop taking new entries after 14:30.",
            "preset_name": "WDO Stalker Strategy v10.1 Robust Timing Stack GPT 5.4",
        },
    ]


def merge_into_leaderboard(
    leaderboard_path: Path,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = json.loads(leaderboard_path.read_text(encoding="utf-8")) if leaderboard_path.exists() else []
    merged = {entry["name"]: entry for entry in existing if isinstance(entry, dict) and "name" in entry}
    for row in rows:
        merged[row["name"]] = row
    leaderboard = list(merged.values())
    leaderboard.sort(
        key=lambda row: (
            float(row.get("test_on_tester_value", 0.0)),
            float(row.get("test_profit_factor", 0.0)),
            float(row.get("test_net_profit_brl", 0.0)),
            -float(row.get("test_max_drawdown_pct", 0.0)),
        ),
        reverse=True,
    )
    for rank, row in enumerate(leaderboard, start=1):
        row["rank"] = rank
    leaderboard_path.write_text(json.dumps(leaderboard, indent=2), encoding="utf-8")
    return leaderboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Full-period timing sweep for Stalker v10.1.")
    parser.add_argument("--data-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--leaderboard-path", type=Path, default=DEFAULT_LEADERBOARD_PATH)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    MT5_TESTER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    data_path = locate_data_file(args.data_path)
    dataset = V10Dataset.from_disk(data_path)
    trade_dates = dataset.trade_dates
    baseline = robust_baseline_params()

    results: list[dict[str, Any]] = []
    for spec in candidate_specs(baseline):
        trades_df, _ = run_backtest(dataset, spec["params"], trade_dates, entry_filter=spec["entry_filter"])
        metrics = calculate_metrics(trades_df, trade_dates)
        results.append(
            {
                "name": spec["name"],
                "notes": spec["notes"],
                "mt5_ready": bool(spec["mt5_ready"]),
                "preset_name": spec["preset_name"],
                "params": asdict(spec["params"]),
                "metrics": metrics,
            }
        )

    baseline_metrics = next(row["metrics"] for row in results if row["name"] == "robust_timing_baseline_full")
    leaderboard_rows: list[dict[str, Any]] = []
    for row in results:
        metrics = row["metrics"]
        delta_net = float(metrics["net_profit_brl"]) - float(baseline_metrics["net_profit_brl"])
        delta_pf = float(metrics["profit_factor"]) - float(baseline_metrics["profit_factor"])
        delta_dd = float(metrics["max_drawdown_pct"]) - float(baseline_metrics["max_drawdown_pct"])
        beats_baseline = (
            float(metrics["net_profit_brl"]) >= float(baseline_metrics["net_profit_brl"])
            and float(metrics["profit_factor"]) >= float(baseline_metrics["profit_factor"])
            and float(metrics["max_drawdown_pct"]) <= float(baseline_metrics["max_drawdown_pct"])
        )
        if row["mt5_ready"] and row["preset_name"]:
            preset_path = MT5_TESTER_PROFILES_DIR / f"{row['preset_name']}.set"
            preset_path.write_text(render_preset(row["params"]), encoding="utf-8")
            row["preset_path"] = str(preset_path.resolve())

        leaderboard_rows.append(
            {
                "name": row["name"],
                "family": "timing_sweep_full_period",
                "screening_method": "integrated_backtest_full_period",
                "quality_tier": 1,
                "mt5_ready": row["mt5_ready"],
                "preset_name": row["preset_name"],
                "test_total_trades": metrics["total_trades"],
                "test_net_profit_brl": metrics["net_profit_brl"],
                "test_profit_factor": metrics["profit_factor"],
                "test_on_tester_value": metrics["on_tester_value"],
                "test_max_drawdown_pct": metrics["max_drawdown_pct"],
                "test_win_rate": metrics["win_rate"],
                "delta_vs_baseline_test_net": round(delta_net, 2),
                "delta_vs_baseline_test_pf": round(delta_pf, 4),
                "delta_vs_baseline_test_dd": round(delta_dd, 2),
                "beats_baseline": beats_baseline,
                "notes": row["notes"],
                "preset_path": row.get("preset_path"),
            }
        )

    results.sort(
        key=lambda row: (
            float(row["metrics"]["on_tester_value"]),
            float(row["metrics"]["profit_factor"]),
            float(row["metrics"]["net_profit_brl"]),
            -float(row["metrics"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )

    summary = {
        "data_source": str(data_path),
        "period_start": pd.Timestamp(trade_dates.min()).date().isoformat(),
        "period_end": pd.Timestamp(trade_dates.max()).date().isoformat(),
        "results": results,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    updated_leaderboard = merge_into_leaderboard(args.leaderboard_path, leaderboard_rows)
    print(
        json.dumps(
            {
                "summary_path": str((args.output_dir / "summary.json").resolve()),
                "top_results": [
                    {
                        "name": row["name"],
                        "metrics": row["metrics"],
                    }
                    for row in results[:5]
                ],
                "leaderboard_count": len(updated_leaderboard),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
