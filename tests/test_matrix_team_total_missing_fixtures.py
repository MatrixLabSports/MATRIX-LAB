"""Regression: no verified future fixtures means no picks, not a crashed workflow."""
from datetime import datetime, timezone
from pathlib import Path

from tools.telegram_team_total_goals_picks import _merged_future_fixture_registry, build_candidates


def test_no_registry_is_auditable_empty_state(tmp_path):
    now=datetime(2026,10,30,12,0,tzinfo=timezone.utc)
    registry=_merged_future_fixture_registry(tmp_path,now)
    assert registry["fixture_registry_status"]=="NO_VERIFIED_FUTURE_FIXTURES"
    assert registry["events"]==[]
    assert registry["source_registry_count"]==0
    assert registry["merged_future_fixture_count"]==0


def test_missing_registry_does_not_create_candidates(tmp_path):
    now=datetime(2026,10,30,12,0,tzinfo=timezone.utc)
    registry=_merged_future_fixture_registry(tmp_path,now)
    candidates,audit=build_candidates({"rows":[{"fixture_id":"not-verified"}]},registry,repo_root=tmp_path,now_utc=now)
    assert candidates==[]
    assert audit["candidate_count"]==0
    assert audit["protections"]["real_money"]=="BLOCKED"
    assert audit["protections"]["automatic_wagering"] is False
