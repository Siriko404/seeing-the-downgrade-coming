"""Tests for yahoo_market.py (pipeline step 5a, the free stand-in for CRSP: Yahoo prices written in the CRSP layout).

The test writes small test inputs (price files) to a temporary folder and runs the module as a command.
It needs no data and no internet.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"


class YahooMarketTests(unittest.TestCase):
    """Check that the command writes the CRSP-format price, link and market-return files from Yahoo-style prices."""
    def test_writes_crsp_format(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "y").mkdir()
            dates = pd.date_range("2025-01-01", periods=5, freq="B")
            for tk, px in (("AAA", [10, 11, 12.1, 12.1, 13.31]), ("SPY", [100, 101, 102, 103, 104])):
                pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "open": px, "high": px, "low": px, "close": px,
                              "adjclose": px, "volume": 1}).to_csv(d / "y" / f"{tk}.csv", index=False)
            pd.DataFrame({"cik": ["123", "456"], "ticker": ["AAA", "BBB"]}).to_csv(d / "t.csv", index=False)
            pd.DataFrame({"cik": ["123", "123"], "t": ["2024-02-01", "2025-02-01"], "shares": [None, 2_000_000]}
                         ).to_csv(d / "p.csv", index=False)
            r = subprocess.run([sys.executable, "-m", "tcf_credit.yahoo_market", str(d / "y"), str(d / "t.csv"),
                                str(d / "p.csv"), str(d / "out")], capture_output=True, text=True,
                               env={"PYTHONPATH": str(SRC)})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("skip BBB", r.stdout)
            daily = pd.read_parquet(d / "out" / "crsp_daily.parquet")
            self.assertEqual(list(daily.columns), ["permno", "date", "prc", "ret", "shrout"])
            self.assertTrue((daily.permno == 123).all())
            self.assertAlmostEqual(daily.ret.iloc[1], 0.1)
            self.assertEqual(daily.shrout.iloc[0], 2000)          # thousands, from the latest 10-K with shares
            links = pd.read_csv(d / "out" / "crsp_links.csv")
            self.assertEqual(links.cik.tolist(), [123])
            m = pd.read_csv(d / "out" / "crsp_vwretd.csv")
            self.assertAlmostEqual(m.vwretd.iloc[0], 0.01)        # first return of SPY, the market proxy


if __name__ == "__main__":
    unittest.main()
