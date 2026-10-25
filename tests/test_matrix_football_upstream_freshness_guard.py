from datetime import datetime, timezone
from pathlib import Path
import json

import tools.matrix_football_upstream_freshness_guard as mod


def test_stale_canonical_is_explicit_blocker_not_zero_demand(tmp_path,monkeypatch):
    manifest=tmp_path/"manifest.json"
    period=tmp_path/"period.json"
    manifest.write_text(json.dumps({
        "source_fixture_capture_at_utc":"2026-10-23T04:05:00+00:00"
    }),encoding="utf-8")
    period.write_text(json.dumps({
        "future_source_fixture_candidates":340,
        "feature_eligible_future_unique_fixtures":288,
        "eligible_future_unique_fixtures":0,
        "duplicate_existing_lane_rows":2304,
        "blocked_count":52
    }),encoding="utf-8")
    monkeypatch.setattr(mod,"CANONICAL_MANIFEST",manifest)
    monkeypatch.setattr(mod,"PERIOD_AUDIT",period)
    r=mod.build(datetime(2026,10,25,17,45,tzinfo=timezone.utc))
    assert r["canonical_stale"] is True
    assert r["upstream_state"]=="STALE_UPSTREAM_BLOCKS_NEW_EVENT_CONVERSION"
    assert r["next_required_action"]=="REFRESH_GOVERNED_DAILY_OR_HORIZON_UPSTREAM_BEFORE_DIAGNOSING_NO_NEW_EVENTS"
    assert r["protections"]["stale_upstream_never_interpreted_as_zero_demand"] is True


def test_fresh_upstream_with_only_duplicates_is_not_pipeline_failure(tmp_path,monkeypatch):
    manifest=tmp_path/"manifest.json"
    period=tmp_path/"period.json"
    manifest.write_text(json.dumps({
        "source_fixture_capture_at_utc":"2026-10-25T16:00:00+00:00"
    }),encoding="utf-8")
    period.write_text(json.dumps({
        "future_source_fixture_candidates":100,
        "feature_eligible_future_unique_fixtures":80,
        "eligible_future_unique_fixtures":0,
        "duplicate_existing_lane_rows":640,
        "blocked_count":20
    }),encoding="utf-8")
    monkeypatch.setattr(mod,"CANONICAL_MANIFEST",manifest)
    monkeypatch.setattr(mod,"PERIOD_AUDIT",period)
    r=mod.build(datetime(2026,10,25,17,0,tzinfo=timezone.utc))
    assert r["canonical_stale"] is False
    assert r["upstream_state"]=="FRESH_UPSTREAM_ALL_ELIGIBLE_EVENTS_ALREADY_SEEN"
