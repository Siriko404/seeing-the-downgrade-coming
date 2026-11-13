"""Fruit fly models on small hand-made wiring (no download); run on the processor, where a fit repeats exactly."""
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path

os.environ["TCF_DEVICE"] = "cpu"

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.linear_model import LogisticRegression

from tcf_credit import brain, fly, readout


def toy_wiring(inputs=30, cells=200, per_cell=6, seed=0):
    rng = np.random.default_rng(seed)
    rows = np.concatenate([rng.choice(inputs, per_cell, replace=False) for _ in range(cells)])
    cols = np.repeat(np.arange(cells), per_cell)
    return sp.csr_matrix((rng.integers(1, 20, rows.size).astype(np.float32), (rows, cols)), shape=(inputs, cells))


def toy_data(n=600, width=8, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, width))
    y = (x[:, 0] + 0.5 * x[:, 1] + rng.normal(size=n) > 1).astype(int)
    return x, y


class FetchTests(unittest.TestCase):
    def test_fetch_checks_the_pinned_hash(self):
        with tempfile.TemporaryDirectory() as d:
            fly.FILES["toy.bin"] = ("https://example.invalid/toy.bin", hashlib.sha256(b"ok").hexdigest())
            try:
                with self.assertRaises(ValueError):
                    fly.fetch("toy.bin", Path(d), lambda url: io.BytesIO(b"tampered"))
                self.assertFalse((Path(d) / "toy.bin").exists())
                self.assertEqual(fly.fetch("toy.bin", Path(d), lambda url: io.BytesIO(b"ok")).read_bytes(), b"ok")
            finally:
                del fly.FILES["toy.bin"]


class MushroomBodyTests(unittest.TestCase):
    def test_only_projection_to_kenyon_connections(self):
        con = pd.DataFrame({"pre": [1, 1, 2, 3, 9], "post": [10, 11, 10, 10, 11], "weight": [5, 7, -3, 4, 8]})
        ann = pd.DataFrame({"root_id": [1, 2, 3, 9, 10, 11],
                            "cell_class": ["ALPN", "ALPN", "MBON", "Kenyon_Cell", "Kenyon_Cell", "Kenyon_Cell"]})
        e = fly.mushroom_body_edges(con, ann).sort_values(["pn", "kc"])
        self.assertEqual([tuple(r) for r in e.itertuples(index=False)], [(1, 10, 5.0), (1, 11, 7.0), (2, 10, -3.0)])

    def test_shuffle_keeps_each_neurons_connection_count_and_strengths(self):
        w = toy_wiring()
        s = fly.shuffled_wiring(w, 1)
        self.assertTrue(np.array_equal(np.diff(w.indptr), np.diff(s.indptr)))
        self.assertTrue(np.array_equal(w.data, s.data))
        self.assertFalse(np.array_equal(w.indices, s.indices))

    def test_exactly_the_active_share_is_on_and_fit_leaves_wiring_unchanged(self):
        w = toy_wiring()
        before = w.copy()
        x, y = toy_data()
        m = fly.MushroomBody(w, seed=1, C=0.1).fit(x, y)
        cells = m.active_cells(x).numpy()
        self.assertEqual(cells.shape, (len(x), 10))                       # 5% of 200 cells
        self.assertTrue(all(len(set(r)) == 10 for r in cells))
        self.assertEqual((w != before).nnz, 0)

    def test_same_seed_same_scores(self):
        x, y = toy_data()
        a = fly.MushroomBody(toy_wiring(), 1, 0.1).fit(x, y).predict_proba(x)
        b = fly.MushroomBody(toy_wiring(), 1, 0.1).fit(x, y).predict_proba(x)
        self.assertTrue(np.array_equal(a, b))

    def test_readout_matches_sklearn_logistic_regression(self):
        rng = np.random.default_rng(0)
        active = np.stack([rng.choice(50, 5, replace=False) for _ in range(400)])
        dense = np.zeros((400, 50))
        np.put_along_axis(dense, active, 1.0, axis=1)
        y = (dense[:, :10].sum(1) + rng.normal(size=400) > 1).astype(int)
        import torch
        ours = readout.ActiveCellReadout(50, 0.5).fit(torch.as_tensor(active), y).predict(torch.as_tensor(active))
        ref = LogisticRegression(C=0.5, max_iter=5000, tol=1e-10).fit(dense, y).predict_proba(dense)[:, 1]
        self.assertLess(np.abs(ours - ref).max(), 1e-3)


class WholeBrainTests(unittest.TestCase):
    def toy_graph(self, n=120, seed=0):
        rng = np.random.default_rng(seed)
        m = sp.random(n, n, density=0.05, random_state=seed, format="csr", dtype=np.float32)
        m.data = np.round(m.data * 20 - 6).astype(np.float32)               # some inhibitory connections
        return brain.Graph(m, np.arange(10), np.arange(n - 40, n))

    def test_pruned_layers_give_the_same_drive_as_all_neurons(self):
        g = self.toy_graph()
        act = np.maximum(np.random.default_rng(1).normal(size=(7, 10)), 0).astype(np.float32)
        m = brain.WholeBrain(g, seed=1, C=0.1, steps=3)
        ref = brain.whole_network_drive(g, act, 3, m.scales)               # the divisors the model itself uses
        import torch
        ours = m.drive(torch.as_tensor(act)).numpy()
        self.assertLess(np.abs(ours - ref).max() / (np.abs(ref).max() + 1e-9), 1e-4)

    def test_whole_brain_fits_and_scores(self):
        g = self.toy_graph()
        x, y = toy_data(n=300)
        p = brain.WholeBrain(g, seed=2, C=0.1, steps=3).fit(x, y).predict_proba(x)
        self.assertEqual(p.shape, (300, 2))
        self.assertTrue(np.all((p >= 0) & (p <= 1)))


if __name__ == "__main__":
    unittest.main()
