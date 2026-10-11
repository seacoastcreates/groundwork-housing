"""Feature-group ablation for both models, with an adoption rule fixed before looking at results.

Each candidate group is added on its own to the current baseline and scored with the walk-forward
backtest (2017-2025). Adoption rule:
  trend:    lower mean metro MAE, lower MAE in at least 6 of 9 years, and 2023+ MAE not worse
  relative: higher mean within-metro rank correlation, higher in at least 6 of 9 years, and MAE not
            more than 1% worse
Groups that pass are then combined, and the combination is kept only if it also passes against the
baseline and beats the best single group. Results go to reports/ablation.json; adopted groups are
written to homeprice/config.json.

    python -u ablation.py [--write-config]
"""
import argparse
import json
import math
import time
from pathlib import Path

import pandas as pd

from homeprice import backtest
from homeprice.models import CONFIG, RelativeModel, TrendModel, load_config
from homeprice.pipeline import build

REPORTS = Path(__file__).resolve().parent / "reports"
YEARS = backtest.TEST_YEARS
REL_ROWS = 600_000      # same cap for every relative variant, to keep the ablation affordable


def summarize(df: pd.DataFrame) -> dict:
    r4 = lambda v: round(float(v), 4)
    out = {"mae": r4(df.mae.mean()), "mae_recent": r4(df[df.year >= 2023].mae.mean()),
           "rank_ic": r4(df.rank_ic.mean()),
           "by_year": {int(r.year): {"mae": r4(r.mae), "rank_ic": r4(r.rank_ic)} for r in df.itertuples()}}
    if "top_decile_beat" in df:
        out["top_decile_beat"] = r4(df.top_decile_beat.mean())
        out["decile_spread"] = r4(df.decile_spread.mean())
    return out


def passes(kind: str, cand: pd.DataFrame, base: pd.DataFrame) -> tuple[bool, int, int]:
    """Judged on the years where the variant changes any prediction. A sparse group (Zillow market data
    from 2018, rent from 2015) leaves earlier years identical to the baseline, so it can't win or lose
    them; it must win two-thirds of the years where it is active. For a group active in all 9 test years
    this is the original 6-of-9 rule. (Amended after the first run, which also had a gating bug that
    dropped Redfin from rows without the new group; both are disclosed on the Model page.)"""
    c, b = cand.set_index("year"), base.set_index("year")
    active = (c.mae - b.mae).abs() > 1e-9
    c, b = c[active], b[active]
    n = int(active.sum())
    need = math.ceil(n * 2 / 3)
    if n == 0:
        return False, 0, 0
    if kind == "trend":
        wins = int((c.mae < b.mae).sum())
        recent_c, recent_b = c[c.index >= 2023].mae.mean(), b[b.index >= 2023].mae.mean()
        ok = c.mae.mean() < b.mae.mean() and wins >= need and not recent_c > recent_b
    else:
        wins = int((c.rank_ic > b.rank_ic).sum())
        ok = c.rank_ic.mean() > b.rank_ic.mean() and wins >= need and c.mae.mean() <= b.mae.mean() * 1.01
    return bool(ok), wins, n


def run_kind(kind: str, panel: pd.DataFrame, baseline: list[str], candidates: list[list[str]], extra: dict):
    make = (lambda g: (lambda: TrendModel(groups=g, params={}))) if kind == "trend" else \
           (lambda g: (lambda: RelativeModel(groups=g, params={}, max_rows=REL_ROWS)))
    score = backtest.score_trend if kind == "trend" else backtest.score_relative
    t0 = time.time()
    base = score(panel, make(baseline), YEARS)
    report = {"baseline": {"groups": baseline, **summarize(base)}, "variants": {}}
    print(f"[{kind}] baseline {baseline}: MAE {base.mae.mean():.3f} rank {base.rank_ic.mean():.3f} "
          f"({time.time() - t0:.0f}s)", flush=True)
    passed, results = [], {}

    def evaluate(label: str, groups: list[str]):
        t = time.time()
        df = score(panel, make(groups), YEARS)
        ok, wins, n = passes(kind, df, base)
        results[label] = df
        report["variants"][label] = {"groups": groups, "passes": ok, "years_better": wins, "years_active": n,
                                     **summarize(df)}
        print(f"[{kind}] {label:<22} MAE {df.mae.mean():.3f} (2023+ {df[df.year >= 2023].mae.mean():.3f}) "
              f"rank {df.rank_ic.mean():.3f}  better in {wins}/{n} active  {'PASS' if ok else 'fail'} "
              f"({time.time() - t:.0f}s)", flush=True)
        return ok

    for groups in candidates:
        label = "+" + "+".join(g for g in groups if g not in baseline)
        if evaluate(label, groups) and len(groups) == len(baseline) + 1:
            passed.append(groups[-1])
    for label, groups in extra.items():
        evaluate(label, groups)

    adopted = baseline
    if passed:
        singles = {g: report["variants"][f"+{g}"] for g in passed}
        best_key = "mae" if kind == "trend" else "rank_ic"
        best = (min if kind == "trend" else max)(singles, key=lambda g: singles[g][best_key])
        adopted = baseline + [best]
        if len(passed) > 1:
            combo = baseline + passed
            label = "+" + "+".join(passed)
            ok = evaluate(label, combo)
            better = (report["variants"][label][best_key] < singles[best][best_key]) if kind == "trend" \
                else (report["variants"][label][best_key] > singles[best][best_key])
            if ok and better:
                adopted = combo
    report["adopted"] = adopted
    print(f"[{kind}] adopted: {adopted}", flush=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-config", action="store_true")
    ap.add_argument("--only", choices=["trend", "relative", "relative2", "retest"])
    args = ap.parse_args()
    mp, zp, _ = build()
    cfg = load_config()
    REPORTS.mkdir(exist_ok=True)
    out_path = REPORTS / "ablation.json"
    out = json.loads(out_path.read_text()) if out_path.exists() else {}

    if args.only in (None, "trend"):
        base = ["base", "heat"]
        out["trend"] = run_kind("trend", mp, base, [base + [g] for g in ("shape", "afford", "rent", "zheat",
                                                                          "unemp", "macro")],
                                extra={"zheat instead of heat": ["base", "zheat"], "no market activity": ["base"]})
        out_path.write_text(json.dumps(out, indent=2))
    if args.only in (None, "relative"):
        base = ["base"]
        out["relative"] = run_kind("relative", zp, base, [base + [g] for g in ("shape", "afford", "tiers", "rent")],
                                   extra={})
        out_path.write_text(json.dumps(out, indent=2))
    if args.only in (None, "relative2"):
        # Round 2 (groups added later: unemployment, national macro), on top of round 1's winners.
        base = out["relative"]["adopted"]
        out["relative_round2"] = run_kind("relative", zp, base, [base + [g] for g in ("unemp", "macro")], extra={})
        out_path.write_text(json.dumps(out, indent=2))

    if args.only == "retest":
        # Round 3: re-tests with fixes, against the currently adopted models. Sparse boosters now need 3 years
        # of training history (models.MIN_SPARSE_YEARS); unemployment comes clipped to pre-2020 ranges or
        # with pandemic-era readings masked.
        base = cfg["trend_groups"]
        out["trend_retest"] = run_kind("trend", mp, base, [base + ["zheat"], base + ["unemp_clip"],
                                                           base + ["unemp_mask"]], extra={})
        out_path.write_text(json.dumps(out, indent=2))
        base = cfg["relative_groups"]
        out["relative_retest"] = run_kind("relative", zp, base, [base + ["unemp_clip"], base + ["unemp_mask"]],
                                          extra={})
        out_path.write_text(json.dumps(out, indent=2))

    if args.write_config:
        if "trend" in out:
            cfg["trend_groups"] = out["trend"]["adopted"]
        if "relative" in out:
            cfg["relative_groups"] = out.get("relative_round2", out["relative"])["adopted"]
        for kind in ("trend", "relative"):
            if f"{kind}_retest" in out:
                cfg[f"{kind}_groups"] = out[f"{kind}_retest"]["adopted"]
        CONFIG.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"config updated: {cfg}")


if __name__ == "__main__":
    main()
