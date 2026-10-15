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

from homeprice.data import RAW, load_mortgage, load_redfin, load_wide, load_zhvi, load_zillow_forecast
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


def copy_values(cur, series_list, chunk: int = 2000) -> int:
    """COPY home values a block of regions at a time, so the 6.7M rows never sit in memory at once
    (the production server has 2 GB)."""
    n = 0
    with cur.copy("COPY home_values (region_id, month, value) FROM STDIN WITH (FORMAT csv)") as cp:
        for s in series_list:
            months = np.array([str(p.start_time.date()) for p in s.logs.columns])
            ids = s.meta.RegionID.to_numpy()
            for i in range(0, len(ids), chunk):
                vals = np.exp(s.logs.iloc[i:i + chunk].to_numpy())
                r, c = np.nonzero(~np.isnan(vals))
                buf = io.StringIO()
                pd.DataFrame({"r": ids[i:i + chunk][r], "m": months[c], "v": vals[r, c].round(2)}).to_csv(
                    buf, index=False, header=False)
                cp.write(buf.getvalue())
                n += len(r)
    return n


def load_geo(cur) -> None:
    """ZIP points from the Census Gazetteer (ZIP codes and ZCTAs share codes for almost every ZIP Zillow
    tracks), then each metro at the mean of its ZIPs. Skipped if the file hasn't been downloaded."""
    path = RAW / "census_zcta_gazetteer.zip"
    if not path.exists():
        print(f"region_geo: skipped, {path.name} not downloaded")
        return
    g = pd.read_csv(path, sep="\t", dtype={"GEOID": str})
    g.columns = g.columns.str.strip()
    cur.execute("TRUNCATE region_geo")
    cur.execute("CREATE TEMP TABLE zcta_in (zcta TEXT, lat REAL, lon REAL)")
    copy(cur, "zcta_in", pd.DataFrame({"zcta": g.GEOID, "lat": g.INTPTLAT, "lon": g.INTPTLONG}))
    cur.execute("""INSERT INTO region_geo SELECT r.id, z.lat, z.lon FROM regions r JOIN zcta_in z ON z.zcta = r.name
                   WHERE r.kind = 'zip'""")
    n_zip = cur.rowcount
    cur.execute("""INSERT INTO region_geo SELECT r.metro_id, avg(g.lat), avg(g.lon)
                   FROM region_geo g JOIN regions r ON r.id = g.region_id
                   WHERE r.kind = 'zip' AND r.metro_id IS NOT NULL GROUP BY r.metro_id""")
    print(f"region_geo: {n_zip:,} ZIPs, {cur.rowcount:,} metros")


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
    rents = pd.concat([load_wide("rent_metro"), load_wide("rent_zip")]).rename_axis("region_id")
    rents.columns = rents.columns.to_timestamp().date
    rents = rents.stack().dropna().rename("rent").rename_axis(["region_id", "month"]).reset_index().round({"rent": 2})
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
        cur.execute("TRUNCATE home_values")
        print(f"home_values: {copy_values(cur, [metros, zips]):,} rows")
        for table, df in (("market_heat", heat), ("mortgage_rates", rate)):
            cur.execute(f"TRUNCATE {table}")
            copy(cur, table, df)
            print(f"{table}: {len(df):,} rows")
        cur.execute("TRUNCATE rents")
        cur.execute("CREATE TEMP TABLE rent_in (LIKE rents)")
        copy(cur, "rent_in", rents)
        cur.execute("INSERT INTO rents SELECT * FROM rent_in WHERE region_id IN (SELECT id FROM regions)")
        print(f"rents: {cur.rowcount:,} rows")
        load_geo(cur)
        cur.execute("CREATE TEMP TABLE zf_in (LIKE zillow_forecasts)")
        copy(cur, "zf_in", zf[["region_id", "base_month", "target", "growth_pct"]])
        cur.execute("INSERT INTO zillow_forecasts SELECT * FROM zf_in WHERE region_id IN (SELECT id FROM regions) "
                    "ON CONFLICT DO NOTHING")
        print(f"zillow_forecasts: +{cur.rowcount:,} rows (base {zf.base_month.max()})")
        cur.execute("REFRESH MATERIALIZED VIEW region_summary")
        cur.execute("ANALYZE")


if __name__ == "__main__":
    main()
