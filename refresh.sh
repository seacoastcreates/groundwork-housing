#!/usr/bin/env bash
# Monthly refresh: download the latest source files, load them, retrain, and publish.
# Each run also archives Zillow's current forecast so it can be scored later.
set -euo pipefail
cd "$(dirname "$0")"
PY="$PWD/.venv/bin/python"

(cd backend && "$PY" -m ingest.download && "$PY" -m ingest.load)
(cd ml && "$PY" -W ignore -u train.py)
(cd backend && "$PY" -m ingest.publish)
