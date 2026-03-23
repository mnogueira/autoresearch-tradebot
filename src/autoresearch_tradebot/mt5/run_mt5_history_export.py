from __future__ import annotations

import argparse
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from ..common.paths import (
    DEFAULT_MT5_COMMON_FILES_DIR,
    MT5_CUSTOM_EXPERTS_DIR,
    MT5_PORTABLE_DIR,
    artifact_output_dir,
)
from .runtime import compile_mq5_source, resolve_metaeditor_path, resolve_terminal_path, sync_expert_source

DEFAULT_TERMINAL_PATH = MT5_PORTABLE_DIR / "terminal64.exe"
DEFAULT_METAEDITOR_PATH = MT5_PORTABLE_DIR / "MetaEditor64.exe"
EXPORTER_SOURCE = MT5_CUSTOM_EXPERTS_DIR / "WDO_History_Exporter_GPT54.mq5"
COMMON_FILES_DIR = DEFAULT_MT5_COMMON_FILES_DIR
DEFAULT_OUTPUT_DIR = artifact_output_dir("mt5_history_export")


def tester_to_date(to_date: str) -> str:
    parsed = datetime.strptime(to_date, "%Y.%m.%d")
    return (parsed + timedelta(days=1)).strftime("%Y.%m.%d")


def expected_export_path(prefix: str, symbol: str, kind: str) -> Path:
    sanitized_prefix = prefix.replace("$", "_").replace(" ", "_")
    sanitized_symbol = symbol.replace("$", "_").replace(" ", "_")
    return COMMON_FILES_DIR / f"{sanitized_prefix}_{sanitized_symbol}_{kind}.csv"


def compile_exporter(metaeditor_path: Path, source_path: Path, timeout_seconds: int) -> None:
    compile_mq5_source(metaeditor_path, source_path, timeout_seconds)


def build_ini(
    terminal_path: Path,
    output_dir: Path,
    expert_name: str,
    model: int,
    symbol: str,
    period: str,
    from_date: str,
    to_date: str,
    output_prefix: str,
    export_ticks: bool,
    tick_chunk_days: int,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"export_model_{model}_{period}.html"
    relative_report = os.path.relpath(report_path.resolve(), terminal_path.parent.resolve())
    config_path = output_dir / f"export_model_{model}_{period}.ini"
    tester_end_date = tester_to_date(to_date)
    config = f"""[Tester]
Expert=Custom\\{expert_name}.ex5
Symbol={symbol}
Period={period}
Optimization=0
Model={model}
Dates=1
FromDate={from_date}
ToDate={tester_end_date}
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
InpSymbolName=
InpFromDate={from_date} 00:00:00
InpToDate={to_date} 23:59:59
InpExportM1Bars=true
InpExportTicks={"true" if export_ticks else "false"}
InpTickChunkDays={tick_chunk_days}
InpOutputPrefix={output_prefix}
InpUseCommonFiles=true
"""
    config_path.write_text(config, encoding="utf-8")
    return config_path


def run_export(
    terminal_path: Path,
    config_path: Path,
    timeout_seconds: int,
    portable: bool,
) -> None:
    terminate_existing_terminal(terminal_path)
    command = [str(terminal_path.resolve()), f"/config:{config_path.resolve()}"]
    if portable:
        command.append("/portable")
    subprocess.run(command, check=True, timeout=timeout_seconds, cwd=str(terminal_path.parent))


def terminate_existing_terminal(terminal_path: Path) -> None:
    normalized_dir = str(terminal_path.resolve().parent).replace("'", "''")
    ps_script = (
        "$targets = Get-Process terminal64,metatester64 -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.Path -like '{normalized_dir}*' }}; "
        "if ($targets) { $targets | Stop-Process -Force }"
    )
    subprocess.run(
        ["pwsh", "-NoProfile", "-Command", ps_script],
        check=False,
        timeout=60,
    )


def wait_for_export(prefix: str, symbol: str, kind: str, timeout_seconds: int) -> Path:
    file_path = expected_export_path(prefix=prefix, symbol=symbol, kind=kind)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if file_path.exists() and file_path.stat().st_size > 0:
            return file_path
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for export file: {file_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile and run the MT5 WDO history exporter.")
    parser.add_argument("--terminal-path", type=Path, default=DEFAULT_TERMINAL_PATH)
    parser.add_argument("--metaeditor-path", type=Path, default=DEFAULT_METAEDITOR_PATH)
    parser.add_argument("--expert-source", type=Path, default=EXPORTER_SOURCE)
    parser.add_argument("--symbol", default="WDO$N")
    parser.add_argument("--period", default="M1")
    parser.add_argument("--model", type=int, default=1, help="1=M1 OHLC, 4=real ticks")
    parser.add_argument("--from-date", default="2021.03.22")
    parser.add_argument("--to-date", default="2026.03.20")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    parser.add_argument("--portable", action="store_true")
    parser.add_argument("--wait-kind", choices=["m1", "ticks"], default="m1")
    parser.add_argument("--output-prefix", default="wdo_history_export")
    parser.add_argument("--export-ticks", action="store_true")
    parser.add_argument("--tick-chunk-days", type=int, default=1)
    args = parser.parse_args()

    terminal_path = resolve_terminal_path(args.terminal_path)
    metaeditor_path = resolve_metaeditor_path(args.metaeditor_path)
    source_path = sync_expert_source(args.expert_source, terminal_path)

    export_path = expected_export_path(prefix=args.output_prefix, symbol=args.symbol, kind=args.wait_kind)
    if export_path.exists():
        export_path.unlink()

    compile_exporter(metaeditor_path, source_path, timeout_seconds=args.timeout_seconds)
    config_path = build_ini(
        terminal_path=terminal_path,
        output_dir=args.output_dir,
        expert_name=source_path.stem,
        model=args.model,
        symbol=args.symbol,
        period=args.period,
        from_date=args.from_date,
        to_date=args.to_date,
        output_prefix=args.output_prefix,
        export_ticks=args.export_ticks,
        tick_chunk_days=args.tick_chunk_days,
    )
    run_export(
        terminal_path=terminal_path,
        config_path=config_path,
        timeout_seconds=args.timeout_seconds,
        portable=args.portable,
    )
    export_path = wait_for_export(
        prefix=args.output_prefix,
        symbol=args.symbol,
        kind=args.wait_kind,
        timeout_seconds=args.timeout_seconds,
    )
    print(export_path.resolve())


if __name__ == "__main__":
    main()
