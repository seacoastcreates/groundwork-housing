"""The two forecasting models and the baselines they have to beat."""
from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd

from homeprice.features import HORIZON, RELATIVE, TREND_CORE, TREND_HEAT

MAX_TRAIN_ROWS = 1_200_000
HEAT_START_YEAR = 2013   # first year with lagged Redfin data for most metros


def _gbm(seed: int = 0) -> lgb.LGBMRegressor:
    return lgb.LGBMRegressor(n_estimators=400, learning_rate=0.03, num_leaves=63, min_child_samples=200,
                             subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
                             random_state=seed, verbose=-1)


def _fit(df: pd.DataFrame, feats: list[str], target: str) -> lgb.LGBMRegressor:
    df = df.dropna(subset=[target])
    if len(df) > MAX_TRAIN_ROWS:
        df = df.sample(MAX_TRAIN_ROWS, random_state=0)
    return _gbm().fit(df[feats], df[target])


def damped_momentum(p: pd.DataFrame, col: str = "r12", damp: float = 0.6) -> np.ndarray:
    return damp * p[col].to_numpy() * HORIZON / 12


@dataclass
class TrendModel:
    """Forecasts a market's change (metros and the nation).

    Two boosters: one with Redfin market-heat features, trained only on rows that have them, and a
    core one for rows without (the nation, the few metros Redfin doesn't cover, and history before
    2013). Training the heat model only where heat exists avoids it learning "missing = old era".
    """
    use_heat: bool = True
    core: lgb.LGBMRegressor | None = field(default=None, repr=False)
    heat: lgb.LGBMRegressor | None = field(default=None, repr=False)

    def fit(self, p: pd.DataFrame) -> "TrendModel":
        self.core = _fit(p, TREND_CORE, "y")
        if self.use_heat:
            hp = p[p.months_of_supply.notna() & (p.origin.dt.year >= HEAT_START_YEAR)]
            self.heat = _fit(hp, TREND_HEAT, "y")
        return self

    def predict(self, p: pd.DataFrame) -> np.ndarray:
        out = self.core.predict(p[TREND_CORE])
        if self.use_heat:
            has = p.months_of_supply.notna().to_numpy()
            if has.any():
                out[has] = self.heat.predict(p.loc[has, TREND_HEAT])
        return out


@dataclass
class RelativeModel:
    """Forecasts a ZIP's change minus its parent market's change."""
    model: lgb.LGBMRegressor | None = field(default=None, repr=False)

    def fit(self, p: pd.DataFrame) -> "RelativeModel":
        self.model = _fit(p, RELATIVE, "y_rel")
        return self

    def predict(self, p: pd.DataFrame) -> np.ndarray:
        return self.model.predict(p[RELATIVE])
