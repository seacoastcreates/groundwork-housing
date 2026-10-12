"""Download unemployment and national macro series from FRED.

County unemployment: BLS Local Area Unemployment Statistics, mirrored on FRED as LAUCN<fips>0000000004
(unemployed) and ...05 (employed). BLS's own bulk files refuse scripted downloads without a contact email
in the User-Agent, so FRED is used instead.

National macro: a handful of monthly or daily FRED series. Transport (official API with a key, or
fredgraph without) is chosen in ingest/fred.py.

    python -m ingest.labor [--resume]
"""
import sys

import pandas as pd

from ingest import fred
from ingest.download import RAW

MACRO_SERIES = ["UNRATE", "PAYEMS", "CPIAUCSL", "DGS10", "T10Y2Y", "HOUST", "PERMIT", "MSACSR", "UMCSENT"]


def counties() -> list[str]:
    c = pd.read_csv(RAW / "census_counties.txt", sep="|", dtype=str)
    return (c.STATEFP + c.COUNTYFP).tolist()


def fetch_laus(have: pd.DataFrame | None = None) -> pd.DataFrame:
    """All county series, skipping counties already in `have` (to resume an interrupted download)."""
    fips = counties()
    done = set(have.fips) if have is not None else set()
    ids = [f"LAUCN{f}000000000{m}" for f in fips if f not in done for m in (4, 5)]
    wide = pd.concat(fred.fetch(ids, progress_every=240), axis=1)
    long = wide.stack().rename("value").reset_index()
    long.columns = ["month", "series", "value"]
    long["fips"] = long.series.str[5:10]
    long["measure"] = long.series.str[-1].map({"4": "unemployed", "5": "employed"})
    out = long.pivot_table(index=["fips", "month"], columns="measure", values="value").reset_index()
    out["month"] = pd.to_datetime(out.month)
    return pd.concat([have, out], ignore_index=True) if have is not None else out


def fetch_macro() -> pd.DataFrame:
    # Daily series (DGS10, T10Y2Y) become monthly means; monthly ones pass through.
    cols = [ser.resample("MS").mean() for ser in fred.fetch(MACRO_SERIES)]
    return pd.concat(cols, axis=1, sort=True).rename_axis("month").reset_index()


def main() -> None:
    if "--resume" not in sys.argv:
        macro = fetch_macro()
        macro.to_csv(RAW / "fred_macro.csv", index=False)
        print(f"fred_macro.csv: {len(macro):,} months, through {macro.month.max():%Y-%m}")
    path = RAW / "laus_county.parquet"
    resume = "--resume" in sys.argv and path.exists()
    laus = fetch_laus(pd.read_parquet(path) if resume else None)
    laus.to_parquet(RAW / "laus_county.parquet", index=False)
    print(f"laus_county.parquet: {laus.fips.nunique():,} counties, {len(laus):,} rows, "
          f"through {laus.month.max():%Y-%m}")


if __name__ == "__main__":
    main()
