"""Tests for philly_fed.py (pipeline step 6 helper: convert the Philadelphia Fed real-time spreadsheets to CSV).

The small test writes tiny spreadsheets to a temporary folder. The reference test runs the converter on the public
reference folder when it exists and is skipped otherwise. Neither test needs the internet.
"""
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from tcf_credit.philly_fed import convert, vintage_first_last


def reference(name: str) -> Path:
    """Find a reference folder by looking for ref/<name> above this file, or use TCF_REF_DIR."""
    roots = [Path(os.environ["TCF_REF_DIR"])] if "TCF_REF_DIR" in os.environ else []
    roots += [p / "ref" for p in Path(__file__).resolve().parents]
    for root in roots:
        if (root / name).is_dir():
            return root / name
    return Path("/nonexistent") / name


REF = reference("philly")


class PhillyFedTests(unittest.TestCase):
    """Checks of the vintage rule and of a full conversion of tiny spreadsheets."""
    def test_first_and_latest_across_vintages(self):
        df = pd.DataFrame({"DATE": ["2000:01", "2000:02", "2000:03", "2000:04"],
                           "RUC01Q1": [np.nan, 2.0, np.nan, np.nan],
                           "RUC01Q2": [1.0, 2.2, np.nan, np.nan],
                           "RUC01Q3": [np.nan, 2.5, 3.0, np.nan]})
        out = vintage_first_last(df)
        self.assertEqual(out.date.tolist(), ["2000:01", "2000:02", "2000:03"])   # empty month dropped
        self.assertEqual(out.first_release.tolist(), [1.0, 2.0, 3.0])
        self.assertEqual(out.first_vintage.tolist(), ["RUC01Q2", "RUC01Q1", "RUC01Q3"])
        self.assertEqual(out.latest.tolist(), [1.0, 2.5, 3.0])   # newest blank column is not the latest value

    def test_converts_tiny_spreadsheets(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            pd.DataFrame({"DATE": ["2000:01", "2000:02", "2000:03", "2000:04"],
                          "RUC01Q1": [np.nan, 2.0, np.nan, np.nan],
                          "RUC01Q2": [1.0, 2.2, np.nan, np.nan],
                          "RUC01Q3": [np.nan, 2.5, 3.0, np.nan]}).to_excel(
                d / "rucQvMd.xlsx", sheet_name="ruc", index=False)
            pd.DataFrame({"DATE": ["2000:01", "2000:02"],
                          "IPT00M1": [np.nan, 10.0],
                          "IPT00M2": [5.0, 11.0]}).to_excel(d / "iptMvMd.xlsx", sheet_name="ipt", index=False)
            pd.DataFrame({"Date": ["2000:Q1", "2000:Q2"], "First": [1.5, np.nan], "Second": [np.nan, 2.0],
                          "Third": [np.nan, np.nan], "Most_Recent": [1.6, 2.1]}).to_excel(
                d / "routput_first_second_third.xlsx", sheet_name="DATA", index=False, startrow=4)
            out = d / "out"
            convert(d, out)
            u = pd.read_csv(out / "unemployment_first_release.csv")
            self.assertEqual(u.columns.tolist(), ["date", "first_release", "first_vintage", "latest"])
            self.assertEqual(u.date.tolist(), ["2000:01", "2000:02", "2000:03"])
            self.assertEqual(u.latest.tolist(), [1.0, 2.5, 3.0])
            iv = pd.read_csv(out / "indpro_vintages.csv")
            self.assertEqual(iv.columns.tolist(), ["DATE", "IPT00M1", "IPT00M2"])
            self.assertEqual(len(iv), 2)
            ip = pd.read_csv(out / "indpro_first_release.csv")
            self.assertEqual(ip.first_release.tolist(), [5.0, 10.0])
            self.assertEqual(ip.first_vintage.tolist(), ["IPT00M2", "IPT00M1"])
            self.assertEqual(ip.latest.tolist(), [5.0, 11.0])
            g = pd.read_csv(out / "gdp_growth_first_second_third.csv")
            self.assertEqual(g.columns.tolist(), ["Date", "First", "Second", "Third", "Most_Recent"])
            self.assertEqual(g.Date.tolist(), ["2000:Q1", "2000:Q2"])
            self.assertTrue(np.isnan(g.First.iloc[1]))   # a missing first release is kept as published

    @unittest.skipUnless(REF.is_dir(), "Philadelphia Fed reference folder not found")
    def test_matches_reference_files(self):
        with tempfile.TemporaryDirectory() as d:
            convert(REF, d)
            for name in ("unemployment_first_release.csv", "indpro_vintages.csv", "indpro_first_release.csv",
                         "gdp_growth_first_second_third.csv"):
                got = pd.read_csv(Path(d) / name)
                want = pd.read_csv(REF / name)
                pd.testing.assert_frame_equal(got, want, check_dtype=False, check_exact=False, rtol=0, atol=1e-9)


if __name__ == "__main__":
    unittest.main()
