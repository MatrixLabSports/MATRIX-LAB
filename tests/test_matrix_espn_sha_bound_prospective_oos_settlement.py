from datetime import datetime,timezone
from unittest.mock import patch
import copy
import pytest

from tools.matrix_espn_sha_bound_prospective_oos_settlement import evaluate


FREEZE="2026-11-22T04:51:41+00:00"
KICKOFF="2026-11-22T11:30:00+00:00"

def fixture():
    return {
        "schema":"MATRIX_ESPN_SHA_PROVEN_TWO_MONTH_OVER25_RESEARCH_FREEZE_V1",
        "source_sha256_and_point_in_time_receipts_verified":True,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "real_money":"BLOCKED",
        "research_frozen_at_utc":FREEZE,
        "research_rows":[{
            "provider_fixture_id":"401875008",
            "original_league_id_research_only":"135",
            "research_frozen_at_utc":FREEZE,
            "kickoff_utc":KICKOFF,
            "research_probability_over25":0.55,
            "home_provider_team_id":"109",
            "away_provider_team_id":"454",
        }]
    }


def capture():
    return {
        "id":"401875008","league":"135",
        "kickoff":datetime.fromisoformat(KICKOFF),
        "home":"109","away":"454",
        "goals":(2,1),"prematch":False,
        "received":datetime(2026,11,22,14,15,tzinfo=timezone.utc),
        "raw_sha256":"abc123"
    }


def fake_reports(monkeypatch,match):
    def get(_folder,_month,lid,_now):
        return [match] if lid=="135" and match is not None else []
    monkeypatch.setattr(
        "tools.matrix_espn_sha_bound_prospective_oos_settlement.read_archive", get)


def test_authentic_exact_final_settles_research_only(monkeypatch,tmp_path):
    fake_reports(monkeypatch,capture())
    result=evaluate(fixture(),tmp_path,now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))
    assert result["verified_prospective_settlements"]==1
    assert result["settled"][0]["outcome_over25"]==1
    assert abs(result["settled"][0]["brier"]-0.2025)<1e-9
    assert result["settled"][0]["final_result_source_sha256"]=="abc123"
    assert result["production_p_matrix_authorized"] is False
    assert result["scientific_independent_model_certified"] is False


def test_future_fixture_does_not_settle(monkeypatch,tmp_path):
    fake_reports(monkeypatch,None)
    report=evaluate(fixture(),tmp_path,now=datetime(2026,11,22,8,0,tzinfo=timezone.utc))
    assert report["verified_prospective_settlements"]==0
    assert report["awaiting_authentic_final"]==1


def test_wrong_team_provider_identity_rejected(monkeypatch,tmp_path):
    bad=capture();bad["away"]="invalid"
    fake_reports(monkeypatch,bad)
    report=evaluate(fixture(),tmp_path,now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))
    assert report["verified_prospective_settlements"]==0
    assert report["rejected_wrong_identity_or_provenance"]==1


def test_final_receipt_cannot_predate_kickoff(monkeypatch,tmp_path):
    bad=capture();bad["received"]=datetime(2026,11,22,10,0,tzinfo=timezone.utc)
    fake_reports(monkeypatch,bad)
    report=evaluate(fixture(),tmp_path,now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))
    assert report["verified_prospective_settlements"]==0
    assert report["rejected_wrong_identity_or_provenance"]==1


def test_missing_final_is_pending_not_a_loss(monkeypatch,tmp_path):
    fake_reports(monkeypatch,None)
    report=evaluate(fixture(),tmp_path,now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))
    assert report["overall_brier"] is None
    assert report["awaiting_authentic_final"]==1


def test_duplicate_forecast_id_fails_closed(monkeypatch,tmp_path):
    fake_reports(monkeypatch,capture())
    entry=fixture()
    entry["research_rows"].append(copy.deepcopy(entry["research_rows"][0]))
    with pytest.raises(ValueError,match="DUPLICATE_FROZEN_OOS_PREDICTION"):
        evaluate(entry,tmp_path,now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))


def test_research_promotion_violation_rejected(monkeypatch,tmp_path):
    fake_reports(monkeypatch,capture())
    entry=fixture();entry["telegram_signal_authorized"]=True
    with pytest.raises(ValueError,match="UNTRUSTED_PREMATCH_FREEZE"):
        evaluate(entry,tmp_path,now=datetime(2026,11,22,15,0,tzinfo=timezone.utc))
