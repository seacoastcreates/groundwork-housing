import os
from datetime import date
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.db import query

app = FastAPI(title="Housing Tracker API", version="0.1.0", docs_url="/api/v1/docs",
              openapi_url="/api/v1/openapi.json")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api/v1")

SOURCES = ("Zillow Home Value Index (Zillow Research); Redfin Data Center market tracker; "
           "Freddie Mac 30-year fixed rate via FRED")


class RegionSummary(BaseModel):
    id: int
    kind: str
    name: str
    state: str | None
    city: str | None
    county: str | None
    metro_id: int | None
    metro_name: str | None
    size_rank: int
    value: float | None
    change_1y_pct: float | None
    change_5y_pct: float | None
    change_pct: float | None
    low_pct: float | None
    high_pct: float | None
    trend_pct: float | None
    relative_pct: float | None
    relative_rank_pct: float | None    # within the parent metro: 100 = strongest forecast


class ValuePoint(BaseModel):
    month: date
    value: float


class HeatPoint(BaseModel):
    month: date
    months_of_supply: float | None
    median_dom: float | None
    sale_to_list: float | None
    price_drops: float | None


class ZillowPoint(BaseModel):
    target: date
    growth_pct: float


class Rent(BaseModel):
    month: date
    rent: float
    change_1y_pct: float | None
    source: Literal["own", "metro"]     # "metro" when Zillow doesn't track rent for the ZIP itself


class RegionDetail(BaseModel):
    region: RegionSummary
    history: list[ValuePoint]
    origin: date | None
    forecast_month: date | None
    heat: list[HeatPoint]
    zillow_forecast: list[ZillowPoint]
    zillow_base: date | None
    rent: Rent | None


class RegionList(BaseModel):
    total: int
    items: list[RegionSummary]


class Overview(BaseModel):
    nation: RegionSummary
    model_version: str | None
    origin: date | None
    horizon_months: int | None
    mortgage_rate: float | None
    mortgage_rate_1y_ago: float | None
    counts: dict[str, int]
    sources: str


SORTS = {"size": "size_rank ASC", "forecast": "change_pct DESC NULLS LAST",
         "forecast_low": "change_pct ASC NULLS LAST", "relative": "relative_pct DESC NULLS LAST",
         "relative_low": "relative_pct ASC NULLS LAST", "change_1y": "change_1y_pct DESC NULLS LAST",
         "change_1y_low": "change_1y_pct ASC NULLS LAST", "value": "value DESC NULLS LAST",
         "value_low": "value ASC NULLS LAST"}


def summaries(where: str, filters: str = "TRUE", sort: str = "size", limit: int = 50, offset: int = 0,
              **params) -> tuple[int, list[dict]]:
    sql = f"""
        SELECT *, count(*) OVER () AS _total FROM region_summary r WHERE ({where}) AND ({filters})
        ORDER BY {SORTS[sort]}, size_rank LIMIT :limit OFFSET :offset"""
    rows = query(sql, limit=limit, offset=offset, **params)
    total = rows[0].pop("_total") if rows else 0
    for r in rows[1:]:
        r.pop("_total")
    return total, rows


@api.get("/health")
def health() -> dict:
    query("SELECT 1")
    return {"ok": True}


@api.get("/overview", response_model=Overview)
def overview() -> dict:
    _, nation = summaries("r.kind = 'country'")
    run = query("SELECT model_version, origin, horizon FROM model_runs WHERE is_active")
    rates = query("SELECT month, rate FROM mortgage_rates ORDER BY month DESC LIMIT 13")
    counts = {r["kind"]: r["n"] for r in query("SELECT kind, count(*) AS n FROM regions GROUP BY kind")}
    return {"nation": nation[0], "model_version": run[0]["model_version"] if run else None,
            "origin": run[0]["origin"] if run else None, "horizon_months": run[0]["horizon"] if run else None,
            "mortgage_rate": rates[0]["rate"] if rates else None,
            "mortgage_rate_1y_ago": rates[12]["rate"] if len(rates) > 12 else None,
            "counts": counts, "sources": SOURCES}


@api.get("/metros", response_model=RegionList)
def metros(sort: Literal[tuple(SORTS)] = "size", limit: int = Query(50, le=1000), offset: int = 0,
           state: str | None = None) -> dict:
    where = "r.kind = 'msa'" + (" AND r.state = :state" if state else "")
    total, items = summaries(where, sort=sort, limit=limit, offset=offset, state=state)
    return {"total": total, "items": items}


@api.get("/zips", response_model=RegionList)
def zips(metro_id: int | None = None, state: str | None = None,
         sort: Literal[tuple(SORTS)] = "relative", limit: int = Query(50, le=1000), offset: int = 0,
         max_size_rank: int | None = Query(None, description="Only ZIPs at least this large by Zillow's size "
                                                             "rank (0 = largest); small ZIPs are noisier")) -> dict:
    where = "r.kind = 'zip'"
    if metro_id is not None:
        where += " AND r.metro_id = :metro_id"
    if state:
        where += " AND r.state = :state"
    filters = "change_pct IS NOT NULL" + (" AND size_rank <= :max_size_rank" if max_size_rank is not None else "")
    total, items = summaries(where, filters, sort=sort, limit=limit, offset=offset,
                             metro_id=metro_id, state=state, max_size_rank=max_size_rank)
    return {"total": total, "items": items}


@api.get("/search", response_model=list[RegionSummary])
def search(q: str = Query(..., min_length=2), limit: int = Query(12, le=50)) -> list[dict]:
    q = q.strip()
    where = """r.name ILIKE :prefix OR r.city ILIKE :prefix
               OR (r.kind = 'msa' AND r.name ILIKE :anywhere)"""
    _, items = summaries(where, sort="size", limit=limit, prefix=f"{q}%", anywhere=f"%{q}%")
    # Metros first, then ZIPs, each by size.
    return sorted(items, key=lambda r: (r["kind"] != "msa", r["size_rank"]))


@api.get("/regions", response_model=list[RegionSummary])
def regions(ids: str = Query(..., pattern=r"^\d+(,\d+){0,49}$", description="Up to 50 comma-separated region IDs")) -> list[dict]:
    """Summaries for a list of regions, in the order given (unknown IDs are skipped)."""
    wanted = [int(i) for i in ids.split(",")]
    _, items = summaries("r.id = ANY(:ids)", limit=len(wanted), ids=wanted)
    by_id = {r["id"]: r for r in items}
    return [by_id[i] for i in dict.fromkeys(wanted) if i in by_id]


@api.get("/regions/{region_id}", response_model=RegionDetail)
def region(region_id: int, since: int = Query(2000, ge=1990)) -> dict:
    found = summaries("r.id = :id", limit=1, id=region_id)[1]
    if not found:
        raise HTTPException(404, "Region not found")
    reg = found[0]
    history = query("SELECT month, value FROM home_values WHERE region_id = :id AND month >= make_date(:y, 1, 1) "
                    "ORDER BY month", id=region_id, y=since)
    heat_id = reg["metro_id"] or (region_id if reg["kind"] == "msa" else None)
    heat = query("""SELECT month, months_of_supply, median_dom, sale_to_list, price_drops FROM market_heat
                    WHERE region_id = :id AND month >= make_date(:y, 1, 1) ORDER BY month""",
                 id=heat_id or -1, y=since)
    zf = query("""SELECT target, growth_pct, base_month FROM zillow_forecasts WHERE region_id = :id
                  AND base_month = (SELECT max(base_month) FROM zillow_forecasts WHERE region_id = :id)
                  ORDER BY target""", id=region_id)
    rent = latest_rent(region_id, "own") or (latest_rent(reg["metro_id"], "metro") if reg["metro_id"] else None)
    run = query("SELECT origin, horizon FROM model_runs WHERE is_active")
    origin = run[0]["origin"] if run else None
    fmonth = date(origin.year + (origin.month - 1 + run[0]["horizon"]) // 12,
                  (origin.month - 1 + run[0]["horizon"]) % 12 + 1, 1) if run else None
    return {"region": reg, "history": history, "origin": origin, "forecast_month": fmonth, "heat": heat,
            "zillow_forecast": [{"target": r["target"], "growth_pct": r["growth_pct"]} for r in zf],
            "zillow_base": zf[0]["base_month"] if zf else None, "rent": rent}


@api.get("/model")
def model() -> dict:
    run = query("SELECT model_version, trained_at, origin, horizon, metrics FROM model_runs WHERE is_active")
    if not run:
        raise HTTPException(503, "No active model")
    return run[0]


def latest_rent(region_id: int, source: str) -> dict | None:
    rows = query("SELECT month, rent FROM rents WHERE region_id = :id ORDER BY month DESC LIMIT 13", id=region_id)
    if not rows:
        return None
    last, oldest = rows[0], rows[-1]
    months_apart = (last["month"].year - oldest["month"].year) * 12 + last["month"].month - oldest["month"].month
    change = (last["rent"] / oldest["rent"] - 1) * 100 if months_apart == 12 else None
    return {"month": last["month"], "rent": last["rent"], "change_1y_pct": change, "source": source}


app.include_router(api)
