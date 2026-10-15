"""Entry point of the monthly SageMaker Processing job: download every source, build the panels, backtest
and train, then hand back the raw files (for the server's database load) and the new model.

Everything heavy runs here because the web server has 2 GB of memory and building the ZIP panels alone
needs about 3 GB. SageMaker uploads /opt/ml/processing/output to S3 when the job ends:
  output/raw/     the downloaded source files
  output/model/   forecasts.parquet, metrics.json, backtest.csv, backtest_forecasts.parquet, and VERSION
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROGRAM = Path("/opt/program")
WORK = Path("/opt/ml/processing/work")
OUT = Path("/opt/ml/processing/output")
ENV = {**os.environ, "HOUSING_DATA_DIR": str(WORK / "data"), "HOUSING_ARTIFACTS_DIR": str(WORK / "artifacts"),
       "PYTHONUNBUFFERED": "1"}


def step(label: str, args: list[str], cwd: Path) -> None:
    started = time.time()
    print(f"=== {label}", flush=True)
    subprocess.run([sys.executable, *args], cwd=cwd, env=ENV, check=True)
    print(f"=== {label} done in {time.time() - started:.0f}s", flush=True)


def fred_key_from_secrets() -> None:
    """Resolve the FRED API key at runtime from Secrets Manager (FRED_SECRET_ID names the secret).
    fred.stlouisfed.org refuses AWS addresses; its official API needs this key. The key only lives in
    this job's environment and is never logged or written out."""
    secret_id = os.environ.get("FRED_SECRET_ID")
    if not secret_id:
        print("FRED_SECRET_ID not set; FRED downloads will try fredgraph", flush=True)
        return
    import boto3
    value = boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)["SecretString"]
    ENV["FRED_API_KEY"] = json.loads(value)["api_key"]
    print(f"FRED API key loaded from {secret_id}", flush=True)


def main() -> int:
    (WORK / "data" / "raw").mkdir(parents=True, exist_ok=True)
    fred_key_from_secrets()
    step("download Zillow, Redfin, mortgage rates", ["-m", "ingest.download"], PROGRAM / "backend")
    step("download county unemployment and macro (FRED)", ["-m", "ingest.labor"], PROGRAM / "backend")
    step("backtest and train", ["-W", "ignore", "train.py"], PROGRAM / "ml")

    version = sorted(p.name for p in (WORK / "artifacts").iterdir())[-1]
    shutil.copytree(WORK / "artifacts" / version, OUT / "model", dirs_exist_ok=True)
    (OUT / "model" / "VERSION").write_text(version)
    shutil.copytree(WORK / "data" / "raw", OUT / "raw", dirs_exist_ok=True)
    print(f"model {version} and {len(list((OUT / 'raw').iterdir()))} raw files written", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
