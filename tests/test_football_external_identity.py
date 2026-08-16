import pytest

from app.sports.football.external_identity import ExternalMatchIdentity


def test_external_match_identity_can_be_created():
    identity = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )

    assert identity.provider == "api_football"
    assert identity.external_id == "1522161"


def test_external_match_identity_rejects_empty_provider():
    with pytest.raises(
        ValueError,
        match="provider no puede estar vacío",
    ):
        ExternalMatchIdentity(
            provider="   ",
            external_id="1522161",
        )


def test_external_match_identity_rejects_empty_external_id():
    with pytest.raises(
        ValueError,
        match="external_id no puede estar vacío",
    ):
        ExternalMatchIdentity(
            provider="api_football",
            external_id="   ",
        )

def test_external_match_identity_is_hashable_and_value_based():
    identity_a = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )
    identity_b = ExternalMatchIdentity(
        provider="api_football",
        external_id="1522161",
    )

    assert identity_a == identity_b
    assert len({identity_a, identity_b}) == 1
