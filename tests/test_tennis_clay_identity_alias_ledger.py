from __future__ import annotations

import pytest

from tools.tennis_clay_identity_alias_ledger import merge_ledger


def _cross(pid="rapidapi-tennis:player:11",cid="P001",status="PASS"):
    return {
        "ranking_cut":"20260921",
        "join_by_name_only":False,
        "real_money":"BLOCKED",
        "revision":"R1",
        "status":"PASS",
        "passed_events":1 if status=="PASS" else 0,
        "events":[{
            "event_id":"e1","provider_player_ids":[pid],
            "status":status,"blockers":[] if status=="PASS" else ["X"],
        }],
        "mappings":[{
            "provider_player_id":pid,
            "canonical_source_id":cid,
            "canonical_name":"Player One",
            "status":"PASS",
        }],
    }


def test_alias_ledger_accumulates_only_passed_identity_rows():
    first=merge_ledger(current=None,crosswalk=_cross(),source_sha256="a"*64)
    second=merge_ledger(
        current=first,
        crosswalk=_cross("rapidapi-tennis:player:22","P002"),
        source_sha256="b"*64,
    )
    assert first["mapping_count"]==1
    assert second["mapping_count"]==2
    assert second["added_count"]==1
    assert second["identity_only"] is True
    assert second["model_admission_forbidden"] is True
    assert second["metrics_opened"] is False
    assert second["real_money"]=="BLOCKED"


def test_alias_ledger_is_idempotent():
    first=merge_ledger(current=None,crosswalk=_cross(),source_sha256="a"*64)
    second=merge_ledger(current=first,crosswalk=_cross(),source_sha256="a"*64)
    assert second["mapping_count"]==1
    assert second["added_count"]==0


def test_alias_ledger_ignores_blocked_event_even_if_mapping_present():
    out=merge_ledger(current=None,crosswalk=_cross(status="BLOCKED"),source_sha256="a"*64)
    assert out["mapping_count"]==0


def test_alias_ledger_fails_closed_on_provider_collision():
    first=merge_ledger(current=None,crosswalk=_cross(),source_sha256="a"*64)
    with pytest.raises(ValueError,match="CLAY_ALIAS_PROVIDER_COLLISION"):
        merge_ledger(
            current=first,
            crosswalk=_cross("rapidapi-tennis:player:11","DIFFERENT"),
            source_sha256="b"*64,
        )
