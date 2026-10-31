import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.api_football_shadow_settlement import (
    ShadowSettlementLedger,
    build_shadow_settlement_queue,
    settlement_from_final_fixture,
    sync_shadow_settlements,
)


UTC = timezone.utc


def _canonical():
    return {
        "inputs": [{
            "fixture_id": "900",
            "home_team_id": "40",
            "home_team_name": "Home FC",
            "away_team_id": "41",
            "away_team_name": "Away FC",
        }]
    }


def _shadow():
    return {
        "model_role": "RESEARCH_SHADOW_BASELINE",
        "model_status": "EXPERIMENTAL_NOT_PROMOTED",
        "p_matrix_status": "NOT_GENERATED",
        "protections": {
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "real_money": "BLOCKED",
        },
        "rows": [{
            "fixture_id": "900",
            "target_key": "api_football:fixture:900",
            "kickoff_utc": "2026-09-28T18:00:00+00:00",
            "freeze_at_utc": "2026-09-28T12:00:00+00:00",
            "input_sha256": "a" * 64,
            "model_name": "transparent_poisson_baseline_v1",
            "model_role": "RESEARCH_SHADOW_BASELINE",
            "model_status": "EXPERIMENTAL_NOT_PROMOTED",
            "markets": {
                "home_win": 0.50,
                "draw": 0.25,
                "away_win": 0.25,
                "over_1_5": 0.80,
                "over_2_5": 0.60,
                "over_3_5": 0.35,
                "btts": 0.55,
            },
        }],
    }


def _final_fixture(status="FT", home_goals=2, away_goals=1):
    return {
        "fixture": {"id": 900, "status": {"short": status}},
        "teams": {
            "home": {"id": 40, "name": "Home FC"},
            "away": {"id": 41, "name": "Away FC"},
        },
        "goals": {"home": home_goals, "away": away_goals},
        "score": {
            "fulltime": {"home": home_goals, "away": away_goals},
        },
    }


def test_queue_waits_until_two_hours_after_kickoff():
    before = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 17, 0, tzinfo=UTC),
    )
    assert before["counts"]["WAITING_KICKOFF"] == 1
    assert before["counts"]["READY_RESULT_LOOKUP"] == 0

    middle = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 19, 0, tzinfo=UTC),
    )
    assert middle["counts"]["WAITING_FINAL_WINDOW"] == 1
    assert middle["counts"]["READY_RESULT_LOOKUP"] == 0

    ready = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 20, 0, 1, tzinfo=UTC),
    )
    assert ready["counts"]["READY_RESULT_LOOKUP"] == 1
    assert ready["metrics_opened"] is False
    assert ready["outcomes_used_for_metrics"] == 0
    assert ready["real_money"] == "BLOCKED"


def test_standard_ft_settlement_derives_all_seven_outcomes():
    queue = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 20, 1, tzinfo=UTC),
    )
    item = queue["items"][0]

    record = settlement_from_final_fixture(
        queue_item=item,
        provider_fixture=_final_fixture(home_goals=2, away_goals=1),
        settled_at_utc=datetime(2026, 9, 28, 20, 2, tzinfo=UTC),
        source_reference="/fixtures?id=900",
        source_payload_sha256="b" * 64,
    )

    assert record["terminal_status"] == "FT"
    assert record["outcomes"] == {
        "home_win": True,
        "draw": False,
        "away_win": False,
        "over_1_5": True,
        "over_2_5": True,
        "over_3_5": False,
        "btts": True,
    }
    assert record["metrics_opened"] is False
    assert record["used_for_metrics"] is False
    assert record["p_matrix_status"] == "NOT_GENERATED"
    assert record["real_money"] == "BLOCKED"


def test_nonstandard_terminal_is_not_settled():
    queue = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 20, 1, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="SHADOW_SETTLEMENT_NOT_STANDARD_FT:AET"):
        settlement_from_final_fixture(
            queue_item=queue["items"][0],
            provider_fixture=_final_fixture(status="AET"),
            settled_at_utc=datetime(2026, 9, 28, 20, 2, tzinfo=UTC),
            source_reference="/fixtures?id=900",
            source_payload_sha256="b" * 64,
        )


def test_team_identity_mismatch_blocks_settlement():
    queue = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 20, 1, tzinfo=UTC),
    )
    fixture = _final_fixture()
    fixture["teams"]["home"]["id"] = 999
    with pytest.raises(ValueError, match="FINAL_FIXTURE_HOME_TEAM_ID_MISMATCH"):
        settlement_from_final_fixture(
            queue_item=queue["items"][0],
            provider_fixture=fixture,
            settled_at_utc=datetime(2026, 9, 28, 20, 2, tzinfo=UTC),
            source_reference="/fixtures?id=900",
            source_payload_sha256="b" * 64,
        )


def test_hash_chain_ledger_keeps_metrics_closed(tmp_path):
    queue = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 20, 1, tzinfo=UTC),
    )
    record = settlement_from_final_fixture(
        queue_item=queue["items"][0],
        provider_fixture=_final_fixture(),
        settled_at_utc=datetime(2026, 9, 28, 20, 2, tzinfo=UTC),
        source_reference="/fixtures?id=900",
        source_payload_sha256="b" * 64,
    )
    ledger = ShadowSettlementLedger(tmp_path / "ledger.jsonl")
    appended = ledger.append(record)
    assert appended["record_sha256"]
    assert appended["settlement_id"]
    audit = ledger.audit()
    assert audit.records == 1
    assert audit.unique_fixtures == 1
    assert audit.hash_chain_verified is True
    assert audit.outcomes_used_for_metrics == 0


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload).encode("utf-8")
        self.headers = {
            "x-ratelimit-requests-limit": "7500",
            "x-ratelimit-requests-remaining": "7000",
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "299",
        }

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, headers, params, timeout):
        self.calls.append({
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
        })
        return FakeResponse(self.payload)


def test_sync_calls_provider_only_for_ready_rows_and_persists_standard_ft(tmp_path):
    queue = build_shadow_settlement_queue(
        shadow=_shadow(),
        canonical_bundle=_canonical(),
        ledger_records=[],
        now_utc=datetime(2026, 9, 28, 20, 1, tzinfo=UTC),
    )
    payload = {
        "errors": {},
        "response": [_final_fixture()],
    }
    session = FakeSession(payload)
    ledger = ShadowSettlementLedger(tmp_path / "ledger.jsonl")

    result = sync_shadow_settlements(
        queue=queue,
        ledger=ledger,
        api_key="secret",
        raw_dir=tmp_path / "raw",
        now_utc=datetime(2026, 9, 28, 20, 2, tzinfo=UTC),
        session=session,
    )

    assert result["status"] == "PASS"
    assert result["new_settlement_count"] == 1
    assert result["network_calls"] == 1
    assert result["ledger_records"] == 1
    assert result["outcomes_used_for_metrics"] == 0
    assert result["metrics_opened"] is False
    assert result["p_matrix_status"] == "NOT_GENERATED"
    assert result["real_money"] == "BLOCKED"
    assert session.calls[0]["params"] == {"id": "900"}
    assert (tmp_path / "raw" / "fixture_900_settlement.bin").is_file()
