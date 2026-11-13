"""Tests for features_v2.py (pipeline step 6: changes since the last report, beta and the economy as first
released) and for the `Prep` class of evaluate.py (step 7: input preparation).

The tests use small made-up tables and economy files written to a temporary folder.
They need no data and no internet.
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from tcf_credit.features_v2 import Macro, beta_idio, fix_debt_ebitda, ratio_history, vintage_date


def firm(dates, ebit_assets, cik="1"):
    n = len(dates)
    return pd.DataFrame({"cik": cik, "t": pd.to_datetime(dates), "ebit_assets": ebit_assets, "debt_assets": [0.3] * n,
                         "ebit_interest": [5.0] * n, "cfo_debt": [0.2] * n, "cash_assets": [0.1] * n,
                         "op_margin": [0.1] * n, "debt_ebitda": [2.0] * n})


class FeaturesV2Tests(unittest.TestCase):
    """Checks of the step 6 helpers: debt/EBITDA fix, ratio changes, volatility, vintage dates, beta, `Macro`."""
    def test_negative_ebitda_zeroed_and_flagged(self):
        df = pd.DataFrame({"debt": [100.0, 100.0, 0.0], "debt_ebitda": [-4.0, 3.0, np.nan]})
        out = fix_debt_ebitda(df)
        self.assertEqual(out.debt_ebitda.tolist()[:2], [0.0, 3.0])
        self.assertEqual(out.neg_ebitda.tolist()[:2], [1.0, 0.0])
        self.assertTrue(np.isnan(out.neg_ebitda.iloc[2]))

    def test_change_needs_previous_annual_report(self):
        df = ratio_history(firm(["2015-03-01", "2016-03-01", "2018-03-01", "2019-03-01"], [0.10, 0.04, 0.08, 0.02]))
        chg = df.chg_ebit_assets.tolist()
        self.assertTrue(np.isnan(chg[0]))
        self.assertAlmostEqual(chg[1], -0.06)
        self.assertTrue(np.isnan(chg[2]))          # two-year gap: no change
        self.assertAlmostEqual(chg[3], -0.06)

    def test_profit_volatility_needs_three_reports(self):
        df = ratio_history(firm(["2015-03-01", "2016-03-01", "2017-03-01"], [0.10, 0.04, 0.07]))
        v = df.vol_ebit_assets_3y.tolist()
        self.assertTrue(np.isnan(v[0]) and np.isnan(v[1]))
        self.assertAlmostEqual(v[2], np.std([0.10, 0.04, 0.07], ddof=1))

    def test_vintage_dates(self):
        self.assertEqual(vintage_date("RUC20Q2"), pd.Timestamp("2020-05-15"))
        self.assertEqual(vintage_date("IPT99M12"), pd.Timestamp("1999-12-15"))

    def test_beta(self):
        rng = np.random.default_rng(0)
        dates = pd.bdate_range("2019-01-01", periods=300)
        m = pd.Series(rng.normal(0, 0.01, 300), index=dates)
        hist = pd.DataFrame({"date": dates, "ret": 2 * m.to_numpy() + rng.normal(0, 0.002, 300)})
        b, iv = beta_idio(hist, m, dates[-1] + pd.Timedelta(days=1))
        self.assertAlmostEqual(b, 2.0, delta=0.05)
        self.assertAlmostEqual(iv, 0.002 * np.sqrt(252), delta=0.005)

    def test_macro_uses_only_data_out_by_t(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); (d / "realtime").mkdir()
            pd.DataFrame({"date": ["2019:03", "2020:03"], "first_release": [3.8, 4.4],
                          "first_vintage": ["RUC19Q2", "RUC20Q2"], "latest": [3.8, 4.4]}).to_csv(d / "realtime/unemployment_first_release.csv", index=False)
            ip = pd.DataFrame({"DATE": [f"2019:{m:02d}" for m in range(1, 13)] + [f"2020:{m:02d}" for m in range(1, 4)]})
            ip["IPT20M3"] = list(range(100, 112)) + [112, 113, np.nan]
            ip["IPT20M4"] = list(range(100, 112)) + [112, 113, 90]
            ip.to_csv(d / "realtime/indpro_vintages.csv", index=False)
            pd.DataFrame({"Date": ["2019:Q4", "2020:Q1"], "First": [2.1, -4.8]}).to_csv(d / "realtime/gdp_growth_first_second_third.csv", index=False)
            days = pd.date_range("2020-03-01", "2020-06-30")
            for name, val in (("BAA10Y", 2.0), ("T10Y3M", 0.5), ("VIXCLS", 20.0)):
                s = pd.DataFrame({"observation_date": days.strftime("%Y-%m-%d"), name: val})
                s.loc[s.observation_date == "2020-05-10", name] = 99.0   # the day t itself must not be used
                s.to_csv(d / f"{name}.csv", index=False)
            m = Macro(d)
            before = m.at(pd.Timestamp("2020-05-10"))
            self.assertEqual(before["unemp"], 3.8)                    # 2020:03 first out on 2020-05-15
            self.assertTrue(np.isnan(before["unemp_chg_12m"]))
            self.assertEqual(before["baa10y"], 2.0)
            self.assertAlmostEqual(before["ip_growth_12m"], 90 / 102 - 1)    # vintage M4 is out (2020-04-15)
            self.assertAlmostEqual(m.at(pd.Timestamp("2020-04-01"))["ip_growth_12m"], 113 / 101 - 1)   # only M3 out
            self.assertEqual(before["gdp_growth"], -4.8)             # 2020:Q1 known 2020-05-05
            after = m.at(pd.Timestamp("2020-05-16"))
            self.assertEqual(after["unemp"], 4.4)
            self.assertAlmostEqual(after["unemp_chg_12m"], 0.6)
            self.assertAlmostEqual(after["ip_growth_12m"], 90 / 102 - 1)


class PrepEmptyColumnTest(unittest.TestCase):
    """Checks that `Prep` copes with an input column that is empty in the training years."""
    def test_column_empty_in_training_window_gives_no_nan(self):
        from tcf_credit.evaluate import Prep
        train = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [np.nan] * 3, "sector": ["x"] * 3})
        test = pd.DataFrame({"a": [2.0], "b": [0.5], "sector": ["x"]})
        X = Prep(["a", "b"]).fit(train).transform(test)
        self.assertFalse(np.isnan(X).any())

    def test_boosting_trains_with_column_empty_in_training_window(self):
        from sklearn.ensemble import HistGradientBoostingClassifier
        from tcf_credit.evaluate import Prep
        rng = np.random.default_rng(0)
        train = pd.DataFrame({"a": rng.normal(size=200), "b": np.nan, "sector": "x"})
        y = rng.integers(0, 2, 200)
        p = Prep(["a", "b"]).fit(train)
        HistGradientBoostingClassifier(max_iter=5).fit(p.transform(train, impute=False), y)
        test = pd.DataFrame({"a": [0.1], "b": [0.5], "sector": ["x"]})
        self.assertEqual(p.transform(test, impute=False)[0, 1], 0.0)


if __name__ == "__main__":
    unittest.main()
