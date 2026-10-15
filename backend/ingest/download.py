"""Download the public source files into data/raw.

Zillow Research: ZHVI (typical home value, mid tier, smoothed, seasonally adjusted) for ZIPs and metros,
plus the current ZHVF growth forecast. Redfin Data Center: the metro market tracker. FRED: the weekly
30-year fixed mortgage rate. All are free bulk files; Zillow and Redfin ask for attribution.

    python -m ingest.download
"""
import shutil
import urllib.request
from pathlib import Path

from homeprice.data import RAW, ZILLOW_EXTRAS
from ingest import fred

ZILLOW = "https://files.zillowstatic.com/research/public_csvs"
TIER = "uc_sfrcondo_tier_0.33_0.67_sm_sa_month"

SOURCES = {
    f"Zip_zhvi_{TIER}.csv": f"{ZILLOW}/zhvi/Zip_zhvi_{TIER}.csv",
    f"Metro_zhvi_{TIER}.csv": f"{ZILLOW}/zhvi/Metro_zhvi_{TIER}.csv",
    f"Zip_zhvf_growth_{TIER}.csv": f"{ZILLOW}/zhvf_growth/Zip_zhvf_growth_{TIER}.csv",
    f"Metro_zhvf_growth_{TIER}.csv": f"{ZILLOW}/zhvf_growth/Metro_zhvf_growth_{TIER}.csv",
    "redfin_metro_market_tracker.tsv000.gz": "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
                                             "redfin_market_tracker/redfin_metro_market_tracker.tsv000.gz",
    # Census reference files for the unemployment features: county FIPS codes, and the 2023 delineation
    # of counties into metro areas.
    "census_counties.txt": "https://www2.census.gov/geo/docs/reference/codes2020/national_county2020.txt",
    "cbsa_delineation_2023.xlsx": "https://www2.census.gov/programs-surveys/metro-micro/geographies/"
                                  "reference-files/2023/delineation-files/list1_2023.xlsx",
    # Census Gazetteer: an interior point (lat/lon) for every ZIP Code Tabulation Area, for the maps.
    "census_zcta_gazetteer.zip": "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2024_Gazetteer/"
                                 "2024_Gaz_zcta_national.zip",
}
# Extra series for the feature groups (tiers, rent, Zillow market activity).
_DIRS = {"Zip_zhvi": "zhvi", "zori": "zori", "invt_fs": "invt_fs", "new_listings": "new_listings",
         "new_pending": "new_pending", "med_doz_pending": "med_doz_pending",
         "perc_listings_price_cut": "perc_listings_price_cut", "mean_sale_to_list": "mean_sale_to_list"}
for _name in ZILLOW_EXTRAS.values():
    _dir = next(d for k, d in _DIRS.items() if k in _name)
    SOURCES[_name] = f"{ZILLOW}/{_dir}/{_name}"


def fetch(name: str, url: str) -> Path:
    dest = RAW / name
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "housing-tracker/0.1 (research)"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)
    return dest


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = fetch(name, url)
        print(f"{name}: {path.stat().st_size / 1e6:.1f} MB")
    # Mortgage rate from FRED (API or fredgraph, see ingest/fred.py), in fredgraph's CSV layout.
    rate = fred.series("MORTGAGE30US")
    rate.rename_axis("observation_date").to_csv(RAW / "mortgage.csv")
    print(f"mortgage.csv: {len(rate):,} weeks through {rate.index.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
