from __future__ import annotations

import unittest

from autoresearch_tradebot.strategies.stalker_v10_1_session_execution_refinement import (
    confirmation_candle_passed,
    has_reached_daily_profit_cap,
    has_reached_max_trade_age,
    pending_order_can_fill_at_index,
    pending_order_has_expired,
    profit_lock_stop_tick,
)


class SessionExecutionRefinementTests(unittest.TestCase):
    def test_max_trade_age_is_disabled_when_limit_is_none_or_non_positive(self) -> None:
        self.assertFalse(has_reached_max_trade_age(10, 0, None))
        self.assertFalse(has_reached_max_trade_age(10, 0, 0))

    def test_max_trade_age_waits_until_the_boundary_bar(self) -> None:
        self.assertFalse(has_reached_max_trade_age(119, 0, 120))
        self.assertTrue(has_reached_max_trade_age(120, 0, 120))

    def test_max_trade_age_uses_entry_index_offset(self) -> None:
        self.assertFalse(has_reached_max_trade_age(214, 95, 120))
        self.assertTrue(has_reached_max_trade_age(215, 95, 120))

    def test_daily_profit_cap_is_disabled_when_missing_or_non_positive(self) -> None:
        self.assertFalse(has_reached_daily_profit_cap(100.0, None))
        self.assertFalse(has_reached_daily_profit_cap(100.0, 0.0))

    def test_daily_profit_cap_triggers_at_boundary(self) -> None:
        self.assertFalse(has_reached_daily_profit_cap(99.99, 100.0))
        self.assertTrue(has_reached_daily_profit_cap(100.0, 100.0))

    def test_pending_order_fill_and_expiry_boundaries(self) -> None:
        order = {"min_fill_index": 11, "expiry_index": 13}
        self.assertFalse(pending_order_can_fill_at_index(10, order))
        self.assertTrue(pending_order_can_fill_at_index(11, order))
        self.assertFalse(pending_order_has_expired(13, order))
        self.assertTrue(pending_order_has_expired(14, order))

    def test_confirmation_candle_requires_directional_close(self) -> None:
        self.assertTrue(confirmation_candle_passed(1, 100, 101))
        self.assertFalse(confirmation_candle_passed(1, 100, 100))
        self.assertTrue(confirmation_candle_passed(-1, 100, 99))
        self.assertFalse(confirmation_candle_passed(-1, 100, 101))

    def test_profit_lock_stop_tick_locks_fraction_of_target_once_activated(self) -> None:
        self.assertIsNone(
            profit_lock_stop_tick(
                position=1,
                entry_tick=1000,
                initial_target_tick=1100,
                current_bid_tick=1074,
                current_ask_tick=1075,
                activation_fraction=0.75,
                lock_fraction=0.25,
            )
        )
        self.assertEqual(
            profit_lock_stop_tick(
                position=1,
                entry_tick=1000,
                initial_target_tick=1100,
                current_bid_tick=1075,
                current_ask_tick=1076,
                activation_fraction=0.75,
                lock_fraction=0.25,
            ),
            1025,
        )
        self.assertEqual(
            profit_lock_stop_tick(
                position=-1,
                entry_tick=1000,
                initial_target_tick=900,
                current_bid_tick=924,
                current_ask_tick=925,
                activation_fraction=0.75,
                lock_fraction=0.25,
            ),
            975,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
