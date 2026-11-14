"""Tests for returns.py (pipeline step 9: stock returns after the report, minus the market return).

The tests use small test inputs (daily returns) in memory. They need no data and no internet.
"""
import unittest

import numpy as np
import pandas as pd

from tcf_credit.returns import forward_returns


def setup(ret=0.01, n=300, start="2020-01-01"):
    dates = pd.bdate_range(start, periods=n)
    daily = pd.DataFrame({"permno": 1, "date": dates, "ret": ret})
    vw = pd.Series(0.0, index=dates)
    return dates, daily, vw


class ForwardReturnTests(unittest.TestCase):
    """Checks of `forward_returns`: the window, delisting returns, the market return, no overwriting."""
    def test_snapshot_day_is_excluded_and_window_is_after_t(self):
        dates, daily, vw = setup(ret=0.0)
        t = dates[10]
        daily.loc[daily.date == t, "ret"] = 0.5            # the filing-day reaction must not count
        daily.loc[daily.date == dates[11], "ret"] = 0.1
        snap = pd.DataFrame({"permno": [1], "t": [t]})
        r = forward_returns(snap, daily, pd.DataFrame(columns=["permno", "date", "dlret", "dlstcd"]), vw)
        self.assertAlmostEqual(r.fwd_ret_3m[0], 0.1)
        self.assertAlmostEqual(r.ex_3m[0], 0.1)

    def test_missing_performance_delisting_return_is_minus_30_percent_and_position_ends(self):
        dates, daily, vw = setup(ret=0.0)
        t = dates[10]
        delist = pd.DataFrame({"permno": [1], "date": [dates[20]], "dlret": [np.nan], "dlstcd": [552.0]})
        daily.loc[daily.date > dates[20], "ret"] = 0.2      # rows after delisting must be ignored
        r = forward_returns(pd.DataFrame({"permno": [1], "t": [t]}), daily, delist, vw)
        self.assertAlmostEqual(r.fwd_ret_3m[0], -0.30)
        self.assertEqual(r.delisted_3m[0], 1)

    def test_missing_delisting_return_can_be_set(self):
        dates, daily, vw = setup(ret=0.0)
        delist = pd.DataFrame({"permno": [1], "date": [dates[20]], "dlret": [np.nan], "dlstcd": [552.0]})
        r = forward_returns(pd.DataFrame({"permno": [1], "t": [dates[10]]}), daily, delist, vw, missing_delist=-0.55)
        self.assertAlmostEqual(r.fwd_ret_3m[0], -0.55)

    def test_non_performance_delisting_without_return_is_not_filled(self):
        dates, daily, vw = setup(ret=0.0)
        delist = pd.DataFrame({"permno": [1], "date": [dates[20]], "dlret": [np.nan], "dlstcd": [231.0]})   # merger
        r = forward_returns(pd.DataFrame({"permno": [1], "t": [dates[10]]}), daily, delist, vw, missing_delist=-0.55)
        self.assertAlmostEqual(r.fwd_ret_3m[0], 0.0)

    def test_market_return_is_subtracted_over_the_same_window(self):
        dates, daily, vw = setup(ret=0.001)
        vw[:] = 0.001
        r = forward_returns(pd.DataFrame({"permno": [1], "t": [dates[5]]}), daily,
                            pd.DataFrame(columns=["permno", "date", "dlret", "dlstcd"]), vw)
        self.assertAlmostEqual(r.ex_12m[0], 0.0, places=10)


    def test_forward_columns_never_overwrite_existing_columns(self):
        dates, daily, vw = setup()
        snap = pd.DataFrame({"permno": [1], "t": [dates[5]], "fwd_ret_3m": [0.0]})
        with self.assertRaises(ValueError):
            forward_returns(snap, daily, pd.DataFrame(columns=["permno", "date", "dlret", "dlstcd"]), vw)


if __name__ == "__main__":
    unittest.main()
