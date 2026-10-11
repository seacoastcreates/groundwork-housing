"""Backtest, fit on all history, and forecast from the latest month.

Writes ml/artifacts/<version>/ with forecasts.parquet, metrics.json and backtest.csv. Load them into
Postgres with `python -m ingest.publish <version>` from backend/.

    python train.py [--skip-backtest]
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from homeprice import backtest
from homeprice.features import HORIZON, REDFIN_LAG
from homeprice.models import RelativeModel, TrendModel, load_config
from homeprice.pipeline import build

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
REPORTS = Path(__file__).resolve().parent / "reports"
INTERVAL = (0.10, 0.90)


def to_pct(log_change):
    return (np.exp(log_change) - 1) * 100


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-backtest", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    mp, zp, latest = build()
    print(f"panels: {len(mp):,} market rows, {len(zp):,} ZIP rows; latest month {latest} "
          f"({time.time() - t0:.0f}s)")

    version = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M")
    out = ARTIFACTS / version
    out.mkdir(parents=True)

    metrics = {"horizon_months": HORIZON, "origin": str(latest), "redfin_lag_months": REDFIN_LAG,
               "test_years": [min(backtest.TEST_YEARS), max(backtest.TEST_YEARS)], "config": load_config()}
    # Feature and tuning experiments ride along so the Model page can show them.
    for name in ("ablation", "tuning", "national"):
        if (REPORTS / f"{name}.json").exists():
            metrics[name] = json.loads((REPORTS / f"{name}.json").read_text())
    resid = {"metro": (-0.08, 0.08), "zip": (-0.10, 0.10)}
    if not args.skip_backtest:
        res, preds = backtest.run(mp, zp)
        res.to_csv(out / "backtest.csv", index=False)
        metrics["backtest"] = backtest.summarize(res)
        # Empirical 80% interval from out-of-sample errors (actual minus forecast, in log change).
        err = preds.y - preds.pred_two_part
        is_zip = preds.parent_id.notna()
        resid = {k: tuple(float(err[m].quantile(q)) for q in INTERVAL)
                 for k, m in (("metro", ~is_zip), ("zip", is_zip))}
        metrics["interval"] = {k: [round(v * 100, 2) for v in r] for k, r in resid.items()}
        print(json.dumps({k: metrics["backtest"][k] for k in metrics["backtest"]}, indent=1, default=str)[:3000])

    trend = TrendModel().fit(mp)
    relative = RelativeModel().fit(zp)
    mnow = mp[mp.origin == latest].copy()
    mnow["trend"] = trend.predict(mnow)
    znow = zp[zp.origin == latest].copy()
    parent_trend = mnow.set_index("region_id").trend
    znow["trend"] = parent_trend.reindex(znow.parent_id).to_numpy()
    znow["relative"] = relative.predict(znow)
    znow = znow.dropna(subset=["trend"])

    def rows(df, rel, kind):
        lo, hi = resid[kind]
        total = df.trend.to_numpy() + rel
        return pd.DataFrame({"region_id": df.region_id.astype(int).to_numpy(), "change_pct": to_pct(total),
                             "low_pct": to_pct(total + lo), "high_pct": to_pct(total + hi),
                             "trend_pct": to_pct(df.trend.to_numpy()), "relative_pct": rel * 100})

    fc = pd.concat([rows(mnow, np.zeros(len(mnow)), "metro"),
                    rows(znow, znow.relative.to_numpy(), "zip")], ignore_index=True)
    fc.to_parquet(out / "forecasts.parquet", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(f"wrote {len(fc):,} forecasts to {out} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
