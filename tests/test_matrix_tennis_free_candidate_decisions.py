"""Fail-closed, offline tests for per-match free-source Hard/Clay decisions."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from tools.matrix_tennis_free_candidate_decisions import evaluate


DAY = "2026-11-11"
UTC = timezone.utc


def write(root: Path, path: str, payload: dict):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
    p.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def fixture(root: Path):
    source_hash = {}
    for name, filename in (
        ("SOFASCORE", "sofascore_opera_full_link_observations.json"),
        ("FLASHSCORE", "flashscore_opera_full_link_observations.json"),
    ):
        source_hash[name] = write(root, f"evidence/tennis_calendar_physical/{DAY}/{filename}", {
            "schema": "MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1",
            "target_date_bogota": DAY, "source": name,
            "real_money": "BLOCKED",
            "canonical_fixture_export_authorized": False,
            "individual_match_date_verified": False,
            "collected_at_utc": "2026-11-11T08:10:00Z",
        })
    write(root, f"evidence/tennis_calendar_reconciliation/{DAY}/MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json", {
        "schema": "MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1",
        "target_date_bogota": DAY,
        "real_money": "BLOCKED",
        "source_capture_sha256": source_hash,
        "hard_holdout_admitted": 0, "clay_holdout_admitted": 0,
        "source_event_equivalence_certified": False,
        "matches": [
            {"source_name_token_key": "alcala de fuente gurri la max santiago",
             "sofascore_id": "17489783", "flashscore_mid": "dp2w9DQh",
             "sofascore_url": "https://www.sofascore.com/es/tennis/match/example#id:17489783",
             "flashscore_url": "https://www.flashscore.co/partido/tenis/example/?mid=dp2w9DQh"},
        ],
    })
    tennis = {
        "request": {"http_status": 200}, "authenticated": True,
        "world_complete": False,
        "d0_d2_hard_rows": 1, "d0_d2_clay_rows": 1,
        "d0_d2_hard_candidates": [
            {"provider_match_id": 21, "surface": "hard", "status": "scheduled",
             "player1_name": "A. One", "player2_name": "B. Two",
             "start_time_utc": "2026-11-11T17:00:00Z", "bogota_date": DAY},
        ],
        "d0_d2_clay_candidates": [
            {"provider_match_id": 22, "surface": "clay", "status": "scheduled",
             "player1_name": "S. De La Fuente", "player2_name": "M. Alcala Gurri",
             "start_time_utc": "2026-11-11T15:00:00Z", "bogota_date": DAY},
        ],
    }
    write(root, f"evidence/free_providers/{DAY}/MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT.json", {
        "schema": "MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT_V1",
        "target_date_bogota": DAY, "generated_at_utc": "2026-11-11T08:00:00Z",
        "status": "PASS", "providers": {"live_tennis_api": tennis},
        "protections": {"real_money": "BLOCKED"},
        "promotion": {"automatic_model_feed": False, "automatic_counter_increment": False},
    })


def test_hard_clay_triage_matches_provenance_no_false_holdout(tmp_path):
    fixture(tmp_path)
    r = evaluate(tmp_path, DAY, datetime(2026, 11, 11, 9, tzinfo=UTC))
    assert r["hard_provider_candidates"] == 1
    assert r["clay_provider_candidates"] == 1
    assert r["two_browser_name_hints_only"] == 1
    assert r["hard_new_holdout_admissions"] == r["clay_new_holdout_admissions"] == 0
    assert r["model_parameters_modified"] is False
    assert r["real_money"] == "BLOCKED"
    assert all(x["official_holdout_admitted"] is False for x in r["records"])
    assert all("CURRENT_PREMATCH_PIT_HISTORY_NOT_CERTIFIED" in x["blockers"] for x in r["records"])
    assert r["records"][1]["browser_name_hint_only"]["sofascore_id"] == "17489783"


def test_tampered_browser_capture_never_passes(tmp_path):
    fixture(tmp_path)
    path = tmp_path / f"evidence/tennis_calendar_physical/{DAY}/sofascore_opera_full_link_observations.json"
    with path.open("a") as f:
        f.write("invalid_source_tamper")
    with pytest.raises(ValueError, match="BROWSER_SOURCE_SHA_OR_GOVERNANCE_MISMATCH"):
        evaluate(tmp_path, DAY, datetime(2026, 11, 11, 9, tzinfo=UTC))


def test_after_kickoff_never_backfills(tmp_path):
    fixture(tmp_path)
    r = evaluate(tmp_path, DAY, datetime(2026, 11, 11, 18, tzinfo=UTC))
    assert all("PROSPECTIVE_WINDOW_CLOSED" in x["blockers"] for x in r["records"])
    assert all(x["official_holdout_admitted"] is False for x in r["records"])
