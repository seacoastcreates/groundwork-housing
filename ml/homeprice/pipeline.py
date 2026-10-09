"""Build (and cache) the market and ZIP panels shared by training, ablation and tuning."""
import hashlib
from pathlib import Path

import pandas as pd

from homeprice.data import RAW, Series, load_mortgage, load_redfin, load_wide, load_zhvi
from homeprice.labor import labor_frames, load_macro
from homeprice.features import (Extras, heat_frame, macro_frame, market_panel, training_origins,
                                zip_panel)

CACHE = RAW.parent / "panels"
ZHEAT_NAMES = ("z_inventory", "z_new_listings", "z_new_pending", "z_days_pending", "z_price_cut",
               "z_sale_to_list")


def _fingerprint() -> str:
    """Changes whenever a raw file or the feature code changes."""
    h = hashlib.sha1()
    for f in sorted(RAW.iterdir()):
        h.update(f"{f.name}:{f.stat().st_mtime_ns}".encode())
    for code in ("features.py", "labor.py"):
        h.update(Path(__file__).with_name(code).read_bytes())
    return h.hexdigest()[:12]


def build(use_cache: bool = True, log=print) -> tuple[pd.DataFrame, pd.DataFrame, pd.Period]:
    """Returns (market panel, ZIP panel, latest month)."""
    key = _fingerprint()
    mpath, zpath = CACHE / f"markets-{key}.parquet", CACHE / f"zips-{key}.parquet"
    metros, zips = load_zhvi("Metro"), load_zhvi("Zip")
    latest = zips.logs.columns[-1]
    if use_cache and mpath.exists() and zpath.exists():
        log(f"panels from cache {key}")
        return _read(mpath), _read(zpath), latest

    is_nat = (metros.meta.RegionType == "country").values
    nation = Series(metros.meta[is_nat].reset_index(drop=True), metros.logs[is_nat].reset_index(drop=True))
    macro = macro_frame(nation, load_mortgage(), load_macro())
    extras = Extras(tier_bottom=load_wide("tier_bottom"), tier_top=load_wide("tier_top"),
                    rent_zip=load_wide("rent_zip"), rent_metro=load_wide("rent_metro"),
                    zheat={n: load_wide(n) for n in ZHEAT_NAMES}, labor=labor_frames(metros, zips))
    origins = sorted(set(training_origins(zips.logs)) | {latest})
    mp = market_panel(metros, origins, macro, heat_frame(load_redfin()), extras)
    zp = zip_panel(zips, metros, origins, macro, extras)
    CACHE.mkdir(parents=True, exist_ok=True)
    for old in CACHE.glob("*.parquet"):
        old.unlink()
    for df, path in ((mp, mpath), (zp, zpath)):
        df.assign(origin=df.origin.dt.to_timestamp()).to_parquet(path, index=False)
    log(f"panels built: {len(mp):,} market rows, {len(zp):,} ZIP rows")
    return mp, zp, latest


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["origin"] = df.origin.dt.to_period("M")
    return df
