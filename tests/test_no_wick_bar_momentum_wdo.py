import unittest

import pandas as pd

from autoresearch_tradebot.strategies.no_wick_bar_momentum_wdo import (
    StrategyParams,
    generate_signal_frame,
    simulate_trade,
)


class NoWickBarMomentumTests(unittest.TestCase):
    def test_generate_signal_requires_directional_full_body_and_trend_alignment(self):
        index = pd.to_datetime(["2026-01-05 10:00:00", "2026-01-05 10:15:00"])
        frame = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [104.0, 101.5],
                "Low": [99.5, 98.0],
                "Close": [103.5, 98.5],
                "Volume": [1000, 1000],
                "session_date": [pd.Timestamp("2026-01-05"), pd.Timestamp("2026-01-05")],
                "next_open_time": [pd.Timestamp("2026-01-05 10:15:00"), pd.NaT],
                "can_signal": [True, False],
                "minute_date_available": [True, True],
                "trend": [1, -1],
                "h1_trend": [1, -1],
                "d1_trend": [1, -1],
            },
            index=index,
        )

        params = StrategyParams(
            wick_tolerance_atr_frac=0.05,
            atr_period=1,
            stop_points=3.0,
            target_points=7.0,
        )

        signal_frame = generate_signal_frame(frame, params)

        self.assertEqual(int(signal_frame.loc[index[0], "signal_direction"]), 1)
        self.assertEqual(int(signal_frame.loc[index[1], "signal_direction"]), 0)

    def test_simulate_trade_is_pessimistic_when_stop_and_target_hit_same_minute(self):
        minutes = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [108.0],
                "Low": [96.0],
                "Close": [101.0],
                "Volume": [10],
            },
            index=pd.to_datetime(["2026-01-05 10:15:00"]),
        )

        exit_time, exit_price, exit_reason = simulate_trade(
            minute_slice=minutes,
            direction=1,
            entry_price=100.0,
            stop_points=3.0,
            target_points=7.0,
        )

        self.assertEqual(exit_time, pd.Timestamp("2026-01-05 10:15:00"))
        self.assertEqual(exit_price, 97.0)
        self.assertEqual(exit_reason, "ambiguous_stop_first")


if __name__ == "__main__":
    unittest.main()
