from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import optuna
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None

from ..common.paths import artifact_output_dir
from .stalker_wdo import (
    FLOAT_EPS,
    POINT_VALUE_BRL,
    ROUND_TRIP_COST_BRL,
    StalkerDataset,
    StrategyParams,
    Trade,
    WalkForwardWindowResult,
    calculate_metrics,
    compute_retracement_price,
    fill_limit_order,
    generate_walk_forward_windows,
    locate_data_file,
    measure_activation_leg,
    optimize_split,
    params_from_mapping,
    parse_clock_time,
    resolve_exit_on_bar,
    round_to_tick,
    run_backtest,
    sample_params,
    split_dates_by_ratio,
)


def run_backtest_1m(
    dataset: StalkerDataset,
    params: StrategyParams,
    trade_dates: pd.Index,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if dataset.bars_1m is None or dataset.bars_1m.empty:
        raise ValueError("1m data is required for intrabar validation.")
    if params.use_1h_filter and params.h1_fast_ema >= params.h1_slow_ema:
        raise ValueError("When the 1h filter is enabled, h1_fast_ema must be < h1_slow_ema.")
    if parse_clock_time(params.session_exit_time) <= parse_clock_time(params.last_entry_time):
        raise ValueError("session_exit_time must be later than last_entry_time.")

    minute_dates = set(dataset.bars_1m.index.normalize())
    overlap_dates = pd.Index([date for date in pd.to_datetime(trade_dates) if date in minute_dates]).sort_values()
    if len(overlap_dates) == 0:
        raise ValueError("No overlap between requested trade_dates and available 1m data.")

    date_set = set(overlap_dates)
    frame = dataset.bars_15m[dataset.bars_15m["session_date"].isin(date_set)].copy()
    minute_frame = dataset.bars_1m[dataset.bars_1m.index.normalize().isin(date_set)].copy()
    minute_by_day = {date: day.copy() for date, day in minute_frame.groupby(minute_frame.index.normalize())}

    atr_series = dataset.get_atr_series(params.atr_timeframe, params.atr_period).reindex(frame.index)
    if params.use_1h_filter:
        trend_series = dataset.get_h1_trend(params.h1_fast_ema, params.h1_slow_ema).reindex(frame.index)
    else:
        trend_series = pd.Series(0, index=frame.index, dtype=int)

    range_reference = dataset.get_range_reference(
        mode=params.range_reference_mode,
        lookback_days=params.range_lookback_days,
        prev_contract_days=params.prev_contract_days,
    )
    range_reference_map = range_reference.to_dict()

    opens = frame["Open"].to_numpy(dtype=float)
    highs = frame["High"].to_numpy(dtype=float)
    lows = frame["Low"].to_numpy(dtype=float)
    closes = frame["Close"].to_numpy(dtype=float)
    atr_values = atr_series.to_numpy(dtype=float)
    trend_values = trend_series.to_numpy(dtype=int)
    times = frame["clock_time"].to_numpy()
    dates = frame["session_date"].to_numpy()
    index = frame.index

    last_entry_time = parse_clock_time(params.last_entry_time)
    session_exit_time = parse_clock_time(params.session_exit_time)
    min_tick_move = 0.25

    trades: list[Trade] = []
    position = 0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    stop_points = 0.0
    target_points = 0.0
    active_signal_time = pd.NaT
    active_entry_time = pd.NaT
    active_retracement_price = 0.0
    active_reference_range = 0.0
    active_atr_points = 0.0
    active_fill_reason = ""

    pending_order: dict[str, Any] | None = None
    blocked_long_above: float | None = None
    blocked_short_below: float | None = None

    current_date = None
    session_open = 0.0
    session_high = 0.0
    session_low = 0.0
    trades_today = 0
    previous_close = 0.0
    previous_timestamp = pd.NaT

    for i in range(len(frame)):
        bar_time = times[i]
        bar_date = dates[i]
        bar_open = opens[i]
        bar_high = highs[i]
        bar_low = lows[i]
        bar_close = closes[i]
        bar_timestamp = index[i]

        if i + 1 < len(frame) and dates[i + 1] == bar_date:
            next_bar_timestamp = index[i + 1]
        else:
            next_bar_timestamp = bar_timestamp + pd.Timedelta(minutes=15)

        day_minutes = minute_by_day.get(pd.Timestamp(bar_date))
        minute_slice = day_minutes.loc[(day_minutes.index >= bar_timestamp) & (day_minutes.index < next_bar_timestamp)] if day_minutes is not None else pd.DataFrame()

        if current_date is None or bar_date != current_date:
            if position != 0:
                exit_price = round_to_tick(previous_close)
                pnl_points = (exit_price - entry_price) * position
                pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                trades.append(
                    Trade(
                        session_date=pd.Timestamp(current_date).date().isoformat(),
                        signal_time=str(active_signal_time),
                        entry_time=str(active_entry_time),
                        exit_time=str(previous_timestamp),
                        direction="long" if position == 1 else "short",
                        signal_direction=position,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        stop_price=stop_price,
                        target_price=target_price,
                        stop_points=stop_points,
                        target_points=target_points,
                        retracement_price=active_retracement_price,
                        reference_range_points=active_reference_range,
                        atr_points=active_atr_points,
                        pnl_points=round(pnl_points, 2),
                        pnl_brl=round(pnl_brl, 2),
                        fill_reason=active_fill_reason or "forced_day_change",
                        exit_reason="forced_day_change",
                    )
                )
                position = 0
                pending_order = None

            current_date = bar_date
            session_open = bar_open
            session_high = bar_high
            session_low = bar_low
            blocked_long_above = None
            blocked_short_below = None
            trades_today = 0
            pending_order = None
            previous_close = bar_close
            previous_timestamp = bar_timestamp
            continue

        updated_session_high = max(session_high, bar_high)
        updated_session_low = min(session_low, bar_low)
        is_new_high = bar_high > session_high + FLOAT_EPS
        is_new_low = bar_low < session_low - FLOAT_EPS

        if position != 0 and not minute_slice.empty:
            for minute_ts, minute in minute_slice.iterrows():
                exit_price, exit_reason = resolve_exit_on_bar(
                    direction=position,
                    bar_high=float(minute["High"]),
                    bar_low=float(minute["Low"]),
                    bar_close=float(minute["Close"]),
                    stop_price=stop_price,
                    target_price=target_price,
                    is_session_exit_bar=minute_ts.time() >= session_exit_time,
                )
                if exit_price is not None and exit_reason is not None:
                    exit_price = round_to_tick(exit_price)
                    pnl_points = (exit_price - entry_price) * position
                    pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                    trades.append(
                        Trade(
                            session_date=pd.Timestamp(bar_date).date().isoformat(),
                            signal_time=str(active_signal_time),
                            entry_time=str(active_entry_time),
                            exit_time=str(minute_ts),
                            direction="long" if position == 1 else "short",
                            signal_direction=position,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            stop_price=stop_price,
                            target_price=target_price,
                            stop_points=stop_points,
                            target_points=target_points,
                            retracement_price=active_retracement_price,
                            reference_range_points=active_reference_range,
                            atr_points=active_atr_points,
                            pnl_points=round(pnl_points, 2),
                            pnl_brl=round(pnl_brl, 2),
                            fill_reason=active_fill_reason or "active_position",
                            exit_reason=exit_reason,
                        )
                    )
                    if exit_reason in {"stop_loss", "ambiguous_stop_first"}:
                        if position == 1:
                            blocked_long_above = updated_session_high
                        else:
                            blocked_short_below = updated_session_low
                    position = 0
                    pending_order = None
                    break

        if position == 0 and pending_order is not None and bar_time <= last_entry_time and not minute_slice.empty:
            for minute_ts, minute in minute_slice.iterrows():
                fill_price, fill_reason = fill_limit_order(
                    direction=int(pending_order["direction"]),
                    limit_price=float(pending_order["limit_price"]),
                    bar_open=float(minute["Open"]),
                    bar_high=float(minute["High"]),
                    bar_low=float(minute["Low"]),
                )
                if fill_price is None or fill_reason is None:
                    continue

                atr_points = float(pending_order["atr_points"])
                stop_points = round_to_tick(max(0.5, atr_points * params.stop_atr_mult))
                target_points = round_to_tick(max(0.5, atr_points * params.target_atr_mult))
                position = int(pending_order["direction"])
                entry_price = fill_price
                active_entry_time = minute_ts
                active_fill_reason = fill_reason
                if position == 1:
                    stop_price = round_to_tick(entry_price - stop_points)
                    target_price = round_to_tick(entry_price + target_points)
                else:
                    stop_price = round_to_tick(entry_price + stop_points)
                    target_price = round_to_tick(entry_price - target_points)

                active_signal_time = pending_order["signal_time"]
                active_retracement_price = float(pending_order["limit_price"])
                active_reference_range = float(pending_order["reference_range"])
                active_atr_points = atr_points
                trades_today += 1
                pending_order = None

                remaining_minutes = minute_slice.loc[minute_slice.index >= minute_ts]
                for exit_ts, exit_minute in remaining_minutes.iterrows():
                    exit_price, exit_reason = resolve_exit_on_bar(
                        direction=position,
                        bar_high=float(exit_minute["High"]),
                        bar_low=float(exit_minute["Low"]),
                        bar_close=float(exit_minute["Close"]),
                        stop_price=stop_price,
                        target_price=target_price,
                        is_session_exit_bar=exit_ts.time() >= session_exit_time,
                    )
                    if exit_price is None or exit_reason is None:
                        continue
                    exit_price = round_to_tick(exit_price)
                    pnl_points = (exit_price - entry_price) * position
                    pnl_brl = pnl_points * POINT_VALUE_BRL - ROUND_TRIP_COST_BRL
                    trades.append(
                        Trade(
                            session_date=pd.Timestamp(bar_date).date().isoformat(),
                            signal_time=str(active_signal_time),
                            entry_time=str(active_entry_time),
                            exit_time=str(exit_ts),
                            direction="long" if position == 1 else "short",
                            signal_direction=position,
                            entry_price=entry_price,
                            exit_price=exit_price,
                            stop_price=stop_price,
                            target_price=target_price,
                            stop_points=stop_points,
                            target_points=target_points,
                            retracement_price=active_retracement_price,
                            reference_range_points=active_reference_range,
                            atr_points=active_atr_points,
                            pnl_points=round(pnl_points, 2),
                            pnl_brl=round(pnl_brl, 2),
                            fill_reason=fill_reason,
                            exit_reason=exit_reason,
                        )
                    )
                    if exit_reason in {"stop_loss", "ambiguous_stop_first"}:
                        if position == 1:
                            blocked_long_above = updated_session_high
                        else:
                            blocked_short_below = updated_session_low
                    position = 0
                    break
                break

        session_high = updated_session_high
        session_low = updated_session_low

        if blocked_long_above is not None and session_high > blocked_long_above + min_tick_move:
            blocked_long_above = None
        if blocked_short_below is not None and session_low < blocked_short_below - min_tick_move:
            blocked_short_below = None

        if position == 0 and pending_order is not None and bar_time > last_entry_time:
            pending_order = None

        if position == 0 and trades_today < params.max_trades_per_day and bar_time < last_entry_time:
            if is_new_high and is_new_low:
                pending_order = None
            else:
                reference_range = range_reference_map.get(pd.Timestamp(bar_date), float("nan"))
                if pd.notna(reference_range) and float(reference_range) > 0.0:
                    candidate_direction = 1 if is_new_high else (-1 if is_new_low else 0)
                    if candidate_direction != 0:
                        activation_value = measure_activation_leg(
                            direction=candidate_direction,
                            session_open=session_open,
                            session_high=session_high,
                            session_low=session_low,
                            activation_basis=params.activation_basis,
                        )
                        day_range = session_high - session_low
                        threshold = float(reference_range) * params.activation_threshold_frac
                        blocked = (
                            candidate_direction == 1 and blocked_long_above is not None
                        ) or (
                            candidate_direction == -1 and blocked_short_below is not None
                        )
                        trend_allowed = not params.use_1h_filter or trend_values[i] == candidate_direction
                        atr_points = atr_values[i]
                        if (
                            not blocked
                            and trend_allowed
                            and activation_value >= threshold
                            and day_range >= params.min_range_points
                            and pd.notna(atr_points)
                            and atr_points > 0.0
                        ):
                            limit_price = compute_retracement_price(
                                direction=candidate_direction,
                                session_open=session_open,
                                session_high=session_high,
                                session_low=session_low,
                                retracement_frac=params.retracement_frac,
                                fib_basis=params.fib_basis,
                            )
                            pending_order = {
                                "direction": candidate_direction,
                                "limit_price": round_to_tick(limit_price),
                                "atr_points": float(atr_points),
                                "signal_time": bar_timestamp,
                                "reference_range": float(reference_range),
                            }
                        else:
                            pending_order = None

        previous_close = bar_close
        previous_timestamp = bar_timestamp

    trades_df = pd.DataFrame(asdict(trade) for trade in trades)
    metrics = calculate_metrics(trades_df=trades_df, trade_dates=overlap_dates)
    return trades_df, metrics


def objective_factory_1m(dataset: StalkerDataset, train_dates: pd.Index):
    min_trades = max(6, int(len(train_dates) * 0.02))

    def objective(trial: optuna.Trial) -> float:
        params = sample_params(trial)
        if params.use_1h_filter and params.h1_fast_ema >= params.h1_slow_ema:
            return -1e9
        if parse_clock_time(params.session_exit_time) <= parse_clock_time(params.last_entry_time):
            return -1e9
        trades_df, metrics = run_backtest_1m(dataset=dataset, params=params, trade_dates=train_dates)
        trial.set_user_attr("train_metrics", metrics)
        total_trades = int(metrics["total_trades"])
        if total_trades < min_trades:
            return -1000.0 + total_trades
        score = float(metrics["sharpe"])
        score += min(float(metrics["profit_factor"]), 5.0) * 0.05
        score -= float(metrics["max_drawdown_pct"]) * 0.02
        if float(metrics["net_profit_brl"]) <= 0.0:
            score -= 2.0
        return score

    return objective


def optimize_split_1m(
    dataset: StalkerDataset,
    train_dates: pd.Index,
    test_dates: pd.Index,
    trials: int,
    seed: int,
) -> tuple[optuna.Study, StrategyParams, pd.DataFrame, dict[str, Any], pd.DataFrame, dict[str, Any]]:
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective_factory_1m(dataset, train_dates), n_trials=trials, show_progress_bar=False)
    best_params = params_from_mapping(study.best_params)
    train_trades, train_metrics = run_backtest_1m(dataset=dataset, params=best_params, trade_dates=train_dates)
    test_trades, test_metrics = run_backtest_1m(dataset=dataset, params=best_params, trade_dates=test_dates)
    return study, best_params, train_trades, train_metrics, test_trades, test_metrics


def run_walk_forward_1m(
    dataset: StalkerDataset,
    overlap_dates: pd.Index,
    train_ratio: float,
    window_total_days: int,
    trials_per_window: int,
    seed: int,
) -> tuple[list[WalkForwardWindowResult], pd.DataFrame, dict[str, Any]]:
    windows = generate_walk_forward_windows(
        dates=overlap_dates,
        window_total_days=window_total_days,
        train_ratio=train_ratio,
    )
    results: list[WalkForwardWindowResult] = []
    all_test_trades: list[pd.DataFrame] = []
    all_test_dates: list[pd.Index] = []

    for window_number, train_dates, test_dates in windows:
        study, best_params, _, train_metrics, test_trades, test_metrics = optimize_split_1m(
            dataset=dataset,
            train_dates=train_dates,
            test_dates=test_dates,
            trials=trials_per_window,
            seed=seed + window_number,
        )
        if not test_trades.empty:
            test_trades = test_trades.copy()
            test_trades["walk_forward_window"] = window_number
            all_test_trades.append(test_trades)
        all_test_dates.append(test_dates)
        results.append(
            WalkForwardWindowResult(
                window=window_number,
                train_start=train_dates[0].date().isoformat(),
                train_end=train_dates[-1].date().isoformat(),
                test_start=test_dates[0].date().isoformat(),
                test_end=test_dates[-1].date().isoformat(),
                best_params=asdict(best_params),
                train_metrics=train_metrics,
                test_metrics=test_metrics,
                optuna_trials=len(study.trials),
                best_objective=float(study.best_value),
            )
        )

    combined_test_trades = pd.concat(all_test_trades, ignore_index=True) if all_test_trades else pd.DataFrame()
    combined_test_dates = pd.Index(sorted(pd.concat([pd.Series(index) for index in all_test_dates]).unique()))
    aggregate_metrics = calculate_metrics(combined_test_trades, combined_test_dates)
    return results, combined_test_trades, aggregate_metrics


def mt5_tick_probe() -> dict[str, Any]:
    if mt5 is None:
        return {"package_available": False}

    result: dict[str, Any] = {"package_available": True}
    initialized = mt5.initialize()
    result["initialized"] = bool(initialized)
    if not initialized:
        result["last_error"] = mt5.last_error()
        return result

    try:
        result["terminal_info"] = str(mt5.terminal_info())
        result["version"] = mt5.version()
        candidate_symbols = ["WDO$N", "WDOJ26", "WDOF26", "WDO1!"]
        selected_symbol = None
        tick_count = 0
        for candidate in candidate_symbols:
            info = mt5.symbol_info(candidate)
            if info is None:
                continue
            mt5.symbol_select(candidate, True)
            ticks = mt5.copy_ticks_range(
                candidate,
                pd.Timestamp("2026-03-19 09:00:00").to_pydatetime(),
                pd.Timestamp("2026-03-19 10:00:00").to_pydatetime(),
                mt5.COPY_TICKS_ALL,
            )
            selected_symbol = candidate
            tick_count = 0 if ticks is None else len(ticks)
            result["symbol_info"] = str(info)
            result["tick_probe_symbol"] = candidate
            result["tick_probe_count"] = int(tick_count)
            break
        if selected_symbol is None:
            result["tick_probe_symbol"] = None
            result["tick_probe_count"] = 0
    finally:
        mt5.shutdown()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Revalidate WDO Stalker with 1m execution and MT5 probe.")
    parser.add_argument("--trials", type=int, default=300, help="Optuna trials for 1m overlap 70/30 re-optimization.")
    parser.add_argument("--wf-trials", type=int, default=40, help="Optuna trials per 1m walk-forward window.")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Chronological train ratio.")
    parser.add_argument("--window-total-days", type=int, default=84, help="Total days per 1m walk-forward window.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--base-summary",
        type=Path,
        default=artifact_output_dir("stalker_wdo", "summary.json"),
        help="Summary JSON from the original 15m-only optimization.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=artifact_output_dir("stalker_wdo_validation"),
        help="Directory for validation artifacts.",
    )
    args = parser.parse_args()

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    dataset = StalkerDataset.from_disk()
    base_summary = json.loads(args.base_summary.read_text(encoding="utf-8"))
    base_params = params_from_mapping(base_summary["holdout"]["best_params"])

    minute_dates = pd.Index(sorted(dataset.bars_1m.index.normalize().unique()))
    overlap_15m_trades, overlap_15m_metrics = run_backtest(
        dataset=dataset,
        params=base_params,
        trade_dates=minute_dates,
    )
    overlap_1m_trades, overlap_1m_metrics = run_backtest_1m(
        dataset=dataset,
        params=base_params,
        trade_dates=minute_dates,
    )

    overlap_train_dates, overlap_test_dates = split_dates_by_ratio(minute_dates, args.train_ratio)
    overlap_study, overlap_best_params, overlap_train_trades, overlap_train_metrics, overlap_test_trades, overlap_test_metrics = optimize_split_1m(
        dataset=dataset,
        train_dates=overlap_train_dates,
        test_dates=overlap_test_dates,
        trials=args.trials,
        seed=args.seed,
    )
    overlap_wf_windows, overlap_wf_trades, overlap_wf_metrics = run_walk_forward_1m(
        dataset=dataset,
        overlap_dates=minute_dates,
        train_ratio=args.train_ratio,
        window_total_days=args.window_total_days,
        trials_per_window=args.wf_trials,
        seed=args.seed,
    )

    mt5_probe = mt5_tick_probe()

    summary = {
        "base_15m_holdout_params": asdict(base_params),
        "minute_overlap": {
            "start_date": minute_dates[0].date().isoformat(),
            "end_date": minute_dates[-1].date().isoformat(),
            "trading_days": int(len(minute_dates)),
            "base_params_15m_execution_metrics": overlap_15m_metrics,
            "base_params_1m_execution_metrics": overlap_1m_metrics,
        },
        "minute_overlap_optimized_holdout": {
            "train_days": int(len(overlap_train_dates)),
            "test_days": int(len(overlap_test_dates)),
            "best_params": asdict(overlap_best_params),
            "optuna_trials": len(overlap_study.trials),
            "train_metrics": overlap_train_metrics,
            "test_metrics": overlap_test_metrics,
        },
        "minute_overlap_walk_forward": {
            "window_total_days": args.window_total_days,
            "window_count": len(overlap_wf_windows),
            "aggregate_metrics": overlap_wf_metrics,
            "windows": [asdict(window) for window in overlap_wf_windows],
        },
        "mt5_probe": mt5_probe,
        "audit_findings": {
            "15m_same_bar_exit_bias": "The original 15m engine can overstate results because many limit-touch entries and exits happen on the same 15m bar, and entry-vs-target ordering is unknowable without lower timeframe data.",
            "1m_residual_bias": "1m revalidation still has same-minute ambiguity, but it is materially more realistic than 15m-bar sequencing.",
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    overlap_15m_trades.to_csv(args.output_dir / "overlap_base_params_15m_execution.csv", index=False)
    overlap_1m_trades.to_csv(args.output_dir / "overlap_base_params_1m_execution.csv", index=False)
    overlap_train_trades.to_csv(args.output_dir / "overlap_optimized_train_trades_1m.csv", index=False)
    overlap_test_trades.to_csv(args.output_dir / "overlap_optimized_test_trades_1m.csv", index=False)
    overlap_wf_trades.to_csv(args.output_dir / "overlap_walk_forward_trades_1m.csv", index=False)

    print("Base full-sample params on 1m overlap")
    print("  15m execution metrics:", overlap_15m_metrics)
    print("  1m execution metrics:", overlap_1m_metrics)
    print()
    print("1m overlap re-optimized holdout")
    print("  best_params:", asdict(overlap_best_params))
    print("  train_metrics:", overlap_train_metrics)
    print("  test_metrics:", overlap_test_metrics)
    print()
    print("1m overlap walk-forward aggregate")
    print("  metrics:", overlap_wf_metrics)
    print()
    print("MT5 probe:", mt5_probe)
    print()
    print(f"Validation artifacts saved to: {args.output_dir}")


if __name__ == "__main__":
    main()
