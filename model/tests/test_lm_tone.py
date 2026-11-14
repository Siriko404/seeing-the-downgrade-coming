"""Tests for lm_tone.py (the optional text-tone step after step 6): the change in tone since the previous 10-K.

The tests use small test inputs (tables). They need no data and no internet.
"""
import unittest

import pandas as pd

from tcf_credit.lm_tone import add_changes


def frame(rows):
    s = pd.DataFrame(rows, columns=["cik", "filed", "lm_neg", "lm_unc"])
    s["filed_dt"] = pd.to_datetime(s.filed)
    return s


class ToneChangeTests(unittest.TestCase):
    """Checks of `add_changes`: which earlier 10-K a tone change is measured against."""
    def test_change_uses_previous_filing_only(self):
        s = add_changes(frame([("1", "2020-03-01", 0.02, 0.01), ("1", "2021-03-01", 0.03, 0.01),
                               ("1", "2022-03-01", 0.01, 0.02)])).set_index("filed")
        self.assertTrue(pd.isna(s.loc["2020-03-01", "lm_neg_chg"]))
        self.assertAlmostEqual(s.loc["2021-03-01", "lm_neg_chg"], 0.01)
        self.assertAlmostEqual(s.loc["2022-03-01", "lm_neg_chg"], -0.02)   # not affected by any later filing

    def test_gap_outside_a_year_gives_no_change(self):
        s = add_changes(frame([("1", "2018-03-01", 0.02, 0.01), ("1", "2021-03-01", 0.03, 0.01)]))
        self.assertTrue(s.lm_neg_chg.isna().all())

    def test_companies_do_not_mix(self):
        s = add_changes(frame([("1", "2020-03-01", 0.02, 0.01), ("2", "2021-03-01", 0.05, 0.01)]))
        self.assertTrue(s.lm_neg_chg.isna().all())


if __name__ == "__main__":
    unittest.main()
