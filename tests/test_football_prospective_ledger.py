import json
from math import log

import pytest

from app.research.football.prospective_ledger import (
    ClosingOddsReference,
    FootballProspectiveEvidenceLedger,
    FrozenProspectiveDecision,
    ProspectivePerformancePolicy,
    ProspectiveSettlement,
)


def _decision(index=1, *, probability=0.75, odds=2.0, block_id=None, authorized=True):
    return FrozenProspectiveDecision(
        decision_id=f"decision-{index}",
        fixture_id=f"fixture-{index}",
        market_key="over_2_5",
        selection_key="over",
        model_version="football-over25-v1",
        model_probability=probability,
        decision_at_utc="2026-08-18T17:15:00+00:00",
        fixture_kickoff_utc="2026-08-18T19:00:00+00:00",
        block_id=block_id or f"2026-08-{18 + (index % 4):02d}",
        odds_snapshot_sha256="a" * 64,
        odds_observed_at_utc="2026-08-18T17:10:00+00:00",
        decimal_odds=odds,
        odds_source_provider="licensed_feed",
        odds_source_reference=f"provider://entry/{index}",
        odds_source_authorized=authorized,
        model_input_sha256s=("b" * 64, "c" * 64),
    )


def _closing(decision, *, odds=1.8, observed="2026-08-18T18:55:00+00:00", authorized=True):
    return ClosingOddsReference(
        decision_id=decision.decision_id,
        fixture_id=decision.fixture_id,
        market_key=decision.market_key,
        selection_key=decision.selection_key,
        source_provider="licensed_feed",
        source_reference=f"provider://close/{decision.decision_id}",
        observed_at_utc=observed,
        fixture_kickoff_utc=decision.fixture_kickoff_utc,
        decimal_odds=odds,
        source_authorized=authorized,
    )


def _settlement(decision, *, outcome=True):
    return ProspectiveSettlement(
        decision_id=decision.decision_id,
        fixture_id=decision.fixture_id,
        outcome=outcome,
        settled_at_utc="2026-08-18T21:30:00+00:00",
        fixture_kickoff_utc=decision.fixture_kickoff_utc,
        result_source_provider="licensed_results",
        result_source_reference=f"provider://result/{decision.fixture_id}",
        result_payload_sha256="d" * 64,
    )


def test_frozen_decision_rejects_hindsight_and_future_odds():
    with pytest.raises(ValueError, match="strictly before kickoff"):
        FrozenProspectiveDecision(
            **{**_decision().__dict__, "decision_at_utc": "2026-08-18T19:00:00+00:00"}
        )
    with pytest.raises(ValueError, match="cannot be after"):
        FrozenProspectiveDecision(
            **{**_decision().__dict__, "odds_observed_at_utc": "2026-08-18T17:16:00+00:00"}
        )


def test_closing_odds_must_remain_pre_match():
    decision = _decision()
    with pytest.raises(ValueError, match="before kickoff"):
        _closing(decision, observed="2026-08-18T19:00:00+00:00")


def test_settlement_must_be_after_kickoff():
    decision = _decision()
    with pytest.raises(ValueError, match="after kickoff"):
        ProspectiveSettlement(
            **{**_settlement(decision).__dict__, "settled_at_utc": "2026-08-18T18:59:00+00:00"}
        )


def test_ledger_is_append_only_hash_chained_and_materializes_paper_trade(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    decision = _decision()
    first = ledger.append_decision(decision)
    second = ledger.append_closing_odds(_closing(decision))
    third = ledger.append_settlement(_settlement(decision))

    assert first.previous_event_sha256 is None
    assert second.previous_event_sha256 == first.event_sha256
    assert third.previous_event_sha256 == second.event_sha256
    assert len(ledger.load_events()) == 3
    audit = ledger.audit()
    assert audit.decision_count == 1
    assert audit.closing_odds_count == 1
    assert audit.settlement_count == 1
    assert audit.authorized_entry_odds
    assert audit.authorized_closing_odds

    observations = ledger.paper_observations(market_key="over_2_5", model_version="football-over25-v1")
    assert len(observations) == 1
    assert observations[0].outcome is True
    assert observations[0].realized_unit_return == pytest.approx(1.0)


def test_ledger_detects_tampering(tmp_path):
    path = tmp_path / "prospective.jsonl"
    ledger = FootballProspectiveEvidenceLedger(path)
    ledger.append_decision(_decision())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["payload"]["model_probability"] = 0.99
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ledger.load_events()


def test_ledger_rejects_duplicate_natural_decision(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    first = _decision(1)
    ledger.append_decision(first)
    duplicate = FrozenProspectiveDecision(
        **{
            **first.__dict__,
            "decision_id": "different-id",
        }
    )
    with pytest.raises(ValueError, match="duplicate fixture-market-selection-model"):
        ledger.append_decision(duplicate)


def test_ledger_rejects_closing_odds_before_decision(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    decision = _decision()
    ledger.append_decision(decision)
    with pytest.raises(ValueError, match="cannot precede"):
        ledger.append_closing_odds(_closing(decision, observed="2026-08-18T17:00:00+00:00"))


def test_ledger_rejects_duplicate_settlement(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    decision = _decision()
    ledger.append_decision(decision)
    ledger.append_settlement(_settlement(decision))
    with pytest.raises(ValueError, match="duplicate settlement"):
        ledger.append_settlement(_settlement(decision))


def test_performance_summary_measures_calibration_returns_and_clv(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    outcomes = [True, True, True, False] * 2
    for index, outcome in enumerate(outcomes, start=1):
        decision = _decision(index, block_id=f"block-{1 + ((index - 1) // 2)}")
        ledger.append_decision(decision)
        ledger.append_closing_odds(_closing(decision, odds=1.8))
        ledger.append_settlement(_settlement(decision, outcome=outcome))

    summary = ledger.performance_summary(
        market_key="over_2_5",
        model_version="football-over25-v1",
        bootstrap_iterations=200,
        random_seed=7,
    )
    assert summary.decision_count == 8
    assert summary.settled_count == 8
    assert summary.closing_odds_count == 8
    assert summary.brier_score == pytest.approx(0.1875)
    assert summary.calibration_error == pytest.approx(0.0)
    assert summary.mean_realized_unit_return == pytest.approx(0.5)
    assert summary.mean_log_clv == pytest.approx(log(2.0 / 1.8))
    assert summary.mean_log_clv_ci_low > 0


def test_prospective_policy_is_fail_closed_for_small_sample(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    decision = _decision()
    ledger.append_decision(decision)
    ledger.append_closing_odds(_closing(decision))
    ledger.append_settlement(_settlement(decision))
    summary = ledger.performance_summary(
        market_key="over_2_5",
        model_version="football-over25-v1",
        bootstrap_iterations=100,
    )
    reasons = ProspectivePerformancePolicy().reasons_blocked(summary)
    assert "insufficient_settled_prospective_sample" in reasons
    assert "insufficient_closing_odds_sample" in reasons


def test_prospective_policy_can_pass_strong_explicit_small_test_policy(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    outcomes = [True, True, True, False] * 2
    for index, outcome in enumerate(outcomes, start=1):
        decision = _decision(index, block_id=f"block-{1 + ((index - 1) // 2)}")
        ledger.append_decision(decision)
        ledger.append_closing_odds(_closing(decision, odds=1.8))
        ledger.append_settlement(_settlement(decision, outcome=outcome))
    summary = ledger.performance_summary(
        market_key="over_2_5",
        model_version="football-over25-v1",
        bootstrap_iterations=200,
        random_seed=7,
    )
    policy = ProspectivePerformancePolicy(
        min_settled_samples=8,
        min_closing_odds_samples=8,
        max_brier_score=0.20,
        max_calibration_error=0.01,
        max_mean_unit_loss=0.0,
    )
    assert policy.reasons_blocked(summary) == ()
    assert policy.verified(summary)


def test_prospective_policy_rejects_reference_price_that_is_not_near_kickoff(tmp_path):
    ledger = FootballProspectiveEvidenceLedger(tmp_path / "prospective.jsonl")
    outcomes = [True, True, True, False] * 2
    for index, outcome in enumerate(outcomes, start=1):
        decision = _decision(index, block_id=f"block-{1 + ((index - 1) // 2)}")
        ledger.append_decision(decision)
        ledger.append_closing_odds(_closing(decision, odds=1.8, observed="2026-08-18T18:00:00+00:00"))
        ledger.append_settlement(_settlement(decision, outcome=outcome))
    summary = ledger.performance_summary(
        market_key="over_2_5",
        model_version="football-over25-v1",
        bootstrap_iterations=200,
        random_seed=7,
    )
    policy = ProspectivePerformancePolicy(
        min_settled_samples=8,
        min_closing_odds_samples=8,
        max_brier_score=0.20,
        max_calibration_error=0.01,
        max_closing_odds_lead_minutes=15,
    )
    assert "closing_odds_not_near_kickoff" in policy.reasons_blocked(summary)
