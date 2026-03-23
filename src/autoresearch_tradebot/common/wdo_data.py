from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .paths import ARTIFACT_OUTPUTS_DIR, DATA_DIR, DEFAULT_EXTERNAL_WDO_BAR_DIR


REPO_BAR_FILES = {
    "1m": DATA_DIR / "wdo_m1.parquet",
    "5m": DATA_DIR / "wdo_m5.parquet",
    "15m": DATA_DIR / "wdo_m15.parquet",
    "1h": DATA_DIR / "wdo_h1.parquet",
}

EXTERNAL_BAR_FILES = {
    "1m": DEFAULT_EXTERNAL_WDO_BAR_DIR / "1m.parquet",
    "5m": DEFAULT_EXTERNAL_WDO_BAR_DIR / "5m.parquet",
    "15m": DEFAULT_EXTERNAL_WDO_BAR_DIR / "15m.parquet",
    "1h": DEFAULT_EXTERNAL_WDO_BAR_DIR / "1h.parquet",
    "1d": DEFAULT_EXTERNAL_WDO_BAR_DIR / "1d.parquet",
}


def wdo_bar_candidates(timeframe: str, extra_candidates: Iterable[Path] | None = None) -> list[Path]:
    key = timeframe.lower()
    candidates: list[Path] = []
    if key in EXTERNAL_BAR_FILES:
        candidates.append(EXTERNAL_BAR_FILES[key])
    if key in REPO_BAR_FILES:
        candidates.append(REPO_BAR_FILES[key])
    if extra_candidates:
        candidates.extend(extra_candidates)
    return candidates


def locate_wdo_bar_file(timeframe: str, extra_candidates: Iterable[Path] | None = None) -> Path:
    candidates = wdo_bar_candidates(timeframe=timeframe, extra_candidates=extra_candidates)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Could not find WDO {timeframe} data. Searched: {searched}")


def exported_m1_history_csv(prefix: str = "wdo_history_export_full_WDO_N_m1.csv") -> Path:
    return ARTIFACT_OUTPUTS_DIR / "mt5_history_export_full" / prefix
