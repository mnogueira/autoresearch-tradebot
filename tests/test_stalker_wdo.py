from __future__ import annotations

import unittest

import pandas as pd

from autoresearch_tradebot.strategies.stalker_wdo import (
    StalkerDataset,
    StrategyParams,
    calculate_metrics,
    compute_retracement_price,
    fill_limit_order,
    measure_activation_leg,
    resolve_exit_on_bar,
    run_backtest,
)


def make_intraday_frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    index = pd.to_datetime([row[0] for row in rows])
    frame = pd.DataFrame(
        {
            "Open": [row[1] for row in rows],
            "High": [row[2] for row in rows],
            "Low": [row[3] for row in rows],
            "Close": [row[4] for row in rows],
            "Volume": [1 for _ in rows],
        },
        index=index,
    )
    frame.index.name = "time"
    return frame


class StalkerWdoTests(unittest.TestCase):
    def test_contract_reference_uses_previous_contract_first_days(self) -> None:
        bars_15m = make_intraday_frame(
            [
                ("2024-01-29 09:00", 100, 110, 100, 109),
                ("2024-01-29 17:45", 109, 110, 100, 101),
                ("2024-01-30 09:00", 100, 112, 100, 111),
                ("2024-01-30 17:45", 111, 112, 100, 102),
                ("2024-01-31 09:00", 100, 114, 100, 113),
                ("2024-01-31 17:45", 113, 114, 100, 103),
                ("2024-02-01 09:00", 100, 116, 100, 115),
                ("2024-02-01 17:45", 115, 116, 100, 104),
                ("2024-02-02 09:00", 100, 118, 100, 117),
                ("2024-02-02 17:45", 117, 118, 100, 105),
            ]
        )
        dataset = StalkerDataset(bars_15m=bars_15m, bars_1h=make_intraday_frame([]))
        contract_reference = dataset.get_range_reference(
            mode="contract_expanding",
            lookback_days=10,
            prev_contract_days=2,
        )

        jan_mean = (10 + 12 + 14) / 3
        self.assertAlmostEqual(contract_reference.loc[pd.Timestamp("2024-02-01")], jan_mean)
        self.assertAlmostEqual(contract_reference.loc[pd.Timestamp("2024-02-02")], jan_mean)

    def test_contract_reference_switches_to_current_contract_average(self) -> None:
        bars_15m = make_intraday_frame(
            [
                ("2024-01-31 09:00", 100, 110, 100, 109),
                ("2024-01-31 17:45", 109, 110, 100, 101),
                ("2024-02-01 09:00", 100, 112, 100, 111),
                ("2024-02-01 17:45", 111, 112, 100, 102),
                ("2024-02-02 09:00", 100, 114, 100, 113),
                ("2024-02-02 17:45", 113, 114, 100, 103),
                ("2024-02-05 09:00", 100, 116, 100, 115),
                ("2024-02-05 17:45", 115, 116, 100, 104),
            ]
        )
        dataset = StalkerDataset(bars_15m=bars_15m, bars_1h=make_intraday_frame([]))
        contract_reference = dataset.get_range_reference(
            mode="contract_expanding",
            lookback_days=10,
            prev_contract_days=2,
        )
        self.assertAlmostEqual(contract_reference.loc[pd.Timestamp("2024-02-05")], 13.0)

    def test_rolling_reference_is_shifted(self) -> None:
        bars_15m = make_intraday_frame(
            [
                ("2024-01-02 09:00", 100, 110, 100, 109),
                ("2024-01-02 17:45", 109, 110, 100, 101),
                ("2024-01-03 09:00", 100, 114, 100, 113),
                ("2024-01-03 17:45", 113, 114, 100, 103),
                ("2024-01-04 09:00", 100, 116, 100, 115),
                ("2024-01-04 17:45", 115, 116, 100, 105),
                ("2024-01-05 09:00", 100, 118, 100, 117),
                ("2024-01-05 17:45", 117, 118, 100, 107),
            ]
        )
        dataset = StalkerDataset(bars_15m=bars_15m, bars_1h=make_intraday_frame([]))
        rolling_reference = dataset.get_range_reference(
            mode="rolling_n",
            lookback_days=3,
            prev_contract_days=5,
        )
        self.assertAlmostEqual(rolling_reference.loc[pd.Timestamp("2024-01-05")], (10 + 14 + 16) / 3)

    def test_retracement_price_uses_session_range(self) -> None:
        price = compute_retracement_price(
            direction=1,
            session_open=100.0,
            session_high=130.0,
            session_low=90.0,
            retracement_frac=0.25,
            fib_basis="session_range",
        )
        self.assertAlmostEqual(price, 120.0)

    def test_retracement_price_uses_directional_leg(self) -> None:
        price = compute_retracement_price(
            direction=-1,
            session_open=100.0,
            session_high=108.0,
            session_low=70.0,
            retracement_frac=0.30,
            fib_basis="directional_leg",
        )
        self.assertAlmostEqual(price, 79.0)

    def test_activation_measurement_supports_directional_leg(self) -> None:
        value = measure_activation_leg(
            direction=-1,
            session_open=100.0,
            session_high=108.0,
            session_low=84.0,
            activation_basis="directional_leg",
        )
        self.assertAlmostEqual(value, 16.0)

    def test_limit_fill_uses_better_open(self) -> None:
        fill_price, fill_reason = fill_limit_order(
            direction=1,
            limit_price=100.0,
            bar_open=99.5,
            bar_high=101.0,
            bar_low=99.0,
        )
        self.assertEqual(fill_price, 99.5)
        self.assertEqual(fill_reason, "better_open")

    def test_same_bar_stop_and_target_is_stop_first(self) -> None:
        exit_price, exit_reason = resolve_exit_on_bar(
            direction=1,
            bar_high=106.0,
            bar_low=94.0,
            bar_close=100.0,
            stop_price=95.0,
            target_price=105.0,
            is_session_exit_bar=False,
        )
        self.assertEqual(exit_price, 95.0)
        self.assertEqual(exit_reason, "ambiguous_stop_first")

    def test_h1_filter_uses_previous_completed_bar(self) -> None:
        bars_15m = make_intraday_frame(
            [
                ("2024-01-02 09:00", 100, 101, 99, 100.5),
                ("2024-01-02 09:15", 100.5, 101, 100, 100.7),
                ("2024-01-02 10:00", 100.7, 101.5, 100.6, 101.2),
                ("2024-01-02 10:15", 101.2, 101.7, 101.0, 101.4),
                ("2024-01-02 11:00", 101.4, 101.6, 100.8, 100.9),
                ("2024-01-02 11:15", 100.9, 101.0, 100.2, 100.3),
            ]
        )
        bars_1h = make_intraday_frame(
            [
                ("2024-01-01 17:00", 99, 100, 98, 100),
                ("2024-01-01 18:00", 100, 101, 99, 101),
                ("2024-01-02 09:00", 101, 103, 100, 103),
                ("2024-01-02 10:00", 103, 104, 102, 104),
                ("2024-01-02 11:00", 104, 104, 99, 99),
            ]
        )
        dataset = StalkerDataset(bars_15m=bars_15m, bars_1h=bars_1h)
        trend = dataset.get_h1_trend(fast_ema=1, slow_ema=2)

        self.assertEqual(int(trend.loc[pd.Timestamp("2024-01-02 10:15")]), 1)
        self.assertEqual(int(trend.loc[pd.Timestamp("2024-01-02 11:15")]), 1)

    def test_metrics_calculation_on_known_trades(self) -> None:
        trades = pd.DataFrame(
            [
                {"session_date": "2024-01-02", "pnl_brl": 100.0, "exit_reason": "take_profit"},
                {"session_date": "2024-01-03", "pnl_brl": -50.0, "exit_reason": "stop_loss"},
                {"session_date": "2024-01-04", "pnl_brl": 200.0, "exit_reason": "take_profit"},
            ]
        )
        trade_dates = pd.Index(pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]))
        metrics = calculate_metrics(trades_df=trades, trade_dates=trade_dates)

        self.assertEqual(metrics["total_trades"], 3)
        self.assertEqual(metrics["net_profit_brl"], 250.0)
        self.assertAlmostEqual(metrics["win_rate"], 2 / 3, places=4)
        self.assertEqual(metrics["take_profit_trades"], 2)
        self.assertEqual(metrics["stop_loss_trades"], 1)

    def test_stop_reentry_requires_new_extreme(self) -> None:
        bars_15m = make_intraday_frame(
            [
                ("2023-12-28 09:00", 95, 99, 95, 98),
                ("2023-12-28 17:45", 98, 100, 96, 97),
                ("2023-12-29 09:00", 96, 101, 96, 100),
                ("2023-12-29 17:45", 100, 102, 97, 98),
                ("2024-01-01 09:00", 97, 103, 97, 102),
                ("2024-01-01 17:45", 102, 104, 98, 99),
                ("2024-01-02 09:00", 100, 106, 100, 105),
                ("2024-01-02 09:15", 105, 112, 104, 111),
                ("2024-01-02 09:30", 111, 111, 108, 109),
                ("2024-01-02 09:45", 109, 110, 103, 104),
                ("2024-01-02 10:00", 104, 111, 104, 110),
                ("2024-01-02 10:15", 110, 113, 108, 112),
                ("2024-01-02 10:30", 112, 112, 108, 109),
            ]
        )
        bars_1h = make_intraday_frame(
            [
                ("2023-12-28 17:00", 95, 100, 95, 97),
                ("2023-12-29 17:00", 96, 102, 96, 98),
                ("2024-01-01 17:00", 97, 104, 97, 99),
                ("2024-01-02 09:00", 100, 112, 100, 111),
                ("2024-01-02 10:00", 111, 113, 104, 112),
            ]
        )
        dataset = StalkerDataset(bars_15m=bars_15m, bars_1h=bars_1h)
        params = StrategyParams(
            range_reference_mode="rolling_n",
            range_lookback_days=5,
            prev_contract_days=5,
            activation_basis="session_range",
            activation_threshold_frac=0.20,
            fib_basis="session_range",
            retracement_frac=0.25,
            min_range_points=0.0,
            atr_timeframe="15m",
            atr_period=2,
            stop_atr_mult=0.50,
            target_atr_mult=5.00,
            use_1h_filter=False,
            h1_fast_ema=5,
            h1_slow_ema=10,
            max_trades_per_day=3,
            last_entry_time="17:15",
            session_exit_time="17:45",
        )

        trades, metrics = run_backtest(dataset=dataset, params=params, trade_dates=dataset.trade_dates)

        self.assertEqual(metrics["total_trades"], 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], "stop_loss")


if __name__ == "__main__":
    unittest.main(verbosity=2)
