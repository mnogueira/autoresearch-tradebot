from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_atr_regime_followups import compute_daily_atr14, daily_ohlc_from_bars
from .stalker_v10_1_contract_phase_switch_followups_20260329 import _combine_filters, _date_filter, _date_set
from .stalker_v10_1_corrected_cost_survival_followups_20260329 import _subset_block, _variant_payload
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates
from .wdo_session_vwap_crossover_exact_20260329 import build_session_vwap_crossover_signal_map


OUTPUT_DIR = artifact_output_dir("stalker_v10_1_corrected_cost_combo_vwap_agreement_20260329")


def _directional_filter(allowed_long_dates: set[pd.Timestamp], allowed_short_hours: set[int]):
    def _allow(context: dict) -> bool:
        direction = int(context.get("direction", 0))
        if direction == 1:
            return pd.Timestamp(context["session_date"]).normalize() in allowed_long_dates
        if direction == -1:
            return int(context["entry_hour"]) in allowed_short_hours
        return False

    return _allow


def _vwap_agreement_filter(signal_map: dict[pd.Timestamp, int]):
    def _allow(context: dict) -> bool:
        direction = int(context.get("direction", 0))
        timestamp = pd.Timestamp(context["timestamp"])
        return int(signal_map.get(timestamp, 0)) == direction

    return _allow


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]
    recent_30 = trade_dates[-30:]
    recent_10 = trade_dates[-10:]

    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
        SL_ATRMultiplier=1.0,
        TP_ATRMultiplier=0.48,
        AllowFriday=False,
    )

    rollover_daily = contract_rollover_buckets(dataset)
    non_last1_dates = pd.Index(rollover_daily.index[rollover_daily["contract_days_to_end"] > 0])

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    prior_day_atr14 = daily_atr14.shift(1)
    threshold = prior_day_atr14.rolling(60, min_periods=20).quantile(2 / 3)
    allowed_long_dates = set(pd.Index(prior_day_atr14.index[(prior_day_atr14 <= threshold) | threshold.isna()]))

    vwap_signal_map = build_session_vwap_crossover_signal_map(dataset)
    entry_filter = _combine_filters(
        session_filter({10, 11, 12, 14}),
        _date_filter(_date_set(non_last1_dates)),
        _directional_filter(allowed_long_dates, {10, 11, 12}),
        _vwap_agreement_filter(vwap_signal_map),
    )
    management = ManagementConfig(min_minutes_between_entries=60)

    trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    payload = _variant_payload(
        name="tier2a_corrected_combo_vwap_agreement",
        rule="Corrected-cost stacked combo with session VWAP crossover agreement at entry time.",
        trades=trades,
        trade_dates=trade_dates,
        params={"params": asdict(params), "management": asdict(management)},
    )

    summary = {
        "variant": payload,
        "walkforward_70_30": {
            "train": _subset_block(trades, train_dates),
            "test": _subset_block(trades, test_dates),
        },
        "recent_windows": {
            "recent_60d": _subset_block(trades, recent_60),
            "recent_30d": _subset_block(trades, recent_30),
            "recent_10d": _subset_block(trades, recent_10),
        },
        "notes": [
            "Corrected-cost stacked combo with an additional session VWAP crossover agreement filter.",
            "Goal: test whether VWAP helps as confirmation even though it failed as a standalone signal family.",
        ],
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
