"""The fruit fly's learning centre (the mushroom body) as a fixed network with a trained readout.

What is a connectome? It is a complete wiring diagram of a brain: for every neuron (nerve cell), which other neurons
it connects to and how strongly. Researchers have
mapped the whole brain of one adult fruit fly this way (FlyWire, version 783). Shiu et al. 2024 turned the map into
signed connections: a positive number means the sending neuron excites the receiving one, a negative number means it
inhibits it.

The mushroom body is the part of the fly brain that learns to link smells with good or bad outcomes. Its wiring is
simple to describe: 319 input neurons (antennal-lobe projection neurons, cell class "ALPN" in the annotations of
Schlegel et al. 2024) connect to 4,887 Kenyon cells (the neurons that form the memory layer). Each Kenyon cell listens
to about 6 input neurons, and which ones looks random. Only the most excited 5% of Kenyon cells stay on for any one
input. This is called an expansion: few inputs are spread onto many cells, and the pattern of which cells are on is
sparse (few are on).

How a company goes through it:
1. The company's prepared inputs (the logit's design matrix, one number per ratio) drive the projection neurons.
   Each projection neuron listens to one input column, to its high side or its low side. `seed` draws which.
2. A Kenyon cell's drive is the sum of what its inputs send, weighted by the connection strengths.
3. Only the most driven 5% of Kenyon cells stay on. The rest are off.
4. A logistic regression reads which cells are on and gives the downgrade probability (readout.py).

Why the wiring is fixed and only the readout learns: the wiring comes from the animal, not from our data. We never
adjust it, so it cannot be tuned to fit the training years. The only thing fitted is one weight per Kenyon cell in
the logistic readout, as in an ordinary regression. This keeps the model small and honest: any skill must come from
the fixed expansion plus a simple readout.

Why the shuffled control matters: if real fly wiring helped, we could not tell whether the biology matters or whether
any wide, sparse, random expansion would do as well. So we also build shuffled wiring: each projection neuron keeps
its number of connections and their strengths, but the target cells are drawn at random (same seed). If the real
wiring beats shuffled wiring consistently, the biology carries information. On the lecture's real data it did not.

The two public files are downloaded once into the folder named by the environment variable TCF_FLY_DIR (default: the
folder .cache/tcf_credit/fly inside your home folder, outside the repository) and checked against a pinned hash (a
fingerprint of the file, so a changed or damaged file is refused). See model/FLY-DATA.md for sources and licences.
"""
import hashlib
import math
import os
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp
import torch

from tcf_credit import readout

FILES = {
    # Shiu et al. 2024: every connection of the whole brain (about 15 million), about 101 MB. MIT licence.
    # github.com/philshiu/Drosophila_brain_model
    "Connectivity_783.parquet": (
        "https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/main/Connectivity_783.parquet",
        "efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347"),
    # Schlegel et al. 2024: what each neuron is (cell class, type, ...), about 32 MB. The repository has no licence
    # file; see model/FLY-DATA.md. github.com/flyconnectome/flywire_annotations
    "Supplemental_file1_neuron_annotations.tsv": (
        "https://raw.githubusercontent.com/flyconnectome/flywire_annotations/main/supplemental_files/"
        "Supplemental_file1_neuron_annotations.tsv",
        "b214970b55d2fbe0853bba536fdcb9e28730f4eb7ab06f600491df795da683cd"),
}
INPUT_CLASS, CELL_CLASS = "ALPN", "Kenyon_Cell"   # the annotations' names for the two cell classes
ACTIVE_SHARE = 0.05                              # the fraction of Kenyon cells that stay on (sparse code)
BATCH_ROWS = 4096                                # companies processed at once, only to limit memory


def fly_dir() -> Path:
    return Path(os.environ.get("TCF_FLY_DIR", Path.home() / ".cache" / "tcf_credit" / "fly"))


def fetch(name: str, folder: Path | None = None, opener=urllib.request.urlopen) -> Path:
    """Path of a public file, downloaded on first use; an error if its hash is not the pinned one.

    The hash check means everyone who runs the code uses exactly the same wiring, and a half-finished or altered
    download is never used."""
    url, pinned = FILES[name]
    folder = fly_dir() if folder is None else folder
    path = folder / name
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        with opener(url) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != pinned:
            raise ValueError(f"{name}: the download does not have the pinned hash")
        path.write_bytes(content)
    if hashlib.sha256(path.read_bytes()).hexdigest() != pinned:
        raise ValueError(f"{path}: the file on disk does not have the pinned hash")
    return path


@lru_cache(maxsize=None)
def connectome():
    """(connections with columns pre, post, weight; neuron annotations with root_id, cell_class).

    `pre` and `post` are neuron identifiers (root_id). `weight` is the signed connection strength (Shiu et al.'s
    column 'Excitatory x Connectivity', a whole
    number), positive when the sending
    neuron excites and negative when it inhibits. Cached, because reading 15 million connections takes seconds."""
    con = pd.read_parquet(fetch("Connectivity_783.parquet"),
                          columns=["Presynaptic_ID", "Postsynaptic_ID", "Excitatory x Connectivity"])
    con.columns = ["pre", "post", "weight"]
    ann = pd.read_csv(fetch("Supplemental_file1_neuron_annotations.tsv"), sep="\t", usecols=["root_id", "cell_class"],
                      dtype={"root_id": "int64", "cell_class": "string"}).drop_duplicates("root_id")
    return con, ann


def mushroom_body_edges(con: pd.DataFrame, ann: pd.DataFrame) -> pd.DataFrame:
    """Connections from projection neurons onto Kenyon cells: pn, kc, signed connection-strength weight.

    The annotation file says which neuron is which; the connection table alone only has identifiers."""
    pns = set(ann.root_id[ann.cell_class == INPUT_CLASS])
    kcs = set(ann.root_id[ann.cell_class == CELL_CLASS])
    e = con[con.pre.isin(pns) & con.post.isin(kcs)]
    return pd.DataFrame({"pn": e.pre.to_numpy(), "kc": e.post.to_numpy(), "weight": e.weight.to_numpy(dtype=float)})


def wiring_matrix(edges: pd.DataFrame) -> sp.csr_matrix:
    """Input neurons in rows, Kenyon cells in columns; only neurons with such a connection get a row or column."""
    _, row = np.unique(edges.pn.to_numpy(), return_inverse=True)
    _, col = np.unique(edges.kc.to_numpy(), return_inverse=True)
    return sp.csr_matrix((edges.weight.to_numpy(np.float32), (row, col)), shape=(row.max() + 1, col.max() + 1))


def shuffled_wiring(wiring: sp.csr_matrix, seed: int) -> sp.csr_matrix:
    """The control wiring. Each input neuron keeps its number of connections and their strengths; only the
    Kenyon cells it connects to are drawn at random (without repeats, so no neuron connects twice to one cell).

    What stays is each input neuron's number of connections and their strengths; who it connects to is destroyed, and
    with it the number of inputs each Kenyon cell receives. A difference in results between
    real and shuffled wiring that holds across seeds would therefore point to the pattern of the fly's wiring,
    including how
    the inputs are spread over the Kenyon cells (one model's AUC moved by 0.025 to 0.036 across seeds alone)."""
    rng = np.random.default_rng(seed)
    indices = np.empty_like(wiring.indices)
    for r in range(wiring.shape[0]):
        a, b = wiring.indptr[r], wiring.indptr[r + 1]
        indices[a:b] = np.sort(rng.choice(wiring.shape[1], b - a, replace=False))
    return sp.csr_matrix((wiring.data.copy(), indices, wiring.indptr.copy()), shape=wiring.shape)


@lru_cache(maxsize=None)
def wiring_for(kind: str, seed: int) -> sp.csr_matrix:
    real = wiring_matrix(mushroom_body_edges(*connectome()))
    return real if kind == "real" else shuffled_wiring(real, seed)


class MushroomBody:
    """fit(X, y) / predict_proba(X) on the logit's design matrix. `wiring` is "real", "shuffled" or a matrix.

    Same method names as scikit-learn models, so it can be compared with the logit on the same rows. `C` is the
    readout's penalty (smaller means weights are held closer to zero); `seed` draws the input assignment and the
    shuffle."""

    def __init__(self, wiring, seed: int, C: float, active_share: float = ACTIVE_SHARE):
        self.wiring = wiring_for(wiring, seed) if isinstance(wiring, str) else wiring
        self.seed, self.C = seed, C
        self.device = readout.device()
        self.dense = torch.as_tensor(np.asarray(self.wiring.todense(), dtype=np.float32), device=self.device)
        self.active = math.ceil(active_share * self.wiring.shape[1] - 1e-9)

    def assign_inputs(self, width: int) -> None:
        """Every input neuron gets one design column and a side; every column is used when there are enough neurons.

        The side says whether the neuron fires for a high or for a low value of its column. A projection neuron cannot
        fire below zero, so one column needs both a "high" and a "low" neuron to be seen from both directions. This is
        part of the fixed network: drawn from the seed alone, never from the outcomes."""
        rng = np.random.default_rng(self.seed)
        n = self.wiring.shape[0]
        self.input_column = np.empty(n, dtype=np.int64)
        self.input_column[rng.permutation(n)] = np.arange(n) % width
        self.input_sign = rng.choice(np.array([-1.0, 1.0], dtype=np.float32), n)

    def drive(self, activity: torch.Tensor) -> torch.Tensor:
        """Rows by input neurons -> rows by Kenyon cells: each cell adds up what its inputs send."""
        return activity @ self.dense

    def active_cells(self, x: np.ndarray) -> torch.Tensor:
        """Rows by the number of cells that stay on: the indices of those Kenyon cells.

        Keeping only the strongest 5% (instead of a fixed threshold) means every company turns on the same number of
        cells, whatever the scale of its inputs."""
        column = torch.as_tensor(self.input_column, device=self.device)
        sign = torch.as_tensor(self.input_sign, device=self.device)
        parts = []
        batch = getattr(self, "batch_rows", BATCH_ROWS)
        for a in range(0, x.shape[0], batch):
            part = torch.as_tensor(x[a:a + batch], dtype=torch.float32, device=self.device)
            d = self.drive(torch.clamp(part[:, column] * sign, min=0.0))
            parts.append(torch.topk(d, self.active, dim=1).indices.to(torch.int32))
        return torch.cat(parts)

    def fit(self, x, y):
        # Only the readout is trained; the wiring and the input assignment are fixed before the outcomes are seen.
        self.assign_inputs(x.shape[1])
        self.readout = readout.ActiveCellReadout(self.n_cells, self.C).fit(self.active_cells(x), np.asarray(y))
        return self

    @property
    def n_cells(self) -> int:
        return self.wiring.shape[1]

    def predict_proba(self, x):
        p = self.readout.predict(self.active_cells(x))
        return np.column_stack([1 - p, p])
