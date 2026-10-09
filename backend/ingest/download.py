"""Download the public source files into data/raw.

Zillow Research: ZHVI (typical home value, mid tier, smoothed, seasonally adjusted) for ZIPs and metros,
plus the current ZHVF growth forecast. Redfin Data Center: the metro market tracker. FRED: the weekly
30-year fixed mortgage rate. All are free bulk files; Zillow and Redfin ask for attribution.

    python -m ingest.download
"""
import shutil
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[2] / "data" / "raw"
ZILLOW = "https://files.zillowstatic.com/research/public_csvs"
TIER = "uc_sfrcondo_tier_0.33_0.67_sm_sa_month"

SOURCES = {
    f"Zip_zhvi_{TIER}.csv": f"{ZILLOW}/zhvi/Zip_zhvi_{TIER}.csv",
    f"Metro_zhvi_{TIER}.csv": f"{ZILLOW}/zhvi/Metro_zhvi_{TIER}.csv",
    f"Zip_zhvf_growth_{TIER}.csv": f"{ZILLOW}/zhvf_growth/Zip_zhvf_growth_{TIER}.csv",
    f"Metro_zhvf_growth_{TIER}.csv": f"{ZILLOW}/zhvf_growth/Metro_zhvf_growth_{TIER}.csv",
    "redfin_metro_market_tracker.tsv000.gz": "https://redfin-public-data.s3.us-west-2.amazonaws.com/"
                                             "redfin_market_tracker/redfin_metro_market_tracker.tsv000.gz",
    "mortgage.csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=MORTGAGE30US",
}


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


if __name__ == "__main__":
    main()
