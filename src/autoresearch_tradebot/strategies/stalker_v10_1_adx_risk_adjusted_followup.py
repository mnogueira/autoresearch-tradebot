from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_risk_adjusted_evaluation import (
    _composite_score,
    _daily_pnl_from_mt5_report,
    _daily_pnl_from_trades,
    _monthly_stability_metrics,
    _risk_adjusted_metrics,
)
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_session_macro_followups import combine_filters, compute_adx
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_adx_risk_adjusted_followup_20260328")


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    daily_wdo = (
        dataset.bars_m1.assign(session_date=pd.to_datetime(dataset.bars_m1["session_date"]).dt.normalize())
        .groupby("session_date")
        .agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    )
    daily_adx = compute_adx(daily_wdo, period=14).shift(1)

    def adx25_filter(context: dict[str, object]) -> bool:
        session = pd.Timestamp(context["session_date"]).normalize()
        value = float(daily_adx.get(session, float("nan")))
        return value > 25.0

    def adx30_filter(context: dict[str, object]) -> bool:
        session = pd.Timestamp(context["session_date"]).normalize()
        value = float(daily_adx.get(session, float("nan")))
        return value > 30.0

    cooldown_management = ManagementConfig(min_minutes_between_entries=30)

    cooldown_trades, cooldown_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=cooldown_management,
    )
    adx_trades, adx_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=combine_filters(base_filter, adx25_filter),
        management=cooldown_management,
    )
    adx30_trades, adx30_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=combine_filters(base_filter, adx30_filter),
        management=cooldown_management,
    )

    mt5_summary_path = Path(
        "artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/summary.json"
    )
    mt5_report_path = Path(
        "artifacts/outputs/mt5_stalker_v10_1_surgical_sltp_sl0p84_tp0p3_every_tick_20260328/mt5_model_0_report.html"
    )
    mt5_daily_pnl = _daily_pnl_from_mt5_report(mt5_report_path, trade_dates)
    cooldown_daily_pnl = _daily_pnl_from_trades(cooldown_trades, trade_dates)
    adx_daily_pnl = _daily_pnl_from_trades(adx_trades, trade_dates)
    adx30_daily_pnl = _daily_pnl_from_trades(adx30_trades, trade_dates)

    candidates = [
        {
            "name": "tier1_mt5_base",
            "metrics": json.loads(mt5_summary_path.read_text(encoding="utf-8"))["mt5_report"],
            "risk_adjusted": _risk_adjusted_metrics(mt5_daily_pnl),
            "monthly_stability": _monthly_stability_metrics(mt5_daily_pnl),
        },
        {
            "name": "tier2_cooldown_only",
            "metrics": cooldown_metrics,
            "risk_adjusted": _risk_adjusted_metrics(cooldown_daily_pnl),
            "monthly_stability": _monthly_stability_metrics(cooldown_daily_pnl),
        },
        {
            "name": "tier2_quality_adx_gt_25",
            "metrics": adx_metrics,
            "risk_adjusted": _risk_adjusted_metrics(adx_daily_pnl),
            "monthly_stability": _monthly_stability_metrics(adx_daily_pnl),
        },
        {
            "name": "tier2_quality_adx_gt_30",
            "metrics": adx30_metrics,
            "risk_adjusted": _risk_adjusted_metrics(adx30_daily_pnl),
            "monthly_stability": _monthly_stability_metrics(adx30_daily_pnl),
        },
    ]

    for row in candidates:
        row["composite_score"] = _composite_score(row["risk_adjusted"])

    candidates.sort(key=lambda row: float(row["composite_score"]), reverse=True)
    for rank, row in enumerate(candidates, start=1):
        row["rank"] = rank

    summary = {
        "candidates": candidates,
        "interpretation": [
            "Use the exact same Sortino-weighted composite as the main production comparison.",
            "This isolates whether the ADX quality mode is superior to the validated MT5 base and the simpler cooldown tier on a risk-adjusted basis.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
