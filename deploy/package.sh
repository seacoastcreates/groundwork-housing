#!/usr/bin/env bash
# Build the data bundle the server restores on first boot: a PostgreSQL dump with the current data and
# active model's forecasts. Run before `cdk deploy`.
set -euo pipefail
cd "$(dirname "$0")/.."
DB=${DB:-housingtracker}
OUT=deploy/bundle
rm -rf "$OUT" && mkdir -p "$OUT"
pg_dump --format=custom --no-owner --no-privileges "$DB" > "$OUT/$DB.dump"
psql -At "$DB" -c "SELECT model_version FROM model_runs WHERE is_active" > "$OUT/ACTIVE_MODEL"
du -sh "$OUT"/* | sed 's/^/  /'
echo "Bundle ready for model $(cat "$OUT/ACTIVE_MODEL")"
