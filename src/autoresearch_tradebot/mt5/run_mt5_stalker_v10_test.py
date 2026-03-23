from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..common.paths import MT5_CUSTOM_EXPERTS_DIR, MT5_PORTABLE_DIR
from .runtime import compile_mq5_source, resolve_metaeditor_path, resolve_terminal_path, sync_expert_source

DEFAULT_TERMINAL_PATH = MT5_PORTABLE_DIR / "terminal64.exe"
DEFAULT_METAEDITOR_PATH = MT5_PORTABLE_DIR / "MetaEditor64.exe"
DEFAULT_EXPERT_SOURCE = MT5_CUSTOM_EXPERTS_DIR / "WDO Stalker Strategy v10.0 GPT 5.4.mq5"


def tester_to_date(to_date: str) -> str:
    parsed = datetime.strptime(to_date, "%Y.%m.%d")
    return (parsed + timedelta(days=1)).strftime("%Y.%m.%d")


def compile_expert(metaeditor_path: Path, source_path: Path, timeout_seconds: int) -> None:
    compile_mq5_source(metaeditor_path, source_path, timeout_seconds)


def terminate_existing_terminal(terminal_path: Path) -> None:
    normalized_dir = str(terminal_path.resolve().parent).replace("'", "''")
    ps_script = (
        "$targets = Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Path -like '{normalized_dir}*' }}; "
        "if ($targets) { $targets | Stop-Process -Force }"
    )
    subprocess.run(["pwsh", "-NoProfile", "-Command", ps_script], check=False, timeout=60)


def format_input_value(value: str) -> str:
    return value


def build_tester_ini(
    terminal_path: Path,
    expert_name: str,
    output_dir: Path,
    report_name: str,
    model: int,
    period: str,
    from_date: str,
    to_date: str,
    inputs: dict[str, str],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / report_name
    relative_report = os.path.relpath(report_path.resolve(), terminal_path.parent.resolve())
    config_path = output_dir / f"{report_path.stem}.ini"

    lines = [
        "[Tester]",
        f"Expert=Custom\\{expert_name}.ex5",
        "Symbol=WDO$N",
        f"Period={period}",
        "Optimization=0",
        f"Model={model}",
        "Dates=1",
        f"FromDate={from_date}",
        f"ToDate={tester_to_date(to_date)}",
        "ForwardMode=0",
        "Deposit=10000",
        "Currency=BRL",
        "ProfitInPips=0",
        "Leverage=1",
        "ExecutionMode=10",
        "OptimizationCriterion=6",
        "Visual=0",
        f"Report={relative_report}",
        "ReplaceReport=1",
        "ShutdownTerminal=1",
        "[TesterInputs]",
    ]
    for key, value in inputs.items():
        lines.append(f"{key}={format_input_value(value)}")

    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
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
) -> None:
    terminate_existing_terminal(terminal_path)
    command = [str(terminal_path.resolve()), f"/config:{config_path.resolve()}", "/portable"]
    subprocess.run(command, cwd=str(terminal_path.parent), check=True, timeout=timeout_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MT5 Strategy Tester for WDO Stalker v10 variants.")
    parser.add_argument("--expert-name", default="WDO Stalker Strategy v10.0 GPT 5.4")
    parser.add_argument("--expert-source", type=Path, default=DEFAULT_EXPERT_SOURCE)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--terminal-path", type=Path, default=DEFAULT_TERMINAL_PATH)
    parser.add_argument("--metaeditor-path", type=Path, default=DEFAULT_METAEDITOR_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-name", required=True)
    parser.add_argument("--from-date", default="2021.03.22")
    parser.add_argument("--to-date", default="2026.03.20")
    parser.add_argument("--model", type=int, default=4)
    parser.add_argument("--period", default="M1")
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    parser.add_argument("--contracts", default="1")
    parser.add_argument("--filter-perc", default="0.40")
    parser.add_argument("--num-days-prev", default="6")
    parser.add_argument("--retracement", default="0.10")
    parser.add_argument("--sl-atr", default="0.75")
    parser.add_argument("--tp-atr", default="0.15")
    parser.add_argument("--atr-timeframe", default="15")
    parser.add_argument("--atr-length", default="36")
    parser.add_argument("--market-close-hour", default="18")
    parser.add_argument("--market-close-minute", default="0")
    parser.add_argument("--close-minutes-before", default="5")
    parser.add_argument("--entry-start-hour", default=None)
    parser.add_argument("--entry-start-minute", default=None)
    parser.add_argument("--last-entry-hour", default=None)
    parser.add_argument("--last-entry-minute", default=None)
    parser.add_argument("--allow-monday", default=None)
    parser.add_argument("--allow-tuesday", default=None)
    parser.add_argument("--allow-wednesday", default=None)
    parser.add_argument("--allow-thursday", default=None)
    parser.add_argument("--allow-friday", default=None)
    args = parser.parse_args()

    terminal_path = resolve_terminal_path(args.terminal_path)
    metaeditor_path = resolve_metaeditor_path(args.metaeditor_path)
    expert_source = sync_expert_source(args.expert_source, terminal_path)

    if args.compile or not expert_source.with_suffix(".ex5").exists():
        compile_expert(metaeditor_path, expert_source, args.timeout_seconds)

    report_path = args.output_dir / args.report_name
    inputs = {
        "ContractsPerTrade": args.contracts,
        "FilterAsPercOfContractMARange": args.filter_perc,
        "NumDaysToConsiderPreviousContractMARange": args.num_days_prev,
        "RetracementLevel": args.retracement,
        "SL_ATRMultiplier": args.sl_atr,
        "TP_ATRMultiplier": args.tp_atr,
        "ATRTimeFrame": args.atr_timeframe,
        "ATR_Length": args.atr_length,
        "MarketClose_Hour": args.market_close_hour,
        "MarketClose_Minute": args.market_close_minute,
        "MinutesBeforeMarketCloseToClosePositions": args.close_minutes_before,
    }
    optional_inputs = {
        "EntryStart_Hour": args.entry_start_hour,
        "EntryStart_Minute": args.entry_start_minute,
        "LastEntry_Hour": args.last_entry_hour,
        "LastEntry_Minute": args.last_entry_minute,
        "AllowMonday": args.allow_monday,
        "AllowTuesday": args.allow_tuesday,
        "AllowWednesday": args.allow_wednesday,
        "AllowThursday": args.allow_thursday,
        "AllowFriday": args.allow_friday,
    }
    for key, value in optional_inputs.items():
        if value is not None:
            inputs[key] = value

    config_path = build_tester_ini(
        terminal_path=terminal_path,
        expert_name=args.expert_name,
        output_dir=args.output_dir,
        report_name=args.report_name,
        model=args.model,
        period=args.period,
        from_date=args.from_date,
        to_date=args.to_date,
        inputs=inputs,
    )

    run_mt5_test(terminal_path, config_path, args.timeout_seconds)
    wait_for_file(report_path, args.timeout_seconds)
    print(report_path.resolve())


if __name__ == "__main__":
    main()
