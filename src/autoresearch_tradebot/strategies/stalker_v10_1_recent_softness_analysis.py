from __future__ import annotations

import json

import pandas as pd

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_1_session_macro_followups import compute_adx
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_recent_softness_analysis_20260328")


def daily_ohlc_from_bars(dataset: V10Dataset) -> pd.DataFrame:
    bars = dataset.bars_m1.copy()
    return (
        bars.assign(session_date=pd.to_datetime(bars["session_date"]).dt.normalize())
        .groupby("session_date")
        .agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"))
    )


def compute_daily_atr14(daily_ohlc: pd.DataFrame) -> pd.Series:
    high = daily_ohlc["High"].astype(float)
    low = daily_ohlc["Low"].astype(float)
    close = daily_ohlc["Close"].astype(float)
    tr = pd.concat(
        [
            (high - low),
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=(1.0 / 14.0), adjust=False).mean()


def recent_vs_full_quality(reference_metrics: dict[str, float], recent_metrics: dict[str, float]) -> dict[str, float]:
    return {
        "trades_per_day_full": round(float(reference_metrics["total_trades"]) / float(reference_metrics["trading_days"]), 4),
        "trades_per_day_recent": round(float(recent_metrics["total_trades"]) / float(recent_metrics["trading_days"]), 4),
        "win_rate_delta": round(float(recent_metrics["win_rate"]) - float(reference_metrics["win_rate"]), 4),
        "avg_profit_brl_delta": round(float(recent_metrics["avg_profit_brl"]) - float(reference_metrics["avg_profit_brl"]), 2),
        "profit_factor_delta": round(float(recent_metrics["profit_factor"]) - float(reference_metrics["profit_factor"]), 4),
    }


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    base_filter = session_filter({10, 11, 12, 14})
    recent_dates = dataset.trade_dates[-30:]

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )
    no_feature_trades, no_feature_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_dates,
        entry_filter=base_filter,
        management=ManagementConfig(),
    )
    cooldown_trades, cooldown_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30),
    )
    maxhold_only_trades, maxhold_only_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_dates,
        entry_filter=base_filter,
        management=ManagementConfig(max_bars_in_trade=120),
    )
    production_trades, production_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=recent_dates,
        entry_filter=base_filter,
        management=ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120),
    )

    production_trades = production_trades.copy()
    production_trades["entry_time"] = pd.to_datetime(production_trades["entry_time"])
    production_trades["session_date"] = pd.to_datetime(production_trades["session_date"])

    recent_trade_tape = {
        "exit_reason_counts": production_trades["exit_reason"].value_counts().to_dict() if not production_trades.empty else {},
        "daily_pnl_brl": {},
        "worst_trades": production_trades.nsmallest(5, "pnl_brl")[
            ["session_date", "entry_time", "direction", "pnl_brl", "exit_reason"]
        ].astype(str).to_dict(orient="records"),
        "best_trades": production_trades.nlargest(5, "pnl_brl")[
            ["session_date", "entry_time", "direction", "pnl_brl", "exit_reason"]
        ].astype(str).to_dict(orient="records"),
    }
    if not production_trades.empty:
        recent_trade_tape["daily_pnl_brl"] = {
            pd.Timestamp(session_date).date().isoformat(): float(pnl_brl)
            for session_date, pnl_brl in production_trades.groupby("session_date")["pnl_brl"].sum().sort_index().round(2).items()
        }

    daily_ohlc = daily_ohlc_from_bars(dataset)
    daily_range = (daily_ohlc["High"] - daily_ohlc["Low"]).astype(float)
    daily_atr14 = compute_daily_atr14(daily_ohlc)
    daily_adx14 = compute_adx(daily_ohlc, period=14).shift(1)

    recent_sessions = pd.to_datetime(recent_dates).normalize()
    recent_regime = daily_adx14.reindex(recent_sessions)
    full_regime = daily_adx14.dropna()

    regime_summary = {
        "recent_mean_daily_adx14": round(float(recent_regime.mean()), 2),
        "full_mean_daily_adx14": round(float(full_regime.mean()), 2),
        "recent_trending_share_gt25": round(float((recent_regime > 25.0).mean()), 4),
        "full_trending_share_gt25": round(float((full_regime > 25.0).mean()), 4),
        "recent_mean_daily_range": round(float(daily_range.reindex(recent_sessions).mean()), 4),
        "full_mean_daily_range": round(float(daily_range.mean()), 4),
        "recent_mean_daily_atr14": round(float(daily_atr14.reindex(recent_sessions).mean()), 4),
        "full_mean_daily_atr14": round(float(daily_atr14.mean()), 4),
    }

    summary = {
        "period": [str(recent_dates[0].date()), str(recent_dates[-1].date())],
        "production_reference_full_sample": reference_metrics,
        "recent_30d_variant_comparison": {
            "session_only_no_cooldown_no_maxhold": no_feature_metrics,
            "session_plus_cooldown_30m": cooldown_metrics,
            "session_plus_maxhold_120m1bars": maxhold_only_metrics,
            "session_plus_cooldown_30m_plus_maxhold_120m1bars": production_metrics,
        },
        "recent_vs_full_quality": recent_vs_full_quality(reference_metrics, production_metrics),
        "recent_trade_tape": recent_trade_tape,
        "recent_regime_summary": regime_summary,
        "interpretation_hints": [
            "If trades per day are not lower but PF and average profit collapse, that points to weaker signal quality rather than a simple signal drought.",
            "If recent ADX and recent daily range/ATR are below the full-sample average, that supports the range-bound / low-volatility explanation for softness.",
            "The feature comparison shows whether cooldown and max-hold still helped inside the weak recent tape, not just over the full sample.",
        ],
    }

    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    production_trades.to_csv(DEFAULT_OUTPUT_DIR / "recent_production_trades.csv", index=False)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
