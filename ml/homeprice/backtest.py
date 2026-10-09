"""Walk-forward backtest.

Test origins are grouped by calendar year. Each fold trains only on origins whose targets were fully
observed before the fold's first origin, so nothing from the test year (or the year it forecasts)
leaks into training. Errors are in percentage points of log change (x100).
"""
import numpy as np
import pandas as pd

from homeprice.features import HORIZON
from homeprice.models import RelativeModel, TrendModel, damped_momentum

TEST_YEARS = range(2017, 2026)
MIN_GROUP = 10     # ZIPs per (origin, parent) group for within-market ranking


def _rank_ic(df: pd.DataFrame, pred: str, actual: str, by: list[str]) -> float:
    ics = [g[pred].corr(g[actual], method="spearman") for _, g in df.groupby(by) if len(g) >= MIN_GROUP]
    return float(np.nanmean(ics))


def _errors(pred: np.ndarray, actual: np.ndarray) -> dict:
    e = (pred - actual) * 100
    return {"mae": float(np.abs(e).mean()), "bias": float(e.mean())}


def _folds(markets: pd.DataFrame, zips: pd.DataFrame, years=TEST_YEARS):
    for yr in years:
        mt = markets[(markets.origin.dt.year == yr) & markets.y.notna()]
        # A few parent metros have gaps in Zillow's series; rows with no relative target can't be scored.
        zt = zips[(zips.origin.dt.year == yr) & zips.y.notna() & zips.y_rel.notna()]
        if mt.empty or zt.empty:
            continue
        cutoff = min(mt.origin.min(), zt.origin.min()) - HORIZON
        yield yr, markets[markets.origin <= cutoff], mt, zips[zips.origin <= cutoff], zt


def run(markets: pd.DataFrame, zips: pd.DataFrame, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (per-year metrics, out-of-sample predictions for every test row)."""
    rows, preds = [], []
    for yr, mtr, mt, ztr, zt in _folds(markets, zips):
        mt = mt.copy()
        mt["pred_trend"] = TrendModel().fit(mtr).predict(mt)
        mt["pred_trend_core"] = TrendModel(groups=["base"]).fit(mtr).predict(mt)
        mt["pred_damped"] = damped_momentum(mt)
        metros = mt[mt.kind == "msa"]
        for name in ("pred_trend", "pred_trend_core", "pred_damped"):
            rows.append(dict(year=yr, level="metro", model=name[5:], n=len(metros),
                             **_errors(metros[name].to_numpy(), metros.y.to_numpy()),
                             rank_ic=_rank_ic(metros, name, "y", ["origin"])))

        zt = zt.copy()
        trend = mt.set_index(["region_id", "origin"]).pred_trend
        zt["pred_parent"] = trend.reindex(pd.MultiIndex.from_arrays([zt.parent_id, zt.origin])).to_numpy()
        zt = zt.dropna(subset=["pred_parent"])
        zt["pred_rel"] = RelativeModel().fit(ztr).predict(zt)
        zt["pred_rel_damped"] = damped_momentum(zt, "rel_r12")
        zt["pred_two_part"] = zt.pred_parent + zt.pred_rel
        zt["pred_damped"] = damped_momentum(zt)
        for name in ("pred_two_part", "pred_damped"):
            rows.append(dict(year=yr, level="zip", model=name[5:], n=len(zt),
                             **_errors(zt[name].to_numpy(), zt.y.to_numpy()),
                             rank_ic=_rank_ic(zt, name, "y", ["origin"])))
        # Within-market ranking: the headline. Zero relative is "every ZIP moves with its metro".
        for name in ("pred_rel", "pred_rel_damped"):
            rows.append(dict(year=yr, level="relative", model=name[5:], n=len(zt),
                             **_errors(zt[name].to_numpy(), zt.y_rel.to_numpy()),
                             rank_ic=_rank_ic(zt, name, "y_rel", ["origin", "parent_id"]),
                             **_decile_spread(zt, name)))
        rows.append(dict(year=yr, level="relative", model="zero", n=len(zt),
                         **_errors(np.zeros(len(zt)), zt.y_rel.to_numpy())))
        preds.append(zt[["region_id", "parent_id", "origin", "y", "y_rel", "pred_two_part", "pred_rel"]])
        preds.append(metros.assign(pred_two_part=metros.pred_trend)[["region_id", "origin", "y", "pred_two_part"]])
        log(f"  backtest {yr}: metro MAE {_errors(metros.pred_trend, metros.y)['mae']:.2f}, "
            f"zip MAE {_errors(zt.pred_two_part, zt.y)['mae']:.2f}")
    return pd.DataFrame(rows), pd.concat(preds, ignore_index=True)


def fold_split(panel: pd.DataFrame, years):
    """(year, train, test) for one panel, with the same leakage rule as the full backtest."""
    for yr in years:
        test = panel[(panel.origin.dt.year == yr) & panel.y.notna()]
        if "y_rel" in panel:
            test = test[test.y_rel.notna()]
        if test.empty:
            continue
        yield yr, panel[panel.origin <= test.origin.min() - HORIZON], test


def score_trend(markets: pd.DataFrame, make_model, years) -> pd.DataFrame:
    """Per-year metro MAE, bias and cross-metro rank correlation for a trend-model variant."""
    rows = []
    for yr, train, test in fold_split(markets, years):
        pred = make_model().fit(train).predict(test)
        m = (test.kind == "msa").to_numpy()
        t = test[m].assign(pred=pred[m])
        rows.append(dict(year=yr, **_errors(t.pred.to_numpy(), t.y.to_numpy()),
                         rank_ic=_rank_ic(t, "pred", "y", ["origin"])))
    return pd.DataFrame(rows)


def score_relative(zips: pd.DataFrame, make_model, years) -> pd.DataFrame:
    """Per-year error and within-metro ranking for a relative-model variant, scored on y_rel directly
    (no trend model involved, so variants are compared on the relative part alone)."""
    rows = []
    for yr, train, test in fold_split(zips, years):
        t = test.assign(pred=make_model().fit(train).predict(test))
        rows.append(dict(year=yr, **_errors(t.pred.to_numpy(), t.y_rel.to_numpy()),
                         rank_ic=_rank_ic(t, "pred", "y_rel", ["origin", "parent_id"]), **_decile_spread(t, "pred")))
    return pd.DataFrame(rows)


def _decile_spread(zt: pd.DataFrame, pred: str) -> dict:
    """Within each origin and market, realized relative change of the top vs bottom predicted decile,
    and how often a top-decile pick actually beat its market."""
    tops, bots = [], []
    for _, g in zt.groupby(["origin", "parent_id"]):
        if len(g) < MIN_GROUP:
            continue
        q = g[pred].rank(pct=True)
        tops.append(g.y_rel[q > 0.9])
        bots.append(g.y_rel[q <= 0.1])
    top, bot = pd.concat(tops), pd.concat(bots)
    return {"top_decile_beat": float((top > 0).mean()),
            "decile_spread": float((top.mean() - bot.mean()) * 100)}


def summarize(res: pd.DataFrame) -> dict:
    """Aggregate per-year metrics into the numbers shown on the Model page."""
    out = {}
    for (level, model), g in res.groupby(["level", "model"]):
        recent = g[g.year >= 2023]
        out.setdefault(level, {})[model] = {
            "mae": round(g.mae.mean(), 3), "bias": round(g.bias.mean(), 3),
            "mae_recent": round(recent.mae.mean(), 3),
            "rank_ic": round(g.rank_ic.mean(), 3) if g.rank_ic.notna().any() else None,
            "top_decile_beat": round(g.top_decile_beat.mean(), 3) if "top_decile_beat" in g and g.top_decile_beat.notna().any() else None,
            "decile_spread": round(g.decile_spread.mean(), 3) if "decile_spread" in g and g.decile_spread.notna().any() else None,
            "by_year": {int(r.year): round(r.mae, 3) for r in g.itertuples()},
        }
    return out
