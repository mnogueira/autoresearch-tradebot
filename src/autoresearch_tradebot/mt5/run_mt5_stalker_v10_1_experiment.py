from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..common.paths import MT5_CUSTOM_EXPERTS_DIR, MT5_TESTER_PROFILES_DIR, artifact_output_dir
from .calibrate_stalker_v10_mt5 import build_tester_ini, parse_mt5_report, run_mt5_test, wait_for_file
from .run_mt5_stalker_v10_test import terminate_existing_terminal
from .runtime import (
    compile_mq5_source,
    resolve_metaeditor_path,
    resolve_terminal_path,
    sync_expert_source,
    sync_tester_profile,
)

DEFAULT_EXPERT_SOURCE = MT5_CUSTOM_EXPERTS_DIR / "WDO Stalker Strategy v10.1 Time Filters GPT 5.4.mq5"
DEFAULT_OUTPUT_DIR = artifact_output_dir("mt5_stalker_v10_1_experiment")
KEY_METRICS = (
    "total_trades",
    "net_profit_brl",
    "profit_factor",
    "expected_payoff",
    "on_tester_value",
    "max_drawdown_pct",
    "win_rate_pct",
)


def compare_metrics(reference_metrics: dict[str, Any], current_metrics: dict[str, Any]) -> dict[str, Any]:
    comparison: dict[str, Any] = {}
    for key in KEY_METRICS:
        if key not in reference_metrics or key not in current_metrics:
            continue
        current_value = float(current_metrics[key])
        reference_value = float(reference_metrics[key])
        comparison[key] = {
            "reference": reference_value,
            "current": current_value,
            "delta_current_minus_reference": round(current_value - reference_value, 6),
        }
    return comparison


def load_reference_metrics(summary_path: Path) -> dict[str, Any]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return payload.get("mt5_report", {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an MT5 Stalker v10.1 experiment from a .set preset.")
    parser.add_argument("--set-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--description", default="")
    parser.add_argument("--reference-summary", type=Path, default=None)
    parser.add_argument("--expert-source", type=Path, default=DEFAULT_EXPERT_SOURCE)
    parser.add_argument("--terminal-path", type=Path, default=None)
    parser.add_argument("--metaeditor-path", type=Path, default=None)
    parser.add_argument("--from-date", default="2021.03.22")
    parser.add_argument("--to-date", default="2026.03.20")
    parser.add_argument("--period", default="M1")
    parser.add_argument("--model", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=int, default=5400)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--portable", action="store_true", default=True)
    args = parser.parse_args()

    terminal_path = resolve_terminal_path(args.terminal_path)
    metaeditor_path = resolve_metaeditor_path(args.metaeditor_path)

    runtime_expert = sync_expert_source(args.expert_source, terminal_path)
    runtime_set = sync_tester_profile(args.set_file, terminal_path)
    if args.compile or not runtime_expert.with_suffix(".ex5").exists():
        compile_mq5_source(metaeditor_path, runtime_expert, args.timeout_seconds)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / f"mt5_model_{args.model}_report.html"
    config_path = build_tester_ini(
        terminal_path=terminal_path,
        output_dir=args.output_dir,
        expert_name=runtime_expert.stem,
        model=args.model,
        period=args.period,
        report_path=report_path,
        from_date=args.from_date,
        to_date=args.to_date,
        set_file=runtime_set,
    )

    terminate_existing_terminal(terminal_path)
    run_mt5_test(terminal_path, config_path, args.timeout_seconds, args.portable)
    wait_for_file(report_path, args.timeout_seconds)

    metrics = parse_mt5_report(report_path)
    summary: dict[str, Any] = {
        "strategy": args.output_dir.name,
        "description": args.description,
        "expert_source": str(args.expert_source.resolve()),
        "set_file": str(args.set_file.resolve()),
        "config_path": str(config_path.resolve()),
        "report_path": str(report_path.resolve()),
        "tester": {
            "model": args.model,
            "period": args.period,
            "from_date": args.from_date,
            "to_date": args.to_date,
        },
        "mt5_report": metrics,
    }

    if args.reference_summary is not None and args.reference_summary.exists():
        reference_metrics = load_reference_metrics(args.reference_summary)
        summary["comparison_vs_reference"] = compare_metrics(reference_metrics, metrics)

    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
