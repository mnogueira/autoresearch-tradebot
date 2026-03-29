from __future__ import annotations

import unittest

import numpy as np

from autoresearch_tradebot.strategies.stalker_v10_1_session_execution_refinement import (
    ManagementConfig,
    atr_trailing_has_activated,
    atr_trailing_stop_tick,
    confirmation_candle_passed,
    confirmation_sequence_passed,
    entry_spread_allows_trade,
    has_reached_daily_profit_cap,
    has_reached_max_trade_age,
    has_reached_weekly_profit_cap,
    pending_order_can_fill_at_index,
    pending_order_has_expired,
    profit_lock_stop_tick,
    recent_trade_pnl_allows_entry,
    resolve_spread_ticks,
    should_exit_on_trend_flip,
    widened_stop_tick,
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

    def test_trend_flip_exit_only_triggers_soon_after_entry_and_on_true_flip(self) -> None:
        self.assertFalse(should_exit_on_trend_flip(1, 0.1, 5, 5, 5))
        self.assertFalse(should_exit_on_trend_flip(1, 0.1, 6, 5, 5))
        self.assertTrue(should_exit_on_trend_flip(1, -0.1, 6, 5, 5))
        self.assertTrue(should_exit_on_trend_flip(-1, 0.1, 7, 5, 5))
        self.assertFalse(should_exit_on_trend_flip(1, -0.1, 11, 5, 5))

    def test_daily_profit_cap_is_disabled_when_missing_or_non_positive(self) -> None:
        self.assertFalse(has_reached_daily_profit_cap(100.0, None))
        self.assertFalse(has_reached_daily_profit_cap(100.0, 0.0))

    def test_daily_profit_cap_triggers_at_boundary(self) -> None:
        self.assertFalse(has_reached_daily_profit_cap(99.99, 100.0))
        self.assertTrue(has_reached_daily_profit_cap(100.0, 100.0))

    def test_weekly_profit_cap_is_disabled_when_missing_or_non_positive(self) -> None:
        self.assertFalse(has_reached_weekly_profit_cap(100.0, None))
        self.assertFalse(has_reached_weekly_profit_cap(100.0, 0.0))

    def test_weekly_profit_cap_triggers_at_boundary(self) -> None:
        self.assertFalse(has_reached_weekly_profit_cap(299.99, 300.0))
        self.assertTrue(has_reached_weekly_profit_cap(300.0, 300.0))

    def test_recent_trade_pnl_gate_allows_until_lookback_is_full(self) -> None:
        self.assertTrue(recent_trade_pnl_allows_entry([10.0, -5.0], 10, 0.0))
        self.assertTrue(recent_trade_pnl_allows_entry([10.0, -5.0], None, 0.0))

    def test_recent_trade_pnl_gate_requires_positive_trailing_sum(self) -> None:
        self.assertTrue(recent_trade_pnl_allows_entry([10.0, -5.0, 4.0], 3, 0.0))
        self.assertFalse(recent_trade_pnl_allows_entry([10.0, -15.0, 4.0], 3, 0.0))

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

    def test_confirmation_sequence_requires_all_bars_in_direction(self) -> None:
        open_ticks = np.array([100, 101, 102, 103], dtype=np.int32)
        close_ticks = np.array([101, 102, 101, 104], dtype=np.int32)
        self.assertTrue(
            confirmation_sequence_passed(
                direction=1,
                open_ticks=open_ticks,
                close_ticks=close_ticks,
                start_index=0,
                consecutive_bars=2,
            )
        )
        self.assertFalse(
            confirmation_sequence_passed(
                direction=1,
                open_ticks=open_ticks,
                close_ticks=close_ticks,
                start_index=1,
                consecutive_bars=2,
            )
        )

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

    def test_widened_stop_tick_relaxes_stop_in_position_direction_only(self) -> None:
        self.assertEqual(
            widened_stop_tick(
                position=1,
                entry_tick=1000,
                current_stop_tick=970,
                entry_atr_value=21.0,
                widened_sl_atr_mult=1.20,
            ),
            950,
        )
        self.assertEqual(
            widened_stop_tick(
                position=-1,
                entry_tick=1000,
                current_stop_tick=1030,
                entry_atr_value=21.0,
                widened_sl_atr_mult=1.20,
            ),
            1050,
        )
        self.assertEqual(
            widened_stop_tick(
                position=1,
                entry_tick=1000,
                current_stop_tick=916,
                entry_atr_value=21.0,
                widened_sl_atr_mult=1.20,
            ),
            916,
        )
        self.assertIsNone(
            widened_stop_tick(
                position=0,
                entry_tick=1000,
                current_stop_tick=916,
                entry_atr_value=21.0,
                widened_sl_atr_mult=1.20,
            )
        )

    def test_atr_trailing_stop_only_tightens_after_best_excursion_advances(self) -> None:
        self.assertEqual(
            atr_trailing_stop_tick(
                position=1,
                current_stop_tick=916,
                best_bid_tick=1050,
                best_ask_tick=1051,
                entry_atr_value=21.0,
                atr_trailing_distance_mult=1.0,
            ),
            1008,
        )
        self.assertEqual(
            atr_trailing_stop_tick(
                position=-1,
                current_stop_tick=1084,
                best_bid_tick=949,
                best_ask_tick=950,
                entry_atr_value=21.0,
                atr_trailing_distance_mult=1.0,
            ),
            992,
        )

    def test_atr_trailing_stop_never_widens_or_acts_without_inputs(self) -> None:
        self.assertIsNone(
            atr_trailing_stop_tick(
                position=1,
                current_stop_tick=1008,
                best_bid_tick=1040,
                best_ask_tick=1041,
                entry_atr_value=21.0,
                atr_trailing_distance_mult=1.0,
            )
        )

    def test_atr_trailing_activation_fraction_requires_half_target_excursion(self) -> None:
        self.assertFalse(
            atr_trailing_has_activated(
                position=1,
                entry_tick=1000,
                initial_target_tick=1080,
                best_bid_tick=1039,
                best_ask_tick=1040,
                activation_fraction=0.5,
            )
        )
        self.assertTrue(
            atr_trailing_has_activated(
                position=1,
                entry_tick=1000,
                initial_target_tick=1080,
                best_bid_tick=1040,
                best_ask_tick=1041,
                activation_fraction=0.5,
            )
        )
        self.assertTrue(
            atr_trailing_has_activated(
                position=-1,
                entry_tick=1000,
                initial_target_tick=920,
                best_bid_tick=959,
                best_ask_tick=960,
                activation_fraction=0.5,
            )
        )
        self.assertIsNone(
            atr_trailing_stop_tick(
                position=0,
                current_stop_tick=1008,
                best_bid_tick=1040,
                best_ask_tick=1041,
                entry_atr_value=21.0,
                atr_trailing_distance_mult=1.0,
            )
        )

    def test_resolve_spread_ticks_uses_fixed_override_when_requested(self) -> None:
        raw = np.array([0, 1, 1, 0], dtype=np.int16)
        result = resolve_spread_ticks(raw, ManagementConfig(fixed_spread_ticks=5))
        np.testing.assert_array_equal(result, np.array([5, 5, 5, 5], dtype=np.int16))

    def test_resolve_spread_ticks_uses_multiplier_when_no_fixed_override(self) -> None:
        raw = np.array([0, 1, 2], dtype=np.int16)
        result = resolve_spread_ticks(raw, ManagementConfig(spread_multiplier=2.5))
        np.testing.assert_array_equal(result, np.array([0, 2, 5], dtype=np.int16))

    def test_entry_spread_gate_defaults_to_allowing_trades(self) -> None:
        self.assertTrue(entry_spread_allows_trade(3, ManagementConfig()))
        self.assertTrue(entry_spread_allows_trade(3, ManagementConfig(max_entry_spread_ticks=-1)))

    def test_entry_spread_gate_blocks_when_current_spread_exceeds_limit(self) -> None:
        self.assertTrue(entry_spread_allows_trade(1, ManagementConfig(max_entry_spread_ticks=1)))
        self.assertFalse(entry_spread_allows_trade(2, ManagementConfig(max_entry_spread_ticks=1)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
