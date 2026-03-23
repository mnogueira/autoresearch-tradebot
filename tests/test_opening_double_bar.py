import unittest

import pandas as pd

from autoresearch_tradebot.strategies.opening_double_bar import (
    StrategyConfig,
    classify_full_body,
    run_backtest,
)


def make_day(rows):
    index = pd.to_datetime([row[0] for row in rows])
    df = pd.DataFrame(
        {
            "Open": [row[1] for row in rows],
            "High": [row[2] for row in rows],
            "Low": [row[3] for row in rows],
            "Close": [row[4] for row in rows],
            "Volume": [row[5] for row in rows],
        },
        index=index,
    )
    df.index.name = "time"
    df["date"] = df.index.normalize()
    df["clock_time"] = df.index.time
    return df


class OpeningDoubleBarTests(unittest.TestCase):
    def test_classify_full_body_bars(self):
        bullish = pd.Series({"Open": 10.0, "High": 12.0, "Low": 10.0, "Close": 12.0})
        bearish = pd.Series({"Open": 12.0, "High": 12.0, "Low": 10.0, "Close": 10.0})
        wick = pd.Series({"Open": 10.0, "High": 12.5, "Low": 10.0, "Close": 12.0})

        self.assertEqual(classify_full_body(bullish), 1)
        self.assertEqual(classify_full_body(bearish), -1)
        self.assertEqual(classify_full_body(wick), 0)

    def test_bullish_setup_hits_target(self):
        df = make_day(
            [
                ("2026-01-05 09:00:00", 10.0, 12.0, 10.0, 12.0, 100),
                ("2026-01-05 09:15:00", 12.0, 14.0, 12.0, 14.0, 100),
                ("2026-01-05 09:30:00", 15.0, 22.0, 15.0, 21.0, 100),
                ("2026-01-05 09:45:00", 21.0, 21.0, 20.0, 20.5, 100),
            ]
        )

        trades, metrics = run_backtest(df, config=StrategyConfig(), period="test")

        self.assertEqual(len(trades), 1)
        trade = trades.iloc[0]
        self.assertEqual(trade["side"], "long")
        self.assertEqual(trade["exit_reason"], "take_profit")
        self.assertEqual(trade["entry_price"], 15.0)
        self.assertEqual(trade["exit_price"], 22.0)
        self.assertEqual(trade["pnl_points"], 7.0)
        self.assertEqual(trade["pnl_brl"], 59.0)
        self.assertEqual(metrics.trades, 1)
        self.assertEqual(metrics.wins, 1)

    def test_requires_two_matching_full_body_bars(self):
        df = make_day(
            [
                ("2026-01-06 09:00:00", 10.0, 12.0, 10.0, 12.0, 100),
                ("2026-01-06 09:15:00", 12.0, 14.5, 12.0, 14.0, 100),
                ("2026-01-06 09:30:00", 14.0, 21.0, 14.0, 20.0, 100),
                ("2026-01-06 09:45:00", 20.0, 20.0, 19.0, 19.5, 100),
            ]
        )

        trades, metrics = run_backtest(df, config=StrategyConfig(), period="test")

        self.assertTrue(trades.empty)
        self.assertEqual(metrics.trades, 0)

    def test_same_bar_conflict_uses_stop_first(self):
        df = make_day(
            [
                ("2026-01-07 09:00:00", 14.0, 14.0, 12.0, 12.0, 100),
                ("2026-01-07 09:15:00", 12.0, 12.0, 10.0, 10.0, 100),
                ("2026-01-07 09:30:00", 10.0, 13.5, 2.5, 8.0, 100),
                ("2026-01-07 09:45:00", 8.0, 8.5, 7.5, 8.0, 100),
            ]
        )

        trades, metrics = run_backtest(df, config=StrategyConfig(), period="test")

        self.assertEqual(len(trades), 1)
        trade = trades.iloc[0]
        self.assertEqual(trade["side"], "short")
        self.assertEqual(trade["exit_reason"], "stop_first_ambiguous_bar")
        self.assertEqual(trade["exit_price"], 13.0)
        self.assertEqual(trade["pnl_points"], -3.0)
        self.assertEqual(trade["pnl_brl"], -41.0)
        self.assertEqual(metrics.losses, 1)
        self.assertEqual(metrics.ambiguous_bars, 1)

    def test_closes_at_session_end_if_neither_level_hits(self):
        df = make_day(
            [
                ("2026-01-08 09:00:00", 14.0, 14.0, 12.0, 12.0, 100),
                ("2026-01-08 09:15:00", 12.0, 12.0, 10.0, 10.0, 100),
                ("2026-01-08 09:30:00", 10.0, 10.5, 9.0, 9.5, 100),
                ("2026-01-08 09:45:00", 9.5, 10.0, 8.5, 8.5, 100),
            ]
        )

        trades, metrics = run_backtest(df, config=StrategyConfig(), period="test")

        self.assertEqual(len(trades), 1)
        trade = trades.iloc[0]
        self.assertEqual(trade["exit_reason"], "session_close")
        self.assertEqual(trade["exit_price"], 8.5)
        self.assertEqual(trade["pnl_points"], 1.5)
        self.assertEqual(trade["pnl_brl"], 4.0)
        self.assertEqual(metrics.session_close_exits, 1)


if __name__ == "__main__":
    unittest.main()
