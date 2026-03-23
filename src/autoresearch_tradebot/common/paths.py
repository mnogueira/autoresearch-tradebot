from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
RESEARCH_DIR = REPO_ROOT / "research"
RESEARCH_LEGACY_DIR = RESEARCH_DIR / "legacy"
RESEARCH_SOURCE_DIR = RESEARCH_DIR / "source_material"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
ARTIFACT_OUTPUTS_DIR = ARTIFACTS_DIR / "outputs"
ARTIFACT_REPORTS_DIR = ARTIFACTS_DIR / "reports"
ARTIFACT_LEGACY_DIR = ARTIFACTS_DIR / "legacy"
LEGACY_RESULTS_PATH = RESEARCH_LEGACY_DIR / "results.tsv"
LEGACY_PROGRESS_PATH = ARTIFACT_LEGACY_DIR / "progress.png"
MT5_DIR = REPO_ROOT / "mt5"
MT5_CUSTOM_EXPERTS_DIR = MT5_DIR / "experts" / "custom"
MT5_TESTER_PROFILES_DIR = MT5_DIR / "profiles" / "tester"
RUNTIME_DIR = REPO_ROOT / "runtime"
MT5_PORTABLE_DIR = RUNTIME_DIR / "mt5-portable"
DEFAULT_MT5_COMMON_FILES_DIR = (
    Path.home() / "AppData" / "Roaming" / "MetaQuotes" / "Terminal" / "Common" / "Files"
)
DEFAULT_EXTERNAL_WDO_BAR_DIR = Path(r"C:\Dev\tradebot\storage\bars\B3\WDO")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def artifact_output_dir(*parts: str) -> Path:
    return ARTIFACT_OUTPUTS_DIR.joinpath(*parts)


def artifact_report_path(*parts: str) -> Path:
    return ARTIFACT_REPORTS_DIR.joinpath(*parts)
