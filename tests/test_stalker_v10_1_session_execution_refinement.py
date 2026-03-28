from __future__ import annotations

import unittest

from autoresearch_tradebot.strategies.stalker_v10_1_session_execution_refinement import (
    has_reached_daily_profit_cap,
    has_reached_max_trade_age,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
