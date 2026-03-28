from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, calculate_metrics, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_minimal_risk_followups_20260328")
SYNTHETIC_STARTING_EQUITY_BRL = 10_000.0


def capture_vs_reference(reference: dict[str, float], candidate: dict[str, float]) -> dict[str, float]:
    def pct(field: str) -> float:
        baseline = float(reference[field])
        if baseline == 0.0:
            return 0.0
        return round(float(candidate[field]) / baseline, 4)

    return {
        "net_profit_capture": pct("net_profit_brl"),
        "profit_factor_capture": pct("profit_factor"),
        "on_tester_capture": pct("on_tester_value"),
        "drawdown_capture": pct("max_drawdown_pct"),
        "trade_count_capture": pct("total_trades"),
    }


def scale_trades(trades: pd.DataFrame, scale: float) -> pd.DataFrame:
    scaled = trades.copy()
    for column in ("pnl_brl", "avg_profit_brl"):
        if column in scaled.columns:
            scaled[column] = scaled[column].astype(float) * float(scale)
    return scaled


def daily_pnl_series(trades: pd.DataFrame, trade_dates: pd.Index) -> pd.Series:
    return (
        trades.assign(session_date=pd.to_datetime(trades["session_date"]))
        .groupby("session_date")["pnl_brl"]
        .sum()
        .reindex(pd.Index(pd.to_datetime(trade_dates)), fill_value=0.0)
    )


def rolling_profit_factor_summary(trades: pd.DataFrame, trade_dates: pd.Index, window_days: int = 60) -> dict[str, object]:
    trade_sessions = pd.to_datetime(trades["session_date"]).dt.normalize()
    pnl = trades["pnl_brl"].astype(float)
    records: list[dict[str, object]] = []
    normalized_trade_dates = pd.Index(pd.to_datetime(trade_dates).normalize())

    for end_idx in range(window_days - 1, len(normalized_trade_dates)):
        window_dates = normalized_trade_dates[end_idx - window_days + 1 : end_idx + 1]
        date_set = set(window_dates)
        mask = trade_sessions.isin(date_set).to_numpy()
        window_pnl = pnl.loc[mask]
        wins = float(window_pnl[window_pnl > 0.0].sum())
        losses = float(window_pnl[window_pnl < 0.0].abs().sum())
        if losses > 0.0:
            pf = wins / losses
        elif wins > 0.0:
            pf = float("inf")
        else:
            pf = 0.0
        records.append(
            {
                "window_start": pd.Timestamp(window_dates[0]).date().isoformat(),
                "window_end": pd.Timestamp(window_dates[-1]).date().isoformat(),
                "profit_factor": float(pf),
            }
        )

    rolling = pd.DataFrame(records)
    below_one = rolling["profit_factor"] < 1.0
    run_ids = below_one.ne(below_one.shift(fill_value=False)).cumsum()
    below_runs = (
        rolling.loc[below_one]
        .groupby(run_ids[below_one])
        .agg(
            length=("profit_factor", "size"),
            start=("window_start", "first"),
            end=("window_end", "last"),
            min_profit_factor=("profit_factor", "min"),
        )
    )
    longest_below_one = None
    if not below_runs.empty:
        longest = below_runs.sort_values(["length", "min_profit_factor"], ascending=[False, True]).iloc[0]
        longest_below_one = {
            "length_windows": int(longest["length"]),
            "start": str(longest["start"]),
            "end": str(longest["end"]),
            "min_profit_factor": round(float(longest["min_profit_factor"]), 4),
        }

    worst_window = rolling.sort_values(["profit_factor", "window_start"]).iloc[0]
    return {
        "window_days": int(window_days),
        "num_windows": int(len(rolling)),
        "min_profit_factor": round(float(rolling["profit_factor"].min()), 4),
        "median_profit_factor": round(float(rolling["profit_factor"].median()), 4),
        "share_windows_below_1": round(float((rolling["profit_factor"] < 1.0).mean()), 4),
        "worst_window": {
            "window_start": str(worst_window["window_start"]),
            "window_end": str(worst_window["window_end"]),
            "profit_factor": round(float(worst_window["profit_factor"]), 4),
        },
        "longest_below_1_stretch": longest_below_one,
    }


def underwater_summary(trades: pd.DataFrame, trade_dates: pd.Index) -> dict[str, object]:
    daily_pnl = daily_pnl_series(trades, trade_dates)
    equity = SYNTHETIC_STARTING_EQUITY_BRL + daily_pnl.cumsum()
    peaks = equity.cummax()
    underwater = equity < peaks
    longest: dict[str, object] | None = None
    current_start: pd.Timestamp | None = None
    current_length = 0
    last_underwater_timestamp: pd.Timestamp | None = None

    for timestamp, is_underwater in underwater.items():
        if bool(is_underwater):
            if current_start is None:
                current_start = pd.Timestamp(timestamp)
                current_length = 1
            else:
                current_length += 1
            last_underwater_timestamp = pd.Timestamp(timestamp)
        elif current_start is not None:
            candidate = {
                "trading_days": int(current_length),
                "start": current_start.date().isoformat(),
                "end": last_underwater_timestamp.date().isoformat() if last_underwater_timestamp is not None else current_start.date().isoformat(),
            }
            if longest is None or int(candidate["trading_days"]) > int(longest["trading_days"]):
                longest = candidate
            current_start = None
            current_length = 0
            last_underwater_timestamp = None

    if current_start is not None:
        candidate = {
            "trading_days": int(current_length),
            "start": current_start.date().isoformat(),
            "end": last_underwater_timestamp.date().isoformat() if last_underwater_timestamp is not None else current_start.date().isoformat(),
        }
        if longest is None or int(candidate["trading_days"]) > int(longest["trading_days"]):
            longest = candidate

    return {
        "longest_underwater_period": longest,
        "current_underwater": bool(underwater.iloc[-1]),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})

    full_trades, full_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    cooldown_only_trades, cooldown_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    session_only_trades, session_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(),
    )

    seventy_thirty_metrics = calculate_metrics(scale_trades(full_trades, 0.7), dataset.trade_dates)

    rolling_pf = rolling_profit_factor_summary(full_trades, dataset.trade_dates, window_days=60)
    underwater = underwater_summary(full_trades, dataset.trade_dates)

    baseline_dd_brl = round(SYNTHETIC_STARTING_EQUITY_BRL * (float(full_metrics["max_drawdown_pct"]) / 100.0), 2)
    stress_drawdown_pct = 46.44
    stress_dd_brl = round(SYNTHETIC_STARTING_EQUITY_BRL * (stress_drawdown_pct / 100.0), 2)
    capital_for_5pct_stress = round(stress_dd_brl / 0.05, 2)
    capital_for_3pct_stress = round(stress_dd_brl / 0.03, 2)

    summary = {
        "reference_variant": {
            "name": "session_winner_cooldown_30m_maxhold_120m1bars",
            "metrics": full_metrics,
        },
        "minimal_variants": {
            "session_plus_cooldown_only": {
                "metrics": cooldown_only_metrics,
                "capture_vs_reference": capture_vs_reference(full_metrics, cooldown_only_metrics),
                "interpretation": "Simplest high-fidelity variant: drops the max hold but keeps the session filter, best SL/TP, and cooldown.",
            },
            "session_only_core": {
                "metrics": session_only_metrics,
                "capture_vs_reference": capture_vs_reference(full_metrics, session_only_metrics),
                "interpretation": "Strict minimal session winner: session filter plus best SL/TP and the core signal stack, without cooldown or max hold.",
            },
        },
        "portfolio_thought_experiment": {
            "note": "True WDO/WIN allocation cannot be optimized without WIN history. This is only a 70% WDO / 30% reserve-cash scaling proxy using the production candidate's own trade tape.",
            "wdo_70_cash_30_metrics": seventy_thirty_metrics,
        },
        "rolling_60d_profit_factor": rolling_pf,
        "underwater_profile": underwater,
        "risk_budget": {
            "synthetic_starting_equity_brl": SYNTHETIC_STARTING_EQUITY_BRL,
            "baseline_drawdown_brl_per_contract": baseline_dd_brl,
            "stress_drawdown_brl_per_contract_3x_spread": stress_dd_brl,
            "capital_needed_for_5pct_stress_budget_per_contract_brl": capital_for_5pct_stress,
            "capital_needed_for_3pct_stress_budget_per_contract_brl": capital_for_3pct_stress,
            "recommended_max_contracts_per_100k_brl": 1,
            "stretch_upper_bound_contracts_per_100k_brl": 2,
            "rationale": "One contract per R$100k keeps even the harsh 3x-spread stress case near a 5% capital drawdown. More than that should wait for live-paper spread confirmation.",
        },
        "notes": [
            "The cooldown-only minimal variant is the cleanest simplification test because the max hold was already shown to be only a marginal refinement.",
            "The 70/30 allocation is not a true WDO/WIN optimizer; it is just a scaled-sleeve thought experiment using WDO-only data.",
            "Rolling 60-day PF is computed over trailing 60-trading-day windows to expose soft patches, while the underwater profile uses the full exact daily equity curve.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
