from __future__ import annotations

import json

from tools.live_tennis_paid_settlement import _final_pair, settle_ledger
from tools.live_tennis_paid_cumulative_gate import build


class FakeClient:
    def __init__(self):
        self.request_count=0
    def fixture_by_match_key(self, match_key):
        self.request_count+=1
        return {"result":[{
            "event_key":str(match_key),
            "event_status":"Finished",
            "event_final_result":"2 - 0",
        }]}


def test_final_pair_and_same_provider_settlement():
    assert _final_pair("2 - 0")== (2,0)
    ledger={
        "states":[{
            "state_key":"api_tennis:123:state:a",
            "match_id":"123",
            "event_type":"Atp Singles",
            "quality_state_valid":True,
            "settlement_status":"PENDING_FINAL",
            "label_opened":False,
        }]
    }
    out=settle_ledger(ledger=ledger,client=FakeClient(),max_requests=5)
    row=out["states"][0]
    assert row["settlement_status"]=="FINAL_STANDARD"
    assert row["label_opened"] is True
    assert row["p1_match_win"]==1
    assert row["settlement_identity"]=="EXACT_PROVIDER_EVENT_KEY"
    assert out["provider_native_settlement"]["cross_provider_equivalence_required"] is False
    assert out["provider_native_settlement"]["real_money"]=="BLOCKED"


def test_paid_gate_counts_unique_quality_final_matches(tmp_path):
    d=tmp_path/"2026-10-12"
    d.mkdir()
    ledger={
        "operational_date_bogota":"2026-10-12",
        "unique_match_count":1,
        "unique_state_count":2,
        "states":[
            {
                "state_key":"api_tennis:123:state:a",
                "match_id":"123",
                "event_type":"Atp Singles",
                "quality_state_valid":True,
                "settlement_status":"FINAL_STANDARD",
                "label_opened":True,
                "p1_match_win":1,
                "settlement_identity":"EXACT_PROVIDER_EVENT_KEY",
            },
            {
                "state_key":"api_tennis:123:state:b",
                "match_id":"123",
                "event_type":"Atp Singles",
                "quality_state_valid":True,
                "settlement_status":"FINAL_STANDARD",
                "label_opened":True,
                "p1_match_win":1,
                "settlement_identity":"EXACT_PROVIDER_EVENT_KEY",
            },
        ],
    }
    p=d/"MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1.json"
    p.write_text(json.dumps(ledger),encoding="utf-8")
    out=build(tmp_path,tmp_path/"gate.json")
    lane=out["lanes"]["api_tennis|atp_singles"]
    assert lane["unique_match_count"]==1
    assert lane["settled_quality_valid_unique_match_count"]==1
    assert lane["gates"]["1"]["status"]=="OPEN"
    assert out["cross_provider_equivalence_required"] is False
    assert out["metrics_status"]=="SEALED"
    assert out["protections"]["real_money"]=="BLOCKED"
