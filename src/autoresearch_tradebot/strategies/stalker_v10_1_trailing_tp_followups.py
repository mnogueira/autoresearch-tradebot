from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import ARTIFACTS_DIR, artifact_output_dir
from .stalker_v10_1_python import V101Params
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
from .stalker_v10_1_confidence_weekday_followups import _allowed_weekdays_filter, _combine_filters
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_trailing_tp_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    risk_metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    return {
        "risk_adjusted_metrics": risk_metrics,
        "sortino_weighted_composite": _composite_score(risk_metrics),
    }


def _variant_payload(
    name: str,
    rule: str,
    trades: pd.DataFrame,
    metrics: dict[str, Any],
    trade_dates: pd.Index,
) -> dict[str, Any]:
    return {
        "name": name,
        "rule": rule,
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
    }


def _leaderboard_row(
    variant: dict[str, Any],
    family: str,
    notes: str,
    artifact: Path,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family=family,
        metrics=dict(variant["metrics"]),
        notes=notes,
        artifact=artifact,
        params=params,
    )
    row["comparison_tier"] = "exact"
    row["screening_method"] = "trailing_tp_followup"
    risk_metrics = dict(variant.get("risk_adjusted_metrics", {}))
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant.get("sortino_weighted_composite")
    return row


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    reference_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=reference_management,
    )
    reference_variant = _variant_payload(
        name="session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
        rule="Reference production candidate: session filter 10/11/12/14, 30m cooldown, 120 M1-bar max hold, SL 0.84 ATR, TP 0.30 ATR.",
        trades=reference_trades,
        metrics=reference_metrics,
        trade_dates=trade_dates,
    )

    variant_payloads: list[dict[str, Any]] = [reference_variant]
    leaderboard_rows: list[dict[str, Any]] = [
        _leaderboard_row(
            variant=reference_variant,
            family="stalker_v10_1_session_execution",
            notes="Reference production candidate for the trailing-stop and ATR-TP follow-up batch.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={
                "entry_hours": [10, 11, 12, 14],
                "management": asdict(reference_management),
                "SL_ATRMultiplier": float(params.SL_ATRMultiplier),
                "TP_ATRMultiplier": float(params.TP_ATRMultiplier),
            },
        )
    ]

    for atr_mult in (1.0, 1.5, 2.0):
        management = ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            atr_trailing_distance_mult=atr_mult,
        )
        trades, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=trade_dates,
            entry_filter=entry_filter,
            management=management,
        )
        variant = _variant_payload(
            name=f"session_winner_cooldown_30m_maxhold120_atrtrail_{atr_mult:.2f}",
            rule=f"Production candidate plus ATR trailing stop at {atr_mult:.2f}x entry ATR from best excursion.",
            trades=trades,
            metrics=metrics,
            trade_dates=trade_dates,
        )
        variant_payloads.append(variant)
        leaderboard_rows.append(
            _leaderboard_row(
                variant=variant,
                family="stalker_v10_1_session_execution",
                notes=f"Production candidate plus ATR trailing stop at {atr_mult:.2f}x entry ATR.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={
                    "entry_hours": [10, 11, 12, 14],
                    "management": asdict(management),
                    "SL_ATRMultiplier": float(params.SL_ATRMultiplier),
                    "TP_ATRMultiplier": float(params.TP_ATRMultiplier),
                },
            )
        )

    dynamic_tp_params = V101Params(
        **{
            **asdict(params),
            "TP_ATRMultiplier": 1.0,
        }
    )
    dynamic_tp_trades, dynamic_tp_metrics = run_backtest_with_management(
        dataset=dataset,
        params=dynamic_tp_params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=reference_management,
    )
    dynamic_tp_variant = _variant_payload(
        name="session_winner_cooldown_30m_maxhold120_tp1p00",
        rule="Production candidate with dynamic ATR target approximation: TP fixed at 1.00x ATR instead of 0.30x ATR.",
        trades=dynamic_tp_trades,
        metrics=dynamic_tp_metrics,
        trade_dates=trade_dates,
    )
    variant_payloads.append(dynamic_tp_variant)
    leaderboard_rows.append(
        _leaderboard_row(
            variant=dynamic_tp_variant,
            family="stalker_v10_1_session_execution",
            notes="Production candidate with TP 1.00x ATR.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={
                "entry_hours": [10, 11, 12, 14],
                "management": asdict(reference_management),
                "SL_ATRMultiplier": float(dynamic_tp_params.SL_ATRMultiplier),
                "TP_ATRMultiplier": float(dynamic_tp_params.TP_ATRMultiplier),
            },
        )
    )

    mon_wed_thu_filter = _combine_filters(entry_filter, _allowed_weekdays_filter({0, 2, 3}))
    mon_wed_thu_trades, mon_wed_thu_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=mon_wed_thu_filter,
        management=reference_management,
    )
    mon_wed_thu_variant = _variant_payload(
        name="session_winner_cooldown_30m_maxhold120_mon_wed_thu_only",
        rule="Production candidate on Monday, Wednesday, and Thursday only; skip Tuesday and Friday.",
        trades=mon_wed_thu_trades,
        metrics=mon_wed_thu_metrics,
        trade_dates=trade_dates,
    )
    variant_payloads.append(mon_wed_thu_variant)
    leaderboard_rows.append(
        _leaderboard_row(
            variant=mon_wed_thu_variant,
            family="stalker_v10_1_session_execution",
            notes="Production candidate but Monday/Wednesday/Thursday only.",
            artifact=DEFAULT_OUTPUT_DIR / "summary.json",
            params={
                "entry_hours": [10, 11, 12, 14],
                "allowed_weekdays": [0, 2, 3],
                "management": asdict(reference_management),
                "SL_ATRMultiplier": float(params.SL_ATRMultiplier),
                "TP_ATRMultiplier": float(params.TP_ATRMultiplier),
            },
        )
    )

    challenger_variants = [item for item in variant_payloads if item["name"] != reference_variant["name"]]
    best_new_variant = max(challenger_variants, key=lambda item: float(item["sortino_weighted_composite"]))

    train_dates, test_dates = split_dates(trade_dates, 0.7)

    if best_new_variant["name"].startswith("session_winner_cooldown_30m_maxhold120_atrtrail_"):
        atr_mult = float(str(best_new_variant["name"]).rsplit("_", 1)[-1])
        best_management = ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            atr_trailing_distance_mult=atr_mult,
        )
        best_params = params
        best_filter = entry_filter
    elif best_new_variant["name"] == "session_winner_cooldown_30m_maxhold120_tp1p00":
        best_management = reference_management
        best_params = dynamic_tp_params
        best_filter = entry_filter
    elif best_new_variant["name"] == "session_winner_cooldown_30m_maxhold120_mon_wed_thu_only":
        best_management = reference_management
        best_params = params
        best_filter = mon_wed_thu_filter
    else:
        best_management = reference_management
        best_params = params
        best_filter = entry_filter

    _, best_train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=best_params,
        trade_dates=train_dates,
        entry_filter=best_filter,
        management=best_management,
    )
    _, best_test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=best_params,
        trade_dates=test_dates,
        entry_filter=best_filter,
        management=best_management,
    )

    summary = {
        "reference_variant": reference_variant,
        "variants": variant_payloads[1:],
        "best_new_variant_walkforward_70_30": {
            "variant_name": best_new_variant["name"],
            "variant_rule": best_new_variant["rule"],
            "train_metrics": best_train_metrics,
            "test_metrics": best_test_metrics,
        },
        "notes": [
            "ATR trailing is implemented as a stop that only tightens: for longs it follows best bid minus N x entry ATR; for shorts it follows best ask plus N x entry ATR.",
            "The dynamic TP experiment uses a fixed 1.00x ATR target on top of the production candidate to approximate a volatility-scaled target.",
            "The Monday/Wednesday/Thursday variant is included here as a direct rerun of the Tuesday/Friday skip idea so it can be scored on the same composite scale as the trailing-stop batch.",
            "The walk-forward block below is run on the strongest new exact variant from this batch, not on the research-only confidence-weighted overlay.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
