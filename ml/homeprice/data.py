"""Read the raw source files into month-indexed frames.

Home values come back as a wide frame of log values: one row per region, one column per month
(pandas Period). Everything downstream works in log space, so a change is a difference of columns.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
TIER = "uc_sfrcondo_tier_0.33_0.67_sm_sa_month"
REDFIN_COLS = {"MONTHS_OF_SUPPLY": "months_of_supply", "MEDIAN_DOM": "median_dom",
               "AVG_SALE_TO_LIST": "sale_to_list", "PRICE_DROPS": "price_drops"}


@dataclass
class Series:
    meta: pd.DataFrame      # RegionID, RegionName, RegionType, State, ... (index aligned with logs)
    logs: pd.DataFrame      # log home value, columns are monthly Periods


def load_zhvi(level: str, raw: Path = RAW) -> Series:
    df = pd.read_csv(raw / f"{level}_zhvi_{TIER}.csv", dtype={"RegionName": str})
    dates = [c for c in df.columns if c[:2] in ("19", "20")]
    meta = df.drop(columns=dates).reset_index(drop=True)
    if level == "Zip":
        meta["RegionName"] = meta.RegionName.str.zfill(5)
    logs = np.log(df[dates].astype(float)).reset_index(drop=True)
    logs.columns = pd.PeriodIndex(pd.to_datetime(dates), freq="M")
    return Series(meta, logs)


def load_redfin(raw: Path = RAW) -> pd.DataFrame:
    """Monthly Redfin metrics indexed by (Zillow-style metro name, month)."""
    cols = ["PERIOD_BEGIN", "REGION", "PROPERTY_TYPE", "IS_SEASONALLY_ADJUSTED", *REDFIN_COLS]
    r = pd.read_csv(raw / "redfin_metro_market_tracker.tsv000.gz", sep="\t", usecols=cols)
    r = r[(r.PROPERTY_TYPE == "All Residential") & ~r.IS_SEASONALLY_ADJUSTED.astype(bool)]
    r["metro"] = r.REGION.str.replace(" metro area", "", regex=False)
    r["month"] = pd.to_datetime(r.PERIOD_BEGIN).dt.to_period("M")
    return r.groupby(["metro", "month"])[list(REDFIN_COLS)].mean().rename(columns=REDFIN_COLS)


def load_mortgage(raw: Path = RAW) -> pd.Series:
    m = pd.read_csv(raw / "mortgage.csv", parse_dates=["observation_date"], na_values=".")
    m = m.set_index("observation_date").MORTGAGE30US.dropna().resample("ME").mean()
    m.index = m.index.to_period("M")
    return m.rename("rate")


def load_zillow_forecast(level: str, raw: Path = RAW) -> pd.DataFrame:
    df = pd.read_csv(raw / f"{level}_zhvf_growth_{TIER}.csv", dtype={"RegionName": str})
    targets = [c for c in df.columns if c[:2] == "20"]
    long = df.melt(id_vars=["RegionID", "BaseDate"], value_vars=targets,
                   var_name="target", value_name="growth_pct").dropna()
    return long


# Extra Zillow series used by the feature groups in features.py, keyed by short name.
ZILLOW_EXTRAS = {
    "tier_bottom": "Zip_zhvi_uc_sfrcondo_tier_0.0_0.33_sm_sa_month.csv",
    "tier_top": "Zip_zhvi_uc_sfrcondo_tier_0.67_1.0_sm_sa_month.csv",
    "rent_zip": "Zip_zori_uc_sfrcondomfr_sm_month.csv",
    "rent_metro": "Metro_zori_uc_sfrcondomfr_sm_month.csv",
    "z_inventory": "Metro_invt_fs_uc_sfrcondo_sm_month.csv",
    "z_new_listings": "Metro_new_listings_uc_sfrcondo_sm_month.csv",
    "z_new_pending": "Metro_new_pending_uc_sfrcondo_sm_month.csv",
    "z_days_pending": "Metro_med_doz_pending_uc_sfrcondo_sm_month.csv",
    "z_price_cut": "Metro_perc_listings_price_cut_uc_sfrcondo_sm_month.csv",
    "z_sale_to_list": "Metro_mean_sale_to_list_uc_sfrcondo_sm_month.csv",
}


def load_wide(name: str, raw: Path = RAW) -> pd.DataFrame:
    """A Zillow wide file as raw values: index RegionID, columns monthly Periods."""
    df = pd.read_csv(raw / ZILLOW_EXTRAS[name])
    dates = [c for c in df.columns if c[:2] in ("19", "20")]
    out = df.set_index("RegionID")[dates].astype(float)
    out.columns = pd.PeriodIndex(pd.to_datetime(dates), freq="M")
    return out
