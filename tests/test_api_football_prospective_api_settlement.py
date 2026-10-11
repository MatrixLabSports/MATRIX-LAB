import json
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_prospective_api_settlement import run


class FakeResponse:
    def __init__(self,payload):
        self._payload=payload
        self.content=json.dumps(payload).encode("utf-8")
    def json(self):
        return self._payload


class FakeSession:
    def __init__(self,payload):
        self.payload=payload
        self.calls=[]
    def get(self,url,headers,params,timeout):
        self.calls.append((url,headers,params,timeout))
        return FakeResponse(self.payload)


def _write_freeze(root:Path):
    p=root/"prospective_market_freeze"
    p.mkdir(parents=True)
    freeze={
        "rows":[{
            "fixture_id":"900",
            "target_key":"api_football:fixture:900",
            "kickoff_utc":"2026-09-28T18:00:00+00:00",
            "freeze_at_utc":"2026-09-28T12:00:00+00:00",
            "input_sha256":"a"*64,
            "home_team_id":"40",
            "home_team_name":"Home",
            "away_team_id":"41",
            "away_team_name":"Away",
            "frozen_research_probabilities":{"1x2":{"H":0.5,"D":0.25,"A":0.25},"over_2_5":0.55,"btts_v2":0.52},
        }]
    }
    (p/"freeze.json").write_text(json.dumps(freeze),encoding="utf-8")


def _provider(status="FT"):
    return {
        "errors":{},
        "response":[{
            "fixture":{"id":900,"status":{"short":status}},
            "teams":{"home":{"id":40,"name":"Home"},"away":{"id":41,"name":"Away"}},
            "score":{"fulltime":{"home":2,"away":1}},
            "goals":{"home":2,"away":1},
        }]
    }


def test_prospective_api_settlement_persists_only_standard_final(tmp_path):
    _write_freeze(tmp_path)
    session=FakeSession(_provider("FT"))
    result=run(tmp_path,"secret",datetime(2026,9,28,20,1,tzinfo=timezone.utc),session)
    assert result["status"]=="PASS"
    assert result["new_settlement_count"]==1
    assert result["ledger_final_count"]==1
    assert result["metrics_opened"] is False
    assert result["outcomes_used_for_metrics"]==0
    assert result["p_matrix_status"]=="NOT_GENERATED"
    assert result["real_money"]=="BLOCKED"
    ledger=(tmp_path/"prospective_market_freeze/settlement_ledger.jsonl").read_text()
    row=json.loads(ledger.strip())
    assert row["terminal_status"]=="FT"
    assert row["outcomes"]=={"1x2":"H","over_2_5":True,"btts":True}
    assert row["used_for_metrics"] is False


def test_nonfinal_result_never_enters_ledger(tmp_path):
    _write_freeze(tmp_path)
    session=FakeSession(_provider("NS"))
    result=run(tmp_path,"secret",datetime(2026,9,28,20,1,tzinfo=timezone.utc),session)
    assert result["new_settlement_count"]==0
    assert result["pending_count"]==1
    assert not (tmp_path/"prospective_market_freeze/settlement_ledger.jsonl").exists()
