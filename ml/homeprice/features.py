"""Point-in-time feature panels.

A row is (region, origin month). Every feature uses data through the origin month only, except Redfin,
which is read REDFIN_LAG months back because its public file trails Zillow's by about that much.
The target is the log change in home value over the next HORIZON months.

The ZIP forecast is split in two:
  trend     = the parent metro's change (or the nation's, for ZIPs outside any metro)
  relative  = the ZIP's change minus its parent's
so one model forecasts where each market is heading and a second ranks ZIPs within it.
"""
import numpy as np
import pandas as pd

from homeprice.data import Series

HORIZON = 12
REDFIN_LAG = 3
LAGS = (1, 3, 6, 12, 24, 36, 60)

OWN = [f"r{k}" for k in LAGS] + ["accel"]
MACRO = ["nat_r3", "nat_r12", "rate", "rate_chg12"]
HEAT = ["months_of_supply", "median_dom", "sale_to_list", "price_drops",
        "months_of_supply_yoy", "median_dom_yoy", "sale_to_list_yoy"]
PARENT = ["parent_r3", "parent_r12", "rel_r3", "rel_r12", "rel_r36", "rel_level"]

TREND_CORE = OWN + MACRO
TREND_HEAT = OWN + MACRO + HEAT
RELATIVE = OWN + PARENT + ["nat_r12", "rate_chg12"]


def _changes(logs: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {f"r{k}": logs - logs.shift(k, axis=1) for k in LAGS}
    out["accel"] = out["r3"] - out["r3"].shift(3, axis=1)
    return out


def _stack(frames: dict[str, pd.DataFrame], origins) -> pd.DataFrame:
    cols = [f[origins].stack(future_stack=True).rename(name) for name, f in frames.items()]
    p = pd.concat(cols, axis=1).reset_index(names=["row", "origin"])
    p["origin"] = p.origin.astype("period[M]")
    return p


def training_origins(logs: pd.DataFrame, start_year: int = 2005) -> list:
    """Quarterly origins; later months are added for the live forecast by the caller."""
    return [c for c in logs.columns if c.month in (1, 4, 7, 10) and c.year >= start_year]


def macro_frame(nation: Series, rate: pd.Series) -> pd.DataFrame:
    nat = nation.logs.iloc[0]
    m = pd.DataFrame({"nat_r3": nat - nat.shift(3), "nat_r12": nat - nat.shift(12)})
    m["rate"] = rate.reindex(m.index)
    m["rate_chg12"] = m.rate - rate.shift(12).reindex(m.index)
    return m


def heat_frame(redfin: pd.DataFrame) -> pd.DataFrame:
    """Redfin metrics plus year-over-year changes, re-keyed to the origin they are usable at."""
    h = redfin.copy()
    base = ["months_of_supply", "median_dom", "sale_to_list"]
    yoy = h[base].groupby(level="metro").diff(12).add_suffix("_yoy")
    h = h.join(yoy).reset_index()
    h["month"] = h.month + REDFIN_LAG
    return h.set_index(["metro", "month"])


def market_panel(s: Series, origins, macro: pd.DataFrame, heat: pd.DataFrame | None) -> pd.DataFrame:
    """Metros and the nation: own history, macro, and (for metros) Redfin heat."""
    frames = _changes(s.logs)
    frames["y"] = s.logs.shift(-HORIZON, axis=1) - s.logs
    p = _stack(frames, origins)
    p["region_id"] = s.meta.RegionID.values[p.row]
    p["kind"] = s.meta.RegionType.values[p.row]
    p = p.join(macro, on="origin")
    if heat is not None:
        p["metro"] = s.meta.RegionName.values[p.row]
        p = p.join(heat, on=["metro", "origin"]).drop(columns="metro")
    for c in HEAT:
        if c not in p:
            p[c] = np.nan
    return p.dropna(subset=["r12"])


def _short_metro(name: str) -> str:
    """'Houston-The Woodlands-Sugar Land, TX' -> 'Houston, TX' (the ZIP file uses full CBSA names,
    the metro file short ones)."""
    city, _, states = name.rpartition(", ")
    return f"{city.split('-')[0].split('/')[0]}, {states.split('-')[0]}"


def parent_ids(zips: Series, markets: Series) -> np.ndarray:
    """Each ZIP's parent region: its metro when Zillow tracks it, else the nation."""
    by_name = dict(zip(markets.meta.RegionName, markets.meta.RegionID))
    nation_id = markets.meta.RegionID[markets.meta.RegionType == "country"].iloc[0]
    return np.array([by_name.get(m, by_name.get(_short_metro(m), nation_id))
                     for m in zips.meta.Metro.fillna("")])


def zip_panel(zips: Series, markets: Series, origins, macro: pd.DataFrame) -> pd.DataFrame:
    parents = parent_ids(zips, markets)
    mlogs = markets.logs.set_index(markets.meta.RegionID).reindex(parents).set_axis(zips.logs.index)
    own, par = _changes(zips.logs), _changes(mlogs)
    frames = dict(own)
    frames.update(parent_r3=par["r3"], parent_r12=par["r12"],
                  rel_r3=own["r3"] - par["r3"], rel_r12=own["r12"] - par["r12"],
                  rel_r36=own["r36"] - par["r36"], rel_level=zips.logs - mlogs)
    future = lambda L: L.shift(-HORIZON, axis=1) - L
    frames["y"] = future(zips.logs)
    frames["y_parent"] = future(mlogs)
    p = _stack(frames, origins)
    p["y_rel"] = p.y - p.y_parent
    p["region_id"] = zips.meta.RegionID.values[p.row]
    p["parent_id"] = parents[p.row]
    p = p.join(macro, on="origin")
    return p.dropna(subset=["r12", "parent_r12"])
