"""All fixtures here are synthetic safety-test examples, never market evidence."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from tools import matrix_independent_free_poisson_oos as m


def write(path: Path, data: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed(root: Path):
    base = root/"evidence/football_world_inventory/2026-11-21/MATRIX_FREE_POISSON_V1_IMMUTABLE"
    poisson={
      "schema":"MATRIX_FREE_POISSON_PROSPECTIVE_RESEARCH_V1",
      "model_id":"MATRIX_FREE_POISSON_TEAM_V1",
      "fixture_id":"560643", "provider":"FOOTBALL_DATA_ORG",
      "provider_competition_id":"2021",
      "kickoff_utc":"2026-11-21T12:30:00+00:00",
      "forecast_frozen_at_utc":"2026-11-19T09:05:57+00:00",
      "history_observed_at_utc":"2026-11-19T09:05:52+00:00",
      "history_raw_sha256":"a"*64,
      "research_probability_over25":0.485329542936,
      "p_matrix_authorized":False,"telegram_signal_authorized":False,
      "real_money":"BLOCKED"
    }
    write(base/"560643.json",poisson)
    return base/"560643.json"


def settle(root: Path, tamper=None):
    base=root/"evidence/football_research_freezes/2026-11-21"
    source=base/"sources"
    original_intake={"fixtures":[{"source_fixture_id":"560643",
        "source_competition_id":2021,"kickoff_utc":"2026-11-21T12:30:00+00:00",
        "home_source_team_id":"17","away_source_team_id":"43"}]}
    intake_sha=write(source/"original_intake.json",original_intake)
    original={
      "schema":"MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1",
      "provider":"FOOTBALL_DATA_ORG","provider_fixture_id":"560643",
      "provider_competition_id":"2021","real_money":"BLOCKED",
      "telegram_signal_authorized":False,
      "kickoff_utc":"2026-11-21T12:30:00+00:00",
      "sealed_at_utc":"2026-11-19T09:05:56+00:00",
      "research_probability_over25":0.5063354725,
      "source_intake_file_path":str((source/"original_intake.json").relative_to(root)),
      "source_intake_file_sha256":intake_sha,
      "source_snapshot_sha256":"a"*64
    }
    original_sha=write(base/"560643_original.json",original)
    provider_final={
        "id":560643,"status":"FINISHED","utcDate":"2026-11-21T12:30:00+00:00",
        "lastUpdated":"2026-11-21T15:00:00+00:00",
        "competition":{"id":2021},
        "homeTeam":{"id":17},"awayTeam":{"id":43},
        "score":{"fullTime":{"home":2,"away":1}},
    }
    if tamper:
        tamper(provider_final)
    result_sha=write(source/"original_final.json",provider_final)
    result={
      "schema":"MATRIX_INDEPENDENT_OVER25_SETTLED_RESEARCH_V1",
      "fixture_id":"560643","competition_id":"2021",
      "real_money":"BLOCKED","telegram_signal_authorized":False,
      "kickoff_utc":"2026-11-21T12:30:00+00:00",
      "forecast_frozen_at_utc":"2026-11-19T09:05:56+00:00",
      "result_observed_at_utc":"2026-11-21T16:00:00+00:00",
      "forecast_sha256":original_sha,
      "raw_result_sha256":result_sha,
      "research_probability_over25":0.5063354725,
      "home_goals":2,"away_goals":1,"over25_outcome":1
    }
    path=base/"560643_result_abcd.json"
    write(path,result)
    return path


def at(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def test_future_does_not_read_results(tmp_path):
    seed(tmp_path)
    d=m.evaluate(tmp_path,now=at("2026-11-19T10:00:00+00:00"))
    assert d["future_forecasts_pending"]==1
    assert d["independently_verified_settled_pairs"]==0
    assert d["mean_poisson_brier"] is None
    assert d["telegram_signal_authorized"] is False


def test_started_no_final_is_explicitly_unresolved(tmp_path):
    seed(tmp_path)
    d=m.evaluate(tmp_path,now=at("2026-11-22T10:00:00+00:00"))
    assert d["started_without_verified_final"]==1
    assert d["independently_verified_settled_pairs"]==0


def test_sha_backed_final_scored_without_promotion(tmp_path):
    seed(tmp_path)
    settle(tmp_path)
    d=m.evaluate(tmp_path,now=at("2026-11-22T10:00:00+00:00"))
    assert d["independently_verified_settled_pairs"]==1
    assert d["future_forecasts_pending"]==0
    assert d["rejected_forecasts_or_settlements"]==[]
    p=d["pairs"][0]
    assert p["outcome"]==1
    assert abs(p["poisson_brier"]-(0.485329542936-1)**2)<1e-12
    assert p["identical_authenticated_history_capture"] is True
    assert d["production_p_matrix_authorized"] is False
    assert d["telegram_signal_authorized"] is False


def test_tampered_final_kickoff_is_rejected(tmp_path):
    seed(tmp_path)
    settle(tmp_path, lambda doc: doc.__setitem__("utcDate","2026-11-21T11:30:00+00:00"))
    d=m.evaluate(tmp_path,now=at("2026-11-22T10:00:00+00:00"))
    assert d["independently_verified_settled_pairs"]==0
    assert "FINAL_SCORE_NOT_AUTHENTIC" in d["rejected_forecasts_or_settlements"][0]["reason"]


def test_unbound_original_forecast_hash_is_rejected(tmp_path):
    seed(tmp_path)
    result=settle(tmp_path)
    j=json.loads(result.read_text())
    j["forecast_sha256"]="0"*64
    write(result,j)
    d=m.evaluate(tmp_path,now=at("2026-11-22T10:00:00+00:00"))
    assert d["independently_verified_settled_pairs"]==0
    assert "ORIGINAL_PREMATCH_FORECAST_SHA_MISSING" in d["rejected_forecasts_or_settlements"][0]["reason"]


def test_postkickoff_forecast_does_not_join_final(tmp_path):
    file=seed(tmp_path)
    row=json.loads(file.read_text())
    row["forecast_frozen_at_utc"]="2026-11-21T13:00:00+00:00"
    write(file,row)
    settle(tmp_path)
    d=m.evaluate(tmp_path,now=at("2026-11-22T10:00:00+00:00"))
    assert d["independently_verified_settled_pairs"]==0
    assert "FREE_POISSON_NOT_PROSPECTIVE" in d["rejected_forecasts_or_settlements"][0]["reason"]


def test_duplicate_poisson_fixture_is_rejected(tmp_path):
    old=seed(tmp_path)
    new=tmp_path/"evidence/football_world_inventory/2026-11-20/MATRIX_FREE_POISSON_V1_IMMUTABLE/560643.json"
    new.parent.mkdir(parents=True)
    new.write_bytes(old.read_bytes())
    d=m.evaluate(tmp_path,now=at("2026-11-19T10:00:00+00:00"))
    assert len(d["rejected_forecasts_or_settlements"])==1
    assert "DUPLICATE_FREE_POISSON_FORECAST" in d["rejected_forecasts_or_settlements"][0]["reason"]
