from __future__ import annotations

import json

from ..common.paths import artifact_output_dir
from .stalker_v10_1_session_advanced_followups import DEFAULT_LEADERBOARD_PATH, update_leaderboard
from .stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    candidate_row,
    run_backtest_with_management,
    session_filter,
    session_winner_params,
)
from .stalker_v10_python import V10Dataset, locate_data_file

DEFAULT_OUTPUT_DIR = artifact_output_dir("stalker_v10_1_session_wrapup_followups_20260328")


def derive_positive_hour_mapping(
    trades,
    period_field: str,
    allowed_hours: set[int],
    min_trades_per_hour: int = 20,
) -> dict[int, list[int]]:
    if trades.empty:
        return {}

    frame = trades.copy()
    frame["entry_time"] = frame["entry_time"].astype("datetime64[ns]")
    frame["entry_hour"] = frame["entry_time"].dt.hour.astype(int)
    frame["month"] = frame["entry_time"].dt.month.astype(int)
    frame["quarter"] = frame["entry_time"].dt.quarter.astype(int)

    grouped = (
        frame.groupby([period_field, "entry_hour"], as_index=False)
        .agg(net_profit_brl=("pnl_brl", "sum"), total_trades=("pnl_brl", "size"))
        .sort_values([period_field, "entry_hour"])
    )

    mapping: dict[int, list[int]] = {}
    for period_value, period_rows in grouped.groupby(period_field):
        selected_hours = sorted(
            int(row["entry_hour"])
            for _, row in period_rows.iterrows()
            if int(row["entry_hour"]) in allowed_hours
            and int(row["total_trades"]) >= int(min_trades_per_hour)
            and float(row["net_profit_brl"]) > 0.0
        )
        mapping[int(period_value)] = selected_hours or sorted(int(hour) for hour in allowed_hours)
    return mapping


def adaptive_period_filter(period_mapping: dict[int, list[int]], period_field: str):
    def _filter(context: dict[str, object]) -> bool:
        timestamp = context["timestamp"]
        entry_hour = int(context["entry_hour"])
        if period_field == "month":
            period_value = int(timestamp.month)
        else:
            period_value = int(timestamp.quarter)
        return entry_hour in period_mapping.get(period_value, [])

    return _filter


def main() -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = V10Dataset.from_disk(locate_data_file(None))
    params = session_winner_params()
    allowed_hours = {10, 11, 12, 14}
    base_filter = session_filter(allowed_hours)
    base_management = ManagementConfig(min_minutes_between_entries=30, max_bars_in_trade=120)

    reference_trades, reference_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=base_management,
    )

    quarter_mapping = derive_positive_hour_mapping(reference_trades, "quarter", allowed_hours)
    month_mapping = derive_positive_hour_mapping(reference_trades, "month", allowed_hours)

    _, adaptive_quarter_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=adaptive_period_filter(quarter_mapping, "quarter"),
        management=base_management,
    )
    _, adaptive_month_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=adaptive_period_filter(month_mapping, "month"),
        management=base_management,
    )

    active_daily_pnl = reference_trades.groupby("session_date")["pnl_brl"].sum()
    avg_active_daily_profit_brl = float(active_daily_pnl.mean()) if not active_daily_pnl.empty else 0.0
    max_daily_profit_brl = round(avg_active_daily_profit_brl * 2.0, 2)

    _, daily_profit_cap_metrics = run_backtest_with_management(
        dataset=dataset,
        params=params,
        trade_dates=dataset.trade_dates,
        entry_filter=base_filter,
        management=ManagementConfig(
            min_minutes_between_entries=30,
            max_bars_in_trade=120,
            max_daily_profit_brl=max_daily_profit_brl,
        ),
    )

    summary = {
        "reference_variant": "session_winner_cooldown_30m_max_hold_120m1bars",
        "reference_metrics": reference_metrics,
        "adaptive_session_hours": {
            "quarter_mapping": quarter_mapping,
            "quarter_metrics": adaptive_quarter_metrics,
            "month_mapping": month_mapping,
            "month_metrics": adaptive_month_metrics,
            "selection_rule": "For each month or quarter, keep the allowed hours whose reference-tape net profit stayed positive with at least 20 trades.",
        },
        "max_daily_profit_rule": {
            "rule": "Stop taking new entries for the day once realized PnL reaches 2x the reference variant's average active-day profit.",
            "avg_active_daily_profit_brl": round(avg_active_daily_profit_brl, 2),
            "max_daily_profit_brl": float(max_daily_profit_brl),
            "metrics": daily_profit_cap_metrics,
        },
        "notes": [
            "The adaptive-hour mappings are derived from the current reference trade tape, so they are exploratory and carry explicit in-sample overfit risk.",
            "The max-daily-profit rule only blocks new entries after the realized session PnL crosses the threshold; it does not force-close an open position.",
        ],
    }
    summary_path = DEFAULT_OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    leaderboard_rows = [
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_quarter_adaptive_hours",
            family="session_adaptive_hours",
            metrics=adaptive_quarter_metrics,
            notes="Exact max-hold leader with exploratory quarter-specific hour subsets derived from the reference trade tape.",
            artifact=summary_path,
            params={"period": "quarter", "mapping": quarter_mapping, "selection_rule": "positive_net_with_min_20_trades"},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_month_adaptive_hours",
            family="session_adaptive_hours",
            metrics=adaptive_month_metrics,
            notes="Exact max-hold leader with exploratory month-specific hour subsets derived from the reference trade tape.",
            artifact=summary_path,
            params={"period": "month", "mapping": month_mapping, "selection_rule": "positive_net_with_min_20_trades"},
        ),
        candidate_row(
            name="session_winner_cooldown_30m_maxhold120_daily_profit_cap_2x_active_day_mean",
            family="session_daily_profit_cap",
            metrics=daily_profit_cap_metrics,
            notes="Exact max-hold leader with a max-daily-profit rule at 2x the reference variant's average active-day profit.",
            artifact=summary_path,
            params={"max_daily_profit_brl": float(max_daily_profit_brl)},
        ),
    ]
    update_leaderboard(DEFAULT_LEADERBOARD_PATH, leaderboard_rows)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
