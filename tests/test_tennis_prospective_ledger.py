from pathlib import Path
import json
import pytest

from app.research.tennis.prospective_ledger import (
    TennisCanonicalEvent,
    TennisClosingOdds,
    TennisFrozenDecision,
    TennisPostMortem,
    TennisProspectiveEvidenceLedger,
    TennisSettlement,
)

SHA = "a" * 64
SHA2 = "b" * 64
SHA3 = "c" * 64
START = "2026-09-03T20:00:00+00:00"
DECISION = "2026-09-03T18:00:00+00:00"
FEATURE = "2026-09-03T17:55:00+00:00"
CUTOFF = "2026-09-03T17:50:00+00:00"
ODDS = "2026-09-03T17:59:00+00:00"
CLOSING = "2026-09-03T19:55:00+00:00"
SETTLED = "2026-09-03T22:00:00+00:00"


def event(**overrides):
    data = dict(
        event_id="sr:sport_event:1",
        player1_id="sr:competitor:1",
        player2_id="sr:competitor:2",
        competition_id="sr:competition:2591",
        season_id="sr:season:134885",
        round="round_of_64",
        surface="hard",
        event_start_utc=START,
        registered_at_utc="2026-09-03T16:00:00+00:00",
        source_provider="sportradar",
        source_reference="trial/v3",
        canonical_event_sha256=SHA,
    )
    data.update(overrides)
    return TennisCanonicalEvent(**data)


def decision(**overrides):
    data = dict(
        event_id="sr:sport_event:1",
        player1_id="sr:competitor:1",
        player2_id="sr:competitor:2",
        competition_id="sr:competition:2591",
        season_id="sr:season:134885",
        round="round_of_64",
        surface="hard",
        market_key="MATCH_WINNER",
        selection_key="PLAYER1",
        line_value=None,
        model_version="tennis-ml-v1",
        calibration_version="cal-v1",
        raw_probability=0.70,
        calibrated_probability=0.68,
        uncertainty_low=0.62,
        uncertainty_high=0.74,
        decision_action="NO_BET",
        decision_reason_codes=("NO_POSITIVE_EV",),
        data_cutoff_utc=CUTOFF,
        feature_snapshot_at_utc=FEATURE,
        decision_at_utc=DECISION,
        event_start_utc=START,
        odds_snapshot_sha256=SHA2,
        odds_observed_at_utc=ODDS,
        decimal_odds=1.40,
        odds_source_provider="book",
        odds_source_reference="quote-1",
        odds_source_authorized=True,
        feature_snapshot_sha256=SHA3,
        model_input_sha256s=(SHA, SHA2),
        canonical_event_sha256=SHA,
        data_quality_status="OK",
        model_risk_status="OK",
        ood_status="OK",
    )
    data.update(overrides)
    return TennisFrozenDecision.build(**data)


def closing(**overrides):
    data = dict(
        decision_id=decision().decision_id,
        event_id="sr:sport_event:1",
        market_key="MATCH_WINNER",
        selection_key="PLAYER1",
        line_value=None,
        source_provider="benchmark",
        source_reference="close-1",
        observed_at_utc=CLOSING,
        event_start_utc=START,
        decimal_odds=1.38,
        source_authorized=True,
    )
    data.update(overrides)
    return TennisClosingOdds(**data)


def settlement(**overrides):
    data = dict(
        decision_id=decision().decision_id,
        event_id="sr:sport_event:1",
        outcome=True,
        settled_at_utc=SETTLED,
        event_start_utc=START,
        result_source_provider="sportradar",
        result_source_reference="summary",
        result_payload_sha256=SHA3,
        provider_definition_version="sportradar-tennis-v3",
    )
    data.update(overrides)
    return TennisSettlement(**data)


def test_probability_overlay_forbidden():
    with pytest.raises(ValueError, match="overlay"):
        decision(overlay_delta=0.01)


def test_decision_must_be_pre_event():
    with pytest.raises(ValueError, match="strictly before"):
        decision(decision_at_utc=START)


def test_probability_inside_uncertainty():
    with pytest.raises(ValueError, match="uncertainty"):
        decision(uncertainty_low=0.70, uncertainty_high=0.80)


def test_bet_requires_authorized_odds():
    with pytest.raises(ValueError, match="authorized"):
        decision(decision_action="BET", odds_source_authorized=False)


def test_no_bet_is_valid_and_persisted(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    ledger.append_decision(decision())
    audit = ledger.audit()
    assert audit.decision_count == 1
    assert audit.no_bet_count == 1
    assert audit.bet_count == 0


def test_decision_requires_registered_event(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    with pytest.raises(ValueError, match="unregistered"):
        ledger.append_decision(decision())


def test_duplicate_semantic_key_rejected(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    ledger.append_decision(decision())
    with pytest.raises(ValueError, match="duplicate event-market"):
        ledger.append_decision(
            decision(
                raw_probability=0.71,
                calibrated_probability=0.69,
                uncertainty_low=0.63,
                uncertainty_high=0.75,
            )
        )


def test_identity_mismatch_rejected(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    with pytest.raises(ValueError, match="identity"):
        ledger.append_decision(decision(player1_id="sr:competitor:999"))


def test_closing_requires_known_decision(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    with pytest.raises(ValueError, match="unknown"):
        ledger.append_closing_odds(closing())


def test_closing_cannot_precede_decision(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    ledger.append_decision(decision())
    with pytest.raises(ValueError, match="precede"):
        ledger.append_closing_odds(closing(observed_at_utc="2026-09-03T17:00:00+00:00"))


def test_settlement_requires_post_start_time():
    with pytest.raises(ValueError, match="after"):
        settlement(settled_at_utc=START)


def test_settlement_identity_binding(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    ledger.append_decision(decision())
    with pytest.raises(ValueError, match="identity"):
        ledger.append_settlement(settlement(event_id="other"))


def test_hash_chain_tamper_detection(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = TennisProspectiveEvidenceLedger(path)
    ledger.register_event(event())
    ledger.append_decision(decision())
    lines = path.read_text(encoding="utf-8").splitlines()
    payload = json.loads(lines[0])
    payload["payload"]["round"] = "tampered"
    lines[0] = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ledger.load_events()


def test_audit_counts_complete_chain(tmp_path):
    ledger = TennisProspectiveEvidenceLedger(tmp_path / "ledger.jsonl")
    ledger.register_event(event())
    frozen = decision(decision_action="BET", decision_reason_codes=("POSITIVE_EV",))
    ledger.append_decision(frozen)
    ledger.append_closing_odds(closing(decision_id=frozen.decision_id))
    ledger.append_settlement(settlement(decision_id=frozen.decision_id))
    ledger.append_post_mortem(
        TennisPostMortem(
            decision_id=frozen.decision_id,
            event_id="sr:sport_event:1",
            recorded_at_utc="2026-09-03T22:10:00+00:00",
            classification="VARIANCE_REVIEWED",
            evidence_sha256=SHA2,
        )
    )
    audit = ledger.audit()
    assert audit.event_count == 5
    assert audit.registered_event_count == 1
    assert audit.decision_count == 1
    assert audit.bet_count == 1
    assert audit.closing_odds_count == 1
    assert audit.settlement_count == 1
    assert audit.post_mortem_count == 1
    assert audit.hash_chain_verified is True


def test_decision_id_is_deterministic():
    assert decision().decision_id == decision().decision_id


def test_canonical_event_must_be_registered_before_start():
    with pytest.raises(ValueError, match="registered before"):
        event(registered_at_utc=START)
