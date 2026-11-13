"""Tests for make_panel.py (the example-data generator).

Run from the folder that holds `model/`:
    PYTHONPATH=model/src python -m unittest discover -s model/synthetic -v
"""
import re
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import make_panel as mp


# The model's input columns and types, in order, written out here so the test also works without any other folder.
# (pandas type names: int64, float64, str). The licensed stock-database identifier is deliberately not made.
EXPECTED = """cik int64|obligor str|sp_name str|accn str|t str|period_end str|fy_end_year int64|sic int64|sector str|
label int64|rating str|notch int64|ig int64|outlook_neg int64|outlook_pos int64|watch_neg int64|watch_pos int64|
dg_prev_year int64|up_prev_year int64|years_rated float64|days_since_action int64|assets float64|debt float64|
debt_src str|debt_assets float64|ebit_assets float64|wc_assets float64|ebit_interest float64|interest_src str|
cfo_debt float64|log_assets float64|re_assets float64|cash_assets float64|op_margin float64|dividend_payer int64|
float_debt float64|debt_ebitda float64|shares float64|debt_current float64|has_prices int64|ret_12m float64|
ret_6m float64|vol_12m float64|mcap_debt float64|dd_naive float64|neg_ebitda float64|chg_debt_assets float64|
chg_ebit_assets float64|chg_ebit_interest float64|chg_cfo_debt float64|chg_cash_assets float64|
chg_op_margin float64|chg_debt_ebitda float64|vol_ebit_assets_3y float64|beta_12m float64|idio_vol_12m float64|
unemp float64|unemp_chg_12m float64|ip_growth_12m float64|gdp_growth float64|baa10y float64|t10y3m float64|
vix_20d float64"""
EXPECTED = [tuple(x.split()) for x in EXPECTED.replace("\n", "").split("|")]


def roundtrip(panel):
    """Write with the real writer and read back the way students (and evaluate.py) do."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "p.csv"
        mp.write_csv(panel, path)
        return pd.read_csv(path)


class ColumnTests(unittest.TestCase):
    """Checks of the panel columns: names, types and gaps."""
    @classmethod
    def setUpClass(cls):
        cls.panel = mp.make_panel(n_firms=120, seed=3)
        cls.back = roundtrip(cls.panel)

    def test_names_and_order(self):
        self.assertEqual(list(self.back.columns), [name for name, _ in EXPECTED])

    def test_types_after_reading_back(self):
        for name, kind in EXPECTED:
            col = self.back[name]
            if kind == "int64":
                self.assertEqual(str(col.dtype), "int64", name)
            elif kind == "float64":
                self.assertEqual(str(col.dtype), "float64", name)
            else:
                self.assertTrue(pd.api.types.is_string_dtype(col.dtype), name)

    def test_integer_columns_have_no_gaps(self):
        for name, kind in EXPECTED:
            if kind == "int64":
                self.assertFalse(self.back[name].isna().any(), name)


class ReproducibilityTests(unittest.TestCase):
    """Checks that the same seed gives the same file and another seed a different one."""
    def write(self, name, **kw):
        d = Path(tempfile.mkdtemp())
        path = d / name
        mp.write_csv(mp.make_panel(n_firms=60, **kw), path)
        return path.read_bytes()

    def test_same_seed_same_bytes(self):
        self.assertEqual(self.write("a.csv", seed=5), self.write("b.csv", seed=5))

    def test_same_seed_same_bytes_gzip(self):
        self.assertEqual(self.write("a.csv.gz", seed=5), self.write("b.csv.gz", seed=5))

    def test_different_seed_different_bytes(self):
        self.assertNotEqual(self.write("a.csv", seed=5), self.write("b.csv", seed=6))

    def test_default_seed_is_fixed(self):
        a = mp.make_panel(n_firms=40)
        b = mp.make_panel(n_firms=40, seed=1)
        pd.testing.assert_frame_equal(a, b)


class ContentTests(unittest.TestCase):
    """Checks of the values in the example panel: made-up names, flags, ratios, dates, label share."""
    @classmethod
    def setUpClass(cls):
        cls.panel = mp.make_panel()          # default size: 400 companies, fiscal years 2009-2025
        cls.back = roundtrip(cls.panel)

    def test_label_share(self):
        share = self.panel["label"].mean()
        self.assertTrue(0.05 <= share <= 0.25, share)

    def test_label_share_in_other_seeds(self):
        for seed in (2, 3, 4):
            share = mp.make_panel(n_firms=200, seed=seed)["label"].mean()
            self.assertTrue(0.05 <= share <= 0.25, (seed, share))

    def test_names_are_example_names(self):
        pattern = re.compile(r"^Example Co \d{3,}( Inc)?$")
        for col in ("obligor", "sp_name"):
            bad = [v for v in self.back[col].unique() if not pattern.match(v)]
            self.assertEqual(bad, [], col)

    def test_company_numbers_and_report_numbers_are_made_up(self):
        self.assertTrue((self.panel["cik"] >= 9_000_001).all())
        self.assertTrue(self.panel["accn"].str.match(r"^0009\d{6}-\d\d-\d{6}$").all())
        self.assertTrue(self.panel["accn"].is_unique)

    def test_rating_letter_matches_notch(self):
        from tcf_credit.build_panel import NOTCH
        self.assertTrue(self.panel["notch"].between(1, 22).all())
        self.assertEqual([NOTCH[r] for r in self.panel["rating"]], list(self.panel["notch"]))

    def test_investment_grade_flag_follows_notch(self):
        self.assertTrue(((self.panel["notch"] <= 10).astype(int) == self.panel["ig"]).all())

    def test_sector_matches_real_code(self):
        from tcf_credit.build_panel import excluded, sector
        self.assertEqual([sector(str(s)) for s in self.panel["sic"]], list(self.panel["sector"]))
        self.assertFalse(any(excluded(str(s)) for s in self.panel["sic"]))

    def test_flags_are_zero_or_one(self):
        for c in ["label", "ig", "outlook_neg", "outlook_pos", "watch_neg", "watch_pos", "dg_prev_year",
                  "up_prev_year", "dividend_payer", "has_prices"]:
            self.assertTrue(self.panel[c].isin([0, 1]).all(), c)
        self.assertFalse(((self.panel.outlook_neg == 1) & (self.panel.outlook_pos == 1)).any())

    def test_ratios_agree_with_amounts(self):
        p = self.panel
        np.testing.assert_allclose(p.debt_assets, p.debt / p.assets, atol=2e-6)   # the file keeps 6 decimals
        np.testing.assert_allclose(p.log_assets, np.log(p.assets), atol=1e-5)

    def test_dates_in_order(self):
        t, pe = pd.to_datetime(self.panel["t"]), pd.to_datetime(self.panel["period_end"])
        self.assertTrue(((t - pe).dt.days > 30).all())
        self.assertTrue((pe.dt.year == self.panel["fy_end_year"]).all())
        # labelled rows only: the 12-month window must have finished by the coverage end
        self.assertTrue((t + pd.Timedelta(days=365) <= pd.Timestamp("2025-12-05")).all())

    def test_default_rolling_test_years_have_both_classes(self):
        year = pd.to_datetime(self.panel["t"]).dt.year
        for y in range(2016, 2025):
            labels = self.panel.loc[year == y, "label"]
            self.assertGreater(len(labels), 100, y)
            self.assertEqual(set(labels), {0, 1}, y)

    def test_first_report_has_no_change_columns(self):
        first = self.panel.sort_values(["cik", "t"]).groupby("cik").head(1)
        self.assertTrue(first[[c for c in self.panel.columns if c.startswith("chg_")]].isna().all().all())
        self.assertTrue(first["vol_ebit_assets_3y"].isna().all())

    def test_market_inputs_empty_without_prices(self):
        none = self.panel[self.panel.has_prices == 0]
        self.assertGreater(len(none), 0)
        self.assertTrue(none[["ret_12m", "ret_6m", "vol_12m", "mcap_debt", "dd_naive"]].isna().all().all())
        some = self.panel[self.panel.has_prices == 1]
        self.assertFalse(some[["ret_12m", "vol_12m"]].isna().any().any())

    def test_label_depends_on_inputs(self):
        # The made-up rule makes risky-looking reports downgrade more often. If the rule were broken (for example
        # labels drawn at random), a simple logistic regression could not beat chance.
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        p = self.panel
        x = p[["debt_assets", "ebit_assets", "notch", "outlook_neg", "watch_neg", "dg_prev_year", "baa10y"]]
        year = pd.to_datetime(p["t"]).dt.year
        tr, te = year <= 2018, year >= 2020
        m = LogisticRegression(max_iter=2000).fit((x[tr] - x[tr].mean()) / x[tr].std(), p.label[tr])
        auc = roc_auc_score(p.label[te], m.predict_proba((x[te] - x[tr].mean()) / x[tr].std())[:, 1])
        self.assertGreater(auc, 0.65)
        self.assertLess(auc, 0.95)       # and the noise keeps it from being perfect

    def test_target_rate_option(self):
        share = mp.make_panel(n_firms=200, seed=1, target_rate=0.20)["label"].mean()
        self.assertTrue(0.15 <= share <= 0.25, share)


if __name__ == "__main__":
    unittest.main()
