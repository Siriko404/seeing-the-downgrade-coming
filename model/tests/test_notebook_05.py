"""Tests for notebook 05 (the real-data notebook).

The saved notebook must have no outputs, and it must run from top to bottom on a tiny fake OUT_DIR. The fake folder
holds a small panel_v2.csv and small run files, so the notebook reads them instead of running the rebuild command.
No network is used. If nbconvert is not installed, the execution test is skipped.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = ROOT / "model" / "notebooks" / "05_real_data.ipynb"

try:
    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor
except ImportError:                                        # nbconvert is optional
    nbformat = None
    ExecutePreprocessor = None


def fake_outputs(folder: Path) -> None:
    """Write the small files the notebook reads."""
    run = folder / "run"
    run.mkdir(parents=True)
    pd.DataFrame({
        "cik": [1, 2, 1, 3],
        "t": ["2020-06-01", "2020-06-01", "2021-06-01", "2021-06-01"],
        "label": [0, 1, 1, 0],
        "rating": ["BBB", "BB", "BB", "A"],
        "notch": [10, 11, 11, 5],
        "has_prices": [1, 1, 1, 1],
    }).to_csv(folder / "panel_v2.csv", index=False)
    pd.DataFrame({
        "model": ["logit"], "rule": ["calibrated_cut"], "n": [4], "downgrades": [2], "roc_auc": [0.8],
        "pr_auc": [0.5], "flagged": [2], "TP": [1], "FP": [1], "FN": [1], "miss_rate": [0.5],
        "false_alarm_rate": [0.5],
    }).to_csv(run / "pooled.csv", index=False)
    pd.DataFrame({
        "year": [2020, 2021], "model": ["logit", "logit"], "rule": ["calibrated_cut", "calibrated_cut"],
        "n": [2, 2], "downgrades": [1, 1], "flagged": [1, 1], "TP": [1, 0], "FP": [0, 1], "FN": [0, 1],
    }).to_csv(run / "per_year.csv", index=False)
    pd.DataFrame({
        "year": [2020, 2021], "model": ["logit", "logit"], "cik": [1, 3], "t": ["2020-06-01", "2021-06-01"],
        "label": [0, 0], "p": [0.2, 0.1], "flag_cut": [True, False], "flag_rank": [True, False],
    }).to_csv(run / "predictions.csv", index=False)
    (run / "params.json").write_text("{}")


class NotebookSavedTests(unittest.TestCase):
    """The notebook in the package is clean: no saved outputs and no execution counts."""

    def test_saved_notebook_has_no_outputs(self):
        nb = json.loads(NOTEBOOK.read_text())
        for i, cell in enumerate(nb["cells"]):
            if cell["cell_type"] == "code":
                self.assertEqual(cell.get("outputs", []), [], f"cell {i} has saved output")
                self.assertIsNone(cell.get("execution_count"), f"cell {i} has an execution count")


@unittest.skipIf(ExecutePreprocessor is None, "nbconvert is not installed")
class NotebookRunTests(unittest.TestCase):
    """The notebook runs on a fake output folder that holds tiny files only."""

    def test_runs_top_to_bottom_on_a_fake_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            out = d / "out"
            fake_outputs(out)
            nb = nbformat.read(NOTEBOOK, as_version=4)
            env = {"TCF_NB_DATA_DIR": str(d / "data"), "TCF_NB_OUT_DIR": str(out), "TCF_NB_ROUTE": "free"}
            with mock.patch.dict(os.environ, env):
                ExecutePreprocessor(timeout=180, kernel_name="python3").preprocess(
                    nb, resources={"metadata": {"path": str(ROOT)}})
            code = [c for c in nb.cells if c.cell_type == "code"]
            text = "".join(o.get("text", "") for c in code for o in c.get("outputs", []))
            self.assertIn("Reading the existing results", text)


if __name__ == "__main__":
    unittest.main()
