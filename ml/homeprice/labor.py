"""County unemployment (BLS LAUS via FRED) aggregated to Zillow metros and mapped to ZIPs, plus national
macro series.

Metro rates are built from county counts using the 2023 Census CBSA delineation (unemployed / labor force
summed over the metro's counties), which also sidesteps New England's NECTA-based LAUS metros. ZIPs get
their county's numbers via Zillow's county name. Values are revised annually by BLS and the latest
revision is used throughout, which flatters the backtest slightly (noted on the Model page).
"""
import re
import unicodedata

import numpy as np
import pandas as pd

from homeprice.data import RAW, Series

SUFFIXES = r"(county|parish|borough|municipality|city and borough|census area|city)$"


def _norm(state: str, name: str, strip_suffix: bool = False) -> str:
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"^saint ", "st ", n)
    if strip_suffix:
        n = re.sub(SUFFIXES, "", n.strip())
    return f"{state}|{re.sub(r'[^a-z0-9]', '', n)}"


def county_fips_map() -> dict[str, str]:
    c = pd.read_csv(RAW / "census_counties.txt", sep="|", dtype=str)
    out = {}
    for r in c.itertuples():
        fips = r.STATEFP + r.COUNTYFP
        out.setdefault(_norm(r.STATE, r.COUNTYNAME), fips)
        out.setdefault(_norm(r.STATE, r.COUNTYNAME, strip_suffix=True), fips)
    return out


def zip_fips(zips: Series) -> np.ndarray:
    cmap = county_fips_map()
    return np.array([cmap.get(_norm(s, n), cmap.get(_norm(s, n, strip_suffix=True)))
                     for s, n in zip(zips.meta.State, zips.meta.CountyName)], dtype=object)


def metro_counties(markets: Series) -> dict[int, list[str]]:
    """Zillow metro RegionID -> county FIPS codes, by matching CBSA titles to Zillow's short names."""
    from homeprice.features import _short_metro
    d = pd.read_excel(RAW / "cbsa_delineation_2023.xlsx", header=2).dropna(subset=["FIPS County Code"])
    d["fips"] = d["FIPS State Code"].astype(int).map("{:02d}".format) + d["FIPS County Code"].astype(int).map("{:03d}".format)
    by_title = d.groupby("CBSA Title").fips.apply(list).to_dict()
    lookup = {}
    for title, fips in by_title.items():
        lookup.setdefault(title, fips)
        lookup.setdefault(_short_metro(title), fips)
    return {rid: lookup[name] for rid, name in zip(markets.meta.RegionID, markets.meta.RegionName) if name in lookup}


def county_counts() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(unemployed, labor force) wide frames: index county FIPS, columns monthly Periods."""
    laus = pd.read_parquet(RAW / "laus_county.parquet")
    laus["month"] = laus.month.dt.to_period("M")
    une = laus.pivot(index="fips", columns="month", values="unemployed")
    emp = laus.pivot(index="fips", columns="month", values="employed")
    return une, une + emp


def labor_frames(markets: Series, zips: Series) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Unemployed and labor-force counts for markets (metros + nation) and ZIPs (their county), as wide
    frames indexed by Zillow RegionID."""
    une, lf = county_counts()
    groups = metro_counties(markets)
    nation_id = int(markets.meta.RegionID[markets.meta.RegionType == "country"].iloc[0])
    groups[nation_id] = list(une.index)
    m_une = pd.DataFrame({rid: une.reindex(f).sum(min_count=1) for rid, f in groups.items()}).T
    m_lf = pd.DataFrame({rid: lf.reindex(f).sum(min_count=1) for rid, f in groups.items()}).T
    fips = zip_fips(zips)
    z_une = une.reindex(fips).set_axis(zips.meta.RegionID.to_numpy())
    z_lf = lf.reindex(fips).set_axis(zips.meta.RegionID.to_numpy())
    return m_une, m_lf, z_une, z_lf


def load_macro() -> pd.DataFrame:
    m = pd.read_csv(RAW / "fred_macro.csv", parse_dates=["month"])
    m["month"] = m.month.dt.to_period("M")
    return m.set_index("month")
