"""Download unemployment and national macro series from FRED.

County unemployment: BLS Local Area Unemployment Statistics, mirrored on FRED as LAUCN<fips>0000000004
(unemployed) and ...05 (employed). BLS's own bulk files refuse scripted downloads without a contact email
in the User-Agent, so FRED is used instead. Series are fetched in batches through fredgraph.csv at about
one request per second.

National macro: a handful of monthly or daily FRED series, one request each.

    python -m ingest.labor [--resume]
"""
import io
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

from ingest.download import RAW

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
UA = {"User-Agent": "housing-tracker/0.1 (research)"}
BATCH = 12             # fredgraph returns at most 12 series per request and silently drops the rest
MACRO_SERIES = ["UNRATE", "PAYEMS", "CPIAUCSL", "DGS10", "T10Y2Y", "HOUST", "PERMIT", "MSACSR", "UMCSENT"]


def _get(ids: list[str]) -> pd.DataFrame | None:
    req = urllib.request.Request(FRED + ",".join(ids), headers=UA)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return pd.read_csv(io.BytesIO(r.read()), na_values=".")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None          # at least one id doesn't exist
            time.sleep(5 * (attempt + 1))
        except urllib.error.URLError:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"FRED failed for {ids[:3]}...")


def _fetch(ids: list[str]) -> list[pd.DataFrame]:
    """Fetch a batch; when FRED 404s because one id is missing, split until the bad ones drop out."""
    df = _get(ids)
    time.sleep(1.0)
    if df is not None:
        df = df.set_index("observation_date")
        missing = [i for i in ids if i not in df.columns]
        if missing and len(missing) < len(ids):
            return [df] + _fetch(missing)
        return [df]
    if len(ids) == 1:
        return []
    mid = len(ids) // 2
    return _fetch(ids[:mid]) + _fetch(ids[mid:])


def counties() -> list[str]:
    c = pd.read_csv(RAW / "census_counties.txt", sep="|", dtype=str)
    return (c.STATEFP + c.COUNTYFP).tolist()


def fetch_laus(have: pd.DataFrame | None = None) -> pd.DataFrame:
    """All county series, skipping counties already in `have` (to resume an interrupted download)."""
    fips = counties()
    done = set(have.fips) if have is not None else set()
    ids = [f"LAUCN{f}000000000{m}" for f in fips if f not in done for m in (4, 5)]
    frames = []
    for i in range(0, len(ids), BATCH):
        frames += _fetch(ids[i:i + BATCH])
        if i // BATCH % 20 == 0:
            print(f"  LAUS {i:,}/{len(ids):,} series", flush=True)
    wide = pd.concat(frames, axis=1)
    long = wide.stack().rename("value").reset_index()
    long.columns = ["month", "series", "value"]
    long["fips"] = long.series.str[5:10]
    long["measure"] = long.series.str[-1].map({"4": "unemployed", "5": "employed"})
    out = long.pivot_table(index=["fips", "month"], columns="measure", values="value").reset_index()
    out["month"] = pd.to_datetime(out.month)
    return pd.concat([have, out], ignore_index=True) if have is not None else out


def fetch_macro() -> pd.DataFrame:
    cols = []
    for s in MACRO_SERIES:
        df = _get([s])
        time.sleep(1.0)
        ser = df.set_index(pd.to_datetime(df.observation_date))[s].astype(float)
        cols.append(ser.resample("MS").mean())       # daily series -> monthly mean
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
