"""Load the raw files into Postgres. Safe to re-run: regions are upserted, monthly series replaced, and
the Zillow forecast snapshot appended (it is the archive we will later score Zillow against).

    createdb housingtracker
    python -m ingest.load
"""
import io
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from homeprice.data import load_mortgage, load_redfin, load_zhvi, load_zillow_forecast
from homeprice.features import parent_ids

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
DSN = os.environ.get("DATABASE_URL", "postgresql://localhost/housingtracker").replace("+psycopg", "")


def copy(cur, table: str, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    with cur.copy(f"COPY {table} ({', '.join(df.columns)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
        while chunk := buf.read(1 << 20):
            cp.write(chunk)


def long_values(s) -> pd.DataFrame:
    v = np.exp(s.logs).set_axis(s.meta.RegionID).stack().dropna().rename("value").reset_index()
    v.columns = ["region_id", "month", "value"]
    v["month"] = v.month.dt.to_timestamp().dt.date
    return v


def main() -> None:
    metros, zips = load_zhvi("Metro"), load_zhvi("Zip")
    m = metros.meta
    regions = pd.DataFrame({"id": m.RegionID, "kind": m.RegionType, "name": m.RegionName,
                            "state": m.StateName, "city": None, "county": None, "metro_id": None,
                            "size_rank": m.SizeRank})
    z = zips.meta
    nation_id = int(m.RegionID[m.RegionType == "country"].iloc[0])
    parents = parent_ids(zips, metros)
    zregions = pd.DataFrame({"id": z.RegionID, "kind": "zip", "name": z.RegionName, "state": z.State,
                             "city": z.City, "county": z.CountyName,
                             "metro_id": pd.array(np.where(parents == nation_id, None, parents), dtype="Int64"),
                             "size_rank": z.SizeRank})
    by_name = dict(zip(m.RegionName, m.RegionID))
    heat = load_redfin().reset_index()
    heat["region_id"] = heat.metro.map(by_name)
    heat = heat.dropna(subset=["region_id"])
    heat["region_id"] = heat.region_id.astype(int)
    heat["month"] = heat.month.dt.to_timestamp().dt.date
    heat = heat[["region_id", "month", "months_of_supply", "median_dom", "sale_to_list", "price_drops"]]
    rate = load_mortgage().reset_index()
    rate.columns = ["month", "rate"]
    rate["month"] = rate.month.dt.to_timestamp().dt.date
    zf = pd.concat([load_zillow_forecast("Metro"), load_zillow_forecast("Zip")])
    zf = zf.rename(columns={"RegionID": "region_id", "BaseDate": "base_month"})
    zf["base_month"] = pd.to_datetime(zf.base_month).dt.to_period("M").dt.to_timestamp().dt.date
    zf["target"] = pd.to_datetime(zf.target).dt.to_period("M").dt.to_timestamp().dt.date

    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        cur.execute("CREATE TEMP TABLE r_in (LIKE regions)")
        copy(cur, "r_in", pd.concat([regions, zregions]))
        cur.execute("""INSERT INTO regions SELECT * FROM r_in WHERE metro_id IS NULL
                       ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, state = EXCLUDED.state,
                         city = EXCLUDED.city, county = EXCLUDED.county, metro_id = NULL,
                         size_rank = EXCLUDED.size_rank""")
        cur.execute("""INSERT INTO regions SELECT * FROM r_in WHERE metro_id IS NOT NULL
                       ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, state = EXCLUDED.state,
                         city = EXCLUDED.city, county = EXCLUDED.county, metro_id = EXCLUDED.metro_id,
                         size_rank = EXCLUDED.size_rank""")
        for table, df in (("home_values", pd.concat([long_values(metros), long_values(zips)])),
                          ("market_heat", heat), ("mortgage_rates", rate)):
            cur.execute(f"TRUNCATE {table}")
            copy(cur, table, df)
            print(f"{table}: {len(df):,} rows")
        cur.execute("CREATE TEMP TABLE zf_in (LIKE zillow_forecasts)")
        copy(cur, "zf_in", zf[["region_id", "base_month", "target", "growth_pct"]])
        cur.execute("INSERT INTO zillow_forecasts SELECT * FROM zf_in WHERE region_id IN (SELECT id FROM regions) "
                    "ON CONFLICT DO NOTHING")
        print(f"zillow_forecasts: +{cur.rowcount:,} rows (base {zf.base_month.max()})")
        cur.execute("REFRESH MATERIALIZED VIEW region_summary")
        cur.execute("ANALYZE")


if __name__ == "__main__":
    main()
