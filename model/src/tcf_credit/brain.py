"""The fruit fly's whole brain as a fixed network with a trained readout.

Role:     a model for `evaluate.py --zoo` (see zoo.py), not a numbered pipeline step.
Goes in:  as for fly.py: the logit's prepared inputs and the 0/1 label.
Comes out: the probability of a downgrade for each row.
Data:     the same two public connectome files as fly.py (see model/FLY-DATA.md).

fly.py uses only the mushroom body: inputs go straight onto the Kenyon cells. Here the inputs first travel through
the rest of the brain, as a smell does in the animal: about 139,000 neurons and 15 million connections. The idea is
the same: the wiring is fixed (a connectome is a wiring diagram, and ours is never adjusted to the data), and only
the logistic readout on the Kenyon cells is trained. The question is whether passing the signal through the real
brain gives the readout something better than the direct mushroom-body connections do.

The wiring is every connection of the FlyWire connectome version 783 as signed by Shiu et al. 2024; it is never
changed. A company's prepared inputs drive the same projection neurons as in fly.py, with the same assignment per seed.
Activity then spreads along the connections for STEPS steps: a neuron adds what its exciting inputs send, subtracts
what its inhibiting inputs send, and cannot go below zero; the input neurons keep their input throughout. After the
last step the most driven 5% of Kenyon cells stay on and the logistic readout of readout.py reads them.

Fixed before any outcome is seen:
- After every step the activity of all non-input neurons is divided by one number per step, so that in total it stays
  as large as the input activity; the numbers come from random inputs (`calibrate`).
- A neuron on no path of STEPS steps from the inputs to the Kenyon cells cannot change the result and is left out
  (`layer_sets`); the result equals the computation with all neurons (tested).
The control is shuffled wiring: every neuron keeps its outgoing connections and strengths, each target is drawn at
random among all neurons (seeded). It tells us whether the real pattern of connections matters or only the number and
strength of connections does.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import scipy.sparse as sp
import torch

from tcf_credit import fly, readout

STEPS = 3
CALIBRATION_ROWS, CALIBRATION_SEED = 512, 20261111


@dataclass(frozen=True, eq=False)
class Graph:
    """The network. wiring: sending neurons in rows, receiving neurons in columns, signed connection strengths.
    inputs: the rows of the neurons that receive the company's numbers. cells: the rows of the Kenyon cells."""
    wiring: sp.csr_matrix
    inputs: np.ndarray
    cells: np.ndarray


@lru_cache(maxsize=None)
def real_graph() -> Graph:
    """The real wiring of all neurons as a sparse matrix, with the input neurons (the projection neurons that connect
    onto a Kenyon cell, as in fly.py) and the Kenyon cells. Built once from the downloaded files."""
    con, ann = fly.connectome()
    pre, post = con.pre.to_numpy(), con.post.to_numpy()
    ids = np.unique(np.concatenate([pre, post]))
    w = sp.csr_matrix((con.weight.to_numpy(np.float32), (np.searchsorted(ids, pre), np.searchsorted(ids, post))),
                      shape=(len(ids), len(ids)))
    edges = fly.mushroom_body_edges(con, ann)
    kenyon = ann.root_id[ann.cell_class == fly.CELL_CLASS].unique()
    cells = np.searchsorted(ids, np.sort(kenyon[np.isin(kenyon, ids)]))
    return Graph(w, np.searchsorted(ids, np.unique(edges.pn.to_numpy())), cells)


@lru_cache(maxsize=None)
def shuffled_graph(seed: int) -> Graph:
    """The control wiring: every neuron keeps its outgoing connections and their strengths, but each target neuron is
    drawn at random among all neurons (seeded). The input neurons and the Kenyon cells stay the same."""
    g = real_graph()
    rng = np.random.default_rng(seed)
    source = np.repeat(np.arange(g.wiring.shape[0]), np.diff(g.wiring.indptr))
    target = rng.integers(0, g.wiring.shape[1], g.wiring.nnz)
    return Graph(sp.csr_matrix((g.wiring.data.copy(), (source, target)), shape=g.wiring.shape), g.inputs, g.cells)


def _mask(size, members):
    """A True/False array of length `size` that is True at the positions in `members`."""
    m = np.zeros(size, dtype=bool)
    m[members] = True
    return m


@lru_cache(maxsize=None)
def layer_sets(graph: Graph, steps: int) -> tuple:
    """Per step 0..steps: neurons whose activity at that step can reach the result (inputs first, Kenyon cells last).

    This is only a speed-up: neurons that cannot influence a Kenyon cell within `steps` steps are skipped."""
    connected = (graph.wiring != 0).astype(np.int32).tocsr()
    size = connected.shape[0]
    inputs = _mask(size, graph.inputs)
    reached = [inputs]
    for _ in range(steps - 1):
        reached.append((np.asarray(connected.T @ reached[-1].astype(np.int32)).ravel() > 0) | inputs)
    reaching = [_mask(size, graph.cells)]
    for _ in range(steps - 1):
        reaching.append(np.asarray(connected @ reaching[-1].astype(np.int32)).ravel() > 0)
    middle = [np.flatnonzero(reached[s] & reaching[steps - s]) for s in range(1, steps)]
    return (graph.inputs, *middle, graph.cells)


@lru_cache(maxsize=None)
def layers(graph: Graph, steps: int) -> tuple:
    """Per step: connections from one step's neurons onto the next step's, receiving neurons in rows (sparse: most
    pairs of neurons are not connected, so only the existing connections are stored)."""
    sets = layer_sets(graph, steps)
    return tuple(graph.wiring[a][:, b].T.tocsr() for a, b in zip(sets[:-1], sets[1:]))


def _relay_steps(graph, activity, steps, scales):
    """The slow, simple version that follows every neuron, step by step; used to calibrate and to test the fast one.
    Yields (divisor, relay total after division, state). Without scales, each step is divided so that the relay
    neurons carry in total what the input neurons carry (otherwise activity would grow or die out at every step)."""
    received = graph.wiring.T.tocsr().astype(np.float64)
    carried = float(activity.sum())
    state = np.zeros((graph.wiring.shape[0], activity.shape[0]))
    state[graph.inputs] = activity.T
    for step in range(steps - 1):
        relay = np.maximum(received @ state, 0.0)
        relay[graph.inputs] = 0.0
        total = float(relay.sum())
        scale = scales[step] if scales is not None else (total / carried if total > 0 and carried > 0 else 1.0)
        state = relay / scale
        state[graph.inputs] = activity.T
        yield scale, total / scale, state
    yield None, None, received @ state


@lru_cache(maxsize=None)
def calibrate(graph: Graph, steps: int, rows: int = CALIBRATION_ROWS, seed: int = CALIBRATION_SEED) -> tuple:
    """The per-step divisors, found on made-up random inputs, never on company data."""
    act = np.maximum(np.random.default_rng(seed).normal(0.0, 1.0, (rows, len(graph.inputs))), 0.0).astype(np.float32)
    return tuple(s for s, _, _ in _relay_steps(graph, act, steps, None) if s is not None)


def whole_network_drive(graph, activity, steps, scales) -> np.ndarray:
    """Rows by Kenyon cells, computed with every neuron: the slow reference for the tests."""
    *_, (_, _, drive) = _relay_steps(graph, activity, steps, scales)
    return drive[graph.cells].T


@lru_cache(maxsize=None)
def _device_layers(graph: Graph, steps: int, device: str) -> tuple:
    """The sparse layers of `layers()` as torch tensors on `device`. Each layer also carries the positions of the
    input neurons that are held at the company's values at that step."""
    sets = layer_sets(graph, steps)
    out = []
    for matrix, receiving in zip(layers(graph, steps), sets[1:]):
        c = matrix.tocoo()
        t = torch.sparse_coo_tensor(np.vstack([c.row, c.col]), c.data.astype(np.float32), size=matrix.shape,
                                    device=device).coalesce()
        present = np.flatnonzero(np.isin(graph.inputs, receiving))
        position = np.searchsorted(receiving, graph.inputs[present])
        out.append((t, torch.as_tensor(present, device=device), torch.as_tensor(position, device=device)))
    return tuple(out)


class WholeBrain(fly.MushroomBody):
    """fit(X, y) / predict_proba(X). `graph` is "real", "shuffled" (seeded) or a Graph.

    It reuses MushroomBody's input assignment, top-5% rule and fit; only how the Kenyon cells are driven differs."""

    def __init__(self, graph, seed: int, C: float, steps: int = STEPS, active_share: float = fly.ACTIVE_SHARE,
                 batch_rows: int = 2048):
        """Choose the wiring ("real", "shuffled" with this seed, or a Graph), find the per-step divisors with
        `calibrate`, and set the layers up on the device. `active` is the number of Kenyon cells kept on
        (`active_share` of them, rounded up)."""
        self.graph = real_graph() if graph == "real" else shuffled_graph(seed) if graph == "shuffled" else graph
        self.steps, self.seed, self.C = steps, seed, C
        self.scales = calibrate(self.graph, steps)
        self.device = readout.device()
        self.layers = _device_layers(self.graph, steps, str(self.device))
        self.wiring = self.graph.wiring[self.graph.inputs][:, self.graph.cells]   # read for its shape only
        self.active = int(np.ceil(active_share * len(self.graph.cells) - 1e-9))
        self.batch_rows = batch_rows

    def drive(self, activity: torch.Tensor) -> torch.Tensor:
        """Let the activity spread for `steps` steps. A neuron cannot go below zero (as a nerve cell cannot fire
        negatively), and the inputs are held at the company's values so they keep pushing signal in."""
        inputs = activity.T.contiguous()
        state = inputs
        for (matrix, present, position), scale in zip(self.layers[:-1], self.scales):
            state = torch.clamp(torch.sparse.mm(matrix, state), min=0.0) / scale
            state[position] = inputs[present]
        return torch.sparse.mm(self.layers[-1][0], state).T
