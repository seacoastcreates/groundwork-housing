"""FRED client: the API transport is exercised with a canned response (no key or network needed)."""
import json

from ingest import fred


def test_api_transport_parses_and_skips_unknown(monkeypatch):
    calls = []

    def fake_open(url, timeout=120):
        calls.append(url)
        if "series_id=NOPE" in url:
            return None
        return json.dumps({"observations": [{"date": "2026-07-01", "value": "4.2"},
                                            {"date": "2026-08-01", "value": "."}]}).encode()

    monkeypatch.setenv("FRED_API_KEY", "test-key")
    monkeypatch.setattr(fred, "_open", fake_open)
    monkeypatch.setattr(fred, "API_INTERVAL", 0)
    got = fred.fetch(["UNRATE", "NOPE"])
    assert [s.name for s in got] == ["UNRATE"]
    assert got[0].iloc[0] == 4.2 and got[0].isna().iloc[1]
    assert all("api.stlouisfed.org" in u and "file_type=json" in u for u in calls)


def test_no_key_uses_fredgraph(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    seen = []
    monkeypatch.setattr(fred, "_open", lambda url, timeout=120: seen.append(url) or b"observation_date,A,B\n2026-01-01,1,2\n")
    monkeypatch.setattr(fred, "GRAPH_INTERVAL", 0)
    got = fred.fetch(["A", "B"])
    assert [s.name for s in got] == ["A", "B"] and len(seen) == 1 and "fredgraph" in seen[0]
