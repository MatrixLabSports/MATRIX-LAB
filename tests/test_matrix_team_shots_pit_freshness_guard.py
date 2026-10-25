from datetime import datetime, timezone
from pathlib import Path
import json
import tools.matrix_team_shots_pit_freshness_guard as mod

def test_stale_pit_requires_refresh(tmp_path,monkeypatch):
    m=tmp_path/"manifest.json"
    a=tmp_path/"audit.json"
    m.write_text(json.dumps({
        "generated_at_utc":"2026-10-02T23:18:42+00:00",
        "lanes":{"TEAM_TOTAL_SHOTS":{"row_count":274,"train_count":224,"validation_count":50}}
    }),encoding="utf-8")
    a.write_text(json.dumps({
        "future_source_fixture_candidates":323,
        "eligible_future_unique_fixtures":0,
        "blocked_reason_counts":{"INSUFFICIENT_PERSISTED_TEAM_SHOTS_PIT_HISTORY":323}
    }),encoding="utf-8")
    monkeypatch.setattr(mod,"PIT_MANIFEST",m)
    monkeypatch.setattr(mod,"TEAM_SHOTS_AUDIT",a)
    r=mod.build(datetime(2026,10,25,22,0,tzinfo=timezone.utc))
    assert r["pit_stale"] is True
    assert r["requires_causal_pit_refresh"] is True
    assert r["protections"]["minimum_history_not_lowered"] is True
    assert r["protections"]["post_start_backfill"] is False

def test_fresh_pit_allows_normal_bridge(tmp_path,monkeypatch):
    m=tmp_path/"manifest.json"
    a=tmp_path/"audit.json"
    m.write_text(json.dumps({
        "generated_at_utc":"2026-10-25T20:00:00+00:00",
        "lanes":{"TEAM_TOTAL_SHOTS":{"row_count":500,"train_count":450,"validation_count":50}}
    }),encoding="utf-8")
    a.write_text(json.dumps({
        "future_source_fixture_candidates":40,
        "eligible_future_unique_fixtures":2,
        "blocked_reason_counts":{"INSUFFICIENT_PERSISTED_TEAM_SHOTS_PIT_HISTORY":20}
    }),encoding="utf-8")
    monkeypatch.setattr(mod,"PIT_MANIFEST",m)
    monkeypatch.setattr(mod,"TEAM_SHOTS_AUDIT",a)
    r=mod.build(datetime(2026,10,25,21,0,tzinfo=timezone.utc))
    assert r["pit_stale"] is False
    assert r["requires_causal_pit_refresh"] is False
