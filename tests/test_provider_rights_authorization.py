from datetime import datetime, timezone

import pytest

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


def test_api_football_rights_baseline_is_fail_closed():
    baseline = api_football_rights_baseline()

    assert (
        baseline.authorization_status
        == "BLOCKED_PENDING_RIGHTS_REVIEW"
    )
    assert baseline.legal_review_required is True
    assert (
        baseline.betting_platform_additional_rights_review_required
        is True
    )
    assert (
        baseline.real_provider_execution_authorized
        is False
    )


def test_betting_platform_grant_requires_rights_holder_evidence():
    with pytest.raises(
        ValueError,
        match="RIGHTS_HOLDER_EVIDENCE_REQUIRED",
    ):
        build_provider_rights_grant(
            provider_key="api_football",
            sport="football",
            use_case="BETTING_PLATFORM",
            environment="PRODUCTION",
            status="APPROVED",
            provider_terms_reference="terms-ref",
            provider_terms_fingerprint="1" * 64,
            rights_holder_evidence_reference=None,
            rights_holder_evidence_fingerprint=None,
            commercial_use_allowed=True,
            publication_allowed=True,
            betting_platform_use_allowed=True,
            redistribution_allowed=False,
            effective_from=NOW,
            expires_at=None,
            approved_by="human-legal-review",
            approval_reference="2" * 64,
            created_at=NOW,
        )


def test_approved_rights_can_be_authorized_and_revoked(
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
        provider_terms_reference="terms-ref",
        provider_terms_fingerprint="1" * 64,
        rights_holder_evidence_reference="rights-ref",
        rights_holder_evidence_fingerprint="3" * 64,
        commercial_use_allowed=True,
        publication_allowed=True,
        betting_platform_use_allowed=True,
        redistribution_allowed=False,
        effective_from=NOW,
        expires_at=None,
        approved_by="human-legal-review",
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
    )

    assert decision.authorized is True
    assert decision.blockers == ()
    assert store.audit_integrity() is True

    store.revoke(
        grant.grant_id,
        revoked_at=NOW,
    )

    revoked = store.authorize(
        grant_id=grant.grant_id,
        provider_key="api_football",
        sport="football",
        use_case="BETTING_PLATFORM",
        environment="PRODUCTION",
        now=NOW,
    )

    assert revoked.authorized is False
    assert "PROVIDER_RIGHTS_REVOKED" in revoked.blockers


def test_pending_rights_never_authorize(
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
        status="PENDING_REVIEW",
        provider_terms_reference="terms-ref",
        provider_terms_fingerprint="1" * 64,
        rights_holder_evidence_reference=None,
        rights_holder_evidence_fingerprint=None,
        commercial_use_allowed=False,
        publication_allowed=False,
        betting_platform_use_allowed=False,
        redistribution_allowed=False,
        effective_from=NOW,
        expires_at=None,
        approved_by=None,
        approval_reference=None,
        created_at=NOW,
    )

    store.register(grant)

    decision = store.authorize(
        grant_id=grant.grant_id,
        provider_key="api_football",
        sport="football",
        use_case="INTERNAL_ANALYTICS",
        environment="SHADOW",
        now=NOW,
    )

    assert decision.authorized is False
    assert (
        "PROVIDER_RIGHTS_NOT_APPROVED"
        in decision.blockers
    )
