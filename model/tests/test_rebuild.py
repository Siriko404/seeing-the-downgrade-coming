"""Tests for rebuild.py (one command that runs the whole pipeline, step by step).

Every step command is replaced by a fake that writes tiny files, so these tests need no network and no real data.
They check the order of the steps, skipping finished steps, --from, a failure in the middle, the manual-download
stop, the WRDS route, --zoo and the final summary.
"""
import contextlib
import gzip
import io
import tempfile
import unittest
from pathlib import Path

from tcf_credit import rebuild
from tcf_credit.fetch_public import MANUAL


def write(path: Path, text: str = "x\n") -> None:
    """Make the parent folder and write a tiny file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class FakeCommands:
    """A stand-in for rebuild.run_command: it records the module and writes that step's small output files."""

    def __init__(self, manual: bool = True, fail_at: str | None = None):
        self.calls = []
        self.manual = manual
        self.fail_at = fail_at

    def __call__(self, argv, env, stdin=None):
        module = argv[argv.index("-m") + 1].split(".")[-1]
        self.calls.append((module, argv))
        data = Path(env["FAKE_DATA"])
        out = Path(env["FAKE_OUT"])
        if self.fail_at == module:
            raise rebuild.CommandFailed(argv, "", "the fake step broke")
        getattr(self, module)(data, out, argv)

    def fetch_public(self, data, out, argv):
        for series in ("BAA10Y", "T10Y3M", "VIXCLS"):
            write(data / "fred" / f"{series}.csv", "observation_date,x\n2020-01-01,1\n")
        for name in ("rucQvMd.xlsx", "iptMvMd.xlsx", "routput_first_second_third.xlsx"):
            write(data / "fred" / "realtime" / name)
        if self.manual:
            for m in MANUAL:
                write(data / m.dest)

    def philly_fed(self, data, out, argv):
        for name in ("unemployment_first_release.csv", "indpro_vintages.csv", "indpro_first_release.csv",
                     "gdp_growth_first_second_third.csv"):
            write(data / "fred" / "realtime" / name, "date,value\n2000:01,1\n")

    def lm_headers(self, data, out, argv):
        write(data / "lm_headers.csv", "cik,name\n1,A\n")

    def fetch_sec_bulk(self, data, out, argv):
        for name in ("companyfacts.zip", "submissions.zip", "company_tickers_exchange.json"):
            write(data / "sec" / name)

    def ratings_parser(self, data, out, argv):
        (out / "ratings").mkdir(parents=True, exist_ok=True)
        with gzip.open(out / "ratings" / "ratings_obligor_events.csv.gz", "wt") as fh:
            fh.write("agency,rating\nS&P,BBB\nS&P,BB\n")
        write(out / "ratings" / "MANIFEST.txt")

    def link_obligors(self, data, out, argv):
        write(out / "links.csv", "cik,obligor\n1,A\n2,B\n")

    def fetch_companyfacts(self, data, out, argv):
        write(data / "companyfacts" / "1.csv", "cik,tag\n1,Assets\n")

    def build_panel(self, data, out, argv):
        write(out / "panel.csv", "cik,t,label\n1,2020-01-01,0\n2,2020-01-01,1\n3,2020-01-01,0\n")

    def tickers(self, data, out, argv):
        write(out / "TICKERS.csv", "cik,ticker,exchange\n1,AAA,N\n")
        write(out / "TICKERS.txt", "AAA\nSPY\n")

    def fetch_yahoo(self, data, out, argv):
        write(data / "yahoo" / "SPY.csv", "date,close\n2020-01-01,1\n")

    def yahoo_market(self, data, out, argv):
        self.crsp(out)

    def fetch_wrds(self, data, out, argv):
        self.crsp(out)

    @staticmethod
    def crsp(out):
        write(out / "crsp" / "crsp_links.csv", "cik,permno\n1,1\n")
        write(out / "crsp" / "crsp_daily.parquet", "x")
        write(out / "crsp" / "crsp_sp500.csv", "date,sprtrn\n2020-01-01,0\n")
        write(out / "crsp" / "crsp_vwretd.csv", "date,vwretd\n2020-01-01,0\n")

    def market_features(self, data, out, argv):
        write(out / "panel_market.csv", "cik,ret_12m\n1,0.1\n2,0.2\n")

    def features_v2(self, data, out, argv):
        write(out / "panel_v2.csv", "cik,t,label,has_prices\n1,2020-01-01,0,1\n2,2020-01-01,1,1\n")

    def evaluate(self, data, out, argv):
        write(out / "run" / "pooled.csv", "model,rule,n,downgrades\nlogit,calibrated_cut,2,1\n")
        write(out / "run" / "per_year.csv", "year,model,rule,n\n2020,logit,calibrated_cut,2\n")
        write(out / "run" / "predictions.csv", "year,model,label,p\n2020,logit,0,0.1\n")
        write(out / "run" / "params.json", "{}")

    def compare_models(self, data, out, argv):
        write(out / "run" / "comparison.csv", "model,roc_auc\nlogit,0.8\n")


class RebuildTests(unittest.TestCase):
    """The runner, with every real command replaced by FakeCommands."""

    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.root = Path(self.work.name)
        self.data, self.out = self.root / "data", self.root / "out"
        self.env = {"FAKE_DATA": str(self.data), "FAKE_OUT": str(self.out)}
        self._real = rebuild.run_command

    def tearDown(self):
        rebuild.run_command = self._real
        self.work.cleanup()

    def run_fake(self, fake, **kw):
        rebuild.run_command = fake
        if fake.manual:
            # The runner decides which commands to build before it starts; the header file must be there then.
            for m in MANUAL:
                write(self.data / m.dest)
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = rebuild.run(self.data, self.out, env=self.env, **kw)
        return code, text.getvalue()

    def modules(self, fake):
        return [m for m, _ in fake.calls]

    def test_steps_run_in_order(self):
        fake = FakeCommands()
        code, text = self.run_fake(fake)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.modules(fake), [
            "fetch_public", "philly_fed", "lm_headers", "fetch_sec_bulk", "ratings_parser",
            "link_obligors", "fetch_companyfacts", "build_panel", "tickers", "fetch_yahoo", "yahoo_market",
            "market_features", "features_v2", "evaluate", "compare_models"])
        sec = [argv for module, argv in fake.calls if module == "fetch_sec_bulk"]
        self.assertTrue(sec and "--tickers-only" in sec[0], "only the SEC ticker list is needed, not the 2 GB zips")
        self.assertIn("Step 4 of 9: build the table", text)
        self.assertIn("3 rows", text)
        self.assertIn("Pooled results", text)
        self.assertIn(str(self.out / "panel_v2.csv"), text)

    def test_finished_steps_are_skipped(self):
        fake = FakeCommands()
        self.run_fake(fake)
        again = FakeCommands(fail_at="fetch_public")
        code, text = self.run_fake(again)
        self.assertEqual(code, 0, text)
        self.assertEqual(again.calls, [])
        self.assertEqual(text.count("skipped (outputs already exist)"), 9)

    def test_from_step_forces_that_step_and_later(self):
        self.run_fake(FakeCommands())
        again = FakeCommands()
        code, text = self.run_fake(again, from_step=5)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.modules(again), [
            "fetch_yahoo", "yahoo_market", "market_features", "features_v2", "evaluate", "compare_models"])

    def test_stops_at_first_failure(self):
        fake = FakeCommands(fail_at="market_features")
        code, text = self.run_fake(fake)
        self.assertEqual(code, 1)
        self.assertIn("Step 6 of 9", text)
        self.assertIn("FAILED", text)
        self.assertIn("check:", text)
        self.assertNotIn("features_v2", self.modules(fake))

    def test_manual_downloads_stop_the_run(self):
        fake = FakeCommands(manual=False)
        code, text = self.run_fake(fake)
        self.assertEqual(code, 1)
        self.assertIn("Step 1 of 9", text)
        self.assertIn("manual downloads needed", text)
        self.assertIn("LoughranMcDonald_10-K_HeaderData_1993-2025.csv", text)
        self.assertEqual(self.modules(fake), ["fetch_public"])

    def test_wrds_route_and_zoo(self):
        fake = FakeCommands()
        code, text = self.run_fake(fake, route="wrds", wrds_user="student", zoo=True)
        self.assertEqual(code, 0, text)
        self.assertIn("LICENSED", text)
        self.assertIn("fetch_wrds", self.modules(fake))
        self.assertNotIn("fetch_yahoo", self.modules(fake))
        evaluate = [argv for module, argv in fake.calls if module == "evaluate"][0]
        self.assertIn("--zoo", evaluate)

    def test_coverage_end_is_passed_to_the_panel(self):
        fake = FakeCommands()
        self.run_fake(fake, coverage_end="2024-06-30")
        panel = [argv for module, argv in fake.calls if module == "build_panel"][0]
        self.assertEqual(panel[panel.index("--coverage-end") + 1], "2024-06-30")


if __name__ == "__main__":
    unittest.main()
