"""Further models for evaluate.py --zoo, each with a small candidate grid chosen on the validation years.

Goes in: the list of inputs that evaluate.py uses. Comes out: model recipes (name -> how to build it, which inputs,
which settings to try). Data: none; evaluate.py calls this module only when --zoo is given.

- boosting_mono: the gradient boosting of evaluate.py with direction rules: predicted risk may only rise with inputs
  in RISK_RISES_WITH and only fall with inputs in RISK_FALLS_WITH (a restriction from credit economics).
- xgboost: XGBoost trees; missing values stay missing.
- random_forest: averaged deep trees on the imputed inputs.
- neural_net: a small fully connected network (scikit-learn MLP) on the simple model's prepared inputs.
- fly_mb_*, fly_brain_*: the fruit fly networks of fly.py and brain.py, real wiring and shuffled wiring, three input
  assignments each.
Their settings are chosen only on validation years before the first test year, like the others.
"""
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.neural_network import MLPClassifier

RISK_RISES_WITH = ["debt_assets", "notch", "outlook_neg", "watch_neg", "dg_prev_year", "vol_12m"]
RISK_FALLS_WITH = ["ebit_assets", "wc_assets", "ebit_interest", "cfo_debt", "re_assets", "cash_assets", "op_margin",
                   "ig", "outlook_pos", "watch_pos", "up_prev_year", "dividend_payer", "float_debt", "ret_12m",
                   "ret_6m", "mcap_debt", "dd_naive"]
DIRECTION = {c: 1 for c in RISK_RISES_WITH} | {c: -1 for c in RISK_FALLS_WITH}

MONO_GRID = [dict(max_depth=3, learning_rate=0.05, min_samples_leaf=50, l2_regularization=1.0),
             dict(max_depth=2, learning_rate=0.05, min_samples_leaf=100, l2_regularization=1.0),
             dict(max_leaf_nodes=15, learning_rate=0.03, min_samples_leaf=100, l2_regularization=5.0)]
XGB_GRID = [dict(max_depth=2, min_child_weight=10, reg_lambda=10.0, n_estimators=300),
            dict(max_depth=3, min_child_weight=10, reg_lambda=10.0, n_estimators=200),
            dict(max_depth=4, min_child_weight=20, reg_lambda=5.0, n_estimators=150)]
XGB_FIXED = dict(learning_rate=0.05, subsample=0.7, colsample_bytree=0.7, tree_method="hist", random_state=0, n_jobs=2)
RF_GRID = [dict(min_samples_leaf=20), dict(min_samples_leaf=50), dict(min_samples_leaf=100)]
RF_FIXED = dict(n_estimators=500, max_features="sqrt", random_state=0, n_jobs=2)
NN_GRID = [dict(hidden_layer_sizes=(32,), alpha=1e-4), dict(hidden_layer_sizes=(64, 32), alpha=1e-4),
           dict(hidden_layer_sizes=(64, 32), alpha=1e-2)]
NN_FIXED = dict(early_stopping=True, validation_fraction=0.15, n_iter_no_change=20, max_iter=500, random_state=0)
FLY_GRID = [dict(C=1e-4), dict(C=1e-3), dict(C=1e-2), dict(C=1e-1)]
FLY_SEEDS = (1, 2, 3)


def mono_hgb(p, cols):
    """Gradient boosting that may only raise risk with the inputs in RISK_RISES_WITH and lower it with RISK_FALLS_WITH.
    Columns are laid out as Prep.transform(impute=False) does: the numeric inputs, then sector indicators (no rule)."""
    def make(n_sectors):
        """Build the boosting model with a direction rule (may only raise risk, may only lower risk, or none) for each
        input column and none for the sector columns."""
        return HistGradientBoostingClassifier(early_stopping=True, validation_fraction=0.15, n_iter_no_change=20,
                                              max_iter=500, random_state=0,
                                              monotonic_cst=[DIRECTION.get(c, 0) for c in cols] + [0] * n_sectors, **p)
    return _Deferred(make, len(cols))


class _Deferred:
    """Builds the estimator at fit time, when the number of sector columns is known from the matrix width."""

    def __init__(self, make, n_numeric):
        """`make(n_sectors)` builds the model; `n_numeric` is the number of input columns before the sector columns."""
        self.make, self.n_numeric = make, n_numeric

    def fit(self, x, y):
        """Count the sector columns from the width of `x`, build the model and fit it. Returns self."""
        self.model = self.make(x.shape[1] - self.n_numeric).fit(x, y)
        return self

    def predict_proba(self, x):
        """The fitted model's class probabilities for `x`."""
        return self.model.predict_proba(x)


def xgb(p, cols):
    """An XGBoost classifier with the settings p (missing values are handled by the trees themselves)."""
    from xgboost import XGBClassifier
    return XGBClassifier(**XGB_FIXED, **p)


def specs(feats):
    """All extra model recipes in the same format as evaluate.specs()."""
    s = {
        "boosting_mono": dict(grid=MONO_GRID, make=mono_hgb, cols=feats, impute=False, sectors=True),
        "xgboost": dict(grid=XGB_GRID, make=xgb, cols=feats, impute=False, sectors=True),
        "random_forest": dict(grid=RF_GRID, make=lambda p, c: RandomForestClassifier(**RF_FIXED, **p),
                              cols=feats, impute=True, sectors=True),
        "neural_net": dict(grid=NN_GRID, make=lambda p, c: MLPClassifier(**NN_FIXED, **p),
                           cols=feats, impute=True, sectors=True),
    }
    from tcf_credit import brain, fly
    for seed in FLY_SEEDS:
        for wiring in ("real", "shuffled"):
            s[f"fly_mb_{wiring}_s{seed}"] = dict(
                grid=FLY_GRID, make=lambda p, c, seed=seed, wiring=wiring: fly.MushroomBody(wiring, seed, p["C"]),
                cols=feats, impute=True, sectors=True)
            s[f"fly_brain_{wiring}_s{seed}"] = dict(
                grid=FLY_GRID, make=lambda p, c, seed=seed, wiring=wiring: brain.WholeBrain(wiring, seed, p["C"]),
                cols=feats, impute=True, sectors=True)
    return s
