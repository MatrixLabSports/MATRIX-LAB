from dataclasses import replace
from datetime import datetime, timezone

from app.application.football.runtime_admission_gate import (
    evaluate_football_runtime_admission,
)
from app.application.tennis.audited_acquisition_execution import (
    execute_audited_tennis_acquisition_queue,
)
from app.application.tennis.runtime_admission_gate import (
    evaluate_tennis_runtime_admission,
)
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.provider_circuit_breaker import (
    ProviderCircuitPolicy,
    SQLiteProviderCircuitStore,
)
from app.core.provider_quota import (
    ProviderQuotaPolicy,
    SQLiteProviderQuotaStore,
)
from app.core.provider_retry import (
    ProviderRetryPolicy,
    RetryableProviderError,
)
from app.core.provider_runtime_stack import build_provider_runtime_stack
from app.core.runtime_audit_ledger import SQLiteRuntimeAuditLedger
from app.core.runtime_reconciliation import reconcile_runtime_run


UTC = timezone.utc
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class SequenceFetcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def fetch(self, queue_item):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def item(char="1"):
    return {
        "sport": "tennis",
        "subject_key": "PLAYER:1",
        "provider_key": "P1",
        "competition_key": "C1",
        "season_key": "2026",
        "queue_item_fingerprint": char * 64,
        "estimated_request_cost": 1,
        "source_fingerprint": "a" * 64,
    }


def run(tmp_path, outcomes, *, attempts=1, char="1"):
    path = tmp_path / "runtime.db"
    audit = SQLiteRuntimeAuditLedger(path)
    persistence = SQLiteAcquisitionStore(path)

    runtime = build_provider_runtime_stack(
        fetcher=SequenceFetcher(outcomes),
        quota_store=SQLiteProviderQuotaStore(path),
        circuit_store=SQLiteProviderCircuitStore(path),
        quota_policies={
            "P1": ProviderQuotaPolicy(
                provider_key="P1",
                window_seconds=60,
                max_request_units=10,
            )
        },
        circuit_policies={
            "P1": ProviderCircuitPolicy(
                provider_key="P1",
                failure_threshold=10,
                cooldown_seconds=60,
            )
        },
        retry_policies={
            "P1": ProviderRetryPolicy(
                provider_key="P1",
                max_attempts=attempts,
                base_delay_seconds=0.0,
                max_delay_seconds=0.0,
                jitter_ratio=0.0,
            )
        },
        max_request_units=5,
        clock=lambda: NOW,
        sleeper=lambda _: None,
    )

    policy = audit.policy_fingerprint(
        quota_policies={"P1": {"limit": 10}},
        circuit_policies={"P1": {"threshold": 10}},
        retry_policies={"P1": {"attempts": attempts}},
        worker_limits={"max_items": 10, "max_requests": 5},
    )

    result = execute_audited_tennis_acquisition_queue(
        queue_manifest={"sport": "tennis", "queue": [item(char)]},
        policy_fingerprint=policy,
        audit_ledger=audit,
        fetcher=runtime.fetcher,
        raw_ledger=persistence,
        checkpoints=persistence,
        limits=WorkerLimits(max_items=10, max_requests=5),
        clock=lambda: NOW,
        request_budget=runtime.request_budget,
    )

    report = reconcile_runtime_run(
        run_id=result.run_id,
        audit_ledger=audit,
        acquisition_store=persistence,
    )

    return result, report, audit


def test_clean_reconciled_run_is_admitted(tmp_path):
    _, report, audit = run(
        tmp_path,
        [{"value": 1}],
    )

    decision = evaluate_tennis_runtime_admission(
        report=report,
        audit_ledger=audit,
    )

    assert decision.admission_status == "ADMIT"
    assert decision.downstream_eligible is True
    assert decision.failed == 0
    assert decision.reason_codes == ()


def test_retry_run_can_be_admitted_when_reconciled(tmp_path):
    _, report, audit = run(
        tmp_path,
        [
            RetryableProviderError("temporary"),
            {"value": 2},
        ],
        attempts=2,
        char="2",
    )

    decision = evaluate_tennis_runtime_admission(
        report=report,
        audit_ledger=audit,
    )

    assert decision.admission_status == "ADMIT"
    assert decision.downstream_eligible is True
    assert report.requests_used == 2


def test_worker_failure_is_quarantined(tmp_path):
    result, report, audit = run(
        tmp_path,
        [RetryableProviderError("down")],
        attempts=1,
        char="3",
    )

    decision = evaluate_tennis_runtime_admission(
        report=report,
        audit_ledger=audit,
    )

    assert result.worker_result.failed == 1
    assert decision.admission_status == "QUARANTINE"
    assert decision.downstream_eligible is False
    assert "WORKER_FAILURES_PRESENT" in decision.reason_codes


def test_failed_reconciliation_is_quarantined(tmp_path):
    _, report, audit = run(
        tmp_path,
        [{"value": 4}],
        char="4",
    )

    corrupted = replace(
        report,
        ok=False,
        errors=("SYNTHETIC_FAILURE",),
    )

    decision = evaluate_tennis_runtime_admission(
        report=corrupted,
        audit_ledger=audit,
    )

    assert decision.admission_status == "QUARANTINE"
    assert "RECONCILIATION_FAILED" in decision.reason_codes


def test_unknown_consumption_is_quarantined(tmp_path):
    _, report, audit = run(
        tmp_path,
        [{"value": 5}],
        char="5",
    )

    unknown = replace(
        report,
        provider_consumed_units=None,
    )

    decision = evaluate_tennis_runtime_admission(
        report=unknown,
        audit_ledger=audit,
    )

    assert decision.admission_status == "QUARANTINE"
    assert "UNKNOWN_PROVIDER_CONSUMPTION" in decision.reason_codes


def test_cross_sport_adapter_quarantines_run(tmp_path):
    _, report, audit = run(
        tmp_path,
        [{"value": 6}],
        char="6",
    )

    decision = evaluate_football_runtime_admission(
        report=report,
        audit_ledger=audit,
    )

    assert decision.admission_status == "QUARANTINE"
    assert decision.downstream_eligible is False
    assert "SPORT_BOUNDARY_VIOLATION" in decision.reason_codes


def test_decision_fingerprint_is_deterministic(tmp_path):
    _, report, audit = run(
        tmp_path,
        [{"value": 7}],
        char="7",
    )

    first = evaluate_tennis_runtime_admission(
        report=report,
        audit_ledger=audit,
    )
    second = evaluate_tennis_runtime_admission(
        report=report,
        audit_ledger=audit,
    )

    assert first.decision_fingerprint == second.decision_fingerprint
    assert len(first.decision_fingerprint) == 64


def test_admission_payload_keeps_safety_flags_false(tmp_path):
    _, report, audit = run(
        tmp_path,
        [{"value": 8}],
        char="8",
    )

    payload = evaluate_tennis_runtime_admission(
        report=report,
        audit_ledger=audit,
    ).payload()

    assert payload["automatic_model_promotion"] is False
    assert payload["automatic_provider_switch"] is False
    assert payload["automatic_wagering"] is False
