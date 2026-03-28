from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_python import run_backtest
from .stalker_v10_1_session_advanced_followups import update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    DEFAULT_LEADERBOARD_PATH,
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_robustness_checks_20260328")


def trade_concentration(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {
            "top_10_trade_share_pct": 0.0,
            "top_20_trade_share_pct": 0.0,
            "top_10_day_share_pct": 0.0,
            "positive_months": 0,
            "negative_months": 0,
            "flat_months": 0,
            "max_consecutive_losing_days": 0,
            "max_consecutive_winning_days": 0,
            "monthly_pnl": [],
            "yearly_pnl": [],
        }

    frame = trades.copy()
    frame["entry_time"] = pd.to_datetime(frame["entry_time"])
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    pnl = frame["pnl_brl"].astype(float)
    net = float(pnl.sum())

    top_10_trade_share = 0.0
    top_20_trade_share = 0.0
    if net != 0.0:
        top_10_trade_share = float(pnl.nlargest(min(10, len(frame))).sum() / net * 100.0)
        top_20_trade_share = float(pnl.nlargest(min(20, len(frame))).sum() / net * 100.0)

    daily = frame.groupby("session_date")["pnl_brl"].sum().sort_values(ascending=False)
    top_10_day_share = float(daily.head(min(10, len(daily))).sum() / net * 100.0) if net != 0.0 else 0.0

    ordered_daily = frame.groupby("session_date")["pnl_brl"].sum().sort_index()
    max_losing_streak = 0
    max_winning_streak = 0
    losing_streak = 0
    winning_streak = 0
    for pnl_value in ordered_daily.astype(float):
        if pnl_value < 0.0:
            losing_streak += 1
            winning_streak = 0
        elif pnl_value > 0.0:
            winning_streak += 1
            losing_streak = 0
        else:
            winning_streak = 0
            losing_streak = 0
        max_losing_streak = max(max_losing_streak, losing_streak)
        max_winning_streak = max(max_winning_streak, winning_streak)

    monthly = (
        frame.assign(year_month=frame["session_date"].dt.to_period("M").astype(str))
        .groupby("year_month")["pnl_brl"]
        .sum()
        .reset_index()
        .rename(columns={"pnl_brl": "net_profit_brl"})
    )
    yearly = (
        frame.assign(year=frame["session_date"].dt.year)
        .groupby("year")["pnl_brl"]
        .sum()
        .reset_index()
        .rename(columns={"pnl_brl": "net_profit_brl"})
    )
    return {
        "top_10_trade_share_pct": round(top_10_trade_share, 2),
        "top_20_trade_share_pct": round(top_20_trade_share, 2),
        "top_10_day_share_pct": round(top_10_day_share, 2),
        "positive_months": int((monthly["net_profit_brl"] > 0.0).sum()),
        "negative_months": int((monthly["net_profit_brl"] < 0.0).sum()),
        "flat_months": int((monthly["net_profit_brl"] == 0.0).sum()),
        "max_consecutive_losing_days": int(max_losing_streak),
        "max_consecutive_winning_days": int(max_winning_streak),
        "monthly_pnl": monthly.to_dict(orient="records"),
        "yearly_pnl": yearly.to_dict(orient="records"),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    entry_filter = session_filter({10, 11, 12, 14})
    current_rr_ratio = float(params.TP_ATRMultiplier) / float(params.SL_ATRMultiplier)

    reference_trades, reference_metrics = run_backtest(dataset, params, dataset.trade_dates, entry_filter=entry_filter)

    spread_stress_results: list[dict[str, Any]] = []
    cooldown_results: list[dict[str, Any]] = []
    dynamic_sl_results: list[dict[str, Any]] = []
    dynamic_tp_results: list[dict[str, Any]] = []
    hybrid_ratio_results: list[dict[str, Any]] = []
    leaderboard_rows: list[dict[str, Any]] = []
    for multiplier in (2.0, 3.0):
        multiplier_label = f"{int(multiplier)}x" if float(multiplier).is_integer() else str(multiplier).replace(".", "p")
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=entry_filter,
            management=ManagementConfig(spread_multiplier=multiplier),
        )
        spread_stress_results.append({"spread_multiplier": multiplier, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_spread_{multiplier_label}",
                family="session_cost_stress",
                metrics=metrics,
                notes=f"Exact session winner with intrabar spread multiplied by {multiplier:.1f}x.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"spread_multiplier": multiplier},
            )
        )

    for cooldown_minutes in (30,):
        _, metrics = run_backtest_with_management(
            dataset=dataset,
            params=params,
            trade_dates=dataset.trade_dates,
            entry_filter=entry_filter,
            management=ManagementConfig(min_minutes_between_entries=int(cooldown_minutes)),
        )
        cooldown_results.append({"min_minutes_between_entries": cooldown_minutes, "metrics": metrics})
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_cooldown_{int(cooldown_minutes)}m",
                family="session_trade_cooldown",
                metrics=metrics,
                notes=f"Exact session winner requiring at least {int(cooldown_minutes)} minutes between filled entries.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"min_minutes_between_entries": int(cooldown_minutes)},
            )
        )

    for atr_length, sl_mult in ((14, 1.00), (14, 1.50), (14, 2.00)):
        dyn_params = params.__class__(
            **{
                **params.__dict__,
                "ATR_Length": int(atr_length),
                "SL_ATRMultiplier": float(sl_mult),
            }
        )
        _, metrics = run_backtest(dataset, dyn_params, dataset.trade_dates, entry_filter=entry_filter)
        dynamic_sl_results.append(
            {
                "atr_length": atr_length,
                "sl_atr_mult": sl_mult,
                "tp_atr_mult": dyn_params.TP_ATRMultiplier,
                "metrics": metrics,
            }
        )
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_dynamic_sl_atr{atr_length}_{str(sl_mult).replace('.', 'p')}",
                family="session_dynamic_sl",
                metrics=metrics,
                notes=f"Exact session winner using ATR{atr_length} with SL {sl_mult:.2f}x ATR and TP unchanged at 0.30 ATR.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"atr_length": atr_length, "sl_atr_mult": sl_mult, "tp_atr_mult": dyn_params.TP_ATRMultiplier},
            )
        )

    for atr_length, tp_mult in ((14, 0.50), (14, 1.00)):
        dyn_params = params.__class__(
            **{
                **params.__dict__,
                "ATR_Length": int(atr_length),
                "TP_ATRMultiplier": float(tp_mult),
            }
        )
        _, metrics = run_backtest(dataset, dyn_params, dataset.trade_dates, entry_filter=entry_filter)
        dynamic_tp_results.append(
            {
                "atr_length": atr_length,
                "sl_atr_mult": dyn_params.SL_ATRMultiplier,
                "tp_atr_mult": tp_mult,
                "metrics": metrics,
            }
        )
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_dynamic_tp_atr{atr_length}_{str(tp_mult).replace('.', 'p')}",
                family="session_dynamic_tp",
                metrics=metrics,
                notes=f"Exact session winner using ATR{atr_length} with TP {tp_mult:.2f}x ATR and SL unchanged at 0.84 ATR.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={"atr_length": atr_length, "sl_atr_mult": dyn_params.SL_ATRMultiplier, "tp_atr_mult": tp_mult},
            )
        )

    for atr_length, sl_mult in ((14, 1.00), (14, 1.50), (14, 2.00)):
        tp_mult = round(float(sl_mult) * current_rr_ratio, 4)
        dyn_params = params.__class__(
            **{
                **params.__dict__,
                "ATR_Length": int(atr_length),
                "SL_ATRMultiplier": float(sl_mult),
                "TP_ATRMultiplier": float(tp_mult),
            }
        )
        _, metrics = run_backtest(dataset, dyn_params, dataset.trade_dates, entry_filter=entry_filter)
        hybrid_ratio_results.append(
            {
                "atr_length": atr_length,
                "sl_atr_mult": sl_mult,
                "tp_atr_mult": tp_mult,
                "reward_to_risk_ratio": current_rr_ratio,
                "metrics": metrics,
            }
        )
        leaderboard_rows.append(
            candidate_row(
                name=f"session_winner_hybrid_ratio_atr{atr_length}_sl{str(sl_mult).replace('.', 'p')}",
                family="session_dynamic_sltp_ratio",
                metrics=metrics,
                notes=f"Exact session winner using ATR{atr_length} stop {sl_mult:.2f}x ATR and TP scaled to preserve the current {current_rr_ratio:.3f} reward/risk ratio.",
                artifact=DEFAULT_OUTPUT_DIR / "summary.json",
                params={
                    "atr_length": atr_length,
                    "sl_atr_mult": sl_mult,
                    "tp_atr_mult": tp_mult,
                    "reward_to_risk_ratio": current_rr_ratio,
                },
            )
        )

    concentration = trade_concentration(reference_trades)
    summary = {
        "reference": {
            "name": "session_winner_hours_10_11_12_14_sl0p84_tp0p30",
            "metrics": reference_metrics,
        },
        "spread_stress_results": spread_stress_results,
        "cooldown_results": cooldown_results,
        "dynamic_sl_results": dynamic_sl_results,
        "dynamic_tp_results": dynamic_tp_results,
        "hybrid_ratio_results": hybrid_ratio_results,
        "equity_curve_shape": concentration,
        "notes": [
            "Spread stress uses the exact every-tick engine with all historical spread ticks multiplied by the stated factor.",
            "Equity-shape concentration is reported from the exact reference session winner, not from a lightweight proxy.",
            "The trade-cooldown follow-up enforces the spacing on actual fills, not on raw candidate signals.",
            "The strategy already uses ATR-based exits; the dynamic SL/TP follow-ups therefore test wider ATR multipliers rather than introducing a new volatility-adaptive exit family.",
            "The hybrid ATR run preserves the current reward/risk ratio while widening both stop and target together.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
