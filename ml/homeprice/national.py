"""National forecast built from metro forecasts.

The nation has no Redfin series, so the trend model predicts it with its weakest booster. Instead the
national change can be a weighted mean of the metro forecasts, which do use Redfin. Weights are metro
size proxies, chosen by how well they reproduce the actual national index from actual metro changes.
"""
import numpy as np
import pandas as pd

WEIGHTS = ("equal", "labor_force", "home_value")


def metro_weights(p: pd.DataFrame, scheme: str) -> pd.Series:
    """Weight per metro row. labor_force: 12-month LAUS labor force (a stand-in for housing stock).
    home_value: labor force times typical home value (a stand-in for housing wealth)."""
    if scheme == "equal":
        return pd.Series(1.0, index=p.index)
    lf = p.lf12
    return lf if scheme == "labor_force" else lf * np.exp(p.lvl)


def aggregate(p: pd.DataFrame, values: pd.Series | np.ndarray, scheme: str) -> pd.Series:
    """Weighted mean of `values` over metro rows, per origin. Rows without a weight are left out."""
    df = pd.DataFrame({"origin": p.origin.to_numpy(), "v": np.asarray(values),
                       "w": metro_weights(p, scheme).to_numpy()})
    df = df[(p.kind == "msa").to_numpy() & df.v.notna().to_numpy() & df.w.notna().to_numpy() & (df.w > 0)]
    return df.groupby("origin").apply(lambda g: np.average(g.v, weights=g.w), include_groups=False)


def with_national(p: pd.DataFrame, pred, method: str, weighting: str) -> np.ndarray:
    """Market predictions with the nation's rows replaced by the metro aggregate when method is
    "aggregate" (origins where no metro has a weight keep the nation's own prediction)."""
    out = pd.Series(np.asarray(pred, dtype=float), index=p.index)
    if method == "aggregate":
        nat = (p.kind == "country").to_numpy()
        agg = aggregate(p, out, weighting).reindex(p.origin[nat]).to_numpy()
        out[nat] = np.where(np.isnan(agg), out[nat].to_numpy(), agg)
    return out.to_numpy()
