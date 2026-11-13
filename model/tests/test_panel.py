"""Tests for build_panel.py (pipeline step 4: the label, the S&P rating state and the exclusion of some industries).

The tests use short lists of made-up rating events. They need no data and no internet.
"""
import datetime as dt
import unittest

from tcf_credit.build_panel import label, rating_state, excluded

D = dt.date


class LabelTests(unittest.TestCase):
    """Checks of `label`: 1, 0 or dropped (None) for the 365 days after the snapshot date."""
    END = D(2025, 12, 5)

    def test_downgrade_inside_window_is_one(self):
        ev = [(D(2019, 1, 1), "BB", "NW", "Stable", ""), (D(2020, 6, 1), "B+", "DG", "Negative", "")]
        self.assertEqual(label(ev, D(2020, 1, 1), self.END), 1)

    def test_downgrade_after_365_days_is_zero(self):
        ev = [(D(2019, 1, 1), "BB", "NW", "Stable", ""), (D(2021, 1, 2), "B+", "DG", "Negative", "")]
        self.assertEqual(label(ev, D(2020, 1, 1), self.END), 0)

    def test_downgrade_on_snapshot_day_is_not_future(self):
        ev = [(D(2020, 1, 1), "B+", "DG", "Negative", "")]
        self.assertEqual(label(ev, D(2020, 1, 1), self.END), 0)

    def test_withdrawal_before_downgrade_censors(self):
        ev = [(D(2020, 3, 1), "NR", "WO", "NR", ""), (D(2020, 6, 1), "B+", "DG", "", "")]
        self.assertIsNone(label(ev, D(2020, 1, 1), self.END))

    def test_window_beyond_coverage_censors(self):
        self.assertIsNone(label([], D(2025, 1, 1), self.END))


class StateTests(unittest.TestCase):
    """Checks of `rating_state` (only events before t count) and of `excluded` (financials, utilities)."""
    def test_state_uses_only_events_before_t(self):
        ev = [(D(2019, 1, 1), "BB", "NW", "Stable", ""), (D(2020, 6, 1), "B+", "DG", "Negative", "WatchNeg")]
        s = rating_state(ev, D(2020, 1, 1))
        self.assertEqual((s["rating"], s["notch"], s["outlook"], s["watch"], s["dg_prev_year"]), ("BB", 12, "Stable", "", 0))

    def test_previous_year_downgrade_flag(self):
        ev = [(D(2019, 6, 1), "B+", "DG", "Negative", "")]
        self.assertEqual(rating_state(ev, D(2020, 1, 1))["dg_prev_year"], 1)

    def test_financials_and_utilities_excluded(self):
        self.assertTrue(excluded("6021") and excluded("4911"))
        self.assertFalse(excluded("7372"))
        self.assertFalse(excluded("4953"))   # refuse systems (Waste Management) are not a utility


if __name__ == "__main__":
    unittest.main()
