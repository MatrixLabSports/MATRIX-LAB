from tools.api_football_physical_uniqueness_audit import (
    audit_football_physical_uniqueness,
)


def _row(fid, kickoff, home="10", away="20", competition="39"):
    return {
        "fixture_id": str(fid),
        "competition_id": competition,
        "season": 2026,
        "home_team_id": home,
        "away_team_id": away,
        "kickoff_utc": kickoff,
    }


def test_football_uniqueness_passes_unique_inventory_and_calibration():
    freeze={"rows":[
        _row("1","2026-10-02T10:00:00+00:00"),
        _row("2","2026-10-05T10:00:00+00:00"),
    ]}
    calibration=[{"fixture_id":"1"}]
    d=audit_football_physical_uniqueness(
        freeze=freeze,
        calibration_rows=calibration,
    )
    assert d["result"]=="PASS"
    assert d["freeze_rows"]==2
    assert d["unique_fixture_ids"]==2
    assert d["exact_physical_duplicate_groups"]==0
    assert d["calibration_duplicate_fixture_ids"]==[]


def test_football_uniqueness_rejects_same_match_new_fixture_id():
    freeze={"rows":[
        _row("1","2026-10-02T10:00:00+00:00"),
        _row("999","2026-10-02T10:00:00+00:00"),
    ]}
    d=audit_football_physical_uniqueness(
        freeze=freeze,
        calibration_rows=[],
    )
    assert d["result"]=="FAIL"
    assert d["exact_physical_duplicate_groups"]==1
    assert "DUPLICATE_PHYSICAL_EVENT_DIFFERENT_FIXTURE_ID" in d["blockers"]


def test_football_uniqueness_flags_same_pair_nearby_for_adjudication():
    freeze={"rows":[
        _row("1","2026-10-02T10:00:00+00:00"),
        _row("2","2026-10-03T20:00:00+00:00"),
    ]}
    d=audit_football_physical_uniqueness(
        freeze=freeze,
        calibration_rows=[],
    )
    assert d["result"]=="FAIL"
    assert d["suspicious_same_pair_within_36h"]==1
    assert "SUSPECT_SAME_TEAMS_WITHIN_36H" in d["blockers"]


def test_football_uniqueness_rejects_duplicate_calibration_fixture():
    freeze={"rows":[_row("1","2026-10-02T10:00:00+00:00")]}
    calibration=[{"fixture_id":"1"},{"fixture_id":"1"}]
    d=audit_football_physical_uniqueness(
        freeze=freeze,
        calibration_rows=calibration,
    )
    assert d["result"]=="FAIL"
    assert d["calibration_duplicate_fixture_ids"]==["1"]
