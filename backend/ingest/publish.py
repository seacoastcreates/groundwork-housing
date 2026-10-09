"""Publish a trained model's forecasts and metrics to Postgres and make it the active model.

    python -m ingest.publish <version>      # e.g. v20261009-1412; omit for the newest artifact
"""
import json
import sys
from pathlib import Path

import pandas as pd
import psycopg

from ingest.load import DSN, copy

ARTIFACTS = Path(__file__).resolve().parents[2] / "ml" / "artifacts"


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else sorted(p.name for p in ARTIFACTS.iterdir())[-1]
    path = ARTIFACTS / version
    metrics = json.loads((path / "metrics.json").read_text())
    fc = pd.read_parquet(path / "forecasts.parquet").round(3)
    origin = pd.Period(metrics["origin"], freq="M").to_timestamp().date()
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("UPDATE model_runs SET is_active = FALSE WHERE is_active")
        cur.execute("""INSERT INTO model_runs (model_version, origin, horizon, metrics, is_active)
                       VALUES (%s, %s, %s, %s, TRUE)
                       ON CONFLICT (model_version) DO UPDATE SET metrics = EXCLUDED.metrics, is_active = TRUE""",
                    (version, origin, metrics["horizon_months"], json.dumps(metrics)))
        cur.execute("DELETE FROM forecasts WHERE model_version = %s", (version,))
        copy(cur, "forecasts", fc.assign(model_version=version)[
            ["model_version", "region_id", "change_pct", "low_pct", "high_pct", "trend_pct", "relative_pct"]])
        cur.execute("ANALYZE forecasts")    # fresh stats, or the planner nested-loops the update below
        cur.execute("""UPDATE forecasts f SET relative_rank_pct = k.p FROM (
                           SELECT f.region_id, 100 * percent_rank() OVER (PARTITION BY r.metro_id ORDER BY f.relative_pct) AS p
                           FROM forecasts f JOIN regions r ON r.id = f.region_id
                           WHERE f.model_version = %(v)s AND r.kind = 'zip' AND r.metro_id IS NOT NULL) k
                       WHERE f.model_version = %(v)s AND f.region_id = k.region_id""", {"v": version})
        cur.execute("REFRESH MATERIALIZED VIEW region_summary")
    print(f"published {version}: {len(fc):,} forecasts from {origin}")


if __name__ == "__main__":
    main()
