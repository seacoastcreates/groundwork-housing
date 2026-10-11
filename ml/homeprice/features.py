"""Point-in-time feature panels.

A row is (region, origin month). Every feature uses data through the origin month only, except series
whose public files trail Zillow's home values: Redfin (REDFIN_LAG months) and Zillow's sale-to-list
ratio (1 month). Those are read that many months back in the backtest and in the live forecast alike.
The target is the log change in home value over the next HORIZON months.

The ZIP forecast is split in two:
  trend     = the parent metro's change (or the nation's, for ZIPs outside any metro)
  relative  = the ZIP's change minus its parent's
so one model forecasts where each market is heading and a second ranks ZIPs within it.

Features come in named groups (TREND_GROUPS, RELATIVE_GROUPS). Which groups each model uses is set in
config.json, from the ablation in ml/ablation.py.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from homeprice.data import Series

HORIZON = 12
REDFIN_LAG = 3
LAGS = (1, 3, 6, 12, 24, 36, 60)
ZHEAT_LAG = {"z_sale_to_list": 1}
LABOR_LAG = 1          # LAUS county data for a month is out about a month after Zillow's
MACRO_LAG = 1          # monthly FRED series; the daily ones (DGS10, T10Y2Y) are complete by month end

OWN = [f"r{k}" for k in LAGS] + ["accel"]
MACRO = ["nat_r3", "nat_r12", "rate", "rate_chg12"]
HEAT = ["months_of_supply", "median_dom", "sale_to_list", "price_drops",
        "months_of_supply_yoy", "median_dom_yoy", "sale_to_list_yoy"]
PARENT = ["parent_r3", "parent_r12", "rel_r3", "rel_r12", "rel_r36", "rel_level"]
SHAPE = ["vol12", "vol36", "dd60", "trend_dev"]
UNEMP = ["ur12", "ur_yoy", "ur_yoy_chg3", "emp_yoy"]
# Re-test variants for the pandemic distortion. Clip bounds are the 1st/99th percentiles of 2005-2019
# metro (and ZIP-vs-metro) values, so they use no pandemic-era data. The mask treats readings from the
# pandemic shock as missing; choosing that window uses hindsight and is disclosed as such.
UNEMP_CLIP = {"ur_yoy": (-0.027, 0.049), "ur_yoy_chg3": (-0.021, 0.017), "emp_yoy": (-0.106, 0.087),
              "cty_ur_yoy_rel": (-0.013, 0.013), "cty_emp_yoy_rel": (-0.073, 0.050)}
PANDEMIC = (pd.Period("2020-04", "M"), pd.Period("2021-09", "M"))
MACRO_X = ["m_unrate", "m_unrate_chg12", "m_payroll_yoy", "m_cpi_yoy", "m_real10", "m_curve", "m_mort_spread",
           "m_starts_yoy", "m_permits_yoy", "m_new_supply", "m_sentiment", "m_sentiment_chg12"]
ZHEAT = ["z_inventory_yoy", "z_new_listings_yoy", "z_new_pending_yoy", "z_days_pending",
         "z_days_pending_yoy", "z_price_cut", "z_price_cut_yoy", "z_sale_to_list", "z_sale_to_list_yoy"]

TREND_GROUPS = {
    "base": OWN + MACRO,
    "heat": HEAT,                                   # Redfin, 3 months lagged
    "shape": SHAPE,
    "afford": ["pay_chg12", "level_vs_nat"],
    "rent": ["ptr", "rent_r12", "ptr_chg12"],
    "zheat": ZHEAT,                                 # Zillow market activity, current
    "unemp": UNEMP,                                 # metro unemployment and job growth (BLS LAUS)
    "unemp_clip": ["ur12", "ur_yoy_c", "ur_yoy_chg3_c", "emp_yoy_c"],
    "unemp_mask": ["ur12", "ur_yoy_m", "ur_yoy_chg3_m", "emp_yoy_m"],
    "macro": MACRO_X,                               # national macro (FRED)
}
RELATIVE_GROUPS = {
    "base": OWN + PARENT + ["nat_r12", "rate_chg12"],
    "shape": SHAPE + ["rel_vol36", "rel_dd60"],
    "afford": ["level_vs_nat"],
    "tiers": ["tier_spread", "tier_spread_chg12", "bot_rel_r12", "top_rel_r12"],
    "rent": ["ptr", "rel_ptr", "rel_rent_r12"],
    "unemp": ["cty_ur_rel", "cty_ur_yoy_rel", "cty_emp_yoy_rel"],
    "unemp_clip": ["cty_ur_rel", "cty_ur_yoy_rel_c", "cty_emp_yoy_rel_c"],
    "unemp_mask": ["cty_ur_rel", "cty_ur_yoy_rel_m", "cty_emp_yoy_rel_m"],
    "macro": MACRO_X,
}
# Groups whose data only exists for part of history or part of the regions, with the column that marks
# availability. The trend model trains a booster per combination of them (see models.TrendModel).
SPARSE_TREND = {"heat": "months_of_supply", "zheat": "z_inventory_yoy", "rent": "ptr"}


def features(groups: dict[str, list[str]], names) -> list[str]:
    out = []
    for g in names:
        out += [c for c in groups[g] if c not in out]
    return out


@dataclass
class Extras:
    """Optional series for the feature groups; any can be None."""
    tier_bottom: pd.DataFrame | None = None     # ZIP wide frames indexed by RegionID, raw values
    tier_top: pd.DataFrame | None = None
    rent_zip: pd.DataFrame | None = None
    rent_metro: pd.DataFrame | None = None
    zheat: dict[str, pd.DataFrame] | None = None
    labor: tuple | None = None                  # (market unemployed, market labor force, ZIP ..., ZIP ...)


# ---------- building blocks: wide frames (region x month) ----------

def _T(f, fn):
    """Apply a rolling op along months (pandas 3 dropped axis=1 rolling)."""
    return fn(f.T).T


def _changes(logs: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {f"r{k}": logs - logs.shift(k, axis=1) for k in LAGS}
    out["accel"] = out["r3"] - out["r3"].shift(3, axis=1)
    return out


def _shape(logs: pd.DataFrame, ch: dict) -> dict[str, pd.DataFrame]:
    m1 = logs.diff(axis=1)
    return {"vol12": _T(m1, lambda d: d.rolling(12, min_periods=9).std()),
            "vol36": _T(m1, lambda d: d.rolling(36, min_periods=24).std()),
            "dd60": logs - _T(logs, lambda d: d.rolling(60, min_periods=24).max()),
            "trend_dev": ch["r12"] - ch["r60"] / 5}


def _align(wide: pd.DataFrame | None, ids, columns) -> pd.DataFrame:
    """Reindex a RegionID-keyed wide frame to the given row ids and month columns."""
    if wide is None:
        return pd.DataFrame(np.nan, index=range(len(ids)), columns=columns)
    return wide.reindex(index=ids, columns=columns).reset_index(drop=True)


def _rent(logs: pd.DataFrame, rent: pd.DataFrame) -> dict[str, pd.DataFrame]:
    lr = np.log(rent * 12)
    ptr = logs - lr
    return {"ptr": ptr, "rent_r12": lr - lr.shift(12, axis=1), "ptr_chg12": ptr - ptr.shift(12, axis=1)}


def _labor(une: pd.DataFrame, lf: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Unemployment and job growth from not-seasonally-adjusted counts: 12-month level, and changes
    against the same 3 months a year earlier (so seasonality cancels). Windows tolerate a missing month
    (BLS published no October 2025 county data because of the shutdown); counts and labor force miss the
    same month, so their ratio is unaffected."""
    une, lf = une.shift(LABOR_LAG, axis=1), lf.shift(LABOR_LAG, axis=1)
    roll = lambda f, n: _T(f, lambda d: d.rolling(n, min_periods=n - max(1, n // 6)).sum())
    u3, l3 = roll(une, 3), roll(lf, 3)
    rate3 = u3 / l3
    yoy = rate3 - rate3.shift(12, axis=1)
    emp3 = np.log(l3 - u3)
    return {"ur12": roll(une, 12) / roll(lf, 12), "ur_yoy": yoy, "ur_yoy_chg3": yoy - yoy.shift(3, axis=1),
            "emp_yoy": emp3 - emp3.shift(12, axis=1), "lf12": roll(lf, 12) / 12}


def _unemp_variants(p: pd.DataFrame) -> pd.DataFrame:
    """Clipped (_c) and pandemic-masked (_m) copies of the unemployment change features."""
    shock = ((p.origin >= PANDEMIC[0]) & (p.origin <= PANDEMIC[1])).to_numpy()
    for col, (lo, hi) in UNEMP_CLIP.items():
        if col in p:
            p[f"{col}_c"] = p[col].clip(lo, hi)
            p[f"{col}_m"] = p[col].mask(shock)
    return p


def _stack(frames: dict[str, pd.DataFrame], origins) -> pd.DataFrame:
    cols = [f[origins].stack(future_stack=True).rename(name) for name, f in frames.items()]
    p = pd.concat(cols, axis=1).reset_index(names=["row", "origin"])
    p["origin"] = p.origin.astype("period[M]")
    return p


def training_origins(logs: pd.DataFrame, start_year: int = 2005) -> list:
    """Quarterly origins; later months are added for the live forecast by the caller."""
    return [c for c in logs.columns if c.month in (1, 4, 7, 10) and c.year >= start_year]


def _pay_factor(rate_pct: pd.Series) -> pd.Series:
    """Monthly payment per dollar borrowed on a 30-year fixed loan."""
    r = rate_pct / 1200
    return r / (1 - (1 + r) ** -360)


def _macro_x(fm: pd.DataFrame, rate: pd.Series) -> pd.DataFrame:
    monthly = fm.drop(columns=["DGS10", "T10Y2Y"]).shift(MACRO_LAG)
    d = fm[["DGS10", "T10Y2Y"]]
    lg = lambda s: np.log(s)
    starts, permits = lg(monthly.HOUST.rolling(3).mean()), lg(monthly.PERMIT.rolling(3).mean())
    cpi_yoy = lg(monthly.CPIAUCSL) - lg(monthly.CPIAUCSL).shift(12)
    return pd.DataFrame({
        "m_unrate": monthly.UNRATE, "m_unrate_chg12": monthly.UNRATE - monthly.UNRATE.shift(12),
        "m_payroll_yoy": lg(monthly.PAYEMS) - lg(monthly.PAYEMS).shift(12), "m_cpi_yoy": cpi_yoy,
        "m_real10": d.DGS10 - cpi_yoy * 100, "m_curve": d.T10Y2Y,
        "m_mort_spread": rate.reindex(fm.index) - d.DGS10,
        "m_starts_yoy": starts - starts.shift(12), "m_permits_yoy": permits - permits.shift(12),
        "m_new_supply": monthly.MSACSR, "m_sentiment": monthly.UMCSENT,
        "m_sentiment_chg12": monthly.UMCSENT - monthly.UMCSENT.shift(12)})


def macro_frame(nation: Series, rate: pd.Series, fred: pd.DataFrame | None = None) -> pd.DataFrame:
    nat = nation.logs.iloc[0]
    m = pd.DataFrame({"nat_r3": nat - nat.shift(3), "nat_r12": nat - nat.shift(12), "nat_level": nat})
    m["rate"] = rate.reindex(m.index)
    m["rate_chg12"] = m.rate - rate.shift(12).reindex(m.index)
    lp = np.log(_pay_factor(rate))
    m["lpay_chg12"] = (lp - lp.shift(12)).reindex(m.index)
    x = _macro_x(fred, rate) if fred is not None else pd.DataFrame(columns=MACRO_X)
    return m.join(x.reindex(m.index))


def heat_frame(redfin: pd.DataFrame) -> pd.DataFrame:
    """Redfin metrics plus year-over-year changes, re-keyed to the origin they are usable at."""
    h = redfin.copy()
    base = ["months_of_supply", "median_dom", "sale_to_list"]
    yoy = h[base].groupby(level="metro").diff(12).add_suffix("_yoy")
    h = h.join(yoy).reset_index()
    h["month"] = h.month + REDFIN_LAG
    return h.set_index(["metro", "month"])


def _zheat_frames(zheat: dict[str, pd.DataFrame] | None, ids, columns) -> dict[str, pd.DataFrame]:
    out = {}
    for name in ("z_inventory", "z_new_listings", "z_new_pending", "z_days_pending", "z_price_cut",
                 "z_sale_to_list"):
        w = _align(None if zheat is None else zheat.get(name), ids, columns)
        w = w.shift(ZHEAT_LAG.get(name, 0), axis=1)
        if name in ("z_inventory", "z_new_listings", "z_new_pending"):   # counts: log change only
            lw = np.log(w.where(w > 0))
            out[f"{name}_yoy"] = lw - lw.shift(12, axis=1)
        else:
            out[name] = w
            out[f"{name}_yoy"] = w - w.shift(12, axis=1)
    return out


def _add_common(p: pd.DataFrame) -> pd.DataFrame:
    p["pay_chg12"] = p.r12 + p.lpay_chg12
    p["level_vs_nat"] = p.lvl - p.nat_level
    return p


# ---------- panels ----------

def market_panel(s: Series, origins, macro: pd.DataFrame, heat: pd.DataFrame | None,
                 extras: Extras | None = None) -> pd.DataFrame:
    """Metros and the nation."""
    extras = extras or Extras()
    ids = s.meta.RegionID.to_numpy()
    cols = s.logs.columns
    frames = _changes(s.logs)
    frames.update(_shape(s.logs, frames))
    frames.update(_rent(s.logs, _align(extras.rent_metro, ids, cols)))
    frames.update(_zheat_frames(extras.zheat, ids, cols))
    m_une, m_lf = (extras.labor[0], extras.labor[1]) if extras.labor else (None, None)
    frames.update(_labor(_align(m_une, ids, cols), _align(m_lf, ids, cols)))
    frames["lvl"] = s.logs
    frames["y"] = s.logs.shift(-HORIZON, axis=1) - s.logs
    p = _stack(frames, origins)
    p["region_id"] = ids[p.row]
    p["kind"] = s.meta.RegionType.values[p.row]
    p = _add_common(p.join(macro, on="origin"))
    if heat is not None:
        p["metro"] = s.meta.RegionName.values[p.row]
        p = p.join(heat, on=["metro", "origin"]).drop(columns="metro")
    for c in HEAT:
        if c not in p:
            p[c] = np.nan
    return _unemp_variants(p.dropna(subset=["r12"]))


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


def zip_panel(zips: Series, markets: Series, origins, macro: pd.DataFrame,
              extras: Extras | None = None) -> pd.DataFrame:
    extras = extras or Extras()
    ids = zips.meta.RegionID.to_numpy()
    cols = zips.logs.columns
    parents = parent_ids(zips, markets)
    mlogs = markets.logs.set_index(markets.meta.RegionID).reindex(parents).set_axis(zips.logs.index)
    own, par = _changes(zips.logs), _changes(mlogs)
    frames = dict(own)
    frames.update(parent_r3=par["r3"], parent_r12=par["r12"],
                  rel_r3=own["r3"] - par["r3"], rel_r12=own["r12"] - par["r12"],
                  rel_r36=own["r36"] - par["r36"], rel_level=zips.logs - mlogs)

    shape, pshape = _shape(zips.logs, own), _shape(mlogs, par)
    frames.update(shape, rel_vol36=shape["vol36"] - pshape["vol36"], rel_dd60=shape["dd60"] - pshape["dd60"])

    bot = np.log(_align(extras.tier_bottom, ids, cols))
    top = np.log(_align(extras.tier_top, ids, cols))
    spread = top - bot
    frames.update(tier_spread=spread, tier_spread_chg12=spread - spread.shift(12, axis=1),
                  bot_rel_r12=(bot - bot.shift(12, axis=1)) - own["r12"],
                  top_rel_r12=(top - top.shift(12, axis=1)) - own["r12"])

    zr = _rent(zips.logs, _align(extras.rent_zip, ids, cols))
    pr = _rent(mlogs, _align(extras.rent_metro, parents, cols))
    frames.update(ptr=zr["ptr"], rel_ptr=zr["ptr"] - pr["ptr"], rel_rent_r12=zr["rent_r12"] - pr["rent_r12"])

    m_une, m_lf, z_une, z_lf = extras.labor if extras.labor else (None,) * 4
    zl = _labor(_align(z_une, ids, cols), _align(z_lf, ids, cols))
    pl = _labor(_align(m_une, parents, cols), _align(m_lf, parents, cols))
    frames.update(cty_ur_rel=zl["ur12"] - pl["ur12"], cty_ur_yoy_rel=zl["ur_yoy"] - pl["ur_yoy"],
                  cty_emp_yoy_rel=zl["emp_yoy"] - pl["emp_yoy"])

    frames["lvl"] = zips.logs
    future = lambda L: L.shift(-HORIZON, axis=1) - L
    frames["y"] = future(zips.logs)
    frames["y_parent"] = future(mlogs)
    p = _stack(frames, origins)
    p["y_rel"] = p.y - p.y_parent
    p["region_id"] = ids[p.row]
    p["parent_id"] = parents[p.row]
    p = _add_common(p.join(macro, on="origin"))
    return _unemp_variants(p.dropna(subset=["r12", "parent_r12"]))
