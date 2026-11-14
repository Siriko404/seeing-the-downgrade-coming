"""Results must not depend on the row order of the panel.

The same panel, with its rows in another order, must give the same models and the same scores. Boosting draws its
validation rows by position, so before the fix a shuffled panel gave different boosting scores. These tests build a
small test panel with model/tests/support/panel_for_tests.py, shuffle a copy, and compare the results.

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
sys.path.insert(0, str(ROOT / "model" / "tests"))

import numpy as np
import pandas as pd

from support import panel_for_tests as mp
from tcf_credit import evaluate as E
from tcf_credit import score_holdings, trend_v3, zoo
from tcf_credit.features_v2 import V2_COLUMNS


def prepared(panel):
    """The panel preparation of evaluate.main, without the fixed order: market rows only, report year, clipped cover."""
    df = panel.copy()
    df["year"] = pd.to_datetime(df["t"]).dt.year
    df = df[df.has_prices == 1].copy()
    df["ebit_interest"] = df["ebit_interest"].clip(-50, 100)
    return df


class EvaluateOrderTests(unittest.TestCase):
    """The evaluation, run as a command, gives the same predictions on a sorted and a shuffled panel."""

    def test_predictions_do_not_depend_on_row_order(self):
        panel = mp.make_panel(n_firms=20, first_year=2012, last_year=2019, seed=5)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            mp.write_csv(panel, d / "sorted.csv")
            mp.write_csv(panel.sample(frac=1, random_state=42), d / "shuffled.csv")
            env = dict(os.environ, PYTHONPATH=str(ROOT / "model" / "src"))
            for name in ("sorted", "shuffled"):
                subprocess.run(
                    [sys.executable, "-m", "tcf_credit.evaluate", str(d / f"{name}.csv"), str(d / name),
                     "--first", "2019", "--last", "2019"],
                    cwd=ROOT, env=env, check=True, capture_output=True, text=True)
            a = pd.read_csv(d / "sorted" / "predictions.csv")
            b = pd.read_csv(d / "shuffled" / "predictions.csv")
            pooled_a = pd.read_csv(d / "sorted" / "pooled.csv")
            pooled_b = pd.read_csv(d / "shuffled" / "pooled.csv")
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(pooled_a, pooled_b)


class ZooOrderTests(unittest.TestCase):
    """Every non-fly zoo engine gives the same scores after evaluate's fixed row order is applied."""

    def setUp(self):
        self._extra = list(E.EXTRA)
        E.EXTRA[:] = list(V2_COLUMNS) + list(E.MARKET)

    def tearDown(self):
        E.EXTRA[:] = self._extra

    def test_zoo_engines_do_not_depend_on_row_order(self):
        panel = prepared(mp.make_panel(n_firms=20, first_year=2012, last_year=2019, seed=5))
        train, test = panel[panel.year <= 2017], panel[panel.year == 2019]
        specs = zoo.specs(E.features())
        for name in ("boosting_mono", "random_forest"):
            sp, p = specs[name], specs[name]["grid"][0]
            make = lambda sp=sp, p=p: sp["make"](p, sp["cols"])
            a = E.fit_predict(make, sp["cols"], sp["impute"], sp["sectors"],
                              E.fixed_order(train), E.fixed_order(test))
            b = E.fit_predict(make, sp["cols"], sp["impute"], sp["sectors"],
                              E.fixed_order(train.sample(frac=1, random_state=1)),
                              E.fixed_order(test.sample(frac=1, random_state=2)))
            # The random forest and XGBoost add numbers in a different order across threads, which can change the
            # last bit; a different row order would change the scores far more.
            np.testing.assert_allclose(a[1], b[1], rtol=1e-12, atol=1e-12, err_msg=name)
            np.testing.assert_allclose(a[0], b[0], rtol=1e-12, atol=1e-12, err_msg=name)


class ScoreHoldingsOrderTests(unittest.TestCase):
    """The scoring path of credit_model (score_holdings) puts both panels in evaluate's fixed order."""

    def test_prepare_puts_rows_in_fixed_order(self):
        panel = mp.make_panel(n_firms=20, first_year=2012, last_year=2019, seed=5)
        a = score_holdings.prepare(panel)
        b = score_holdings.prepare(panel.sample(frac=1, random_state=42))
        pd.testing.assert_frame_equal(a, b)


class TrendOrderTests(unittest.TestCase):
    """trend_v3's score momentum fits the logit on the same rows whatever order the panel file has."""

    def test_score_momentum_does_not_depend_on_row_order(self):
        panel = mp.make_panel(n_firms=20, first_year=2012, last_year=2019, seed=5)
        df = prepared(panel)
        df["t"] = pd.to_datetime(df["t"])
        a = trend_v3.score_momentum(df)
        b = trend_v3.score_momentum(df.sample(frac=1, random_state=42))
        a = a.sort_values(["cik", "t"]).reset_index(drop=True)
        b = b.sort_values(["cik", "t"]).reset_index(drop=True)
        for col in trend_v3.B_COLS:
            np.testing.assert_array_equal(a[col].to_numpy(), b[col].to_numpy(), err_msg=col)


if __name__ == "__main__":
    unittest.main()
