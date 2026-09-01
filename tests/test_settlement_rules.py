from dataclasses import replace
from datetime import UTC, datetime, timedelta
import pytest
from app.core.canonical_market_semantics import canonical_candidate_market_definitions
from app.core.settlement_rules import (
    DNPPolicy, PushPolicy, SettlementRuleDefinition,
    validate_settlement_profile_for_market,
)

NOW = datetime(2026, 9, 1, tzinfo=UTC)

def rule(**kw):
    market = canonical_candidate_market_definitions()[2]
    d = dict(
        version="MATRIX-SETTLE-R2/book-a/football/CORNERS/total-corners/v1",
        market_version=market.version,
        sport=market.sport,
        market_family=market.market_family,
        market_variant=market.market_variant,
        period=market.period,
        venue="book-a",
        jurisdiction="CO",
        valid_from=NOW,
        valid_until=None,
        rule_source_sha256="a"*64,
        outcome_source="OFFICIAL_SETTLEMENT_FEED",
        push_policy=PushPolicy.PUSH,
        dnp_policy=DNPPolicy.NOT_APPLICABLE,
        abandonment_rule="VENUE_RULE_SOURCE_REQUIRED",
        postponement_rule="VENUE_RULE_SOURCE_REQUIRED",
        provider_override_required=True,
    )
    d.update(kw)
    return SettlementRuleDefinition(**d)


def test_settlement_profile_binds_exact_venue_jurisdiction_time_and_rule_source():
    r = rule()
    assert r.venue == "book-a" and r.jurisdiction == "CO"
    assert r.applies_at(NOW + timedelta(seconds=1))
    assert len(r.fingerprint) == 64


def test_settlement_profile_requires_exact_rule_source_sha256():
    with pytest.raises(ValueError, match="RULE_SOURCE_SHA256_REQUIRED"):
        rule(rule_source_sha256="not-a-sha")


def test_provider_override_cannot_hide_behind_generic_venue():
    with pytest.raises(ValueError, match="PROVIDER_OVERRIDE_REQUIRES_EXACT_VENUE"):
        rule(venue="CANONICAL_GENERIC", version="MATRIX-SETTLE-R2/CANONICAL_GENERIC/football/CORNERS/total-corners/v1")


def test_settlement_version_binds_venue_and_market_identity():
    with pytest.raises(ValueError, match="SETTLEMENT_VERSION_IDENTITY_MISMATCH"):
        rule(market_variant="different")


def test_invalid_validity_window_fails_closed():
    with pytest.raises(ValueError, match="SETTLEMENT_VALIDITY_WINDOW_INVALID"):
        rule(valid_until=NOW)


def test_settlement_profile_must_match_exact_market_payload():
    r = rule()
    market = canonical_candidate_market_definitions()[2]
    validate_settlement_profile_for_market(r, market.payload())
    bad = dict(market.payload()); bad["period"] = "FIRST_HALF"
    with pytest.raises(ValueError, match="SETTLEMENT_MARKET_BINDING_MISMATCH:period"):
        validate_settlement_profile_for_market(r, bad)
