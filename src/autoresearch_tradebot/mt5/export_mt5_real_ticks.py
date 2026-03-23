from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd
from dateutil.relativedelta import relativedelta

from ..common.paths import MT5_PORTABLE_DIR, artifact_output_dir
from .runtime import resolve_terminal_path


DEFAULT_TERMINAL_PATH = MT5_PORTABLE_DIR / "terminal64.exe"
DEFAULT_OUTPUT_DIR = artifact_output_dir("mt5_real_ticks")


@dataclass
class ChunkSummary:
    chunk: str
    start: str
    end: str
    rows: int
    first_time_msc: int | None
    last_time_msc: int | None
    file: str | None


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y.%m.%d")


def month_floor(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def connect(terminal_path: Path) -> None:
    if not mt5.initialize(path=str(terminal_path.resolve())):
        raise RuntimeError(f"MetaTrader5 initialize() failed: {mt5.last_error()}")


def fetch_chunk(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
    if ticks is None:
        raise RuntimeError(f"copy_ticks_range() failed for {symbol} {start} -> {end}: {mt5.last_error()}")

    if len(ticks) == 0:
        return pd.DataFrame(
            columns=["time", "bid", "ask", "last", "volume", "time_msc", "flags", "volume_real"]
        )

    df = pd.DataFrame(ticks)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    df = df[(df["time_msc"] >= start_ms) & (df["time_msc"] < end_ms)].copy()
    if df.empty:
        return df

    df["time_utc"] = pd.to_datetime(df["time_msc"], unit="ms", utc=True)
    return df


def write_monthly_parquet(
    symbol: str,
    from_date: datetime,
    to_date: datetime,
    output_dir: Path,
) -> list[ChunkSummary]:
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[ChunkSummary] = []
    cursor = month_floor(from_date)
    hard_stop = month_floor(to_date) + relativedelta(months=1)

    while cursor < hard_stop:
        next_cursor = cursor + relativedelta(months=1)
        chunk_start = max(cursor, from_date)
        chunk_end = min(next_cursor, to_date)

        df = fetch_chunk(symbol=symbol, start=chunk_start, end=chunk_end)
        file_path: Path | None = None
        first_time_msc: int | None = None
        last_time_msc: int | None = None

        if not df.empty:
            token = symbol.replace("$", "_").replace(" ", "_")
            file_path = output_dir / f"{token}_ticks_{cursor.strftime('%Y_%m')}.parquet"
            df.to_parquet(file_path, index=False)
            first_time_msc = int(df.iloc[0]["time_msc"])
            last_time_msc = int(df.iloc[-1]["time_msc"])

        summaries.append(
            ChunkSummary(
                chunk=cursor.strftime("%Y-%m"),
                start=chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
                end=chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                rows=int(len(df)),
                first_time_msc=first_time_msc,
                last_time_msc=last_time_msc,
                file=str(file_path.resolve()) if file_path else None,
            )
        )
        print(f"{cursor.strftime('%Y-%m')}: {len(df)} rows")
        cursor = next_cursor

    return summaries


def write_manifest(output_dir: Path, symbol: str, summaries: list[ChunkSummary]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": symbol,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "chunks": [asdict(item) for item in summaries],
        "total_rows": sum(item.rows for item in summaries),
        "non_empty_chunks": sum(1 for item in summaries if item.rows > 0),
    }

    (output_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    pd.DataFrame([asdict(item) for item in summaries]).to_csv(output_dir / "manifest.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export native MT5 real tick history to monthly parquet files.")
    parser.add_argument("--terminal-path", type=Path, default=DEFAULT_TERMINAL_PATH)
    parser.add_argument("--symbol", default="WDO$N")
    parser.add_argument("--from-date", default="2021.03.22")
    parser.add_argument("--to-date", default="2026.03.20")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR / "WDO_N")
    args = parser.parse_args()

    from_date = parse_date(args.from_date)
    to_date = parse_date(args.to_date) + relativedelta(days=1)

    terminal_path = resolve_terminal_path(args.terminal_path)
    connect(terminal_path)
    try:
        summaries = write_monthly_parquet(
            symbol=args.symbol,
            from_date=from_date,
            to_date=to_date,
            output_dir=args.output_dir,
        )
    finally:
        mt5.shutdown()

    write_manifest(output_dir=args.output_dir, symbol=args.symbol, summaries=summaries)


if __name__ == "__main__":
    main()
