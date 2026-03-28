from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import _ensure_every_tick_cache
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_spread_entry_diagnostics_20260328")


def _counts(series: pd.Series) -> dict[str, int]:
    counts = series.value_counts(dropna=False).sort_index()
    return {str(int(index)): int(value) for index, value in counts.items() if pd.notna(index)}


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=session_filter({10, 11, 12, 14}),
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    cache = _ensure_every_tick_cache(dataset)
    spread_by_timestamp = pd.Series(
        cache["spread_ticks"],
        index=pd.DatetimeIndex(cache["timestamps"]),
        dtype="int64",
    )

    trades = trades.copy()
    trades["entry_timestamp"] = pd.to_datetime(trades["entry_time"])
    trades["entry_spread_ticks"] = trades["entry_timestamp"].map(spread_by_timestamp)

    summary = {
        "total_trades": int(len(trades)),
        "losing_trades": int((trades["pnl_brl"] < 0).sum()),
        "winning_trades": int((trades["pnl_brl"] > 0).sum()),
        "entry_spread_distribution": _counts(trades["entry_spread_ticks"]),
        "losing_entry_spread_distribution": _counts(trades.loc[trades["pnl_brl"] < 0, "entry_spread_ticks"]),
        "winning_entry_spread_distribution": _counts(trades.loc[trades["pnl_brl"] > 0, "entry_spread_ticks"]),
        "notes": [
            "The cached exact-engine spread only takes values 0 or 1 tick in this dataset.",
            "This means the 1-tick spread guard is a live execution safeguard, not a historical alpha lever.",
            "Losing trades are not clustered in a wider-spread bucket because the historical tape never exceeds 1 tick at entry.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
