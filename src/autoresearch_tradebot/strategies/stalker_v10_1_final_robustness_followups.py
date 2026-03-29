from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_roc_agreement_followups import _make_roc_filter, _risk_block
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_structural_ablation_rollover import contract_rollover_buckets
from .stalker_v10_python import V10Dataset, locate_data_file, split_dates

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_final_robustness_followups_20260329")


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _rollover_safe_filter(dataset: V10Dataset):
    rollover_daily = contract_rollover_buckets(dataset)
    allowed_dates = {
        pd.Timestamp(value).date().isoformat()
        for value in rollover_daily.index[rollover_daily["rollover_bucket"] != "last_3_contract_days"]
    }

    def _allow(context: dict[str, object]) -> bool:
        return pd.Timestamp(context["session_date"]).date().isoformat() in allowed_dates

    return _allow


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    trade_dates = dataset.trade_dates
    train_dates, test_dates = split_dates(trade_dates, 0.7)
    params = session_winner_params()

    tier1_filter = session_filter({10, 11, 12, 13, 14})
    tier2_filter = session_filter({10, 11, 12, 14})
    roc5_filter_fn = _make_roc_filter(dataset, 5)
    rollover_filter_fn = _rollover_safe_filter(dataset)

    def tier2a_filter(context: dict[str, object]) -> bool:
        return bool(tier2_filter(context) and roc5_filter_fn(context))

    def best_of_breed_filter(context: dict[str, object]) -> bool:
        return bool(tier2_filter(context) and roc5_filter_fn(context) and rollover_filter_fn(context))

    t1_management = ManagementConfig()
    t2_management = ManagementConfig(min_minutes_between_entries=25)

    t1_train_trades, t1_train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=tier1_filter,
        management=t1_management,
    )
    t1_test_trades, t1_test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=tier1_filter,
        management=t1_management,
    )
    t2_train_trades, t2_train_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=train_dates,
        entry_filter=tier2_filter,
        management=t2_management,
    )
    t2_test_trades, t2_test_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=test_dates,
        entry_filter=tier2_filter,
        management=t2_management,
    )

    best_trades, best_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=best_of_breed_filter,
        management=t2_management,
    )

    t2a_existing = _load_json(
        "artifacts/outputs/stalker_v10_1_roc_agreement_tier2_validation_20260329/summary.json"
    )
    t3_existing = _load_json(
        "artifacts/outputs/stalker_v10_1_maxhold150_walkforward_20260328/summary.json"
    )

    summary = {
        "tier_walkforward_70_30": {
            "tier1_exact_analog": {
                "note": "This is the exact-engine analog of the MT5 base preset, not a literal MT5 walk-forward.",
                "train_metrics": t1_train_metrics,
                "train_risk": _risk_block(t1_train_trades, train_dates),
                "test_metrics": t1_test_metrics,
                "test_risk": _risk_block(t1_test_trades, test_dates),
            },
            "tier2_cooldown_25m": {
                "train_metrics": t2_train_metrics,
                "train_risk": _risk_block(t2_train_trades, train_dates),
                "test_metrics": t2_test_metrics,
                "test_risk": _risk_block(t2_test_trades, test_dates),
            },
            "tier2a_cooldown_25m_roc5": t2a_existing["walkforward_70_30"],
            "tier3_cooldown_25m_maxhold150": {
                "train_metrics": t3_existing["train"]["metrics"],
                "train_risk": {
                    "risk_adjusted_metrics": t3_existing["train"]["risk_adjusted_metrics"],
                    "sortino_weighted_composite": t3_existing["train"]["sortino_weighted_composite"],
                },
                "test_metrics": t3_existing["test"]["metrics"],
                "test_risk": {
                    "risk_adjusted_metrics": t3_existing["test"]["risk_adjusted_metrics"],
                    "sortino_weighted_composite": t3_existing["test"]["sortino_weighted_composite"],
                },
            },
        },
        "best_of_breed_rollover_combo": {
            "name": "tier2a_cooldown_25m_roc5_skip_last3_contractdays",
            "rule": "Session + 25m cooldown + ROC(5) agreement + skip the last 3 contract days of each monthly contract bucket.",
            "metrics": best_metrics,
            **_risk_block(best_trades, trade_dates),
            "params": {
                "management": asdict(t2_management),
                "roc_agreement_bars": 5,
                "skip_last_contract_days": 3,
            },
        },
        "notes": [
            "Tier 1 is reported as an exact-engine analog because the MT5 Every Tick base preset does not have a literal Python walk-forward artifact.",
            "T2A and T3 reuse their existing exact walk-forward artifacts to avoid recomputing already validated runs.",
            "The best-of-breed combo tests whether stacking ROC agreement and rollover avoidance actually helps the now-mature core strategy.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    update_leaderboard(
        DEFAULT_LEADERBOARD_PATH,
        [
            candidate_row(
                name="tier2a_cooldown25_roc5_skip_last3_contractdays",
                family="stalker_v10_1_final_robustness",
                metrics=best_metrics,
                notes="Session + 25m cooldown + ROC(5) agreement + skip the last 3 contract days of each contract month proxy.",
                artifact=summary_path,
                params={
                    "management": asdict(t2_management),
                    "roc_agreement_bars": 5,
                    "skip_last_contract_days": 3,
                },
            )
        ],
    )


if __name__ == "__main__":
    main()
