import unittest
from datetime import datetime

from autoresearch_tradebot.strategies.paper_trade_mt5 import (
    determine_order_delta,
    last_completed_bar_open,
)


class TestPaperTradeMt5(unittest.TestCase):
    def test_order_delta_for_flip(self) -> None:
        self.assertEqual(determine_order_delta(current_position=-1, desired_position=1, contracts=1), 2)
        self.assertEqual(determine_order_delta(current_position=1, desired_position=0, contracts=1), -1)
        self.assertEqual(determine_order_delta(current_position=0, desired_position=-1, contracts=2), -2)

    def test_last_completed_bar_open(self) -> None:
        now = datetime(2026, 3, 23, 10, 26, 30)
        self.assertEqual(str(last_completed_bar_open(now)), "2026-03-23 10:20:00")


if __name__ == "__main__":
    unittest.main()
