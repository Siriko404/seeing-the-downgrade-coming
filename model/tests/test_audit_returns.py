"""Tests for audit_returns.py (pipeline step 9b: the audit of extreme 12-month stock winners).

Each test builds a small test input (a price history) in memory and runs the audit checks on it.
It needs no data and no internet.
"""
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from tcf_credit.audit_returns import audit_one


def stock(n=300, daily=0.005, start="2020-01-01", price=2.0):
    dates = pd.bdate_range(start, periods=n)
    prc = price * np.cumprod(np.full(n, 1 + daily))
    ret = np.r_[np.nan, prc[1:] / prc[:-1] - 1]
    return pd.DataFrame({"permno": 1, "date": dates, "prc": prc, "ret": ret, "cfacpr": 1.0})


NAMES = pd.DataFrame({"permno": [1], "namedt": [pd.Timestamp("2000-01-01")], "nameenddt": [pd.Timestamp("2030-01-01")],
                      "shrcd": [11]})


def snapshot(g, t_index=5, delisted=0):
    t = g.date[t_index]
    win = g[(g.date > t) & (g.date <= t + pd.DateOffset(months=12))]
    return SimpleNamespace(permno=1, t=t, fwd_ret_12m=float(np.prod(1 + win.ret.fillna(0)) - 1), delisted_12m=delisted)


class AuditTests(unittest.TestCase):
    """Checks of `audit_one`: which price histories pass or fail each audit check."""
    def test_consistent_prices_pass_every_check(self):
        g = stock()
        r = audit_one(snapshot(g), g, NAMES)
        for c in ("recompute", "price_path", "big_days", "coverage", "identity", "unique"):
            self.assertTrue(r[c], c)

    def test_a_return_spike_without_a_price_move_fails(self):
        g = stock()
        g.loc[100, "ret"] = 3.0                              # a 300% day that the prices do not show
        r = audit_one(snapshot(g), g, NAMES)
        self.assertFalse(r["price_path"])
        self.assertFalse(r["big_days"])

    def test_a_split_does_not_fail_when_cfacpr_adjusts(self):
        g = stock()
        g.loc[150:, "prc"] = g.loc[150:, "prc"] / 10         # 10-for-1 split: raw price falls, adjustment factor too
        g.loc[150:, "cfacpr"] = 0.1
        r = audit_one(snapshot(g), g, NAMES)
        self.assertTrue(r["price_path"])

    def test_non_common_share_fails_identity(self):
        g = stock()
        names = NAMES.assign(shrcd=73)                       # 73 = exchange-traded fund
        self.assertFalse(audit_one(snapshot(g), g, names)["identity"])

    def test_duplicated_rows_fail_unique(self):
        g = stock()
        g = pd.concat([g, g.iloc[[50]]]).sort_values("date").reset_index(drop=True)
        self.assertFalse(audit_one(snapshot(g), g, NAMES)["unique"])


if __name__ == "__main__":
    unittest.main()
