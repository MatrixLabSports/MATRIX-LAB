from datetime import UTC, datetime

import pytest

import app.core.provider_network_execution_authorization as module
from app.core.provider_health_evidence import (
    SQLiteProviderHealthEvidenceLedger,
)
from app.core.provider_health_policy import (
    ProviderHealthDecision,
)
from app.core.provider_network_execution_authorization import (
    ProviderNetworkAuthority,
    SQLiteProviderNetworkPermitStore,
)
from app.core.provider_run_mode_evidence import (
    SQLiteProviderRunModeEvidenceStore,
)
from app.core.provider_scheduling_authorization import (
    authorize_provider_scheduling,
)
from app.core.provider_scheduling_evidence import (
    SQLiteProviderSchedulingEvidenceLedger,
)


NOW = datetime(
    2026,
    8,
    22,
    22,
    30,
    tzinfo=UTC,
)


def queue():
    return {
        "sport": "football",
        "queue": [
            {
                "sport": "football",
                "subject_key": "STATUS:API_FOOTBALL",
                "provider_key": "api_football",
                "competition_key": "CONNECTIVITY",
                "season_key": "2026",
                "queue_item_fingerprint": "1" * 64,
                "estimated_request_cost": 1,
                "source_fingerprint": "2" * 64,
            }
        ],
    }


def health_decision(
    *,
    status="REVIEW_REQUIRED",
    eligible=False,
    fingerprint_char="3",
):
    return ProviderHealthDecision(
        provider_key="api_football",
        sport="football",
        decision_status=status,
        scheduling_eligible=eligible,
        terminal_calls=1,
        failure_rate=0.0,
        zero_consumption_refusal_rate=0.0,
        policy_fingerprint="4" * 64,
        snapshot_fingerprint="5" * 64,
        reason_codes=(
            ("INSUFFICIENT_OBSERVATIONS",)
            if status == "REVIEW_REQUIRED"
            else ()
        ),
        decision_fingerprint=(
            fingerprint_char * 64
        ),
    )


class EndpointRegistry:
    def authorize_request(self, **kwargs):
        return type(
            "EndpointDecision",
            (),
            {
                "status": "AUTHORIZED",
                "executable": True,
                "manifest_id": "6" * 64,
                "decision_fingerprint": "7" * 64,
            },
        )()


class SecurityEvidence:
    def record(self, decision):
        return "8" * 64


def security_ok(**kwargs):
    return type(
        "SecurityDecision",
        (),
        {
            "status": "EXECUTE",
            "executable": True,
            "decision_fingerprint": "9" * 64,
        },
    )()


def build_bootstrap(
    tmp_path,
    *,
    health_status="REVIEW_REQUIRED",
    quarantine=True,
    max_items=1,
    max_requests=1,
    preflight_queue_fp=None,
    preflight_scheduling_fp=None,
):
    manifest = queue()

    health_ledger = (
        SQLiteProviderHealthEvidenceLedger(
            tmp_path / "health.db"
        )
    )
    decision = health_decision(
        status=health_status,
        eligible=(
            health_status == "ELIGIBLE"
        ),
    )
    health_ledger.record_decision(
        decision
    )

    scheduling = authorize_provider_scheduling(
        queue_manifest=manifest,
        health_decisions={
            "api_football": decision
        },
        expected_sport="football",
    )

    scheduling_ledger = (
        SQLiteProviderSchedulingEvidenceLedger(
            tmp_path / "scheduling.db"
        )
    )
    scheduling_ledger.record_authorization(
        authorization=scheduling,
        health_evidence_ledger=health_ledger,
    )

    preflight = type(
        "Preflight",
        (),
        {
            "status": "EXECUTE",
            "executable": True,
            "run_id": "c2-status-probe",
            "sport": "football",
            "provider_key": "api_football",
            "mode": "BOOTSTRAP_PROBE",
            "decision_fingerprint": "a" * 64,
            "queue_fingerprint": (
                scheduling.queue_fingerprint
                if preflight_queue_fp is None
                else preflight_queue_fp
            ),
            "scheduling_evidence_fingerprint": (
                scheduling.authorization_fingerprint
                if preflight_scheduling_fp is None
                else preflight_scheduling_fp
            ),
            "provider_health_status": (
                health_status
            ),
            "downstream_quarantine_required": (
                quarantine
            ),
            "max_items": max_items,
            "max_requests": max_requests,
        },
    )()

    network_store = (
        SQLiteProviderNetworkPermitStore(
            tmp_path / "network.db"
        )
    )

    authority = ProviderNetworkAuthority(
        run_id="c2-status-probe",
        sport="football",
        provider_key="api_football",
        mode="BOOTSTRAP_PROBE",
        queue_manifest=manifest,
        scheduling_authorization_fingerprint=(
            scheduling.authorization_fingerprint
        ),
        scheduling_evidence_ledger=(
            scheduling_ledger
        ),
        health_evidence_ledger=(
            health_ledger
        ),
        preflight_decision=preflight,
        preflight_evidence_store=object(),
        security_evidence_store=(
            SecurityEvidence()
        ),
        endpoint_registry=EndpointRegistry(),
        secret_reference=object(),
        secret_reference_fingerprint="b" * 64,
        secret_reference_registry=object(),
        network_permit_store=network_store,
        run_mode_evidence_store=(
            SQLiteProviderRunModeEvidenceStore(
                tmp_path / "mode.db"
            )
        ),
        clock=lambda: NOW,
        resolver=lambda host, port: (
            "8.8.8.8",
        ),
    )

    return authority, network_store


def test_review_required_bootstrap_does_not_call_production_gate(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "verify_provider_execution_authorization",
        lambda **kwargs: pytest.fail(
            "production execution gate must not "
            "run in BOOTSTRAP_PROBE"
        ),
    )
    monkeypatch.setattr(
        module,
        "evaluate_authoritative_provider_security",
        security_ok,
    )

    authority, store = build_bootstrap(
        tmp_path
    )
    permit = authority.authorize(
        request_nonce="one-status-call",
        method="GET",
        endpoint_url=(
            "https://v3.football."
            "api-sports.io/status"
        ),
        query_keys=(),
    )

    assert permit.mode == "BOOTSTRAP_PROBE"
    assert store.audit_integrity() is True


def test_eligible_bootstrap_is_also_valid(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "verify_provider_execution_authorization",
        lambda **kwargs: pytest.fail(
            "production execution gate must not "
            "run in BOOTSTRAP_PROBE"
        ),
    )
    monkeypatch.setattr(
        module,
        "evaluate_authoritative_provider_security",
        security_ok,
    )

    authority, _ = build_bootstrap(
        tmp_path,
        health_status="ELIGIBLE",
    )
    permit = authority.authorize(
        request_nonce="eligible-status-call",
        method="GET",
        endpoint_url=(
            "https://v3.football."
            "api-sports.io/status"
        ),
        query_keys=(),
    )

    assert permit.mode == "BOOTSTRAP_PROBE"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        (
            "preflight_queue_fp",
            "0" * 64,
            "BOOTSTRAP_PREFLIGHT_QUEUE_MISMATCH",
        ),
        (
            "preflight_scheduling_fp",
            "0" * 64,
            "BOOTSTRAP_SCHEDULING_EVIDENCE_MISMATCH",
        ),
        (
            "quarantine",
            False,
            "BOOTSTRAP_QUARANTINE_REQUIRED",
        ),
        (
            "max_items",
            2,
            "BOOTSTRAP_SINGLE_ITEM_REQUIRED",
        ),
        (
            "max_requests",
            2,
            "BOOTSTRAP_SINGLE_REQUEST_REQUIRED",
        ),
    ],
)
def test_bootstrap_preflight_binding_mismatch_fails_closed(
    tmp_path,
    monkeypatch,
    field,
    value,
    reason,
):
    security_calls = []

    monkeypatch.setattr(
        module,
        "verify_provider_execution_authorization",
        lambda **kwargs: pytest.fail(
            "production execution gate must not "
            "run in BOOTSTRAP_PROBE"
        ),
    )
    monkeypatch.setattr(
        module,
        "evaluate_authoritative_provider_security",
        lambda **kwargs: (
            security_calls.append(kwargs)
            or security_ok()
        ),
    )

    authority, _ = build_bootstrap(
        tmp_path,
        **{field: value},
    )

    with pytest.raises(
        ValueError,
        match=reason,
    ):
        authority.authorize(
            request_nonce="blocked",
            method="GET",
            endpoint_url=(
                "https://v3.football."
                "api-sports.io/status"
            ),
            query_keys=(),
        )

    assert security_calls == []


def test_ineligible_bootstrap_health_fails_closed(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        module,
        "verify_provider_execution_authorization",
        lambda **kwargs: pytest.fail(
            "production execution gate must not run"
        ),
    )
    monkeypatch.setattr(
        module,
        "evaluate_authoritative_provider_security",
        lambda **kwargs: pytest.fail(
            "security must not run"
        ),
    )

    authority, _ = build_bootstrap(
        tmp_path,
        health_status="INELIGIBLE",
    )

    with pytest.raises(
        ValueError,
        match="BOOTSTRAP_PROVIDER_HEALTH_NOT_ALLOWED",
    ):
        authority.authorize(
            request_nonce="blocked-health",
            method="GET",
            endpoint_url=(
                "https://v3.football."
                "api-sports.io/status"
            ),
            query_keys=(),
        )


def test_production_path_still_contains_normal_execution_gate():
    source = __import__("pathlib").Path(
        "app/core/provider_network_execution_authorization.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    assert 'if self.mode == "PRODUCTION":' in source
    assert (
        "execution = verify_provider_execution_authorization("
        in source
    )
    assert (
        '"production_health_eligibility_required": False'
        in source
    )
