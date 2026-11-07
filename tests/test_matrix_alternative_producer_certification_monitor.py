"""Read-only certification monitor, using empty real-evidence fixtures only."""
from tools.matrix_alternative_producer_certification_monitor import report

def test_no_original_six_league_archive_or_oos_is_not_certification(tmp_path):
    r=report(tmp_path)
    assert r["full_alternative_producer_certified"] is False
    assert r["prospective_validated_prediction_count"]==0
    assert r["archived_league_id_count"]==0
    assert "FEWER_THAN_SIX_ORIGINAL_ARCHIVED_LEAGUES" in r["unresolved_requirements"]
    assert "SIX_GOVERNED_VALIDATION_COHORTS_NOT_YET_SELECTED" in r["unresolved_requirements"]
    assert "PROSPECTIVE_FREEZE_SNAPSHOT_SOURCE_MISSING" in r["unresolved_requirements"]
    assert r["telegram_signal_authorized"] is False
    assert r["real_money"]=="BLOCKED"
