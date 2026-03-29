from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_trades,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_roc_agreement_followups_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_adjusted = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_adjusted,
        "sortino_weighted_composite": _composite_score(risk_adjusted),
    }


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "comparison_tier": "exact",
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


def _leaderboard_row(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family="stalker_v10_1_roc_agreement",
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = "exact"
    row["screening_method"] = "roc_agreement_followup"
    risk_metrics = dict(variant["risk_adjusted_metrics"])
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
    return row


def _make_roc_filter(dataset: V10Dataset, window_bars: int) -> Callable[[dict[str, Any]], bool]:
    bars = dataset.bars_m1
    session_key = bars["session_date"]
    close_values = bars["Close"]
    roc_values = close_values.groupby(session_key).transform(lambda series: series.pct_change(int(window_bars)))
    roc_array = roc_values.to_numpy(dtype=float)

    def _allow(context: dict[str, Any]) -> bool:
        idx = int(context["dataset_index"])
        roc_value = float(roc_array[idx])
        if not np.isfinite(roc_value):
            return False
        direction = int(context["direction"])
        return roc_value > 0.0 if direction == 1 else roc_value < 0.0

    return _allow


def _daily_atr_tp_scale(
    dataset: V10Dataset,
    atr_length: int,
    lookback_sessions: int,
    min_scale: float,
    max_scale: float,
) -> np.ndarray:
    bars = dataset.bars_m1
    session_dates = pd.to_datetime(bars["session_date"]).dt.normalize()
    atr_series = pd.Series(dataset.get_atr_current(int(atr_length)), index=bars.index, dtype=float)
    daily_atr = atr_series.groupby(session_dates).first().astype(float)
    daily_reference = daily_atr.shift(1).rolling(int(lookback_sessions), min_periods=5).mean()
    daily_scale = (daily_atr / daily_reference).replace([np.inf, -np.inf], np.nan).clip(float(min_scale), float(max_scale))
    daily_scale = daily_scale.fillna(1.0)
    scale_lookup = daily_scale.to_dict()
    return session_dates.map(scale_lookup).astype(float).to_numpy()


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    tier2_management = ManagementConfig(min_minutes_between_entries=25)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)
    roc5_filter = _combine_filters(base_filter, _make_roc_filter(dataset, 5))
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    variants: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []

    for name, rule, entry_filter, management, tp_scale_override, params_block in (
        (
            "tier2_reference",
            "Current Tier 2 exact production candidate.",
            base_filter,
            tier2_management,
            None,
            {"management": asdict(tier2_management), "entry_hours": [10, 11, 12, 14]},
        ),
        (
            "tier3_reference",
            "Current Tier 3 exact production candidate.",
            base_filter,
            tier3_management,
            None,
            {"management": asdict(tier3_management), "entry_hours": [10, 11, 12, 14]},
        ),
        (
            "tier2_trend_efficiency_plus_roc5_agreement",
            "Keep the existing trend-efficiency signal family and add ROC(5) directional agreement as an extra confirmation gate on Tier 2.",
            roc5_filter,
            tier2_management,
            None,
            {"management": asdict(tier2_management), "roc_agreement_bars": 5},
        ),
        (
            "tier3_trend_efficiency_plus_roc5_agreement",
            "Keep the existing trend-efficiency signal family and add ROC(5) directional agreement as an extra confirmation gate on Tier 3.",
            roc5_filter,
            tier3_management,
            None,
            {"management": asdict(tier3_management), "roc_agreement_bars": 5},
        ),
        (
            "tier3_dynamic_tp_ratio_0p90_1p20",
            "Tier 3 with a tighter daily-ATR TP scaling clip of 0.90x to 1.20x.",
            base_filter,
            tier3_management,
            _daily_atr_tp_scale(dataset, int(params.ATR_Length), 20, 0.90, 1.20),
            {"management": asdict(tier3_management), "tp_scale_clip": [0.90, 1.20]},
        ),
        (
            "tier3_dynamic_tp_ratio_0p85_1p30",
            "Tier 3 with a moderate daily-ATR TP scaling clip of 0.85x to 1.30x.",
            base_filter,
            tier3_management,
            _daily_atr_tp_scale(dataset, int(params.ATR_Length), 20, 0.85, 1.30),
            {"management": asdict(tier3_management), "tp_scale_clip": [0.85, 1.30]},
        ),
        (
            "tier3_roc5_agreement_plus_dynamic_tp_0p90_1p20",
            "Combine the two most plausible exact levers from this batch: ROC(5) agreement and tighter ATR-scaled TP on Tier 3.",
            roc5_filter,
            tier3_management,
            _daily_atr_tp_scale(dataset, int(params.ATR_Length), 20, 0.90, 1.20),
            {"management": asdict(tier3_management), "roc_agreement_bars": 5, "tp_scale_clip": [0.90, 1.20]},
        ),
    ):
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
            tp_scale_override=tp_scale_override,
        )
        variant = _variant_payload(
            name=name,
            rule=rule,
            trades=trades,
            metrics=metrics,
            trade_dates=trade_dates,
            params=params_block,
        )
        variants.append(variant)
        leaderboard_rows.append(_leaderboard_row(variant, summary_path))

    ranked = sorted(
        variants,
        key=lambda row: (
            float(row["sortino_weighted_composite"]),
            float(row["risk_adjusted_metrics"]["sortino_ratio"]),
            float(row["risk_adjusted_metrics"]["calmar_ratio"]),
            float(row["metrics"]["net_profit_brl"]),
        ),
        reverse=True,
    )
    for rank, row in enumerate(ranked, start=1):
        row["batch_rank"] = rank

    best_variant = ranked[0]
    best_entry_filter = roc5_filter if "roc5_agreement" in str(best_variant["name"]) else base_filter
    best_management = tier3_management if "tier3" in str(best_variant["name"]) else tier2_management
    best_tp_scale = None
    if str(best_variant["name"]).endswith("0p90_1p20"):
        best_tp_scale = _daily_atr_tp_scale(dataset, int(params.ATR_Length), 20, 0.90, 1.20)
    elif str(best_variant["name"]).endswith("0p85_1p30"):
        best_tp_scale = _daily_atr_tp_scale(dataset, int(params.ATR_Length), 20, 0.85, 1.30)

    train_dates, test_dates = split_dates(trade_dates, 0.7)
    train_trades, train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=best_entry_filter,
        management=best_management,
        tp_scale_override=best_tp_scale,
    )
    test_trades, test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=best_entry_filter,
        management=best_management,
        tp_scale_override=best_tp_scale,
    )

    recent_dates = trade_dates[-60:]
    if test_trades.empty:
        recent_trades = test_trades
    else:
        test_session_dates = pd.to_datetime(test_trades["session_date"]).dt.normalize()
        recent_index = pd.Index(pd.to_datetime(recent_dates))
        recent_trades = test_trades.loc[test_session_dates.isin(recent_index)].reset_index(drop=True)
    recent_metrics = calculate_metrics(recent_trades, pd.Index(pd.to_datetime(recent_dates)))

    summary = {
        "variants": ranked,
        "best_variant_walkforward_70_30": {
            "variant_name": best_variant["name"],
            "train_metrics": train_metrics,
            "train_risk_adjusted": _risk_block(train_trades, train_dates),
            "test_metrics": test_metrics,
            "test_risk_adjusted": _risk_block(test_trades, test_dates),
        },
        "best_variant_recent_60d": {
            "variant_name": best_variant["name"],
            "metrics": recent_metrics,
            **_risk_block(recent_trades, pd.Index(pd.to_datetime(recent_dates))),
        },
        "notes": [
            "This batch tests ROC(5) as an agreement filter instead of a full replacement for trend-efficiency.",
            "It also retests daily-ATR adaptive TP with tighter clips after the wider 0.75x-1.50x version underperformed.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
