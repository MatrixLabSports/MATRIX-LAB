from datetime import datetime, timezone

import pytest

from app.core.provider_legal_evidence import (
    SQLiteProviderLegalEvidenceStore,
    build_provider_legal_evidence,
)
from app.core.provider_rights_authorization import (
    SQLiteProviderRightsAuthorizationStore,
    build_provider_rights_grant,
)
from app.providers.api_football.rights_baseline import (
    api_football_rights_baseline,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def _legal_store(tmp_path):
    store = SQLiteProviderLegalEvidenceStore(
        tmp_path / "legal.db"
    )

    for kind, fingerprint, source in (
        (
            "PROVIDER_TERMS",
            "1" * 64,
            "provider-terms-source",
        ),
        (
            "RIGHTS_HOLDER_LICENSE",
            "3" * 64,
            "rights-holder-source",
        ),
        (
            "HUMAN_APPROVAL",
            "2" * 64,
            "approval-record",
        ),
    ):
        store.record(
            build_provider_legal_evidence(
                evidence_kind=kind,
                source_reference=source,
                content_fingerprint=fingerprint,
                captured_at=NOW,
                verified_by="legal-reviewer",
                verification_reference="9" * 64,
            )
        )

    return store


def test_api_football_rights_baseline_is_fail_closed():
    baseline = api_football_rights_baseline()

    assert (
        baseline.authorization_status
        == "BLOCKED_PENDING_RIGHTS_REVIEW"
    )
    assert baseline.legal_review_required is True
    assert (
        baseline.real_provider_execution_authorized
        is False
    )


def test_production_rights_never_activate_from_opaque_self_asserted_fingerprints(
    tmp_path,
):
    store = SQLiteProviderRightsAuthorizationStore(
        tmp_path / "rights.db"
    )

    grant = build_provider_rights_grant(
        provider_key="api_football",
        sport="football",
        use_case="BETTING_PLATFORM",
        environment="PRODUCTION",
        status="APPROVED",
        provider_terms_reference="arbitrary",
        provider_terms_fingerprint="1" * 64,
        rights_holder_evidence_reference="arbitrary",
        rights_holder_evidence_fingerprint="3" * 64,
        commercial_use_allowed=True,
        publication_allowed=True,
        betting_platform_use_allowed=True,
        redistribution_allowed=True,
        effective_from=NOW,
        expires_at=None,
        approved_by="arbitrary-human",
        approval_reference="2" * 64,
        created_at=NOW,
    )

    store.register(grant)

    decision = store.authorize(
        grant_id=grant.grant_id,
        provider_key="api_football",
        sport="football",
        use_case="BETTING_PLATFORM",
        environment="PRODUCTION",
        now=NOW,
        legal_evidence_store=_legal_store(
            tmp_path
        ),
    )

    assert decision.authorized is False
    assert (
        "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED"
        in decision.blockers
    )


def test_shadow_internal_analytics_requires_verified_external_evidence(
    tmp_path,
):
    store = SQLiteProviderRightsAuthorizationStore(
        tmp_path / "rights.db"
    )

    grant = build_provider_rights_grant(
        provider_key="api_football",
        sport="football",
        use_case="INTERNAL_ANALYTICS",
        environment="SHADOW",
        status="APPROVED",
        provider_terms_reference="terms",
        provider_terms_fingerprint="1" * 64,
        rights_holder_evidence_reference=None,
        rights_holder_evidence_fingerprint=None,
        commercial_use_allowed=False,
        publication_allowed=False,
        betting_platform_use_allowed=False,
        redistribution_allowed=False,
        effective_from=NOW,
        expires_at=None,
        approved_by="legal-reviewer",
        approval_reference="2" * 64,
        created_at=NOW,
    )

    store.register(grant)

    without_evidence = store.authorize(
        grant_id=grant.grant_id,
        provider_key="api_football",
        sport="football",
        use_case="INTERNAL_ANALYTICS",
        environment="SHADOW",
        now=NOW,
    )

    assert without_evidence.authorized is False
    assert (
        "PROVIDER_LEGAL_EVIDENCE_STORE_REQUIRED"
        in without_evidence.blockers
    )

    with_evidence = store.authorize(
        grant_id=grant.grant_id,
        provider_key="api_football",
        sport="football",
        use_case="INTERNAL_ANALYTICS",
        environment="SHADOW",
        now=NOW,
        legal_evidence_store=_legal_store(
            tmp_path
        ),
    )

    assert with_evidence.authorized is True
    assert with_evidence.blockers == ()


def test_legal_evidence_store_rederives_integrity(
    tmp_path,
):
    legal = _legal_store(
        tmp_path
    )

    assert legal.audit_integrity() is True
