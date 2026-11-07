"""Regression checks for original-only, fail-closed pre-capture candidate sync."""
from datetime import datetime, timedelta, timezone
import json

from tools.matrix_browser_governed_intake_sync import build
from tools.matrix_selfhosted_browser_quote_collector import synchronized_governed_candidate_rows


NOW=datetime(2026,11,4,13,0,tzinfo=timezone.utc)


def make_fixture(tmp_path):
    promotion=tmp_path/"evidence/api_football/governance/over_2_5_p_matrix_promotion.json"
    promotion.parent.mkdir(parents=True)
    promotion.write_text(json.dumps({
      "market":"OVER_2_5",
      "promotion_status":"PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
      "engine_executable_for_p_matrix":True,
      "promotion_scope":"MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY",
      "protections":{"real_money":"BLOCKED","automatic_wagering":False}
    }),encoding="utf-8")
    source=tmp_path/"evidence/api_football/daily_prematch_reports/2026-11-04/over25_shadow_ev/fixture.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"signal_generation_authorized":true}',encoding="utf-8")
    candidate={
      "sport":"football","market_key":"Goles totales Más/Menos","selection_key":"Más de 2.5",
      "fixture_id":"original-42","match":"Home vs Away",
      "kickoff":(NOW+timedelta(minutes=70)).isoformat(),
      "p_matrix":0.71,"source":str(source.relative_to(tmp_path))
    }
    return source,candidate,promotion


def save_report(tmp_path,report):
    p=tmp_path/"evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json"
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report),encoding="utf-8")


def test_original_governed_candidate_survives_immediate_cycle(tmp_path):
    source,c,promotion=make_fixture(tmp_path)
    report=build(NOW,root=tmp_path,discover=lambda dates:{"fixture":c})
    assert report["candidate_count"]==1
    assert report["status"]=="GOVERNED_CANDIDATES_FOUND"
    assert report["candidates"][0]["p_matrix"]==0.71
    assert report["telegram_signal_authorized"] is False
    save_report(tmp_path,report)
    rows=synchronized_governed_candidate_rows(NOW,root=tmp_path)
    assert len(rows)==1 and rows[0]["fixture_id"]=="original-42"


def test_expired_or_modified_source_is_rejected(tmp_path):
    source,c,_=make_fixture(tmp_path)
    report=build(NOW,root=tmp_path,discover=lambda dates:{"fixture":c})
    save_report(tmp_path,report)
    source.write_text('{"tampered":true}',encoding="utf-8")
    assert synchronized_governed_candidate_rows(NOW,root=tmp_path)==[]


def test_stale_report_never_revives_supervisor_candidates(tmp_path):
    _,c,_=make_fixture(tmp_path)
    report=build(NOW,root=tmp_path,discover=lambda dates:{"fixture":c})
    save_report(tmp_path,report)
    assert synchronized_governed_candidate_rows(NOW+timedelta(minutes=6),root=tmp_path)==[]


def test_unpromoted_alternative_cannot_generate_p_matrix(tmp_path):
    source,c,promotion=make_fixture(tmp_path)
    promotion.write_text('{"promotion_status":"RESEARCH_ONLY"}',encoding="utf-8")
    report=build(NOW,root=tmp_path,discover=lambda dates:{"fixture":c})
    assert report["candidate_count"]==0
    assert report["status"]=="MODEL_PROMOTION_NOT_VERIFIED"


def test_prospective_outside_window_excluded(tmp_path):
    _,c,_=make_fixture(tmp_path)
    c["kickoff"]=(NOW+timedelta(hours=3)).isoformat()
    report=build(NOW,root=tmp_path,discover=lambda dates:{"fixture":c})
    assert report["candidate_count"]==0


def test_independent_source_not_accepted(tmp_path):
    _,c,_=make_fixture(tmp_path)
    independent=tmp_path/"evidence/football_world_inventory/2026-11-04/research.json"
    independent.parent.mkdir(parents=True)
    independent.write_text("{}",encoding="utf-8")
    c["source"]=str(independent.relative_to(tmp_path))
    report=build(NOW,root=tmp_path,discover=lambda dates:{"fixture":c})
    assert report["candidate_count"]==0


def test_synchronizer_refuses_absent_report(tmp_path):
    assert synchronized_governed_candidate_rows(NOW,root=tmp_path) is None


def test_empty_original_producer_is_distinguished_from_gate_rejections(tmp_path):
    make_fixture(tmp_path)
    report = build(NOW, root=tmp_path, discover=lambda dates: {})
    assert report["candidate_count"] == 0
    assert report["upstream_discovered_candidate_count"] == 0
    assert report["no_candidates_reason"] == "ORIGINAL_SUPERVISOR_DISCOVERY_EMPTY"
    assert report["telegram_signal_authorized"] is False


def test_original_candidate_outside_window_is_not_reported_as_absent(tmp_path):
    _, candidate, _ = make_fixture(tmp_path)
    candidate["kickoff"] = (NOW + timedelta(hours=3)).isoformat()
    report = build(NOW, root=tmp_path, discover=lambda dates: {"fixture": candidate})
    assert report["upstream_discovered_candidate_count"] == 1
    assert report["candidate_count"] == 0
    assert report["no_candidates_reason"] == "ORIGINAL_CANDIDATES_FAILED_SCOPE_OR_TIME_GATES"
