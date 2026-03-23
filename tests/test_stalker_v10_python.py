from __future__ import annotations

import unittest

import pandas as pd

from autoresearch_tradebot.strategies.stalker_v10_python import V10Dataset, resolve_intrabar_exit


def make_m1_frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
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


class StalkerV10PythonTests(unittest.TestCase):
    def test_contract_signal_range_uses_previous_then_current_contract_average(self) -> None:
        frame = make_m1_frame(
            [
                ("2024-01-30 09:00", 100, 110, 100, 105),
                ("2024-01-30 09:01", 105, 110, 102, 103),
                ("2024-01-31 09:00", 100, 112, 100, 106),
                ("2024-01-31 09:01", 106, 112, 101, 104),
                ("2024-02-01 09:00", 100, 114, 100, 107),
                ("2024-02-01 09:01", 107, 114, 102, 103),
                ("2024-02-02 09:00", 100, 116, 100, 108),
                ("2024-02-02 09:01", 108, 116, 103, 104),
                ("2024-02-05 09:00", 100, 118, 100, 109),
                ("2024-02-05 09:01", 109, 118, 104, 105),
            ]
        )
        dataset = V10Dataset(frame)
        signal_range = dataset.get_signal_range(0.5, 2)
        lookup = pd.Series(signal_range, index=dataset.bars_m1.index)

        january_mean = ((110 - 100) + (112 - 100)) / 2
        self.assertAlmostEqual(float(lookup.loc[pd.Timestamp("2024-02-01 09:00")]), january_mean * 0.5)
        self.assertAlmostEqual(float(lookup.loc[pd.Timestamp("2024-02-02 09:00")]), january_mean * 0.5)

        expected_current_avg_prev = (((114 - 100) + (116 - 100)) / 2) * 0.5
        self.assertAlmostEqual(float(lookup.loc[pd.Timestamp("2024-02-05 09:00")]), expected_current_avg_prev)

    def test_same_bar_stop_and_target_resolves_stop_first(self) -> None:
        exit_price, exit_reason = resolve_intrabar_exit(
            direction=1,
            bar_high=106.0,
            bar_low=94.0,
            stop_price=95.0,
            target_price=105.0,
        )
        self.assertEqual(exit_price, 95.0)
        self.assertEqual(exit_reason, "ambiguous_stop_first")


if __name__ == "__main__":
    unittest.main(verbosity=2)
