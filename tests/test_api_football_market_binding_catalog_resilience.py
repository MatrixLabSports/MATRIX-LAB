import json
from pathlib import Path

import tools.api_football_market_binding_catalog as catalog


class Resp:
    status_code=200
    def __init__(self,payload):
        self._payload=payload
    def json(self):
        return self._payload


def test_empty_provider_response_preserves_last_nonempty_catalog(monkeypatch,tmp_path):
    out=tmp_path/"catalog.json"
    previous={
        "schema":"MATRIX_API_FOOTBALL_MARKET_BINDING_CATALOG_V1",
        "observed_at_utc":"2026-10-24T10:00:00+00:00",
        "provider":"api_football",
        "catalog_count":338,
        "matches":{"TEAM_TOTAL_GOALS_HOME":[{"id":1,"name":"Home Team Total"}]},
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    out.write_text(json.dumps(previous))
    monkeypatch.setattr(catalog.requests,"get",lambda *a,**k:Resp({"response":[]}))
    r=catalog.run("k",out)
    assert r["catalog_count"]==338
    assert r["status"]=="STALE_LAST_NONEMPTY_FAIL_CLOSED"
    assert r["refresh_status"]=="PROVIDER_EMPTY_LAST_NONEMPTY_PRESERVED"
    persisted=json.loads(out.read_text())
    assert persisted["catalog_count"]==338
    assert persisted["real_money"]=="BLOCKED"


def test_empty_provider_response_without_history_is_fail_closed(monkeypatch,tmp_path):
    out=tmp_path/"catalog.json"
    monkeypatch.setattr(catalog.requests,"get",lambda *a,**k:Resp({"response":[]}))
    r=catalog.run("k",out)
    assert r["catalog_count"]==0
    assert r["status"]=="PROVIDER_EMPTY_FAIL_CLOSED"
    assert r["automatic_wagering"] is False
    assert r["real_money"]=="BLOCKED"


def test_daily_limit_is_classified_explicitly(monkeypatch,tmp_path):
    out=tmp_path/"catalog.json"
    payload={"errors":{"requests":"request limit reached for day"},"response":[]}
    monkeypatch.setattr(catalog.requests,"get",lambda *a,**k:Resp(payload))
    r=catalog.run("k",out)
    assert r["catalog_count"]==0
    assert r["status"]=="PROVIDER_LIMIT_REACHED_FAIL_CLOSED"
    assert r["provider_error_classification"]=="DAILY_REQUEST_LIMIT_REACHED"
    assert r["provider_errors"]==payload["errors"]
    assert r["real_money"]=="BLOCKED"
