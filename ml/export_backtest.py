"""Write backtest_forecasts.parquet into an existing model artifact without retraining the model.

train.py writes this file for new models; this backfills one trained before it did. It reruns the
walk-forward backtest (same folds and config as training), so it takes a few minutes.

    python export_backtest.py [<version>]      # default: the newest artifact
"""
import sys

from homeprice import backtest
from homeprice.pipeline import build
from train import ARTIFACTS, INTERVAL


def main() -> None:
    version = sys.argv[1] if len(sys.argv) > 1 else sorted(p.name for p in ARTIFACTS.iterdir())[-1]
    out = ARTIFACTS / version
    mp, zp, _ = build()
    _, preds = backtest.run(mp, zp)
    table = backtest.forecast_table(preds, backtest.interval_residuals(preds, INTERVAL))
    table.to_parquet(out / "backtest_forecasts.parquet", index=False)
    print(f"wrote {len(table):,} backtest forecasts to {out}")


if __name__ == "__main__":
    main()
