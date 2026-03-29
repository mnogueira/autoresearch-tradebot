from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_contract_stress_followups import summarise_contract_months
from .stalker_v10_1_final_robustness_followups import _load_json
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import filter_trades_to_dates
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_portfolio_contract_followups_20260329")


def _combine_filters(*filters: Callable[[dict[str, Any]], bool] | None) -> Callable[[dict[str, Any]], bool] | None:
    active = [entry_filter for entry_filter in filters if entry_filter is not None]
    if not active:
        return None

    def _combined(context: dict[str, Any]) -> bool:
        return all(bool(entry_filter(context)) for entry_filter in active)

    return _combined


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
        "metrics": metrics,
        **_risk_block(trades, trade_dates),
        "params": params,
    }


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
    sleeves = [_scaled_sleeve(trades, 1.0 / len(trade_frames), sleeve_name) for sleeve_name, trades in trade_frames]
    if not sleeves:
        return pd.DataFrame()
    combined = pd.concat(sleeves, ignore_index=True)
    sort_columns = [column for column in ("entry_time", "exit_time", "signal_time") if column in combined.columns]
    if sort_columns:
        combined = combined.sort_values(sort_columns).reset_index(drop=True)
    return combined


def _contract_variant_rows(
    variant_name: str,
    trades: pd.DataFrame,
    dataset: V10Dataset,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for contract_id, contract_daily in dataset.daily.groupby("contract_id", sort=True):
        contract_dates = pd.Index(contract_daily.index)
        contract_trades = filter_trades_to_dates(trades, contract_dates)
        metrics = calculate_metrics(contract_trades, contract_dates)
        risk_block = _risk_block(contract_trades, contract_dates)
        rows.append(
            {
                "variant_name": variant_name,
                "contract_id": str(contract_id),
                "trading_days": int(len(contract_dates)),
                "metrics": metrics,
                "risk_adjusted_metrics": risk_block["risk_adjusted_metrics"],
                "sortino_weighted_composite": risk_block["sortino_weighted_composite"],
            }
        )
    return rows


def _cross_variant_contract_summary(contract_rows_by_variant: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    variant_maps = {
        variant_name: {row["contract_id"]: row for row in rows}
        for variant_name, rows in contract_rows_by_variant.items()
    }
    all_contract_ids = sorted({contract_id for rows in variant_maps.values() for contract_id in rows})
    contract_rank_rows: list[dict[str, Any]] = []
    best_counts = {variant_name: 0 for variant_name in contract_rows_by_variant}

    for contract_id in all_contract_ids:
        ranking = []
        for variant_name, variant_map in variant_maps.items():
            row = variant_map.get(contract_id)
            if row is None:
                continue
            ranking.append(
                {
                    "variant_name": variant_name,
                    "net_profit_brl": row["metrics"]["net_profit_brl"],
                    "profit_factor": row["metrics"]["profit_factor"],
                    "max_drawdown_pct": row["metrics"]["max_drawdown_pct"],
                    "sortino_weighted_composite": row["sortino_weighted_composite"],
                }
            )
        ranking.sort(
            key=lambda item: (
                float(item["sortino_weighted_composite"]),
                float(item["profit_factor"]),
                float(item["net_profit_brl"]),
            ),
            reverse=True,
        )
        if ranking:
            best_counts[str(ranking[0]["variant_name"])] += 1
        contract_rank_rows.append({"contract_id": contract_id, "ranking": ranking})

    tier2_rows = variant_maps.get("tier2_cooldown_25m", {})
    tier2a_rows = variant_maps.get("tier2a_cooldown_25m_roc5", {})
    portfolio_rows = variant_maps.get("portfolio_equal_weight_t2_t2a", {})

    tier2a_beats_t2 = sum(
        1
        for contract_id in all_contract_ids
        if contract_id in tier2_rows
        and contract_id in tier2a_rows
        and float(tier2a_rows[contract_id]["sortino_weighted_composite"])
        > float(tier2_rows[contract_id]["sortino_weighted_composite"])
    )
    portfolio_beats_both = sum(
        1
        for contract_id in all_contract_ids
        if contract_id in tier2_rows
        and contract_id in tier2a_rows
        and contract_id in portfolio_rows
        and float(portfolio_rows[contract_id]["sortino_weighted_composite"])
        > max(
            float(tier2_rows[contract_id]["sortino_weighted_composite"]),
            float(tier2a_rows[contract_id]["sortino_weighted_composite"]),
        )
    )

    return {
        "best_variant_counts_by_contract": best_counts,
        "tier2a_beats_tier2_contract_count": int(tier2a_beats_t2),
        "portfolio_beats_both_contract_count": int(portfolio_beats_both),
        "rankings_by_contract": contract_rank_rows,
    }


def _leaderboard_row(variant: dict[str, Any], artifact: Path) -> dict[str, Any]:
    row = candidate_row(
        name=str(variant["name"]),
        family="stalker_v10_1_portfolio_contract_followup",
        metrics=dict(variant["metrics"]),
        notes=str(variant["rule"]),
        artifact=artifact,
        params=variant["params"],
    )
    row["comparison_tier"] = "research_portfolio" if "portfolio" in str(variant["name"]) else "exact"
    row["screening_method"] = "portfolio_contract_followup"
    risk_metrics = dict(variant["risk_adjusted_metrics"])
    row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
    row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
    row["omega_ratio"] = risk_metrics.get("omega_ratio")
    row["sortino_weighted_composite"] = variant["sortino_weighted_composite"]
    return row


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    recent_dates = trade_dates[-60:]
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    roc5_filter = _make_roc_filter(dataset, 5)

    def tier2a_filter(context: dict[str, Any]) -> bool:
        return bool(base_filter(context) and roc5_filter(context))

    management = ManagementConfig(min_minutes_between_entries=25)
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"

    t2_trades, t2_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=base_filter,
        management=management,
    )
    t2a_trades, t2a_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=tier2a_filter,
        management=management,
    )

    portfolio_trades = _equal_weight_portfolio(
        [
            ("tier2_cooldown_25m", t2_trades),
            ("tier2a_cooldown_25m_roc5", t2a_trades),
        ]
    )
    portfolio_metrics = calculate_metrics(portfolio_trades, trade_dates)

    variants = [
        _variant_payload(
            name="tier2_cooldown_25m",
            rule="Current simpler post-Monday upgrade path.",
            trades=t2_trades,
            metrics=t2_metrics,
            trade_dates=trade_dates,
            params={"management": asdict(management), "entry_hours": [10, 11, 12, 14]},
        ),
        _variant_payload(
            name="tier2a_cooldown_25m_roc5",
            rule="Tier 2 plus ROC(5) directional agreement.",
            trades=t2a_trades,
            metrics=t2a_metrics,
            trade_dates=trade_dates,
            params={"management": asdict(management), "entry_hours": [10, 11, 12, 14], "roc_agreement_bars": 5},
        ),
        _variant_payload(
            name="portfolio_equal_weight_t2_t2a",
            rule="Research-only 50/50 sleeve blend of Tier 2 and Tier 2A daily trade flow.",
            trades=portfolio_trades,
            metrics=portfolio_metrics,
            trade_dates=trade_dates,
            params={"sleeves": ["tier2_cooldown_25m", "tier2a_cooldown_25m_roc5"], "weights": [0.5, 0.5]},
        ),
    ]

    walkforward: dict[str, Any] = {}
    recent_60d: dict[str, Any] = {}
    contract_rows_by_variant: dict[str, list[dict[str, Any]]] = {}

    for variant in variants:
        variant_name = str(variant["name"])
        trades_df = (
            t2_trades
            if variant_name == "tier2_cooldown_25m"
            else t2a_trades
            if variant_name == "tier2a_cooldown_25m_roc5"
            else portfolio_trades
        )

        train_trades = filter_trades_to_dates(trades_df, train_dates)
        test_trades = filter_trades_to_dates(trades_df, test_dates)
        recent_trades = filter_trades_to_dates(trades_df, recent_dates)

        walkforward[variant_name] = {
            "train_metrics": calculate_metrics(train_trades, train_dates),
            "train_risk": _risk_block(train_trades, train_dates),
            "test_metrics": calculate_metrics(test_trades, test_dates),
            "test_risk": _risk_block(test_trades, test_dates),
        }
        recent_60d[variant_name] = {
            "metrics": calculate_metrics(recent_trades, recent_dates),
            **_risk_block(recent_trades, recent_dates),
        }
        contract_rows_by_variant[variant_name] = _contract_variant_rows(variant_name, trades_df, dataset)

    contract_summary_by_variant = {
        variant_name: summarise_contract_months(rows) for variant_name, rows in contract_rows_by_variant.items()
    }
    contract_cross_summary = _cross_variant_contract_summary(contract_rows_by_variant)

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

    summary = {
        "variants": ranked,
        "walkforward_70_30": walkforward,
        "recent_60d": recent_60d,
        "contract_month_behavior": {
            "by_variant_summary": contract_summary_by_variant,
            "cross_variant_summary": contract_cross_summary,
            "all_contract_rows": contract_rows_by_variant,
        },
        "notes": [
            "The portfolio sleeve is research-only and assumes equal capital split across Tier 2 and Tier 2A running in parallel.",
            "Contract-month behavior uses the existing monthly contract_id buckets from the daily dataset.",
            "This batch is designed to answer whether diversification between the current best simple exact lines beats either sleeve on its own.",
        ],
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(
        DEFAULT_LEADERBOARD_PATH,
        [_leaderboard_row(variant, summary_path) for variant in variants],
    )


if __name__ == "__main__":
    main()
