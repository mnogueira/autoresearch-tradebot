from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

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
from .stalker_v10_1_python import _ensure_signal_strength_cache
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_ml_recent_followups_20260328")


def _risk_block(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, Any]:
    if trades.empty:
        return {
            "risk_adjusted_metrics": {
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "omega_ratio": 0.0,
                "annual_return_pct": 0.0,
                "max_drawdown_frac": 0.0,
            },
            "sortino_weighted_composite": 0.0,
        }
    risk_metrics = _risk_adjusted_metrics(_daily_pnl_from_trades(trades, trade_dates))
    for key in ("sortino_ratio", "calmar_ratio", "omega_ratio"):
        value = float(risk_metrics[key])
        if not np.isfinite(value):
            risk_metrics[key] = 0.0
    return {
        "risk_adjusted_metrics": risk_metrics,
        "sortino_weighted_composite": _composite_score(risk_metrics),
    }


def _leaderboard_row(
    name: str,
    metrics: dict[str, Any],
    notes: str,
    artifact: Path,
    comparison_tier: str,
    params: dict[str, Any] | None = None,
    risk_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = candidate_row(
        name=name,
        family="stalker_v10_1_ml_signal",
        metrics=metrics,
        notes=notes,
        artifact=artifact,
        params=params,
    )
    row["comparison_tier"] = comparison_tier
    row["screening_method"] = "ml_signal_followup"
    if risk_block is not None:
        risk_metrics = dict(risk_block.get("risk_adjusted_metrics", {}))
        row["sortino_ratio"] = risk_metrics.get("sortino_ratio")
        row["calmar_ratio"] = risk_metrics.get("calmar_ratio")
        row["omega_ratio"] = risk_metrics.get("omega_ratio")
        row["sortino_weighted_composite"] = risk_block.get("sortino_weighted_composite")
    return row


def _build_trade_feature_frame(
    dataset: V10Dataset,
    trades: pd.DataFrame,
) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    high_col = "High" if "High" in bars.columns else "high"
    low_col = "Low" if "Low" in bars.columns else "low"
    close_col = "Close" if "Close" in bars.columns else "close"
    real_volume_col = "RealVolume" if "RealVolume" in bars.columns else "real_volume"
    close = bars[close_col].astype(float)
    ret_1 = close.pct_change()
    strength = _ensure_signal_strength_cache(dataset=dataset, trend_window=15, volume_window=30, relative_volume_lookback=20)
    atr14 = dataset.get_atr_current(14)
    range_points = (bars[high_col].astype(float) - bars[low_col].astype(float)).astype(float)

    features = pd.DataFrame(index=bars.index)
    features["trend_eff_raw"] = strength["trend_efficiency_raw"]
    features["signal_volume_sum"] = strength["signal_volume_sum"]
    features["relative_volume"] = strength["relative_volume"]
    features["atr14"] = atr14
    features["bar_volume"] = bars[real_volume_col].astype(float)
    features["ret_5"] = close.pct_change(5)
    features["ret_20"] = close.pct_change(20)
    features["ret_100"] = close.pct_change(100)
    features["vol_20"] = ret_1.rolling(20).std()
    features["vol_100"] = ret_1.rolling(100).std()
    features["avg_range_20"] = range_points.rolling(20).mean()
    features["avg_range_100"] = range_points.rolling(100).mean()
    features["hour"] = features.index.hour.astype(float)
    features["minute"] = features.index.minute.astype(float)
    features["dayofweek"] = features.index.dayofweek.astype(float)

    trade_frame = trades.copy()
    trade_frame["signal_time"] = pd.to_datetime(trade_frame["signal_time"]).dt.floor("min")
    trade_frame["direction_num"] = trade_frame["direction"].map({"long": 1.0, "short": -1.0}).astype(float)
    trade_frame["entry_time"] = pd.to_datetime(trade_frame["entry_time"]).dt.floor("min")

    joined = trade_frame.join(features, on="signal_time")
    joined["signed_trend_eff"] = joined["direction_num"] * joined["trend_eff_raw"]
    joined["signed_ret_5"] = joined["direction_num"] * joined["ret_5"]
    joined["signed_ret_20"] = joined["direction_num"] * joined["ret_20"]
    joined["signed_ret_100"] = joined["direction_num"] * joined["ret_100"]
    joined["next_close"] = close.shift(-1).reindex(joined["signal_time"]).to_numpy()
    joined["signal_close"] = close.reindex(joined["signal_time"]).to_numpy()
    joined["label_next_bar_supports_direction"] = (
        (joined["next_close"] - joined["signal_close"]) * joined["direction_num"]
    ) > 0.0
    return joined


def _time_series_oof_probabilities(
    frame: pd.DataFrame,
    feature_columns: list[str],
    label_column: str,
    model_name: str,
) -> dict[str, Any]:
    data = frame.reset_index(drop=True).copy()
    valid_mask = data[feature_columns].notna().all(axis=1) & data[label_column].notna()
    data = data.loc[valid_mask].reset_index(drop=True)
    X = data[feature_columns]
    y = data[label_column].astype(int)

    if model_name == "logistic":
        estimator = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", LogisticRegression(max_iter=2000)),
            ]
        )
    else:
        estimator = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=300,
                        max_depth=6,
                        min_samples_leaf=10,
                        random_state=42,
                        n_jobs=1,
                    ),
                ),
            ]
        )

    splitter = TimeSeriesSplit(n_splits=5)
    probabilities = np.full(len(data), np.nan, dtype=float)
    for train_idx, test_idx in splitter.split(X):
        y_train = y.iloc[train_idx]
        if y_train.nunique() < 2:
            probabilities[test_idx] = float(y_train.iloc[0]) if len(y_train) else 0.5
            continue
        estimator.fit(X.iloc[train_idx], y_train)
        probabilities[test_idx] = estimator.predict_proba(X.iloc[test_idx])[:, 1]

    evaluated = ~np.isnan(probabilities)
    auc = float(roc_auc_score(y.iloc[evaluated], probabilities[evaluated])) if evaluated.sum() > 1 else 0.5
    acc = float(accuracy_score(y.iloc[evaluated], probabilities[evaluated] >= 0.5)) if evaluated.sum() else 0.0
    data["predicted_prob"] = probabilities
    return {
        "scored_frame": data,
        "coverage": int(evaluated.sum()),
        "coverage_pct": round(float(evaluated.mean() * 100.0), 2),
        "auc": round(float(auc), 4),
        "accuracy": round(float(acc), 4),
    }


def _apply_probability_gate(
    scored_frame: pd.DataFrame,
    threshold: float,
    trade_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    gated = scored_frame.loc[scored_frame["predicted_prob"].ge(float(threshold))].copy()
    metrics = calculate_metrics(gated, trade_dates)
    return gated, metrics


def _apply_probability_overlay(
    scored_frame: pd.DataFrame,
    trade_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, float]]:
    frame = scored_frame.copy()
    frame["size_multiplier"] = np.clip(1.0 + ((frame["predicted_prob"] - 0.5) / 0.2), 0.5, 1.5)
    frame["pnl_brl"] = frame["pnl_brl"].astype(float) * frame["size_multiplier"]
    frame["pnl_points"] = frame["pnl_points"].astype(float) * frame["size_multiplier"]
    metrics = calculate_metrics(frame, trade_dates)
    stats = {
        "mean": round(float(frame["size_multiplier"].mean()), 4),
        "median": round(float(frame["size_multiplier"].median()), 4),
        "p25": round(float(frame["size_multiplier"].quantile(0.25)), 4),
        "p75": round(float(frame["size_multiplier"].quantile(0.75)), 4),
        "min": round(float(frame["size_multiplier"].min()), 4),
        "max": round(float(frame["size_multiplier"].max()), 4),
    }
    return frame, metrics, stats


def _blend_trade_sets(trades_a: pd.DataFrame, trades_b: pd.DataFrame, trade_dates: pd.Index) -> tuple[pd.DataFrame, dict[str, Any]]:
    key_cols = ["session_date", "signal_time", "entry_time", "direction"]
    left = trades_a.copy()
    right = trades_b.copy()
    for frame in (left, right):
        frame["signal_time"] = pd.to_datetime(frame["signal_time"]).dt.floor("min")
        frame["entry_time"] = pd.to_datetime(frame["entry_time"]).dt.floor("min")
    merged = left.merge(
        right[key_cols + ["pnl_brl", "pnl_points"]],
        on=key_cols,
        suffixes=("_a", "_b"),
        how="inner",
    )
    blended = merged.drop(columns=["pnl_brl_b", "pnl_points_b"]).rename(
        columns={"pnl_brl_a": "pnl_brl", "pnl_points_a": "pnl_points"}
    )
    blended["pnl_brl"] = (merged["pnl_brl_a"].astype(float) + merged["pnl_brl_b"].astype(float)) / 2.0
    blended["pnl_points"] = (merged["pnl_points_a"].astype(float) + merged["pnl_points_b"].astype(float)) / 2.0
    metrics = calculate_metrics(blended, trade_dates)
    return blended, metrics


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    trade_dates = dataset.trade_dates
    entry_filter = session_filter({10, 11, 12, 14})
    management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=management,
    )

    feature_frame = _build_trade_feature_frame(dataset, reference_trades)
    feature_columns = [
        "signed_trend_eff",
        "atr14",
        "signal_volume_sum",
        "relative_volume",
        "bar_volume",
        "signed_ret_5",
        "signed_ret_20",
        "signed_ret_100",
        "vol_20",
        "vol_100",
        "avg_range_20",
        "avg_range_100",
        "hour",
        "minute",
        "dayofweek",
    ]
    core_feature_columns = [
        "signed_trend_eff",
        "atr14",
        "relative_volume",
        "signal_volume_sum",
        "hour",
        "dayofweek",
    ]
    label_column = "label_next_bar_supports_direction"

    logistic_result = _time_series_oof_probabilities(feature_frame, feature_columns, label_column, "logistic")
    logistic_core_result = _time_series_oof_probabilities(feature_frame, core_feature_columns, label_column, "logistic")
    forest_result = _time_series_oof_probabilities(feature_frame, feature_columns, label_column, "forest")

    logistic_gate_trades, logistic_gate_metrics = _apply_probability_gate(
        logistic_result["scored_frame"],
        threshold=0.55,
        trade_dates=trade_dates,
    )
    logistic_overlay_trades, logistic_overlay_metrics, logistic_overlay_stats = _apply_probability_overlay(
        logistic_result["scored_frame"],
        trade_dates=trade_dates,
    )
    logistic_core_overlay_trades, logistic_core_overlay_metrics, logistic_core_overlay_stats = _apply_probability_overlay(
        logistic_core_result["scored_frame"],
        trade_dates=trade_dates,
    )
    forest_gate_trades, forest_gate_metrics = _apply_probability_gate(
        forest_result["scored_frame"],
        threshold=0.55,
        trade_dates=trade_dates,
    )
    forest_overlay_trades, forest_overlay_metrics, forest_overlay_stats = _apply_probability_overlay(
        forest_result["scored_frame"],
        trade_dates=trade_dates,
    )

    time_widened_trades, _ = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=trade_dates,
        entry_filter=entry_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            widen_stop_after_bars=30,
            widened_sl_atr_mult=1.20,
        ),
    )
    ensemble_trades, ensemble_metrics = _blend_trade_sets(reference_trades, time_widened_trades, trade_dates)

    recent_dates = trade_dates[-10:]
    recent_trades, recent_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_dates,
        entry_filter=entry_filter,
        management=management,
    )

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30",
            "metrics": reference_metrics,
            **_risk_block(reference_trades, trade_dates),
        },
        "ml_signal_models": {
            "logistic_regression_next_bar_direction": {
                "coverage": logistic_result["coverage"],
                "coverage_pct": logistic_result["coverage_pct"],
                "auc": logistic_result["auc"],
                "accuracy": logistic_result["accuracy"],
            },
            "logistic_regression_core_feature_set": {
                "coverage": logistic_core_result["coverage"],
                "coverage_pct": logistic_core_result["coverage_pct"],
                "auc": logistic_core_result["auc"],
                "accuracy": logistic_core_result["accuracy"],
            },
            "random_forest_next_bar_direction": {
                "coverage": forest_result["coverage"],
                "coverage_pct": forest_result["coverage_pct"],
                "auc": forest_result["auc"],
                "accuracy": forest_result["accuracy"],
            },
        },
        "logistic_gate_0p55": {
            "rule": "Only keep production-candidate trades whose out-of-fold logistic probability of next-bar support is at least 0.55.",
            "metrics": logistic_gate_metrics,
            **_risk_block(logistic_gate_trades, trade_dates),
        },
        "logistic_confidence_overlay": {
            "rule": "Research-only probability-weighted sizing overlay from out-of-fold logistic regression predictions.",
            "metrics": logistic_overlay_metrics,
            **_risk_block(logistic_overlay_trades, trade_dates),
            "multiplier_stats": logistic_overlay_stats,
        },
        "logistic_core_feature_overlay": {
            "rule": "Research-only probability-weighted sizing overlay from a simpler out-of-fold logistic model using only core trend/ATR/volume/calendar features.",
            "metrics": logistic_core_overlay_metrics,
            **_risk_block(logistic_core_overlay_trades, trade_dates),
            "multiplier_stats": logistic_core_overlay_stats,
        },
        "random_forest_gate_0p55": {
            "rule": "Only keep production-candidate trades whose out-of-fold random-forest probability of next-bar support is at least 0.55.",
            "metrics": forest_gate_metrics,
            **_risk_block(forest_gate_trades, trade_dates),
        },
        "random_forest_confidence_overlay": {
            "rule": "Research-only probability-weighted sizing overlay from out-of-fold random-forest predictions.",
            "metrics": forest_overlay_metrics,
            **_risk_block(forest_overlay_trades, trade_dates),
            "multiplier_stats": forest_overlay_stats,
        },
        "equal_weight_ensemble_reference_and_timewidened": {
            "rule": "Research-only equal-weight blend of the two strongest exact strategies: max-hold v2 and time-widened stop.",
            "metrics": ensemble_metrics,
            **_risk_block(ensemble_trades, trade_dates),
        },
        "recent_10_trading_days_check": {
            "start_date": str(pd.to_datetime(recent_dates[0]).date()),
            "end_date": str(pd.to_datetime(recent_dates[-1]).date()),
            "metrics": recent_metrics,
            **_risk_block(recent_trades, recent_dates),
        },
        "notes": [
            "The ML overlay is intentionally research-only: it scores executed production-candidate trades with out-of-fold time-series predictions and then applies either a hard gate or a probability-weighted sizing multiplier.",
            "Labels are defined as whether the next M1 bar closes in the trade direction immediately after the signal timestamp.",
            "This is a directional confirmation experiment, not a full replacement for the exact entry engine.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        _leaderboard_row(
            name="session_winner_cooldown_30m_maxhold120_logistic_gate_0p55",
            metrics=logistic_gate_metrics,
            notes="Research-only out-of-fold logistic gate on the production candidate.",
            artifact=summary_path,
            comparison_tier="analysis",
            params={"model": "logistic_regression", "threshold": 0.55},
            risk_block=_risk_block(logistic_gate_trades, trade_dates),
        ),
        _leaderboard_row(
            name="session_winner_cooldown_30m_maxhold120_logistic_confidence_overlay",
            metrics=logistic_overlay_metrics,
            notes="Research-only out-of-fold logistic confidence-weighted sizing overlay on the production candidate.",
            artifact=summary_path,
            comparison_tier="analysis",
            params={"model": "logistic_regression", "overlay": "probability_weighted"},
            risk_block=_risk_block(logistic_overlay_trades, trade_dates),
        ),
        _leaderboard_row(
            name="session_winner_cooldown_30m_maxhold120_logistic_core_confidence_overlay",
            metrics=logistic_core_overlay_metrics,
            notes="Research-only out-of-fold logistic confidence-weighted sizing overlay on the production candidate using a simpler core feature set.",
            artifact=summary_path,
            comparison_tier="analysis",
            params={"model": "logistic_regression_core", "overlay": "probability_weighted"},
            risk_block=_risk_block(logistic_core_overlay_trades, trade_dates),
        ),
        _leaderboard_row(
            name="session_winner_cooldown_30m_maxhold120_random_forest_gate_0p55",
            metrics=forest_gate_metrics,
            notes="Research-only out-of-fold random-forest gate on the production candidate.",
            artifact=summary_path,
            comparison_tier="analysis",
            params={"model": "random_forest", "threshold": 0.55},
            risk_block=_risk_block(forest_gate_trades, trade_dates),
        ),
        _leaderboard_row(
            name="session_winner_cooldown_30m_maxhold120_random_forest_confidence_overlay",
            metrics=forest_overlay_metrics,
            notes="Research-only out-of-fold random-forest confidence-weighted sizing overlay on the production candidate.",
            artifact=summary_path,
            comparison_tier="analysis",
            params={"model": "random_forest", "overlay": "probability_weighted"},
            risk_block=_risk_block(forest_overlay_trades, trade_dates),
        ),
        _leaderboard_row(
            name="session_winner_equal_weight_ensemble_maxhold_timewidened",
            metrics=ensemble_metrics,
            notes="Research-only equal-weight blend of the max-hold and time-widened exact strategies.",
            artifact=summary_path,
            comparison_tier="analysis",
            params={"blend": ["session_winner_cooldown_30m_maxhold120_sl0p84_tp0p30", "session_winner_cooldown_30m_maxhold120_timewidened"], "weights": [0.5, 0.5]},
            risk_block=_risk_block(ensemble_trades, trade_dates),
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)


if __name__ == "__main__":
    main()
