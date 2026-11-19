"""Synthetic fixtures only test the free independent Poisson safety contract.

Synthetic test goals are never submitted to MATRIX's calibration ledgers.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from tools import matrix_independent_free_poisson_v1 as m


def sample():
    d0 = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    matches = []
    for i in range(40):
        # Legitimate distinct historic fixtures; home id 1 and away id 2
        # each acquire a real non-zero venue history in the test.
        home = 1 if i % 4 == 0 else 100 + i
        away = 2 if i % 4 == 1 else 200 + i
        stamp = d0 + timedelta(days=i)
        matches.append({
            "id": 7000 + i,
            "status": "FINISHED",
            "competition": {"id": 2021},
            "homeTeam": {"id": home, "name": "Home" if home == 1 else "Other"},
            "awayTeam": {"id": away, "name": "Away" if away == 2 else "Other"},
            "utcDate": stamp.isoformat(),
            "lastUpdated": (stamp + timedelta(hours=2)).isoformat(),
            "score": {"fullTime": {"home": i % 4, "away": (i + 1) % 3}},
        })
    # Keep only completed matches whose provider update was available before
    # the simulated current pre-kickoff capture on Nov 19.
    matches = [x for x in matches if x["lastUpdated"] < "2026-11-19T08:55:00+00:00"]
    raw = json.dumps({"competition": {"id": 2021}, "matches": matches}, sort_keys=True).encode()
    now = datetime(2026, 11, 19, 9, 10, tzinfo=timezone.utc)
    intake = {
        "schema": "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
        "source": "FOOTBALL_DATA_ORG", "target_date_bogota": "2026-11-21",
        "generated_at_utc": "2026-11-19T09:00:00+00:00",
        "signal_generation_authorized": False, "real_money": "BLOCKED",
        "fixtures": [{
            "source": "FOOTBALL_DATA_ORG", "source_fixture_id": "560643",
            "source_competition_id": 2021, "home_source_team_id": "1",
            "away_source_team_id": "2", "api_football_fixture_id": None,
            "home": "Manchester City", "away": "Fulham",
            "kickoff_utc": "2026-11-21T12:30:00+00:00",
            "signal_generation_authorized": False,
        }],
    }
    shadow = {
        "schema": "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
        "source": "FOOTBALL_DATA_ORG", "target_date_bogota": "2026-11-21",
        "real_money": "BLOCKED", "parameter_refit": False,
        "market_signal_authorized": False,
        "generated_at_utc": "2026-11-19T09:00:00+00:00",
        "completed_at_utc": "2026-11-19T09:05:00+00:00",
        "authenticated_raw_group_replay_evidence": {
            "2021": {
                "competition_id": 2021,
                "source_payload_sha256": hashlib.sha256(raw).hexdigest(),
                "response_base64": base64.b64encode(raw).decode(),
                "observed_at_utc": "2026-11-19T09:02:00+00:00",
            }
        },
    }
    return intake, shadow, now


def test_authentic_sha_backed_history_and_independent_model_produce_research_prediction():
    intake, shadow, now = sample()
    r = m.forecast(intake, shadow, now=now)
    assert r["scored_count"] == 1
    assert r["blocked_count"] == 0
    p = r["scored"][0]
    assert 0 < p["research_probability_over25"] < 1
    assert p["home_venue_history_count"] >= 3
    assert p["away_venue_history_count"] >= 3
    assert p["model_id"] == "MATRIX_FREE_POISSON_TEAM_V1"
    assert p["history_raw_sha256"] == shadow["authenticated_raw_group_replay_evidence"]["2021"]["source_payload_sha256"]
    assert p["forecast_frozen_at_utc"] < p["kickoff_utc"]
    assert not r["production_p_matrix_authorized"]
    assert not r["telegram_signal_authorized"]


def test_same_inputs_deterministic_same_probability():
    intake, shadow, now = sample()
    a = m.forecast(intake, shadow, now=now)
    b = m.forecast(copy.deepcopy(intake), copy.deepcopy(shadow), now=now)
    assert a["scored"][0]["research_probability_over25"] == b["scored"][0]["research_probability_over25"]


def test_wrong_raw_sha_is_blocked_not_counted():
    intake, shadow, now = sample()
    shadow["authenticated_raw_group_replay_evidence"]["2021"]["source_payload_sha256"] = "0"*64
    r = m.forecast(intake, shadow, now=now)
    assert r["scored_count"] == 0
    assert "HISTORY_RAW_SHA256_INVALID" in r["blocked"][0]["reason"]


def test_after_kickoff_never_reconstructs_forecast():
    intake, shadow, _ = sample()
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    r = m.forecast(intake, shadow, now=now)
    assert r["scored_count"] == 0
    assert r["blocked"][0]["reason"] == "FORECAST_AFTER_KICKOFF"


def test_missing_league_source_stays_blocked():
    intake, shadow, now = sample()
    shadow["authenticated_raw_group_replay_evidence"] = {}
    r = m.forecast(intake, shadow, now=now)
    assert r["scored_count"] == 0
    assert r["blocked"][0]["reason"] == "COMPETITION_RAW_EVIDENCE_MISSING"


def test_source_scope_cannot_be_promoted():
    intake, shadow, now = sample()
    shadow["market_signal_authorized"] = True
    with pytest.raises(ValueError, match="MODEL_RESEARCH_ONLY_REQUIRED"):
        m.forecast(intake, shadow, now=now)


def test_duplicate_fixture_never_counts_twice():
    intake, shadow, now = sample()
    intake["fixtures"].append(copy.deepcopy(intake["fixtures"][0]))
    with pytest.raises(ValueError, match="DUPLICATE_FIXTURE"):
        m.forecast(intake, shadow, now=now)


def test_source_update_after_capture_never_used():
    intake, shadow, now = sample()
    group = shadow["authenticated_raw_group_replay_evidence"]["2021"]
    payload = json.loads(base64.b64decode(group["response_base64"]))
    # Every earlier source row becomes unproven at capture time.
    for match in payload["matches"]:
        match["lastUpdated"] = "2026-11-20T09:02:00+00:00"
    raw = json.dumps(payload, sort_keys=True).encode()
    group["response_base64"] = base64.b64encode(raw).decode()
    group["source_payload_sha256"] = hashlib.sha256(raw).hexdigest()
    r = m.forecast(intake, shadow, now=now)
    assert r["scored_count"] == 0
    assert r["blocked"][0]["reason"] == "LEAGUE_HISTORY_TOO_SHORT"


def test_original_provider_id_cannot_masquerade_as_free_provider():
    intake, shadow, now = sample()
    intake["fixtures"][0]["api_football_fixture_id"] = "560643"
    r = m.forecast(intake, shadow, now=now)
    assert r["scored_count"] == 0
    assert r["blocked"][0]["reason"] == "PROVIDER_ID_NAMESPACE_VIOLATION"


def test_future_shadow_is_rejected():
    intake, shadow, now = sample()
    shadow["completed_at_utc"] = "2026-11-20T09:05:00+00:00"
    with pytest.raises(ValueError, match="SHADOW_NOT_COMPLETED"):
        m.forecast(intake, shadow, now=now)
