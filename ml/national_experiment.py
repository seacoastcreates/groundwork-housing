"""Should the national forecast be an aggregate of the metro forecasts?

Step 1 picks the weighting that best reproduces the actual national 12-month change from actual metro
changes, using 2005-2016 only (before any test year). Step 2 backtests, 2017-2025, the current national
forecast (trend model on the nation's own row), the weighted aggregate of the metro forecasts, and damped
momentum. Rule, fixed beforehand: adopt the aggregate if its national MAE is lower over all test years and
in at least 6 of 9. With 4 quarterly origins a year this is a small sample, and the page says so.

    python -u national_experiment.py [--write-config]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from homeprice import backtest
from homeprice.models import CONFIG, TrendModel, damped_momentum, load_config
from homeprice.national import WEIGHTS, aggregate
from homeprice.pipeline import build

REPORTS = Path(__file__).resolve().parent / "reports"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-config", action="store_true")
    args = ap.parse_args()
    mp, _, _ = build()
    nation = mp[mp.kind == "country"].set_index("origin")

    # Step 1: aggregation fidelity on actual outcomes, pre-test years only.
    early = mp[mp.origin.dt.year.between(2005, 2016) & mp.y.notna()]
    fidelity = {}
    for scheme in WEIGHTS:
        agg = aggregate(early, early.y, scheme)
        err = (agg - nation.y.reindex(agg.index)).dropna() * 100
        fidelity[scheme] = {"mae": round(float(err.abs().mean()), 3), "bias": round(float(err.mean()), 3)}
        print(f"fidelity {scheme:<12} MAE {fidelity[scheme]['mae']:.3f} bias {fidelity[scheme]['bias']:+.3f}")
    scheme = min(fidelity, key=lambda k: fidelity[k]["mae"])
    print(f"chosen weighting: {scheme}")

    # Step 2: walk-forward backtest of national forecasts.
    rows = []
    for yr, train, test in backtest.fold_split(mp, backtest.TEST_YEARS):
        pred = pd.Series(TrendModel().fit(train).predict(test), index=test.index)
        nat = test[test.kind == "country"].set_index("origin")
        agg = aggregate(test, pred, scheme).reindex(nat.index)
        cands = {"aggregate": agg, "own_row": pred[test.kind == "country"].set_axis(nat.index),
                 "damped": pd.Series(damped_momentum(nat), index=nat.index)}
        for name, p in cands.items():
            e = (p - nat.y) * 100
            rows.append(dict(year=yr, model=name, mae=float(e.abs().mean()), bias=float(e.mean())))
    res = pd.DataFrame(rows)
    table = res.pivot(index="year", columns="model", values="mae")
    print(table.round(2).to_string())
    a, o = table["aggregate"], table["own_row"]
    wins = int((a < o).sum())
    adopt = bool(a.mean() < o.mean() and wins >= 6)
    print(f"aggregate MAE {a.mean():.3f} vs own row {o.mean():.3f}; better in {wins}/{len(a)} -> "
          f"{'ADOPT' if adopt else 'keep own row'}")

    summary = {m: {"mae": round(float(g.mae.mean()), 3), "bias": round(float(g.bias.mean()), 3),
                   "by_year": {int(r.year): round(float(r.mae), 3) for r in g.itertuples()}}
               for m, g in res.groupby("model")}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "national.json").write_text(json.dumps(
        {"fidelity_2005_2016": fidelity, "weighting": scheme, "backtest": summary,
         "years_better": wins, "adopt": adopt}, indent=2))
    if args.write_config:
        cfg = load_config()
        cfg["national"] = {"method": "aggregate" if adopt else "own_row", "weighting": scheme}
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"config national -> {cfg['national']}")


if __name__ == "__main__":
    main()
