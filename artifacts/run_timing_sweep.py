from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autoresearch_tradebot.strategies.stalker_v10_1_optimization_screening import (  # noqa: E402
    render_preset,
    robust_baseline_params,
)
from autoresearch_tradebot.strategies.stalker_v10_1_python import (  # noqa: E402
    V101Params,
    run_backtest,
)
from autoresearch_tradebot.strategies.stalker_v10_python import locate_data_file  # noqa: E402


OUTPUT_DIR = ROOT / "artifacts" / "outputs" / "stalker_v10_1_timing_sweep_20260327"
LEADERBOARD_PATH = ROOT / "artifacts" / "leaderboard.json"
PRESET_DIR = ROOT / "mt5" / "profiles" / "tester"
PATTERN_PATH = ROOT / "artifacts" / "outputs" / "stalker_v10_1_pattern_analysis_20260327" / "summary.json"


def make_exclusion_filter(func: Callable[[dict[str, Any]], bool]) -> Callable[[dict[str, Any]], bool]:
    def allow(context: dict[str, Any]) -> bool:
        return bool(func(context))

    return allow


def load_pattern_notes() -> list[str]:
    if not PATTERN_PATH.exists():
        return []
    payload = json.loads(PATTERN_PATH.read_text(encoding="utf-8"))
    notes = payload.get("notes", [])
    return notes if isinstance(notes, list) else []


def candidate(
    name: str,
    params: V101Params,
    *,
    mt5_ready: bool,
    notes: str,
    preset_name: str | None = None,
    entry_filter: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "params": params,
        "mt5_ready": mt5_ready,
        "notes": notes,
        "preset_name": preset_name,
        "entry_filter": entry_filter,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PRESET_DIR.mkdir(parents=True, exist_ok=True)

    data_path = locate_data_file(None)
    dataset = __import__(
        "autoresearch_tradebot.strategies.stalker_v10_python",
        fromlist=["V10Dataset"],
    ).V10Dataset.from_disk(data_path)
    trade_dates = dataset.trade_dates
    pattern_notes = load_pattern_notes()

    base = robust_baseline_params()
    base_payload = asdict(base)

    candidates = [
        candidate(
            "robust_base_timing_ref",
            base,
            mt5_ready=True,
            notes="Full-period robust timing reference.",
            preset_name="WDO Stalker Strategy v10.1 EffVol Robust GPT 5.4",
        ),
        candidate(
            "robust_skip_wednesday",
            V101Params(**{**base_payload, "SkipWednesday": True}),
            mt5_ready=True,
            notes="Skip Wednesday only.",
            preset_name="WDO Stalker Strategy v10.1 Robust Skip Wednesday GPT 5.4",
        ),
        candidate(
            "robust_skip_hour_13",
            V101Params(**{**base_payload, "SkipHour13": True}),
            mt5_ready=True,
            notes="Skip the full 13:00-13:59 hour.",
            preset_name="WDO Stalker Strategy v10.1 Robust Skip Hour 13 GPT 5.4",
        ),
        candidate(
            "robust_skip_wed_hour_13",
            V101Params(**{**base_payload, "SkipWednesday": True, "SkipHour13": True}),
            mt5_ready=True,
            notes="Skip Wednesday and the full 13:00-13:59 hour.",
            preset_name="WDO Stalker Strategy v10.1 Robust Timing Edge GPT 5.4",
        ),
        candidate(
            "robust_skip_hours_13_14",
            V101Params(**{**base_payload, "SkipHour13": True, "SkipHour14": True}),
            mt5_ready=True,
            notes="Skip the full 13:00-14:59 lunch window.",
            preset_name="WDO Stalker Strategy v10.1 Robust Skip Hours 13 14 GPT 5.4",
        ),
        candidate(
            "robust_skip_tue_wed_hour_13",
            V101Params(
                **{
                    **base_payload,
                    "AllowTuesday": False,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                }
            ),
            mt5_ready=True,
            notes="Skip Tuesday, Wednesday, and the full 13:00-13:59 hour.",
            preset_name="WDO Stalker Strategy v10.1 Robust Skip Tuesday Wednesday Hour 13 GPT 5.4",
        ),
        candidate(
            "robust_skip_friday_afternoon",
            base,
            mt5_ready=False,
            notes="Screen-only filter: skip Friday entries from 13:00 onward.",
            entry_filter=make_exclusion_filter(
                lambda context: not (
                    int(context["weekday"]) == 4 and int(context["entry_hour"]) >= 13
                )
            ),
        ),
        candidate(
            "robust_skip_wed_hour_13_relvol_short_lb20_0p85",
            V101Params(
                **{
                    **base_payload,
                    "SkipWednesday": True,
                    "SkipHour13": True,
                    "RelativeVolumeLookbackDays": 20,
                    "ApplyRelativeVolumeFilterToShorts": True,
                    "MinRelativeVolumeAtTime": 0.85,
                }
            ),
            mt5_ready=True,
            notes="Timing edge plus short-side relative volume >= 0.85 with 20-day lookback.",
            preset_name="WDO Stalker Strategy v10.1 Robust Timing Edge RelVol Short LB20 0p85 GPT 5.4",
        ),
    ]

    results: list[dict[str, Any]] = []
    baseline_metrics: dict[str, Any] | None = None

    for spec in candidates:
        trades_df, metrics = run_backtest(
            dataset,
            spec["params"],
            trade_dates,
            entry_filter=spec["entry_filter"],
        )
        row = {
            "name": spec["name"],
            "mt5_ready": spec["mt5_ready"],
            "notes": spec["notes"],
            "preset_name": spec["preset_name"],
            "params": asdict(spec["params"]),
            "metrics": metrics,
            "total_trades_frame_rows": int(len(trades_df)),
        }
        if baseline_metrics is None:
            baseline_metrics = metrics
        row["delta_vs_baseline"] = {
            "net_profit_brl": round(float(metrics["net_profit_brl"]) - float(baseline_metrics["net_profit_brl"]), 2),
            "profit_factor": round(float(metrics["profit_factor"]) - float(baseline_metrics["profit_factor"]), 4),
            "max_drawdown_pct": round(float(metrics["max_drawdown_pct"]) - float(baseline_metrics["max_drawdown_pct"]), 2),
            "win_rate": round(float(metrics["win_rate"]) - float(baseline_metrics["win_rate"]), 4),
            "on_tester_value": round(float(metrics["on_tester_value"]) - float(baseline_metrics["on_tester_value"]), 4),
        }
        row["beats_baseline"] = bool(
            float(metrics["net_profit_brl"]) >= float(baseline_metrics["net_profit_brl"])
            and float(metrics["profit_factor"]) >= float(baseline_metrics["profit_factor"])
            and float(metrics["max_drawdown_pct"]) <= float(baseline_metrics["max_drawdown_pct"])
        )
        results.append(row)

    results.sort(
        key=lambda row: (
            float(row["metrics"]["on_tester_value"]),
            float(row["metrics"]["profit_factor"]),
            float(row["metrics"]["net_profit_brl"]),
            -float(row["metrics"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )

    for row in results:
        preset_name = row.get("preset_name")
        if row["mt5_ready"] and preset_name:
            preset_path = PRESET_DIR / f"{preset_name}.set"
            preset_path.write_text(render_preset(row["params"]), encoding="utf-8")
            row["preset_path"] = str(preset_path.resolve())

    summary = {
        "data_source": str(data_path),
        "period_start": str(trade_dates.min().date()),
        "period_end": str(trade_dates.max().date()),
        "pattern_notes": pattern_notes,
        "results": results,
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard = []
    if LEADERBOARD_PATH.exists():
        leaderboard = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
    merged = {entry["name"]: entry for entry in leaderboard if isinstance(entry, dict) and "name" in entry}
    for row in results:
        metrics = row["metrics"]
        merged[row["name"]] = {
            "name": row["name"],
            "family": "timing_sweep_full_period",
            "screening_method": "integrated_backtest_full_period",
            "quality_tier": 1,
            "mt5_ready": row["mt5_ready"],
            "test_total_trades": metrics["total_trades"],
            "test_net_profit_brl": metrics["net_profit_brl"],
            "test_profit_factor": metrics["profit_factor"],
            "test_on_tester_value": metrics["on_tester_value"],
            "test_max_drawdown_pct": metrics["max_drawdown_pct"],
            "test_win_rate": metrics["win_rate"],
            "delta_vs_baseline_test_net": row["delta_vs_baseline"]["net_profit_brl"],
            "delta_vs_baseline_test_pf": row["delta_vs_baseline"]["profit_factor"],
            "delta_vs_baseline_test_dd": row["delta_vs_baseline"]["max_drawdown_pct"],
            "beats_baseline": row["beats_baseline"],
            "notes": f"Full-period timing sweep. {row['notes']}",
            "analysis_notes": pattern_notes,
            "preset_name": row.get("preset_name"),
            "preset_path": row.get("preset_path"),
        }

    leaderboard_rows = list(merged.values())
    leaderboard_rows.sort(
        key=lambda row: (
            float(row.get("test_on_tester_value", 0.0)),
            float(row.get("test_profit_factor", 0.0)),
            float(row.get("test_net_profit_brl", 0.0)),
            -float(row.get("test_max_drawdown_pct", 0.0)),
        ),
        reverse=True,
    )
    for rank, row in enumerate(leaderboard_rows, start=1):
        row["rank"] = rank
    LEADERBOARD_PATH.write_text(json.dumps(leaderboard_rows, indent=2), encoding="utf-8")

    top_rows = [
        {
            "name": row["name"],
            "net_profit_brl": row["metrics"]["net_profit_brl"],
            "profit_factor": row["metrics"]["profit_factor"],
            "max_drawdown_pct": row["metrics"]["max_drawdown_pct"],
            "win_rate": row["metrics"]["win_rate"],
            "on_tester_value": row["metrics"]["on_tester_value"],
            "beats_baseline": row["beats_baseline"],
        }
        for row in results
    ]
    print(json.dumps({"summary_path": str((OUTPUT_DIR / "summary.json").resolve()), "results": top_rows}, indent=2))


if __name__ == "__main__":
    main()
