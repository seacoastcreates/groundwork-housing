"""FRED access with two transports.

- Official API (api.stlouisfed.org), used when FRED_API_KEY is set. fred.stlouisfed.org refuses
  connections from AWS addresses, but the API does not, so the SageMaker refresh job uses this. The job
  sets FRED_API_KEY from Secrets Manager at runtime; the key is never stored in code or config.
- fredgraph.csv (no key), the fallback for local runs. It takes up to 12 series per request.

Both return a Series of floats indexed by observation date, named after the series id.
"""
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

GRAPH = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
API = "https://api.stlouisfed.org/fred/series/observations"
UA = {"User-Agent": "housing-tracker/0.1 (research)"}
API_INTERVAL = 0.55        # seconds between API calls: FRED allows 120 requests per minute
GRAPH_INTERVAL = 1.0
GRAPH_BATCH = 12           # fredgraph returns at most 12 series per request and silently drops the rest


def api_key() -> str | None:
    return os.environ.get("FRED_API_KEY") or None


def _open(url: str, timeout: int = 120) -> bytes | None:
    """GET with retries; None when FRED says the series doesn't exist."""
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None          # unknown series (the API answers 400, fredgraph 404)
            time.sleep(10 * (attempt + 1) if e.code == 429 else 5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"FRED request failed after retries: {url.split('api_key=')[0]}")


def _api_series(sid: str, key: str) -> pd.Series | None:
    q = urllib.parse.urlencode({"series_id": sid, "api_key": key, "file_type": "json"})
    body = _open(f"{API}?{q}")
    time.sleep(API_INTERVAL)
    if body is None:
        return None
    obs = json.loads(body)["observations"]
    s = pd.Series({o["date"]: o["value"] for o in obs}, name=sid)
    s.index = pd.to_datetime(s.index)
    return pd.to_numeric(s, errors="coerce")       # FRED marks missing values with "."


def _graph_batch(ids: list[str]) -> list[pd.Series]:
    """One fredgraph request; when it 404s because an id is missing, split until the bad ones drop out."""
    body = _open(GRAPH + ",".join(ids))
    time.sleep(GRAPH_INTERVAL)
    if body is None:
        if len(ids) == 1:
            return []
        mid = len(ids) // 2
        return _graph_batch(ids[:mid]) + _graph_batch(ids[mid:])
    # Mixed frequencies (e.g. daily + monthly) come back as a ZIP with one CSV per frequency.
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            csvs = [z.read(n) for n in z.namelist() if n.lower().endswith(".csv")]
    else:
        csvs = [body]
    out = []
    for raw in csvs:
        df = pd.read_csv(io.BytesIO(raw), na_values=".", index_col=0, parse_dates=True)
        out += [pd.to_numeric(df[c], errors="coerce").rename(c) for c in df.columns if c in ids]
    missing = [i for i in ids if i not in {s.name for s in out}]
    return out + (_graph_batch(missing) if missing and len(missing) < len(ids) else [])


def fetch(ids: list[str], progress_every: int = 0) -> list[pd.Series]:
    """Fetch many series; unknown ids are skipped."""
    key = api_key()
    out = []
    step = 1 if key else GRAPH_BATCH
    for i in range(0, len(ids), step):
        if key:
            s = _api_series(ids[i], key)
            out += [s] if s is not None else []
        else:
            out += _graph_batch(ids[i:i + step])
        if progress_every and i % progress_every < step:
            print(f"  FRED {i:,}/{len(ids):,} series ({'API' if key else 'fredgraph'})", flush=True)
    return out


def series(sid: str) -> pd.Series:
    got = fetch([sid])
    if not got:
        raise RuntimeError(f"FRED series {sid} not found")
    return got[0]
