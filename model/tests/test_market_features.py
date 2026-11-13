"""Tests for market_features.py (pipeline step 5b: stock-market inputs added to the panel).

The tests build a made-up daily price history in memory. They need no data and no internet.
"""
import unittest

import numpy as np
import pandas as pd

from tcf_credit.market_features import stock_features, row_features


def series(n_days, start="2019-01-01", ret=0.001, prc=10.0, shrout=1000.0):
    dates = pd.bdate_range(start, periods=n_days)
    return pd.DataFrame({"date": dates, "prc": prc, "ret": ret, "shrout": shrout})


class MarketFeatureTests(unittest.TestCase):
    """Checks of `stock_features` and `row_features`: no look-ahead, excess return, missing history."""
    def test_uses_only_days_before_t(self):
        h = series(400)
        t = h.date.iloc[300]
        sp = pd.Series(0.0, index=h.date)
        base = stock_features(h, sp, t)
        h2 = h.copy()
        h2.loc[h2.date >= t, "ret"] = -0.5          # a crash on and after t must not change the inputs
        h2.loc[h2.date >= t, "prc"] = 0.01
        self.assertEqual(stock_features(h2, sp, t), base)

    def test_excess_return_over_market(self):
        h = series(300, ret=0.001)
        t = h.date.iloc[-1] + pd.Timedelta(days=1)
        sp = pd.Series(0.001, index=h.date)
        self.assertAlmostEqual(stock_features(h, sp, t)["ret_12m"], 0.0, places=12)

    def test_short_history_or_stale_price_gives_none(self):
        h = series(200)
        sp = pd.Series(0.0, index=h.date)
        self.assertIsNone(stock_features(h, sp, h.date.iloc[-1] + pd.Timedelta(days=1)))
        h = series(300)
        sp = pd.Series(0.0, index=h.date)
        self.assertIsNone(stock_features(h, sp, h.date.iloc[-1] + pd.Timedelta(days=30)))

    def test_negative_crsp_price_is_bid_ask_midpoint(self):
        h = series(300, prc=-10.0)
        t = h.date.iloc[-1] + pd.Timedelta(days=1)
        f = stock_features(h, pd.Series(0.0, index=h.date), t)
        self.assertEqual(f["e"], 10.0 * 1000.0 * 1000)
        r = row_features([(1, f)], debt=5e6, debt_current=1e6)
        self.assertAlmostEqual(r["mcap_debt"], 2.0)
        self.assertTrue(np.isfinite(r["dd_naive"]))


if __name__ == "__main__":
    unittest.main()
