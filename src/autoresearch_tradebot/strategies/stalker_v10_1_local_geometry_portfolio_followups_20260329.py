from __future__ import annotations

import json
from dataclasses import asdict, replace

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_regime_roc_fine_followups_20260329 import _leaderboard_row
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_local_geometry_portfolio_followups_20260329")


def _combine_filters(*filters):
    active = [candidate for candidate in filters if candidate is not None]
    if not active:
        return None

    def _combined(context):
        return all(bool(candidate(context)) for candidate in active)

    return _combined


def _scaled_sleeve(trades: pd.DataFrame, weight: float, sleeve_name: str) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    scaled = trades.copy()
    scaled["pnl_brl"] = scaled["pnl_brl"].astype(float) * float(weight)
    if "pnl_points" in scaled.columns:
        scaled["pnl_points"] = scaled["pnl_points"].astype(float) * float(weight)
    scaled["portfolio_sleeve"] = sleeve_name
    scaled["portfolio_weight"] = float(weight)
    return scaled


def _equal_weight_portfolio(trade_frames: list[tuple[str, pd.DataFrame]]) -> pd.DataFrame:
    if not trade_frames:
        return pd.DataFrame()
    sleeves = [_scaled_sleeve(trades, 1.0 / len(trade_frames), sleeve_name) for sleeve_name, trades in trade_frames]
    combined = pd.concat(sleeves, ignore_index=True)
    sort_columns = [column for column in ("entry_time", "exit_time", "signal_time") if column in combined.columns]
    if sort_columns:
        combined = combined.sort_values(sort_columns).reset_index(drop=True)
    return combined


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_60 = trade_dates[-60:]

    params = replace(
        session_winner_params(),
        ATR_Length=10,
        NumDaysToConsiderPreviousContractMARange=2,
    )
    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)
    entry_filter = _combine_filters(base_filter, roc5_filter)

    tier2a_management = ManagementConfig(min_minutes_between_entries=28)
    tier3_management = ManagementConfig(min_minutes_between_entries=25, max_bars_in_trade=150)

    tier2a_trades, tier2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier2a_management,
    )
    tier3_trades, tier3_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=tier3_management,
    )

    portfolio_trades = _equal_weight_portfolio(
        [
            ("tier2a_atr10_contractlookback2_cooldown28", tier2a_trades),
            ("tier3_atr10_contractlookback2_roc5_maxhold150", tier3_trades),
        ]
    )
    portfolio_metrics = calculate_metrics(portfolio_trades, trade_dates)

    train_portfolio = filter_trades_to_dates(portfolio_trades, train_dates)
    test_portfolio = filter_trades_to_dates(portfolio_trades, test_dates)
    recent_portfolio = filter_trades_to_dates(portfolio_trades, recent_60)

    summary = {
        "tier2a_reference": {
            "metrics": tier2a_metrics,
            **_risk_block(tier2a_trades, trade_dates),
        },
        "tier3_reference": {
            "metrics": tier3_metrics,
            **_risk_block(tier3_trades, trade_dates),
        },
        "portfolio_equal_weight_t2a_t3_local_geometry": {
            "metrics": portfolio_metrics,
            **_risk_block(portfolio_trades, trade_dates),
        },
        "walkforward_70_30": {
            "train_metrics": calculate_metrics(train_portfolio, train_dates),
            "train_risk": _risk_block(train_portfolio, train_dates),
            "test_metrics": calculate_metrics(test_portfolio, test_dates),
            "test_risk": _risk_block(test_portfolio, test_dates),
        },
        "recent_60d": {
            "metrics": calculate_metrics(recent_portfolio, recent_60),
            **_risk_block(recent_portfolio, recent_60),
        },
        "params": {
            "tier2a_management": asdict(tier2a_management),
            "tier3_management": asdict(tier3_management),
            "roc_agreement_bars": 5,
            "ATR_Length": int(params.ATR_Length),
            "NumDaysToConsiderPreviousContractMARange": int(params.NumDaysToConsiderPreviousContractMARange),
            "weights": {"tier2a": 0.5, "tier3": 0.5},
        },
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_variant = {
        "name": "portfolio_equal_weight_t2a_t3_local_geometry",
        "rule": "Research-only 50/50 sleeve blend of strengthened Tier 2A and strengthened Tier 3 local-geometry branches.",
        "metrics": portfolio_metrics,
        "risk_adjusted_metrics": summary["portfolio_equal_weight_t2a_t3_local_geometry"]["risk_adjusted_metrics"],
        "sortino_weighted_composite": summary["portfolio_equal_weight_t2a_t3_local_geometry"]["sortino_weighted_composite"],
        "params": summary["params"],
    }
    row = _leaderboard_row(leaderboard_variant, summary_path)
    row["family"] = "stalker_v10_1_local_geometry_portfolio_followup"
    row["screening_method"] = "local_geometry_portfolio_followup"
    row["comparison_tier"] = "research_portfolio"
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, [row])


if __name__ == "__main__":
    main()
