from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_core_horizon_validation_20260329")


def _combine_filters(*filters):
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _filter_trades_to_dates(trades: pd.DataFrame, trade_dates: pd.Index) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    allowed = {pd.Timestamp(value).date().isoformat() for value in pd.to_datetime(trade_dates)}
    mask = pd.to_datetime(trades["session_date"]).dt.date.astype(str).isin(allowed)
    return trades.loc[mask].copy()


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_10 = trade_dates[-10:]

    params = replace(
        session_winner_params(),
        ATR_Length=14,
        NumDaysToConsiderPreviousContractMARange=3,
    )
    management = ManagementConfig(min_minutes_between_entries=25)
    entry_filter = _combine_filters(session_filter({10, 11, 12, 14}), _make_roc_filter(dataset, 5))

    full_trades, full_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )
    train_trades, train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=entry_filter,
        management=management,
    )
    test_trades, test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=entry_filter,
        management=management,
    )
    recent_60_trades = _filter_trades_to_dates(full_trades, recent_60)
    recent_10_trades = _filter_trades_to_dates(full_trades, recent_10)

    summary = {
        "variant_name": "tier2a_atr14_contractlookback3",
        "full_sample": {
            "metrics": full_metrics,
            **_risk_block(full_trades, trade_dates),
        },
        "walkforward_70_30": {
            "train_metrics": train_metrics,
            "train_risk": _risk_block(train_trades, train_dates),
            "test_metrics": test_metrics,
            "test_risk": _risk_block(test_trades, test_dates),
        },
        "recent_60d": {
            "metrics": calculate_metrics(recent_60_trades, recent_60),
            **_risk_block(recent_60_trades, recent_60),
        },
        "recent_10d": {
            "metrics": calculate_metrics(recent_10_trades, recent_10),
            **_risk_block(recent_10_trades, recent_10),
        },
        "params": {
            "management": asdict(management),
            "roc_agreement_bars": 5,
            "ATR_Length": int(params.ATR_Length),
            "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
            "RetracementLevel": float(params.RetracementLevel),
            "FilterAsPercOfContractMARange": float(params.FilterAsPercOfContractMARange),
        },
    }
    (DEFAULT_OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    full_trades.tail(5).to_csv(DEFAULT_OUTPUT_DIR / "last5_trades.csv", index=False)


if __name__ == "__main__":
    main()
