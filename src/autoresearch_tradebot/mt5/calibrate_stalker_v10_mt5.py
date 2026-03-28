from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import MT5_CUSTOM_EXPERTS_DIR, MT5_PORTABLE_DIR, MT5_TESTER_PROFILES_DIR, artifact_output_dir
from .runtime import (
    compile_mq5_source,
    resolve_metaeditor_path,
    resolve_terminal_path,
    sync_expert_source,
    sync_tester_profile,
)


EXPERT_NAME = "WDO Stalker Strategy v10.0 GPT 5.4"
DEFAULT_TERMINAL_PATH = MT5_PORTABLE_DIR / "terminal64.exe"
DEFAULT_METAEDITOR_PATH = MT5_PORTABLE_DIR / "MetaEditor64.exe"
DEFAULT_SET_FILE = MT5_TESTER_PROFILES_DIR / f"{EXPERT_NAME}.set"
DEFAULT_EXPERT_SOURCE = MT5_CUSTOM_EXPERTS_DIR / f"{EXPERT_NAME}.mq5"
PYTHON_SUMMARY = artifact_output_dir("stalker_v10_python", "summary.json")
DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_calibration")


def parse_number(value: str) -> float:
    cleaned = (
        value.replace(" ", "")
        .replace("%", "")
        .replace("\xa0", "")
        .replace(",", "")
        .strip()
    )
    cleaned = cleaned.replace("-.", "-0.")
    return float(cleaned)


def parse_percent_from_parentheses(value: str) -> float:
    match = re.search(r"\(([\d\s.,-]+)%\)", value)
    if not match:
        raise ValueError(f"Could not parse percent from: {value}")
    return parse_number(match.group(1))


def parse_trade_ratio(value: str) -> tuple[int, float]:
    match = re.search(r"([\d\s]+)\s*\(([\d\s.,-]+)%\)", value)
    if not match:
        raise ValueError(f"Could not parse trade ratio from: {value}")
    count = int(match.group(1).replace(" ", ""))
    pct = parse_number(match.group(2))
    return count, pct


def read_set_inputs(set_file: Path) -> str:
    raw = set_file.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16")
        return sanitize_set_inputs(text)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = raw.decode(encoding)
            return sanitize_set_inputs(text)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Could not decode {set_file}")


def sanitize_set_inputs(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";") or "=" not in stripped:
            cleaned_lines.append(line)
            continue

        name, value = line.split("=", 1)
        if "||" not in value:
            cleaned_lines.append(line)
            continue

        head = value.split("||", 1)[0].strip()
        numeric_like = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", head) is not None
        bool_like = head.lower() in {"true", "false"}
        datetime_like = re.fullmatch(r"D'.*'", head) is not None
        if numeric_like or bool_like or datetime_like:
            cleaned_lines.append(line)
            continue

        cleaned_lines.append(f"{name}={head}")

    return "\n".join(cleaned_lines) + ("\n" if text.endswith(("\n", "\r")) else "")


def build_tester_ini(
    terminal_path: Path,
    output_dir: Path,
    expert_name: str,
    model: int,
    period: str,
    report_path: Path,
    from_date: str,
    to_date: str,
    set_file: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    relative_report = os.path.relpath(report_path, terminal_path.parent)
    config_path = output_dir / f"mt5_model_{model}.ini"
    config = f"""[Tester]
Expert=Custom\\{expert_name}.ex5
Symbol=WDO$N
Period={period}
Optimization=0
Model={model}
Dates=1
FromDate={from_date}
ToDate={to_date}
ForwardMode=0
Deposit=10000
Currency=BRL
ProfitInPips=0
Leverage=1
ExecutionMode=10
OptimizationCriterion=6
Visual=0
Report={relative_report}
ReplaceReport=1
ShutdownTerminal=1
[TesterInputs]
{read_set_inputs(set_file)}
"""
    config_path.write_text(config, encoding="utf-8")
    return config_path


def wait_for_file(path: Path, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for report file: {path}")


def run_mt5_test(
    terminal_path: Path,
    config_path: Path,
    timeout_seconds: int,
    portable: bool,
) -> None:
    command = [str(terminal_path.resolve()), f"/config:{config_path.resolve()}"]
    if portable:
        command.append("/portable")
    subprocess.run(
        command,
        cwd=str(terminal_path.parent),
        check=True,
        timeout=timeout_seconds,
    )


def parse_mt5_report(report_path: Path) -> dict[str, Any]:
    table = pd.read_html(report_path)[0]
    extracted: dict[str, str] = {}
    for _, row in table.iterrows():
        for label_idx, value_idx in ((0, 3), (4, 7), (8, 11)):
            label = row.iloc[label_idx]
            value = row.iloc[value_idx] if value_idx < len(row) else None
            if pd.isna(label) or pd.isna(value):
                continue
            label_text = str(label).strip()
            value_text = str(value).strip()
            if label_text and label_text != "nan":
                extracted[label_text] = value_text

    profit_trades_count, profit_trades_pct = parse_trade_ratio(extracted["Profit Trades (% of total):"])
    return {
        "symbol": extracted["Symbol:"],
        "period": extracted["Period:"],
        "history_quality": extracted["History Quality:"],
        "bars": int(parse_number(extracted["Bars:"])),
        "ticks": int(parse_number(extracted["Ticks:"])),
        "total_trades": int(parse_number(extracted["Total Trades:"])),
        "net_profit_brl": parse_number(extracted["Total Net Profit:"]),
        "profit_factor": parse_number(extracted["Profit Factor:"]),
        "expected_payoff": parse_number(extracted["Expected Payoff:"]),
        "on_tester_value": parse_number(extracted["OnTester result:"]),
        "max_drawdown_pct": parse_percent_from_parentheses(extracted["Equity Drawdown Maximal:"]),
        "win_rate_pct": profit_trades_pct,
        "profit_trades": profit_trades_count,
    }


def read_python_baseline(summary_path: Path) -> dict[str, Any]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = payload["baseline_metrics"]
    return {
        "total_trades": int(metrics["total_trades"]),
        "net_profit_brl": float(metrics["net_profit_brl"]),
        "profit_factor": float(metrics["profit_factor"]),
        "expected_payoff": float(metrics["expected_payoff"]),
        "on_tester_value": float(metrics["on_tester_value"]),
        "max_drawdown_pct": float(metrics["max_drawdown_pct"]),
        "win_rate_pct": float(metrics["win_rate"]) * 100.0,
    }


def build_comparison(python_metrics: dict[str, Any], mt5_metrics: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "total_trades",
        "net_profit_brl",
        "profit_factor",
        "expected_payoff",
        "on_tester_value",
        "max_drawdown_pct",
        "win_rate_pct",
    ]
    diff: dict[str, Any] = {}
    for key in keys:
        py_value = float(python_metrics[key])
        mt5_value = float(mt5_metrics[key])
        diff[key] = {
            "python": py_value,
            "mt5": mt5_value,
            "absolute_diff": round(py_value - mt5_value, 6),
            "pct_diff_vs_mt5": round(((py_value / mt5_value) - 1.0) * 100.0, 4) if mt5_value != 0 else None,
        }
    return diff


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate Python stalker_v10 port against MT5.")
    parser.add_argument("--model", type=int, default=1, help="MT5 model: 1=M1 OHLC, 4=real ticks")
    parser.add_argument("--period", default="M1")
    parser.add_argument("--from-date", default="2025.07.09")
    parser.add_argument("--to-date", default="2026.03.20")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--terminal-path", type=Path, default=DEFAULT_TERMINAL_PATH)
    parser.add_argument("--metaeditor-path", type=Path, default=DEFAULT_METAEDITOR_PATH)
    parser.add_argument("--expert-source", type=Path, default=DEFAULT_EXPERT_SOURCE)
    parser.add_argument("--set-file", type=Path, default=DEFAULT_SET_FILE)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()

    terminal_path = resolve_terminal_path(args.terminal_path)
    metaeditor_path = resolve_metaeditor_path(args.metaeditor_path)
    expert_source = sync_expert_source(args.expert_source, terminal_path)
    set_file = sync_tester_profile(args.set_file, terminal_path)
    if args.compile or not expert_source.with_suffix(".ex5").exists():
        compile_mq5_source(metaeditor_path, expert_source, args.timeout_seconds)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / f"mt5_model_{args.model}_report.html"
    config_path = build_tester_ini(
        terminal_path=terminal_path,
        output_dir=args.output_dir,
        expert_name=expert_source.stem,
        model=args.model,
        period=args.period,
        report_path=report_path,
        from_date=args.from_date,
        to_date=args.to_date,
        set_file=set_file,
    )

    run_mt5_test(terminal_path, config_path, args.timeout_seconds, args.portable)
    wait_for_file(report_path, args.timeout_seconds)

    mt5_metrics = parse_mt5_report(report_path)
    python_metrics = read_python_baseline(PYTHON_SUMMARY)
    comparison = {
        "model": args.model,
        "period": args.period,
        "from_date": args.from_date,
        "to_date": args.to_date,
        "python_baseline": python_metrics,
        "mt5_report": mt5_metrics,
        "differences": build_comparison(python_metrics, mt5_metrics),
        "config_path": str(config_path.resolve()),
        "report_path": str(report_path.resolve()),
    }
    out_path = args.output_dir / f"comparison_model_{args.model}.json"
    out_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
