"""API tests against the local database (run `python -m ingest.load` and `python -m ingest.publish` first)."""
import math

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/v1/health").json() == {"ok": True}


def test_overview_has_nation_and_forecast():
    ov = client.get("/api/v1/overview").json()
    assert ov["nation"]["kind"] == "country"
    assert ov["nation"]["value"] > 0
    assert ov["nation"]["change_pct"] is not None
    assert ov["counts"]["zip"] > 20000


def test_metros_sorted_by_forecast():
    items = client.get("/api/v1/metros", params={"sort": "forecast", "limit": 20}).json()["items"]
    vals = [m["change_pct"] for m in items]
    assert vals == sorted(vals, reverse=True)
    assert all(m["kind"] == "msa" for m in items)


def test_metros_by_value_ascending_within_state():
    items = client.get("/api/v1/metros", params={"sort": "value_low", "state": "CA", "limit": 50}).json()["items"]
    vals = [m["value"] for m in items if m["value"] is not None]
    assert vals and vals == sorted(vals)
    assert all(m["state"] == "CA" for m in items)


def test_search_zip_and_metro():
    zips = client.get("/api/v1/search", params={"q": "03909"}).json()
    assert zips and zips[0]["name"] == "03909" and zips[0]["state"] == "ME"
    metros = client.get("/api/v1/search", params={"q": "Portland"}).json()
    assert any(m["name"] == "Portland, ME" for m in metros)


def test_zip_detail_decomposes_forecast():
    zid = client.get("/api/v1/search", params={"q": "03909"}).json()[0]["id"]
    d = client.get(f"/api/v1/regions/{zid}").json()
    r = d["region"]
    assert r["metro_name"] == "Portland, ME"
    assert r["low_pct"] <= r["change_pct"] <= r["high_pct"]
    # change = (1 + trend) * exp(relative) - 1, in percent; trend and relative add in log space.
    implied = ((1 + r["trend_pct"] / 100) * math.exp(r["relative_pct"] / 100) - 1) * 100
    assert abs(implied - r["change_pct"]) < 0.01
    assert 0 <= r["relative_rank_pct"] <= 100
    assert d["history"][0]["month"] <= d["history"][-1]["month"]
    assert d["heat"], "ZIP pages show their metro's Redfin activity"


def test_metro_zip_list_is_ranked_within_metro():
    metro = next(m for m in client.get("/api/v1/search", params={"q": "Portland, ME"}).json() if m["kind"] == "msa")
    items = client.get("/api/v1/zips", params={"metro_id": metro["id"], "limit": 1000}).json()["items"]
    assert all(z["metro_id"] == metro["id"] for z in items)
    ranks = [z["relative_rank_pct"] for z in items]
    assert ranks == sorted(ranks, reverse=True) and ranks[0] == 100


def test_unknown_region_404():
    assert client.get("/api/v1/regions/999999999").status_code == 404


def test_region_rent_own_or_metro():
    metro = client.get("/api/v1/metros", params={"limit": 1}).json()["items"][0]
    rent = client.get(f"/api/v1/regions/{metro['id']}").json()["rent"]
    assert rent["source"] == "own" and rent["rent"] > 0 and rent["change_1y_pct"] is not None
    # A ZIP Zillow doesn't track rent for falls back to its metro's rent.
    zips = client.get("/api/v1/zips", params={"metro_id": metro["id"], "sort": "size", "limit": 1000}).json()["items"]
    sources = {client.get(f"/api/v1/regions/{z['id']}").json()["rent"]["source"] for z in zips[-5:]}
    assert sources <= {"own", "metro"} and sources


def test_regions_by_ids_keeps_order_and_skips_unknown():
    metros = client.get("/api/v1/metros", params={"limit": 3}).json()["items"]
    ids = [metros[2]["id"], 999999999, metros[0]["id"]]
    got = client.get("/api/v1/regions", params={"ids": ",".join(map(str, ids))}).json()
    assert [r["id"] for r in got] == [metros[2]["id"], metros[0]["id"]]
    assert client.get("/api/v1/regions", params={"ids": "1,abc"}).status_code == 422


def test_track_record_summary_and_region_history():
    tr = client.get("/api/v1/track-record").json()
    overall = {r["level"]: r for r in tr["rows"] if r["period"] == "all"}
    assert set(overall) == {"metro", "zip"}
    # Ranges are empirical 80% quantiles of these same errors, so pooled coverage is close to 80%.
    assert all(70 < r["coverage_pct"] < 90 for r in overall.values())
    metro = client.get("/api/v1/metros", params={"limit": 1}).json()["items"][0]
    past = client.get(f"/api/v1/regions/{metro['id']}").json()["track_record"]
    assert len(past) > 20
    assert all(p["low_pct"] <= p["predicted_pct"] <= p["high_pct"] for p in past)
