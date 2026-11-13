"""The trained part of the fly models: a logistic regression over the cells that are on.

This is the only part of the fly models that learns. The fixed network (fly.py, brain.py) decides which Kenyon cells
are on for a company; this readout learns one weight per cell, so that cells that tend to be on before downgrades get
a positive weight. It is the same kind of model as the logit, only with 0/1 inputs ("cell on or off") instead of
financial ratios. The penalty (scikit-learn's C) keeps the weights small, which matters because there are thousands
of cells and few downgrades.

A row is a fixed number of active cells, given by their column numbers. The
score of a row is the sum of the weights of its active cells plus a constant,
passed through the logistic function. The fit minimises what scikit-learn's
`LogisticRegression(C=penalty)` minimises on the same rows written as a 0/1
matrix (tested on a small sample), but works on the list of active cells, so
that it fits on a graphics card with little memory.

The device is the graphics card when PyTorch finds one, the processor
otherwise; the environment variable TCF_DEVICE ("cpu" or "cuda") overrides it.
Sums on a graphics card may be added in a different order from run to run (our reading, not tested here), so two fits
there can
differ in the last digits; on the processor a fit repeats exactly.
"""

import os

import numpy as np
import torch


def device() -> torch.device:
    name = os.environ.get("TCF_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


class ActiveCellReadout:
    """Logistic regression with one weight per cell; `penalty` is scikit-learn's C (smaller is stronger)."""

    def __init__(self, cells: int, penalty: float, max_iter: int = 300):
        self.cells = cells
        self.penalty = penalty
        self.max_iter = max_iter

    def _logits(self, active: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.embedding_bag(active, self.weight[:, None], mode="sum")[:, 0] + self.constant

    def fit(self, active: torch.Tensor, outcome: np.ndarray) -> "ActiveCellReadout":
        """`active`: rows by active cells, whole numbers below `cells`, already on the device to fit on.

        L-BFGS is a standard way to minimise a smooth function step by step."""
        target = torch.tensor(np.asarray(outcome), dtype=torch.float32, device=active.device)
        self.weight = torch.zeros(self.cells, dtype=torch.float32, device=active.device, requires_grad=True)
        self.constant = torch.zeros(1, dtype=torch.float32, device=active.device, requires_grad=True)
        optimizer = torch.optim.LBFGS(
            [self.weight, self.constant], max_iter=self.max_iter, history_size=10,
            tolerance_grad=1e-7, tolerance_change=1e-10, line_search_fn="strong_wolfe",
        )
        rows = len(target)

        def loss() -> torch.Tensor:
            optimizer.zero_grad()
            fit = torch.nn.functional.binary_cross_entropy_with_logits(self._logits(active), target, reduction="sum")
            total = (fit + self.weight.square().sum() / (2 * self.penalty)) / rows  # the constant is not penalised
            total.backward()
            return total

        optimizer.step(loss)
        self.weight.requires_grad_(False)
        self.constant.requires_grad_(False)
        return self

    def predict(self, active: torch.Tensor) -> np.ndarray:
        with torch.no_grad():
            return torch.sigmoid(self._logits(active).double()).cpu().numpy()
