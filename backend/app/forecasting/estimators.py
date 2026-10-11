"""Fixed, predeclared numerical families. Only locally generated artifacts are loaded."""

import base64
import hashlib
import io
import warnings
from functools import lru_cache
import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from sklearn.linear_model import ElasticNet, BayesianRidge, HuberRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.ensemble import (
    RandomForestRegressor,
    ExtraTreesRegressor,
    HistGradientBoostingRegressor,
)
from sklearn.multioutput import MultiOutputRegressor

FAMILIES = {
    "direct-ridge-log-return": "Ridge",
    "elastic-net": "Elastic Net",
    "bayesian-ridge": "Bayesian Ridge",
    "huber": "Huber",
    "knn": "K-nearest neighbours",
    "random-forest": "Random Forest",
    "extra-trees": "Extra Trees",
    "hist-gradient-boosting": "Histogram Gradient Boosting",
    "lightgbm": "LightGBM",
    "catboost": "CatBoost",
}
SEED = 20261011


def make(family):
    if family == "elastic-net":
        return MultiOutputRegressor(
            ElasticNet(alpha=0.001, l1_ratio=0.5, max_iter=5000)
        )
    if family == "bayesian-ridge":
        return MultiOutputRegressor(BayesianRidge())
    if family == "huber":
        return MultiOutputRegressor(HuberRegressor(alpha=0.01, max_iter=500))
    if family == "knn":
        return KNeighborsRegressor(n_neighbors=40, weights="distance", n_jobs=1)
    if family == "random-forest":
        return RandomForestRegressor(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=20,
            random_state=SEED,
            n_jobs=1,
        )
    if family == "extra-trees":
        return ExtraTreesRegressor(
            n_estimators=100,
            max_depth=6,
            min_samples_leaf=20,
            random_state=SEED,
            n_jobs=1,
        )
    if family == "hist-gradient-boosting":
        # No random validation split / early stopping in a chronological experiment.
        return MultiOutputRegressor(
            HistGradientBoostingRegressor(
                max_iter=120,
                max_leaf_nodes=15,
                min_samples_leaf=25,
                l2_regularization=1,
                learning_rate=0.05,
                early_stopping=False,
                random_state=SEED,
            )
        )
    if family == "lightgbm":
        from lightgbm import LGBMRegressor

        return MultiOutputRegressor(
            LGBMRegressor(
                n_estimators=120,
                num_leaves=15,
                min_child_samples=25,
                learning_rate=0.05,
                reg_lambda=1,
                random_state=SEED,
                n_jobs=1,
                verbosity=-1,
            )
        )
    if family == "catboost":
        from catboost import CatBoostRegressor

        return CatBoostRegressor(
            iterations=150,
            depth=5,
            learning_rate=0.05,
            loss_function="MultiRMSE",
            random_seed=SEED,
            thread_count=1,
            verbose=False,
            allow_writing_files=False,
        )
    raise ValueError("Unknown model family")


def fit(x, y, family):
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-10] = 1
    estimator = make(family)
    with threadpool_limits(limits=1):
        estimator.fit((x - mean) / scale, y)
    stream = io.BytesIO()
    joblib.dump(estimator, stream, compress=3)
    blob = stream.getvalue()
    return dict(
        mean=mean.tolist(),
        scale=scale.tolist(),
        family=family,
        estimator_blob=base64.b64encode(blob).decode(),
        estimator_sha256=hashlib.sha256(blob).hexdigest(),
        estimator_parameters={
            k: v
            for k, v in estimator.get_params(deep=False).items()
            if isinstance(v, (str, int, float, bool, type(None)))
        },
    )


@lru_cache(maxsize=32)
def loaded(blob, digest):
    decoded = base64.b64decode(blob, validate=True)
    if hashlib.sha256(decoded).hexdigest() != digest:
        raise ValueError("Numerical model artifact checksum differs")
    # No upload/import endpoint: artifacts originate from fitting in this process.
    return joblib.load(io.BytesIO(decoded))


def predict(parameters, x):
    z = (x - np.array(parameters["mean"])) / np.array(parameters["scale"])
    estimator = loaded(parameters["estimator_blob"], parameters["estimator_sha256"])
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="X does not have valid feature names",
            category=UserWarning,
        )
        return np.asarray(estimator.predict(z))
