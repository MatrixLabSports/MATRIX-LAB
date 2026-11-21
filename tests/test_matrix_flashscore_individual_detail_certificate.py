"""Strict individual Flashscore detail regressions and authentic Opera replay."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from tools.matrix_flashscore_individual_detail_certificate import verify, scan

DAY = "2026-11-05"
PATH = "evidence/browser_capture_inbox/opera_football_flash_detail/2026-11-05/20261105T093954Z.json"


def doc():
    return {
      "schema": "MATRIX_FLASH_OPERA_INDIVIDUAL_DETAIL_CAPTURE_V1",
      "source": "FLASHSCORE", "target_date_bogota": DAY,
      "capture_method": "OPERA_CONNECTOR_ACCESSIBILITY_TREE",
      "display_timezone": "America/Bogota",
      "event_url": "https://www.flashscore.co/partido/futbol/ac-milan-8Sa8HInO/ferencvaros-pKS9M7R7/?mid=hUC4nhiT",
      "event_mid": "hUC4nhiT", "home": "AC Milan", "away": "Ferencváros",
      "visible_event_datetime": "05.11.2026 12:45",
      "observed_at_utc": "2026-11-05T09:39:54.010Z",
      "signal_generation_authorized": False, "automatic_wagering": False,
      "real_money": "BLOCKED",
    }


def test_strict_individual_detail_is_research_only():
    result = verify(doc(), expected_day=DAY, now=datetime(2026, 11, 5, 9, 45, tzinfo=timezone.utc))
    assert result["event_mid"] == "hUC4nhiT"
    assert result["kickoff_utc_from_declared_display_timezone"] == "2026-11-05T17:45:00+00:00"
    assert result["cross_provider_fixture_identity_verified"] is False
    assert result["model_probability_authorized"] is False
    assert result["telegram_signal_authorized"] is False


@pytest.mark.parametrize("change", [
    {"event_mid": "not_equal"},
    {"visible_event_datetime": "jueves, 5 de noviembre de 2026"},
    {"visible_event_datetime": "06.11.2026 12:45"},
    {"display_timezone": "UTC"},
    {"real_money": "ENABLED"},
    {"signal_generation_authorized": True},
    {"event_url": "https://evil.example/partido/futbol/a/b/?mid=hUC4nhiT"},
    {"observed_at_utc": "2026-11-05T18:00:00Z"},
    {"observed_at_utc": "2026-11-04T08:00:00Z"},
])
def test_unsafe_missing_or_stale_detail_fails_closed(change):
    check_time = (datetime(2026, 11, 5, 19, 0, tzinfo=timezone.utc)
                  if change.get("observed_at_utc") == "2026-11-05T18:00:00Z"
                  else datetime(2026, 11, 5, 9, 45, tzinfo=timezone.utc))
    with pytest.raises((ValueError, TypeError)):
        verify({**doc(), **change}, expected_day=DAY, now=check_time)


def test_actual_connected_opera_detail_file_can_be_read(tmp_path):
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / PATH
    original = json.loads(source.read_text(encoding="utf-8"))
    observed = datetime.fromisoformat(original["observed_at_utc"].replace("Z", "+00:00"))
    dest = tmp_path / PATH
    dest.parent.mkdir(parents=True)
    dest.write_bytes(source.read_bytes())
    result = scan(tmp_path, DAY, now=observed + timedelta(seconds=30))
    assert result["verified_individual_count"] == 1
    assert result["events"][0]["source_file_sha256"]
    assert result["telegram_signal_authorized"] is False


def test_genuine_sofa_and_flashscore_detail_produce_two_source_research_only_pair(tmp_path):
    from pathlib import Path
    from tools.matrix_flashscore_individual_detail_certificate import scan_two_source
    root = Path(__file__).resolve().parents[1]
    sofa_dir = root / "evidence/browser_capture_inbox/opera_football_sofa_detail" / DAY
    source = sorted(sofa_dir.glob("*.json"))[-1]
    assert source.is_file()
    for p in (root / PATH, source):
        target = tmp_path / p.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    result = scan_two_source(tmp_path, DAY,
                  now=datetime(2026, 11, 5, 9, 50, tzinfo=timezone.utc))
    assert result["verified_event_pair_count"] == 1
    pair = result["matched"][0]
    assert pair["flashscore_mid"] == "hUC4nhiT"
    assert pair["sofascore_event_id"] == "16943966"
    assert pair["third_provider_fixture_identity_verified"] is False
    assert pair["telegram_signal_authorized"] is False


def test_reversed_teams_cannot_be_cross_certified():
    from tools.matrix_flashscore_individual_detail_certificate import exact_sofa_crosscheck
    flash = verify(doc(), expected_day=DAY, now=datetime(2026, 11, 5, 9, 45, tzinfo=timezone.utc))
    sofa = {
      "schema": "MATRIX_SOFA_OPERA_INDIVIDUAL_DETAIL_CAPTURE_V1",
      "source": "SOFASCORE",
      "capture_method": "OPERA_CONNECTOR_ACCESSIBILITY_TREE",
      "source_page_url": "https://www.sofascore.com/es/football/match/ac-milan-ferencvaros-tc/ANsRdb#id:16943966",
      "source_event_id": "16943966",
      "real_money": "BLOCKED", "automatic_wagering": False,
      "signal_generation_authorized": False,
      "display_timezone": "America/Bogota",
      "home": "Ferencváros TC", "away": "AC Milan",
      "visible_event_date": "5/11/2026", "visible_event_time": "12:45",
      "observed_at_utc": "2026-11-05T09:49:30.313Z"
    }
    with pytest.raises(ValueError, match="TEAM_MISMATCH"):
        exact_sofa_crosscheck(flash, sofa,
            now=datetime(2026, 11, 5, 9, 50, tzinfo=timezone.utc))
