from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.controlled_network_certification import (
    certify_controlled_network_boundary,
)
from app.core.governed_provider_http import (
    SQLiteProviderNetworkCallEvidenceStore,
)
from app.core.governed_provider_request import (
    JitSecretPinnedHttpsTransport,
)
from app.core.pinned_https_transport import (
    StdlibPinnedHttpsTransport,
)
from app.core.provider_activation_readiness import (
    certify_provider_activation_readiness,
)
from app.core.provider_attempt_intent import (
    SQLiteProviderAttemptIntentStore,
)
from app.core.provider_contract_endpoint_binding import (
    SQLiteProviderContractEndpointBindingStore,
    build_provider_contract_endpoint_binding,
)
from app.core.provider_endpoint_authorization import (
    SQLiteProviderEndpointAuthorizationRegistry,
    build_provider_endpoint_manifest,
)
from app.core.provider_legal_evidence import (
    SQLiteProviderLegalEvidenceStore,
    build_provider_legal_evidence,
)
from app.core.provider_network_binding import (
    BindingAuditPinnedHttpsTransport,
    ProviderNetworkBindingCollector,
    SQLiteProviderNetworkBindingEvidenceStore,
)
from app.core.provider_network_execution_authorization import (
    SQLiteProviderNetworkPermitStore,
)
from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    build_secret_reference,
)
from app.providers.api_football.request_contracts import (
    build_api_football_request_contracts,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def _rule_name(rule):
    return (
        getattr(rule, "name", None)
        or getattr(rule, "parameter_name", None)
        or getattr(rule, "key", None)
    )


def _setup(tmp_path):
    secret = build_secret_reference(
        provider_key="api_football",
        environment_variable=(
            "MATRIX_API_FOOTBALL_KEY"
        ),
        secret_type="API_KEY",
    )

    contracts = (
        build_api_football_request_contracts(
            secret_reference_fingerprint=(
                secret.reference_fingerprint
            ),
            valid_from=NOW,
        )
    )
    contract = contracts[
        "fixture_by_id"
    ]

    contract_registry = (
        SQLiteProviderRequestContractRegistry(
            tmp_path / "contracts.db"
        )
    )
    contract_registry.register(
        contract
    )

    endpoint_registry = (
        SQLiteProviderEndpointAuthorizationRegistry(
            tmp_path / "endpoint-auth.db"
        )
    )

    query_keys = tuple(
        name
        for rule
        in tuple(
            getattr(
                contract,
                "parameter_rules",
                (),
            )
        )
        for name
        in (
            _rule_name(rule),
        )
        if name
    )

    manifest = (
        build_provider_endpoint_manifest(
            provider_key=(
                contract.provider_key
            ),
            sport=contract.sport,
            method=contract.method,
            endpoint_url=(
                "https://api.example.test"
                + contract.path
            ),
            allowed_query_keys=(
                query_keys
            ),
            secret_reference_fingerprint=(
                secret.reference_fingerprint
            ),
            valid_from=NOW,
        )
    )
    endpoint_registry.register(
        manifest
    )

    endpoint_binding_store = (
        SQLiteProviderContractEndpointBindingStore(
            tmp_path / "contract-endpoint.db"
        )
    )
    endpoint_binding_store.register(
        build_provider_contract_endpoint_binding(
            provider_key=(
                contract.provider_key
            ),
            sport=contract.sport,
            request_contract_id=(
                contract.contract_id
            ),
            endpoint_manifest_id=(
                manifest.manifest_id
            ),
            path=contract.path,
            valid_from=NOW,
            valid_until=None,
        )
    )

    legal_store = (
        SQLiteProviderLegalEvidenceStore(
            tmp_path / "legal.db"
        )
    )
    legal = (
        build_provider_legal_evidence(
            evidence_kind=(
                "PROVIDER_TERMS"
            ),
            source_reference=(
                "api-sports-terms"
            ),
            content_fingerprint=(
                "7" * 64
            ),
            captured_at=NOW,
            verified_by=(
                "matrix-test-reviewer"
            ),
            verification_reference=(
                "8" * 64
            ),
        )
    )
    legal_store.record(
        legal
    )

    binding_store = (
        SQLiteProviderNetworkBindingEvidenceStore(
            tmp_path / "binding.db"
        )
    )
    permit_store = (
        SQLiteProviderNetworkPermitStore(
            tmp_path / "permit.db"
        )
    )
    call_store = (
        SQLiteProviderNetworkCallEvidenceStore(
            tmp_path / "call.db"
        )
    )
    attempt_store = (
        SQLiteProviderAttemptIntentStore(
            tmp_path / "intent.db"
        )
    )

    governed = (
        BindingAuditPinnedHttpsTransport(
            inner=(
                JitSecretPinnedHttpsTransport(
                    inner=(
                        StdlibPinnedHttpsTransport()
                    ),
                    secret_reference=secret,
                    auth_header_name=(
                        "x-apisports-key"
                    ),
                )
            ),
            binding_store=(
                binding_store
            ),
            collector=(
                ProviderNetworkBindingCollector()
            ),
            clock=lambda: NOW,
            attempt_intent_store=(
                attempt_store
            ),
        )
    )

    boundary = (
        certify_controlled_network_boundary(
            transport=governed,
            request_contract_registry=(
                contract_registry
            ),
            binding_store=(
                binding_store
            ),
            network_permit_store=(
                permit_store
            ),
            network_call_evidence_store=(
                call_store
            ),
        )
    )

    rights = SimpleNamespace(
        authorized=False,
        blockers=(
            "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED",
        ),
    )

    return {
        "secret": secret,
        "contract": contract,
        "contract_registry": (
            contract_registry
        ),
        "endpoint_registry": (
            endpoint_registry
        ),
        "endpoint_binding_store": (
            endpoint_binding_store
        ),
        "legal_store": legal_store,
        "legal": legal,
        "attempt_store": attempt_store,
        "governed": governed,
        "boundary": boundary,
        "rights": rights,
    }


def _certify(state, **overrides):
    values = {
        "network_boundary_certification": (
            state["boundary"]
        ),
        "governed_transport": (
            state["governed"]
        ),
        "secret_reference": (
            state["secret"]
        ),
        "request_contract_registry": (
            state[
                "contract_registry"
            ]
        ),
        "request_contract_ids": (
            state[
                "contract"
            ].contract_id,
        ),
        "contract_endpoint_binding_store": (
            state[
                "endpoint_binding_store"
            ]
        ),
        "endpoint_authorization_registry": (
            state[
                "endpoint_registry"
            ]
        ),
        "endpoint_base_url": (
            "https://api.example.test"
        ),
        "as_of": NOW,
        "legal_evidence_store": (
            state["legal_store"]
        ),
        "legal_evidence_ids": (
            state["legal"].evidence_id,
        ),
        "rights_decision": (
            state["rights"]
        ),
        "attempt_intent_store": (
            state["attempt_store"]
        ),
    }
    values.update(
        overrides
    )
    return (
        certify_provider_activation_readiness(
            **values
        )
    )


def test_readiness_cross_binds_endpoint_legal_and_attempt_store(
    tmp_path,
):
    state = _setup(
        tmp_path
    )
    certification = _certify(
        state
    )

    assert (
        certification.status
        == "TECHNICALLY_READY_RIGHTS_BLOCKED"
    )
    assert (
        certification.endpoint_manifest_semantics_verified
        is True
    )
    assert (
        certification.legal_evidence_nonempty
        is True
    )
    assert (
        certification.attempt_intent_store_cross_bound
        is True
    )
    assert (
        certification.real_provider_execution_authorized
        is False
    )


def test_empty_legal_evidence_cannot_certify(
    tmp_path,
):
    state = _setup(
        tmp_path
    )
    certification = _certify(
        state,
        legal_evidence_ids=(),
    )

    assert certification.status == "NOT_READY"
    assert (
        "NONEMPTY_LEGAL_EVIDENCE_REQUIRED"
        in certification.blockers
    )


def test_arbitrary_attempt_store_cannot_certify(
    tmp_path,
):
    state = _setup(
        tmp_path
    )
    other = (
        SQLiteProviderAttemptIntentStore(
            tmp_path / "other-intent.db"
        )
    )
    certification = _certify(
        state,
        attempt_intent_store=other,
    )

    assert certification.status == "NOT_READY"
    assert (
        "ATTEMPT_INTENT_STORE_CROSS_BINDING_REQUIRED"
        in certification.blockers
    )


def test_revoked_endpoint_manifest_blocks_readiness(
    tmp_path,
):
    state = _setup(
        tmp_path
    )
    state[
        "endpoint_registry"
    ].revoke(
        manifest_id=(
            state[
                "endpoint_binding_store"
            ].get_verified_by_contract(
                state[
                    "contract"
                ].contract_id
            ).endpoint_manifest_id
        ),
        revoked_at=NOW,
        reason_code="TEST_REVOKE",
    )

    certification = _certify(
        state
    )

    assert certification.status == "NOT_READY"
    assert (
        "ENDPOINT_MANIFEST_SEMANTIC_AUTHORIZATION_REQUIRED"
        in certification.blockers
    )
