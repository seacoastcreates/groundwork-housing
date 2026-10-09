"""Tune LightGBM hyperparameters with Optuna, without tuning on the years we report.

Optuna searches using only the 2017-2021 test years (walk-forward, same leakage rule as the backtest).
The best parameters and the defaults are then both scored on 2022-2025, which the search never saw,
and the tuned set is adopted only if it wins there:
  trend:    lower holdout metro MAE
  relative: higher holdout within-metro rank correlation, and MAE not more than 1% worse
Results go to reports/tuning.json (the study itself to reports/optuna.db); adopted parameters are
written to homeprice/config.json with --write-config.

    python -u tune.py [--trials-trend 60] [--trials-relative 30] [--write-config]
"""
import argparse
import json
import time
from pathlib import Path

import optuna
import pandas as pd

from homeprice import backtest
from homeprice.models import CONFIG, DEFAULT_PARAMS, MAX_TRAIN_ROWS, RelativeModel, TrendModel, load_config
from homeprice.pipeline import build

REPORTS = Path(__file__).resolve().parent / "reports"
TUNE_YEARS = {"trend": list(range(2017, 2022)), "relative": [2017, 2019, 2021]}
HOLDOUT_YEARS = list(range(2022, 2026))
TUNE_REL_ROWS = 300_000     # subsample while searching; the holdout comparison uses the full cap


def space(trial: optuna.Trial, kind: str) -> dict:
    objective = trial.suggest_categorical("objective", ["regression", "huber", "regression_l1"])
    return {
        "objective": objective,
        "n_estimators": trial.suggest_int("n_estimators", 100, 1500, log=True),
        "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.15, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 7, 255, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 10 if kind == "trend" else 50,
                                               400 if kind == "trend" else 3000, log=True),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "subsample_freq": 1,
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 30.0, log=True),
        # Huber's delta is in target units (log change); default 1.0 would make it plain L2 here.
        **({"alpha": trial.suggest_float("huber_delta", 0.005, 0.1, log=True)}
           if objective == "huber" else {}),
    }


def make(kind: str, params: dict, max_rows: int):
    if kind == "trend":
        return lambda: TrendModel(params=params, max_rows=max_rows)
    return lambda: RelativeModel(params=params, max_rows=max_rows)


def fold_score(kind: str, df: pd.DataFrame) -> float:
    """Lower is better for Optuna's minimize direction."""
    return float(df.mae.iloc[0]) if kind == "trend" else -float(df.rank_ic.iloc[0])


def tune(kind: str, panel: pd.DataFrame, trials: int, storage: str) -> optuna.Study:
    score = backtest.score_trend if kind == "trend" else backtest.score_relative
    rows = MAX_TRAIN_ROWS if kind == "trend" else TUNE_REL_ROWS
    years = TUNE_YEARS[kind]

    def objective(trial: optuna.Trial) -> float:
        params = space(trial, kind)
        vals = []
        for i, yr in enumerate(years):
            vals.append(fold_score(kind, score(panel, make(kind, params, rows), [yr])))
            trial.report(sum(vals) / len(vals), i)
            if trial.should_prune():
                raise optuna.TrialPruned()
        return sum(vals) / len(vals)

    study = optuna.create_study(study_name=f"{kind}-{time.strftime('%Y%m%d-%H%M')}", storage=storage,
                                direction="minimize", sampler=optuna.samplers.TPESampler(seed=0),
                                pruner=optuna.pruners.MedianPruner(n_startup_trials=8, n_warmup_steps=1))
    # Seed the search with the current defaults so "tuned" can never start worse than them.
    study.enqueue_trial({k: v for k, v in DEFAULT_PARAMS.items() if k != "subsample_freq"} | {"objective": "regression"})
    t0 = time.time()

    def progress(st: optuna.Study, tr: optuna.trial.FrozenTrial):
        if tr.state == optuna.trial.TrialState.COMPLETE:
            print(f"[{kind}] trial {tr.number:>3} value {tr.value:+.4f}  best {st.best_value:+.4f}  "
                  f"({time.time() - t0:.0f}s)", flush=True)

    study.optimize(objective, n_trials=trials, callbacks=[progress])
    return study


def best_params(study: optuna.Study) -> dict:
    p = dict(study.best_params)
    if "huber_delta" in p:
        p["alpha"] = p.pop("huber_delta")
    return {**p, "subsample_freq": 1}


def holdout(kind: str, panel: pd.DataFrame, tuned: dict) -> dict:
    score = backtest.score_trend if kind == "trend" else backtest.score_relative
    res = {}
    for label, params in (("default", {}), ("tuned", tuned)):
        df = score(panel, make(kind, params, MAX_TRAIN_ROWS), HOLDOUT_YEARS)
        res[label] = {"mae": round(float(df.mae.mean()), 4), "rank_ic": round(float(df.rank_ic.mean()), 4),
                      "by_year": {int(r.year): {"mae": round(float(r.mae), 4), "rank_ic": round(float(r.rank_ic), 4)}
                                  for r in df.itertuples()}}
        print(f"[{kind}] holdout {label}: MAE {res[label]['mae']:.3f} rank {res[label]['rank_ic']:.3f}", flush=True)
    d, t = res["default"], res["tuned"]
    res["adopt"] = bool((t["mae"] < d["mae"]) if kind == "trend" else
                        (t["rank_ic"] > d["rank_ic"] and t["mae"] <= d["mae"] * 1.01))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials-trend", type=int, default=60)
    ap.add_argument("--trials-relative", type=int, default=30)
    ap.add_argument("--only", choices=["trend", "relative"])
    ap.add_argument("--write-config", action="store_true")
    args = ap.parse_args()
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    REPORTS.mkdir(exist_ok=True)
    storage = f"sqlite:///{REPORTS / 'optuna.db'}"
    mp, zp, _ = build()
    cfg = load_config()
    out_path = REPORTS / "tuning.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}

    for kind, panel, trials in (("trend", mp, args.trials_trend), ("relative", zp, args.trials_relative)):
        if args.only and args.only != kind:
            continue
        study = tune(kind, panel, trials, storage)
        params = best_params(study)
        states = pd.Series([t.state.name for t in study.trials]).value_counts().astype(int).to_dict()
        imp = optuna.importance.get_param_importances(study) if states.get("COMPLETE", 0) > 2 else {}
        out[kind] = {"study": study.study_name, "groups": cfg[f"{kind}_groups"], "tune_years": TUNE_YEARS[kind],
                     "holdout_years": HOLDOUT_YEARS, "trials": states, "best_tune_value": study.best_value,
                     "best_params": params, "param_importance": {k: round(float(v), 3) for k, v in imp.items()},
                     "holdout": holdout(kind, panel, params)}
        out_path.write_text(json.dumps(out, indent=2))
        if args.write_config:
            cfg[f"{kind}_params"] = params if out[kind]["holdout"]["adopt"] else {}
            CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
            print(f"[{kind}] {'adopted tuned' if out[kind]['holdout']['adopt'] else 'kept default'} params", flush=True)


if __name__ == "__main__":
    main()
