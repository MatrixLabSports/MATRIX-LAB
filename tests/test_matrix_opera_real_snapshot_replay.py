"""Physical forensic replay of an actual Opera source capture into the research-only bridge.

Uses pinned source timestamps, never substitutes the test clock for the capture clock.
No fresh-price or production-certification claims.
"""
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from tools.matrix_opera_calendar_handoff import discover, persist

REPO = Path(__file__).resolve().parents[1]
DAY = "2026-11-06"
SOURCE = REPO / "evidence/browser_capture_inbox/opera_football/2026-11-06/20261105T093021Z.json"
INTAKE = REPO / "evidence/football_world_inventory/2026-11-06/MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"
PREVIOUS = REPO / "evidence/football_world_inventory/2026-11-06/MATRIX_SOFA_BROWSER_OBSERVATIONS.json"


def test_real_recent_opera_evidence_replaces_prior_snapshot_in_isolated_replay(tmp_path):
    assert SOURCE.is_file() and INTAKE.is_file() and PREVIOUS.is_file()
    fresh = json.loads(SOURCE.read_text(encoding="utf-8"))
    old = json.loads(PREVIOUS.read_text(encoding="utf-8"))
    new_time = datetime.fromisoformat(fresh["observed_at_utc"].replace("Z", "+00:00"))
    old_time = datetime.fromisoformat(old["observed_at_utc"].replace("Z", "+00:00"))
    # The operational snapshot may already have advanced to this very source.
    # Build a deliberately older isolated fixture to regression-test replacement.
    if old_time >= new_time:
        old["observed_at_utc"] = (new_time - timedelta(hours=2)).isoformat()
        old_time = datetime.fromisoformat(old["observed_at_utc"])
    assert new_time > old_time
    # This is an immutable forensic replay at the authentic capture time,
    # not an assertion that the snapshot remains current at test runtime.
    inbox = tmp_path / "evidence/browser_capture_inbox/opera_football" / DAY
    inbox.mkdir(parents=True)
    shutil.copy2(SOURCE, inbox / SOURCE.name)
    intake = json.loads(INTAKE.read_text(encoding="utf-8"))
    obs, receipt = discover(tmp_path, intake, DAY, now=new_time + timedelta(seconds=30))
    assert obs is not None
    assert len(obs["matches"]) >= 7
    assert obs["source_capture_relpath"].endswith(SOURCE.name)
    assert obs["source_capture_sha256"]
    target = tmp_path / "evidence/football_world_inventory" / DAY / "MATRIX_SOFA_BROWSER_OBSERVATIONS.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(old), encoding="utf-8")
    assert persist(target, obs, receipt, DAY) is True
    saved = json.loads(target.read_text(encoding="utf-8"))
    assert datetime.fromisoformat(saved["observed_at_utc"].replace("Z", "+00:00")) == new_time
    assert saved["signal_generation_authorized"] is False
    assert saved["quotes_verified"] is False
    assert saved["flashscore_corroborated"] is False
    assert receipt["status"] == "OPERA_SOURCE_IMPORTED_FOR_EXISTING_CALENDAR_CROSSCHECK"
