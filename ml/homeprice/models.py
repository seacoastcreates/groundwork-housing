"""The two forecasting models and the baselines they have to beat.

Feature groups and LightGBM parameters come from config.json: groups are adopted by ml/ablation.py and
parameters by ml/tune.py. Either can be overridden per instance for experiments.
"""
import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from homeprice.features import HORIZON, RELATIVE_GROUPS, SPARSE_TREND, TREND_GROUPS, features

CONFIG = Path(__file__).with_name("config.json")
MAX_TRAIN_ROWS = 1_200_000
SPARSE_START_YEAR = 2013     # first year with lagged Redfin data for most metros
MIN_SPARSE_ROWS = 2_000      # below this the sparse booster isn't trained and the core one is used

DEFAULT_PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=63, min_child_samples=200,
                      subsample=0.8, subsample_freq=1, colsample_bytree=0.8)


def load_config() -> dict:
    return json.loads(CONFIG.read_text())


def _gbm(params: dict, seed: int = 0) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(**{**DEFAULT_PARAMS, **params}, random_state=seed, verbose=-1)


def _fit(df: pd.DataFrame, feats: list[str], target: str, params: dict,
         max_rows: int = MAX_TRAIN_ROWS) -> lgb.LGBMRegressor:
    df = df.dropna(subset=[target])
    if len(df) > max_rows:
        df = df.sample(max_rows, random_state=0)
    return _gbm(params).fit(df[feats], df[target])


def damped_momentum(p: pd.DataFrame, col: str = "r12", damp: float = 0.6) -> np.ndarray:
    return damp * p[col].to_numpy() * HORIZON / 12


@dataclass
class TrendModel:
    """Forecasts a market's change (metros and the nation).

    Some groups only exist for part of history or for some markets (Redfin from 2012, Zillow market
    activity from 2018, rent from 2015). One booster is trained for each combination of the sparse
    groups in use, on rows that have exactly that data or more, and each row is predicted by the most
    complete booster its data supports. So no booster learns "missing = old era", and a row missing one
    source still uses the others.
    """
    groups: list[str] | None = None
    params: dict | None = None
    max_rows: int = MAX_TRAIN_ROWS
    boosters: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        cfg = load_config()
        self.groups = self.groups if self.groups is not None else cfg["trend_groups"]
        self.params = self.params if self.params is not None else cfg.get("trend_params", {})
        self.sparse = [g for g in self.groups if g in SPARSE_TREND]
        dense = [g for g in self.groups if g not in SPARSE_TREND]
        # Largest subsets first, so prediction picks the most complete booster available.
        self.subsets = sorted((tuple(c) for n in range(len(self.sparse) + 1)
                               for c in combinations(self.sparse, n)), key=len, reverse=True)
        self.feats = {sub: features(TREND_GROUPS, dense + list(sub)) for sub in self.subsets}

    def _has(self, p: pd.DataFrame, sub: tuple) -> np.ndarray:
        mask = np.ones(len(p), dtype=bool)
        for g in sub:
            mask &= p[SPARSE_TREND[g]].notna().to_numpy()
        return mask

    def fit(self, p: pd.DataFrame) -> "TrendModel":
        self.boosters = {}
        for sub in self.subsets:
            rows = p
            if sub:
                rows = p[self._has(p, sub) & (p.origin.dt.year >= SPARSE_START_YEAR).to_numpy()]
                if rows.y.notna().sum() < MIN_SPARSE_ROWS:
                    continue
            self.boosters[sub] = _fit(rows, self.feats[sub], "y", self.params, self.max_rows)
        return self

    def predict(self, p: pd.DataFrame) -> np.ndarray:
        out = np.full(len(p), np.nan)
        todo = np.ones(len(p), dtype=bool)
        for sub in self.subsets:
            if sub not in self.boosters:
                continue
            use = todo & self._has(p, sub)
            if use.any():
                out[use] = self.boosters[sub].predict(p.loc[use, self.feats[sub]])
                todo &= ~use
        return out


@dataclass
class RelativeModel:
    """Forecasts a ZIP's change minus its parent market's change."""
    groups: list[str] | None = None
    params: dict | None = None
    max_rows: int = MAX_TRAIN_ROWS
    model: lgb.LGBMRegressor | None = field(default=None, repr=False)

    def __post_init__(self):
        cfg = load_config()
        self.groups = self.groups if self.groups is not None else cfg["relative_groups"]
        self.params = self.params if self.params is not None else cfg.get("relative_params", {})
        self.feats = features(RELATIVE_GROUPS, self.groups)

    def fit(self, p: pd.DataFrame) -> "RelativeModel":
        self.model = _fit(p, self.feats, "y_rel", self.params, self.max_rows)
        return self

    def predict(self, p: pd.DataFrame) -> np.ndarray:
        return self.model.predict(p[self.feats])
