from datetime import datetime, timezone
import json

from tools.matrix_independent_pit_browser_preflight import assess, FILES

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)
DAY = "2026-11-06"


def fixture_docs():
    return {
        "intake": {
            "schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
            "source": "FOOTBALL_DATA_ORG",
            "provider_status": "AUTHENTICATED_FIXTURE_CAPTURE",
            "target_date_bogota": DAY, "real_money": "BLOCKED",
            "signal_generation_authorized": False,
            "fixtures": [{"source_fixture_id": "42",
                          "source_competition_code": "ELC",
                          "source_competition_id": 2016}]},
        "shadow": {
            "schema": "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
            "target_date_bogota": DAY, "real_money": "BLOCKED",
            "market_signal_authorized": False, "parameter_refit": False,
            "scored": [{"source_fixture_id": "42"}]},
        "sofa": {
            "schema": "MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK_V1",
            "target_date_bogota": DAY, "real_money": "BLOCKED",
            "signal_generation_authorized": False,
            "status": "PASS_SOFA_IDENTITIES_ONLY_NO_DOUBLE_SOURCE_OR_SIGNAL",
            "rejected_count": 0,
            "matched": [{"fixture_id": "42",
                         "identity_time_and_teams_verified": True}]},
        "flash": {
            "schema": "MATRIX_FLASH_FOOTBALL_CROSSCHECK_V1",
            "target_date_bogota": DAY, "real_money": "BLOCKED",
            "signal_generation_authorized": False,
            "status": "PASS_THREE_SOURCE_FIXTURE_IDENTITY_ONLY_NO_QUOTES_OR_SIGNALS",
            "sofascore_verified": True, "flashscore_verified": True,
            "rejected_count": 0,
            "matched": [{"source_fixture_id": "42",
                         "three_source_calendar_identity_verified": True}]},
    }


def write(tmp_path, docs):
    folder = tmp_path / "evidence" / "football_world_inventory" / DAY
    folder.mkdir(parents=True, exist_ok=True)
    for name, body in docs.items():
        (folder / FILES[name]).write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def test_strict_exact_elc_native_id_can_enter_attestation_but_never_telegram(tmp_path):
    doc = assess(write(tmp_path, fixture_docs()), DAY, now=NOW)
    assert doc["ready_for_strict_attestation"] is True
    assert doc["exact_triple_source_championship_ids"] == ["42"]
    assert doc["status"] == "READY_STRICT_PIT_ATTESTATION_ONLY"
    assert len(doc["source_sha256"]) == 4
    assert all(len(x) == 64 for x in doc["source_sha256"].values())
    assert doc["production_p_matrix_authorized"] is False
    assert doc["telegram_signal_authorized"] is False


def test_missing_browser_source_is_explicit_sha_bound_blocker(tmp_path):
    docs = fixture_docs()
    docs.pop("flash")
    report = assess(write(tmp_path, docs), DAY, now=NOW)
    assert report["ready_for_strict_attestation"] is False
    assert report["status"] == "BLOCKED_MISSING_SOURCE_DOCUMENTS"
    assert report["missing_sources"] == ["flash"]


def test_actual_nine_non_elc_games_cannot_enter_championship_gate(tmp_path):
    docs = fixture_docs()
    docs["intake"]["fixtures"][0]["source_competition_code"] = "BSA"
    docs["intake"]["fixtures"][0]["source_competition_id"] = 2013
    report = assess(write(tmp_path, docs), DAY, now=NOW)
    assert report["championship_native_fixtures"] == 0
    assert report["status"] == "BLOCKED_NO_CHAMPIONSHIP_FIXTURES"
    assert report["ready_for_strict_attestation"] is False


def test_missing_browser_matches_not_silently_promoted(tmp_path):
    docs = fixture_docs()
    docs["sofa"]["matched"] = []
    docs["sofa"]["status"] = "BLOCKED_NO_CURRENT_BROWSER_CAPTURE"
    report = assess(write(tmp_path, docs), DAY, now=NOW)
    assert report["status"] == "BLOCKED_TRIPLE_BROWSER_CALENDAR_EVIDENCE"
    assert report["ready_for_strict_attestation"] is False


def test_real_money_change_fails_closed(tmp_path):
    docs = fixture_docs()
    docs["shadow"]["real_money"] = "ENABLED"
    report = assess(write(tmp_path, docs), DAY, now=NOW)
    assert report["ready_for_strict_attestation"] is False
    assert report["telegram_signal_authorized"] is False
