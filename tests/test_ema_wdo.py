import unittest

import numpy as np
import pandas as pd

from autoresearch_tradebot.strategies.ema_wdo import (
    EmaStrategyParams,
    add_session_columns,
    generate_executable_signals,
    generate_raw_positions,
    lookup_fill_price,
)


class FakeCache:
    def __init__(self, frame: pd.DataFrame, values: dict[str, list[float]]):
        self.frame = frame
        self.values = values

    def _series(self, key: str) -> pd.Series:
        return pd.Series(self.values[key], index=self.frame.index, dtype=float)

    def ema(self, window: int) -> pd.Series:
        return self._series(f"ema_{window}")

    def rsi(self, window: int) -> pd.Series:
        return self._series(f"rsi_{window}")

    def adx(self, window: int) -> pd.Series:
        return self._series(f"adx_{window}")

    def atr(self, window: int) -> pd.Series:
        return self._series(f"atr_{window}")

    def trix(self, window: int) -> pd.Series:
        return self._series(f"trix_{window}")

    def trix_median(self, trix_window: int, median_window: int, min_periods: int) -> pd.Series:
        return self._series(f"trix_median_{trix_window}_{median_window}_{min_periods}")

    def hurst(self, window: int) -> pd.Series:
        return self._series(f"hurst_{window}")

    def vr(self, short_window: int, long_window: int) -> pd.Series:
        return self._series(f"vr_{short_window}_{long_window}")

    def vwap(self) -> pd.Series:
        return self._series("vwap")


def make_frame(timestamps: list[str], closes: list[float] | None = None) -> pd.DataFrame:
    index = pd.to_datetime(timestamps)
    closes = closes or [100.0] * len(index)
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": np.array(closes) + 1.0,
            "Low": np.array(closes) - 1.0,
            "Close": closes,
            "Volume": 1000,
        },
        index=index,
    )
    return add_session_columns(frame)


class TestEmaWdo(unittest.TestCase):
    def setUp(self) -> None:
        self.params = EmaStrategyParams(
            ema_fast=2,
            ema_slow=3,
            trend_window=4,
            rsi_window=5,
            rsi_long=60,
            rsi_short=40,
            adx_window=6,
            adx_threshold=20,
            atr_window=7,
            atr_mult=2.0,
            trix_window=8,
            trix_median_window=9,
            trix_median_min_periods=1,
            hurst_window=10,
            hurst_threshold=0.5,
            vr_short_window=2,
            vr_long_window=5,
            vr_max=2.0,
            use_vwap=True,
            skip_12=True,
            skip_13=True,
            skip_14=False,
            entry_cutoff_time="14:55",
            flat_after_bar_time="17:25",
        )

    def test_long_entry_is_delayed_to_next_bar(self) -> None:
        frame = make_frame(
            ["2026-03-02 09:00:00", "2026-03-02 09:05:00", "2026-03-02 09:10:00", "2026-03-02 09:15:00", "2026-03-02 09:20:00"]
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [1, 1, 1, 3, 3],
                "ema_3": [2, 2, 2, 1, 1],
                "ema_4": [0, 0, 0, 1, 1],
                "rsi_5": [50, 50, 50, 70, 70],
                "adx_6": [25, 25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1, 1],
                "trix_8": [0, 0, 0, 0, 0],
                "trix_median_8_9_1": [-1, -1, -1, -1, -1],
                "hurst_10": [0.6, 0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1, 1],
                "vwap": [50, 50, 50, 50, 50],
            },
        )
        raw = generate_raw_positions(frame, self.params, cache=cache)
        signals = generate_executable_signals(frame, self.params, cache=cache)
        self.assertEqual(raw.iloc[3], 1)
        self.assertEqual(signals.iloc[3], 0)
        self.assertEqual(signals.iloc[4], 1)

    def test_short_entry_path(self) -> None:
        frame = make_frame(
            ["2026-03-02 09:00:00", "2026-03-02 09:05:00", "2026-03-02 09:10:00", "2026-03-02 09:15:00", "2026-03-02 09:20:00"]
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [3, 3, 3, 1, 1],
                "ema_3": [2, 2, 2, 3, 3],
                "ema_4": [200, 200, 200, 150, 150],
                "rsi_5": [50, 50, 50, 30, 30],
                "adx_6": [25, 25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1, 1],
                "trix_8": [0, 0, 0, 0, 0],
                "trix_median_8_9_1": [1, 1, 1, 1, 1],
                "hurst_10": [0.6, 0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1, 1],
                "vwap": [200, 200, 200, 200, 200],
            },
        )
        raw = generate_raw_positions(frame, self.params, cache=cache)
        self.assertEqual(raw.iloc[3], -1)

    def test_skip_hour_blocks_entries(self) -> None:
        frame = make_frame(
            ["2026-03-02 12:00:00", "2026-03-02 12:05:00", "2026-03-02 12:10:00", "2026-03-02 12:15:00"]
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [1, 1, 1, 3],
                "ema_3": [2, 2, 2, 1],
                "ema_4": [0, 0, 0, 1],
                "rsi_5": [70, 70, 70, 70],
                "adx_6": [25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1],
                "trix_8": [0, 0, 0, 0],
                "trix_median_8_9_1": [-1, -1, -1, -1],
                "hurst_10": [0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1],
                "vwap": [0, 0, 0, 0],
            },
        )
        raw = generate_raw_positions(frame, self.params, cache=cache)
        self.assertTrue((raw == 0).all())

    def test_entry_cutoff_blocks_entries(self) -> None:
        frame = make_frame(
            ["2026-03-02 14:50:00", "2026-03-02 14:55:00", "2026-03-02 15:00:00", "2026-03-02 15:05:00"]
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [1, 1, 1, 3],
                "ema_3": [2, 2, 2, 1],
                "ema_4": [0, 0, 0, 1],
                "rsi_5": [70, 70, 70, 70],
                "adx_6": [25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1],
                "trix_8": [0, 0, 0, 0],
                "trix_median_8_9_1": [-1, -1, -1, -1],
                "hurst_10": [0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1],
                "vwap": [0, 0, 0, 0],
            },
        )
        raw = generate_raw_positions(frame, self.params, cache=cache)
        self.assertTrue((raw == 0).all())

    def test_trix_exit_clears_long_position(self) -> None:
        frame = make_frame(
            ["2026-03-02 09:00:00", "2026-03-02 09:05:00", "2026-03-02 09:10:00", "2026-03-02 09:15:00", "2026-03-02 09:20:00", "2026-03-02 09:25:00"]
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [1, 1, 1, 3, 3, 3],
                "ema_3": [2, 2, 2, 1, 1, 1],
                "ema_4": [0, 0, 0, 1, 1, 1],
                "rsi_5": [50, 50, 50, 70, 70, 70],
                "adx_6": [25, 25, 25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1, 1, 1],
                "trix_8": [0, 0, 0, 1.5, 1.0, -1.0],
                "trix_median_8_9_1": [-1, -1, -1, -0.5, 0.5, 0.5],
                "hurst_10": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1, 1, 1],
                "vwap": [0, 0, 0, 0, 0, 0],
            },
        )
        raw = generate_raw_positions(frame, self.params, cache=cache)
        self.assertEqual(raw.iloc[3], 1)
        self.assertEqual(raw.iloc[5], 0)

    def test_atr_exit_clears_short_position(self) -> None:
        frame = make_frame(
            ["2026-03-02 09:00:00", "2026-03-02 09:05:00", "2026-03-02 09:10:00", "2026-03-02 09:15:00", "2026-03-02 09:20:00", "2026-03-02 09:25:00"],
            closes=[100, 100, 100, 95, 94, 97],
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [3, 3, 3, 1, 1, 1],
                "ema_3": [2, 2, 2, 3, 3, 3],
                "ema_4": [200, 200, 200, 150, 150, 150],
                "rsi_5": [50, 50, 50, 30, 30, 30],
                "adx_6": [25, 25, 25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1, 1, 1],
                "trix_8": [0, 0, 0, 0, 0, 0],
                "trix_median_8_9_1": [1, 1, 1, 1, 1, 1],
                "hurst_10": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1, 1, 1],
                "vwap": [200, 200, 200, 200, 200, 200],
            },
        )
        raw = generate_raw_positions(frame, self.params, cache=cache)
        self.assertEqual(raw.iloc[3], -1)
        self.assertEqual(raw.iloc[5], 0)

    def test_no_overnight_carry(self) -> None:
        frame = make_frame(
            [
                "2026-03-02 09:00:00",
                "2026-03-02 09:05:00",
                "2026-03-02 09:10:00",
                "2026-03-02 09:15:00",
                "2026-03-03 09:00:00",
                "2026-03-03 09:05:00",
            ]
        )
        cache = FakeCache(
            frame,
            {
                "ema_2": [1, 1, 1, 3, 3, 3],
                "ema_3": [2, 2, 2, 1, 1, 1],
                "ema_4": [0, 0, 0, 1, 1, 1],
                "rsi_5": [50, 50, 50, 70, 70, 70],
                "adx_6": [25, 25, 25, 25, 25, 25],
                "atr_7": [1, 1, 1, 1, 1, 1],
                "trix_8": [0, 0, 0, 0, 0, 0],
                "trix_median_8_9_1": [-1, -1, -1, -1, -1, -1],
                "hurst_10": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
                "vr_2_5": [1, 1, 1, 1, 1, 1],
                "vwap": [0, 0, 0, 0, 0, 0],
            },
        )
        signals = generate_executable_signals(frame, self.params, cache=cache)
        self.assertEqual(signals.iloc[4], 0)

    def test_lookup_fill_price_uses_next_available_minute(self) -> None:
        frame = make_frame(
            ["2026-03-02 10:01:00", "2026-03-02 10:02:00", "2026-03-02 10:03:00"],
            closes=[101, 102, 103],
        )
        self.assertEqual(lookup_fill_price(frame, pd.Timestamp("2026-03-02 10:00:00")), 101.0)
        self.assertEqual(lookup_fill_price(frame, pd.Timestamp("2026-03-02 10:02:00")), 102.0)

    def test_last_30min_marker_counts_7_bars(self) -> None:
        index = pd.date_range("2026-03-02 09:00:00", periods=108, freq="5min")
        frame = make_frame([str(ts) for ts in index])
        marked = int((frame["bars_remaining"] <= 6).sum())
        self.assertEqual(marked, 7)


if __name__ == "__main__":
    unittest.main()
