from dataclasses import replace
import pytest

from matrix_elite.support_contract_binding_variants import (
    BINDING_VARIANTS,
    CANONICAL_API_FOOTBALL_PROVIDER_KEY,
    EXPECTED_VERSION_FIELDS,
    REQUIRED_CONTROLS,
    ScopeContext,
    registry_fingerprint,
    registry_payload,
    resolve_binding,
    validate_binding_registry,
)


def predictive(sport="football", family="CORNERS"):
    variant = "total-corners" if sport == "football" else "match-winner"
    if sport == "tennis":
        family = "MATCH_WINNER"
    return ScopeContext(
        "PREDICTIVE", sport,
        market_family=family,
        market_variant=variant,
        period="FULL_TIME" if sport == "football" else "MATCH",
        subject_scope="MATCH",
        line_semantics="TOTAL" if family == "CORNERS" else "NONE",
        line_unit="CORNER_COUNT" if family == "CORNERS" else "NONE",
        metric_key="corner_total" if family == "CORNERS" else "match_winner",
    )


def live(provider="api_football", sport="football"):
    return ScopeContext(
        "LIVE", sport,
        market_family="CORNERS" if sport == "football" else "MATCH_WINNER",
        market_variant="total-corners" if sport == "football" else "match-winner",
        period="FULL_TIME" if sport == "football" else "MATCH",
        subject_scope="MATCH",
        line_semantics="TOTAL" if sport == "football" else "NONE",
        line_unit="CORNER_COUNT" if sport == "football" else "NONE",
        metric_key="corner_total" if sport == "football" else "match_winner",
        provider_key=provider,
    )


def failover(sport="football", environment="SHADOW"):
    return ScopeContext(
        "FAILOVER", sport,
        primary_provider="provider-a",
        secondary_provider="provider-b",
        environment=environment,
    )


def test_registry_contains_exactly_21_required_controls_and_19_version_fields():
    validate_binding_registry()
    assert len(BINDING_VARIANTS) == 21
    assert {x.control_id for x in BINDING_VARIANTS} == set(REQUIRED_CONTROLS)
    assert len(EXPECTED_VERSION_FIELDS) == 19


def test_every_binding_version_binds_control_and_variant_and_has_content_fingerprint():
    for row in BINDING_VARIANTS:
        assert row.binding_version == f"MATRIX-SCB-R2/{row.control_id}/{row.variant_id}"
        assert len(row.fingerprint) == 64
    assert len({row.fingerprint for row in BINDING_VARIANTS}) == 21


def test_support_promotion_is_impossible_in_binding_constructor():
    row = BINDING_VARIANTS[0]
    with pytest.raises(ValueError, match="SUPPORT_PROMOTION_FORBIDDEN"):
        replace(row, support_declared=True)
    with pytest.raises(ValueError, match="SUPPORT_PROMOTION_FORBIDDEN"):
        replace(row, support_status="PASS")


def test_predictive_binding_resolves_for_both_sports():
    assert resolve_binding("baseline_definition", predictive("football")).variant_id == "global-baseline-v1"
    assert resolve_binding("baseline_definition", predictive("tennis")).variant_id == "global-baseline-v1"


def test_live_context_requires_provider_key_and_tennis_live_fails_closed():
    with pytest.raises(ValueError, match="SCOPE_PROVIDER_KEY_REQUIRED"):
        ScopeContext(
            "LIVE", "football", market_family="CORNERS", market_variant="total-corners",
            period="FULL_TIME", subject_scope="MATCH", line_semantics="TOTAL", line_unit="CORNER_COUNT", metric_key="corner_total",
        )
    with pytest.raises(ValueError, match="SUPPORT_CONTRACT_BINDING_NOT_FOUND"):
        resolve_binding("event_time_contract", live(sport="tennis", provider="tennis-provider"))


def test_shadow_binding_is_exactly_api_football_not_provider_agnostic():
    row = resolve_binding("shadow_live_protocol", live(CANONICAL_API_FOOTBALL_PROVIDER_KEY))
    assert row.variant_id == "football-provider-shadow-v1"
    with pytest.raises(ValueError, match="SUPPORT_CONTRACT_BINDING_NOT_FOUND"):
        resolve_binding("shadow_live_protocol", live("other-provider"))


def test_failover_context_preserves_ordered_distinct_pair_and_forbids_production():
    assert resolve_binding("rollback_plan", failover()).scope_kind == "FAILOVER"
    with pytest.raises(ValueError, match="SCOPE_PROVIDERS_MUST_DIFFER"):
        ScopeContext("FAILOVER", "football", primary_provider="same", secondary_provider="same", environment="SHADOW")
    with pytest.raises(ValueError, match="SCOPE_FAILOVER_ENVIRONMENT_INVALID"):
        failover(environment="PRODUCTION")


def test_football_only_identity_reconciliation_does_not_satisfy_tennis_failover():
    assert resolve_binding("identity_reconciliation_contract", failover("football")).variant_id == "football-provider-pair-v1"
    with pytest.raises(ValueError, match="SUPPORT_CONTRACT_BINDING_NOT_FOUND"):
        resolve_binding("identity_reconciliation_contract", failover("tennis"))


def test_static_registry_audit_rejects_overlapping_applicability():
    row = BINDING_VARIANTS[0]
    duplicate = replace(row, variant_id="overlap-v2")
    with pytest.raises(ValueError, match="R51_OVERLAPPING_APPLICABILITY:canonical_market_definition"):
        validate_binding_registry((*BINDING_VARIANTS, duplicate))


def test_registry_payload_keeps_all_governance_boundaries_false():
    payload = registry_payload()
    assert payload["support_status"] == "NOT_EVALUATED"
    for key in (
        "support_declared", "supportability_pack_ready", "candidate_inventory_generated",
        "selection_r2_executed", "builder_r2_executed", "registry_r3_executed",
        "freeze_r3_executed", "performance_information_used_for_scope_selection",
        "controlled_live_admissible", "production_admissible",
    ):
        assert payload[key] is False
    assert len(registry_fingerprint()) == 64


def test_no_generic_test_anchor_is_permitted():
    for row in BINDING_VARIANTS:
        for ref in row.test_refs:
            assert all(anchor.startswith("test_") for anchor in ref.anchors)
            assert all(anchor != "test_" for anchor in ref.anchors)


def test_new_contract_bindings_reference_exact_new_test_files():
    expected = {
        "canonical_market_definition": "tests/test_canonical_market_semantics.py",
        "settlement_rules": "tests/test_settlement_rules.py",
        "rollback_plan": "tests/security/test_provider_failover_rollback.py",
    }
    for control, path in expected.items():
        row = next(x for x in BINDING_VARIANTS if x.control_id == control)
        assert row.test_refs[0].path == path


def test_composite_bindings_keep_multiple_exact_evidence_refs():
    odds = next(x for x in BINDING_VARIANTS if x.control_id == "odds_binding_contract")
    evaluation = next(x for x in BINDING_VARIANTS if x.control_id == "evaluation_protocol")
    secondary = next(x for x in BINDING_VARIANTS if x.control_id == "secondary_rights_profile")
    assert len(odds.implementation_refs) == 2
    assert len(evaluation.implementation_refs) == 5
    assert len(secondary.implementation_refs) == 2 and len(secondary.test_refs) == 2


def test_scope_market_identity_is_not_family_only():
    with pytest.raises(ValueError, match="SCOPE_MARKET_VARIANT_REQUIRED"):
        ScopeContext(
            "PREDICTIVE", "football", market_family="CORNERS", market_variant=None,
            period="FULL_TIME", subject_scope="MATCH", line_semantics="TOTAL", line_unit="CORNER_COUNT", metric_key="corner_total",
        )


def test_line_markets_require_unit_in_runtime_scope_context():
    with pytest.raises(ValueError, match="SCOPE_LINE_UNIT_REQUIRED"):
        ScopeContext(
            "PREDICTIVE", "football", market_family="CORNERS", market_variant="total-corners",
            period="FULL_TIME", subject_scope="MATCH", line_semantics="TOTAL", line_unit=None, metric_key="corner_total",
        )


def test_scope_rejects_cross_sport_market_family_even_when_family_is_known():
    with pytest.raises(ValueError, match="SCOPE_MARKET_FAMILY_SPORT_MISMATCH"):
        ScopeContext(
            "PREDICTIVE", "football", market_family="MATCH_WINNER", market_variant="match-winner",
            period="MATCH", subject_scope="MATCH", line_semantics="NONE", line_unit="NONE", metric_key="match_winner",
        )


def test_scope_requires_explicit_metric_key_and_explicit_non_line_unit():
    with pytest.raises(ValueError, match="SCOPE_METRIC_KEY_REQUIRED"):
        ScopeContext(
            "PREDICTIVE", "football", market_family="RESULT_OR_DOUBLE_CHANCE", market_variant="result",
            period="FULL_TIME", subject_scope="MATCH", line_semantics="NONE", line_unit="NONE", metric_key=None,
        )
    with pytest.raises(ValueError, match="SCOPE_NONLINE_UNIT_MUST_BE_NONE"):
        ScopeContext(
            "PREDICTIVE", "football", market_family="RESULT_OR_DOUBLE_CHANCE", market_variant="result",
            period="FULL_TIME", subject_scope="MATCH", line_semantics="NONE", line_unit="GOAL_COUNT", metric_key="match_result",
        )


def test_registry_exposes_exact_version_field_mapping_not_only_a_count():
    payload = registry_payload()
    assert tuple(payload["expected_version_fields"]) == EXPECTED_VERSION_FIELDS
    mapped = [row["version_field"] for row in payload["variants"] if row["version_field"] is not None]
    assert len(mapped) == 19
    assert set(mapped) == set(EXPECTED_VERSION_FIELDS)
