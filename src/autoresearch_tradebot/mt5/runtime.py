from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..common.paths import MT5_PORTABLE_DIR


PROGRAM_FILES_MT5_DIR = Path(r"C:\Program Files\MetaTrader 5 Terminal")


def _first_existing(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Could not find a matching MT5 runtime asset. Searched: {searched}")


def resolve_terminal_path(path_override: Path | None = None) -> Path:
    candidates = []
    if path_override is not None:
        candidates.append(path_override)
    candidates.extend(
        [
            MT5_PORTABLE_DIR / "terminal64.exe",
            PROGRAM_FILES_MT5_DIR / "terminal64.exe",
        ]
    )
    return _first_existing(candidates)


def resolve_metaeditor_path(path_override: Path | None = None) -> Path:
    candidates = []
    if path_override is not None:
        candidates.append(path_override)
    candidates.extend(
        [
            MT5_PORTABLE_DIR / "MetaEditor64.exe",
            PROGRAM_FILES_MT5_DIR / "MetaEditor64.exe",
        ]
    )
    return _first_existing(candidates)


def runtime_root(terminal_path: Path) -> Path:
    return terminal_path.resolve().parent


def runtime_custom_experts_dir(terminal_path: Path) -> Path:
    return runtime_root(terminal_path) / "MQL5" / "Experts" / "Custom"


def runtime_tester_profiles_dir(terminal_path: Path) -> Path:
    return runtime_root(terminal_path) / "MQL5" / "Profiles" / "Tester"


def sync_file(source_path: Path, destination_dir: Path) -> Path:
    if not source_path.exists():
        raise FileNotFoundError(f"Required MT5 asset not found: {source_path}")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / source_path.name
    shutil.copy2(source_path, destination_path)
    return destination_path


def sync_expert_source(source_path: Path, terminal_path: Path) -> Path:
    return sync_file(source_path, runtime_custom_experts_dir(terminal_path))


def sync_tester_profile(source_path: Path, terminal_path: Path) -> Path:
    return sync_file(source_path, runtime_tester_profiles_dir(terminal_path))


def compile_mq5_source(metaeditor_path: Path, source_path: Path, timeout_seconds: int) -> Path:
    include_path = source_path.parents[2]
    command = (
        f'cmd /c ""{metaeditor_path.resolve()}" '
        f'/compile:"{source_path.resolve()}" '
        f'/include:"{include_path.resolve()}" '
        f'/log"'
    )
    output_path = source_path.with_suffix(".ex5")
    try:
        subprocess.run(
            command,
            check=True,
            timeout=timeout_seconds,
            cwd=str(metaeditor_path.parent),
            shell=True,
        )
    except subprocess.CalledProcessError:
        if not output_path.exists():
            raise
    if not output_path.exists():
        raise FileNotFoundError(f"Expected compiled file was not created: {output_path}")
    return output_path
