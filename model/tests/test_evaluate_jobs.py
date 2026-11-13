"""evaluate --jobs must spread the test years over processes without changing the results.

The test years are independent once the settings are tuned. Running them in worker processes must therefore give
byte-identical per_year.csv, pooled.csv and predictions.csv files to a --jobs 1 run. A second test feeds the parent's
merging step results that finish out of order and checks that the years are put back in order.

Run from the folder that holds `model/`:
    PYTHONPATH=model/src python -m unittest discover -s model/tests
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "model" / "synthetic"))

import pandas as pd

import make_panel as mp
from tcf_credit import evaluate as E


class EvaluateJobsTests(unittest.TestCase):
    """The same example panel gives the same three result files with one and with two workers."""

    def test_jobs_one_and_two_give_identical_files(self):
        panel = mp.make_panel(n_firms=20, first_year=2012, last_year=2019, seed=5)
        outputs = ("pooled.csv", "per_year.csv", "predictions.csv")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            mp.write_csv(panel, d / "panel.csv")
            env = dict(os.environ, PYTHONPATH=str(ROOT / "model" / "src"))
            for jobs in ("1", "2"):
                subprocess.run(
                    [sys.executable, "-m", "tcf_credit.evaluate", str(d / "panel.csv"), str(d / f"run{jobs}"),
                     "--first", "2018", "--last", "2019", "--only", "logit", "--jobs", jobs],
                    cwd=ROOT, env=env, check=True, capture_output=True, text=True)
            years = pd.read_csv(d / "run1" / "per_year.csv")["year"].unique().tolist()
            for name in outputs:
                a = (d / "run1" / name).read_bytes()
                b = (d / "run2" / name).read_bytes()
                self.assertEqual(a, b, f"{name} differs between --jobs 1 and --jobs 2")
        self.assertEqual(years, [2018, 2019])     # the test must really run more than one year


class ThreadBudgetTests(unittest.TestCase):
    """Each worker gets an even share of the cores, and never less than one thread."""

    def test_budget_splits_the_cores(self):
        cores = os.cpu_count() or 1
        self.assertEqual(E.thread_budget(1), cores)
        self.assertEqual(E.thread_budget(cores), 1)
        self.assertEqual(E.thread_budget(cores * 4), 1)


class MergeYearOrderTests(unittest.TestCase):
    """The parent joins the worker results in year order, even when the workers finish in another order."""

    def test_merge_puts_years_in_order(self):
        def result(year):
            return dict(year=year,
                        rows=[dict(year=year, model="m", rule="calibrated_cut")],
                        preds=pd.DataFrame({"year": [year], "p": [0.5]}),
                        timing={"m": 1.0})

        per_year, preds, timing = E.merge_year_results([result(2020), result(2018), result(2019)])

        self.assertEqual(per_year["year"].tolist(), [2018, 2019, 2020])
        self.assertEqual(preds["year"].tolist(), [2018, 2019, 2020])
        self.assertEqual(timing["m"], 3.0)


if __name__ == "__main__":
    unittest.main()
