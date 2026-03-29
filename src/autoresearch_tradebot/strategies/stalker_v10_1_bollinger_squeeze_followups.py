from __future__ import annotations

import json
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_bollinger_squeeze_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _bollinger_squeeze_mask(
    close: pd.Series,
    width_window: int = 20,
    regime_lookback: int = 100,
    quantile: float = 0.25,
) -> np.ndarray:
    basis = close.rolling(int(width_window), min_periods=int(width_window)).mean()
    std = close.rolling(int(width_window), min_periods=int(width_window)).std(ddof=0)
    width = ((basis + (2.0 * std)) - (basis - (2.0 * std))) / basis.replace(0.0, np.nan)
    width = width.shift(1)
    threshold = width.rolling(int(regime_lookback), min_periods=max(20, int(regime_lookback // 2))).quantile(float(quantile))
    threshold = threshold.shift(1)
    allowed = width <= threshold
    return allowed.fillna(False).to_numpy(dtype=bool)


def _squeeze_filter(mask: np.ndarray) -> Callable[[dict[str, Any]], bool]:
    def _filter(context: dict[str, Any]) -> bool:
        index = int(context["dataset_index"])
        if index < 0 or index >= len(mask):
            return False
        return bool(mask[index])

    return _filter


def _result_block(trades: pd.DataFrame, metrics: dict[str, Any], trade_dates: pd.Index, note: str) -> dict[str, Any]:
    return {
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "note": note,
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    management = ManagementConfig(min_minutes_between_entries=30)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=management,
    )

    close = dataset.bars_m1["Close"].astype(float)
    squeeze_q25 = _bollinger_squeeze_mask(close=close, width_window=20, regime_lookback=100, quantile=0.25)
    squeeze_q33 = _bollinger_squeeze_mask(close=close, width_window=20, regime_lookback=100, quantile=1.0 / 3.0)

    q25_trades, q25_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(base_filter, _squeeze_filter(squeeze_q25)),
        management=management,
    )
    q33_trades, q33_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=_combine_filters(base_filter, _squeeze_filter(squeeze_q33)),
        management=management,
    )

    summary = {
        "reference_tier2_cooldown_only": _result_block(
            reference_trades,
            reference_metrics,
            dataset.trade_dates,
            "Session winner + 30-minute cooldown only.",
        ),
        "bollinger_squeeze_bottom_quartile": _result_block(
            q25_trades,
            q25_metrics,
            dataset.trade_dates,
            "Only trade when Bollinger-band width is in the bottom 25% of its trailing 100-bar distribution.",
        ),
        "bollinger_squeeze_bottom_third": _result_block(
            q33_trades,
            q33_metrics,
            dataset.trade_dates,
            "Only trade when Bollinger-band width is in the bottom third of its trailing 100-bar distribution.",
        ),
        "notes": [
            "This is an exact every-tick rerun of Tier 2 with a Bollinger-band-width squeeze gate.",
            "The width measure uses 20 bars and 2 standard deviations, shifted by one bar to avoid lookahead.",
        ],
    }

    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
