import json
from pathlib import Path


REGISTRY = Path("config/matrix_multisource_registry.json")


def _load():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_multisource_registry_is_permanent_and_scoped_to_tennis_football():
    data = _load()
    assert data["schema"] == "MATRIX_MULTI_SOURCE_REGISTRY_V1"
    assert data["permanent_rule"] is True
    assert set(data["sports_scope"]) == {"tennis", "football"}


def test_global_multisource_safeguards_cannot_be_disabled():
    policy = _load()["global_policy"]
    assert policy["all_managed_sources_must_be_considered"] is True
    assert policy["all_accessible_sources_should_be_queried_for_discovery_and_crosscheck"] is True
    assert policy["source_failure_or_unavailability_must_be_persisted"] is True
    assert policy["silent_source_omission_forbidden"] is True
    assert policy["silent_overwrite_forbidden"] is True
    assert policy["no_single_source_can_declare_world_complete"] is True
    assert policy["source_specific_counts_must_remain_source_specific_until_reconciliation"] is True
    assert policy["canonical_identity_before_cross_provider_merge"] is True
    assert policy["physical_dedupe_before_counter_increment"] is True
    assert policy["discrepancies_must_be_persisted_and_adjudicated"] is True
    assert policy["pit_cutoff_required_for_model_features"] is True
    assert policy["missing_not_zero"] is True
    assert policy["silent_imputation_forbidden"] is True
    assert policy["odds_to_p_matrix_forbidden"] is True
    assert policy["real_money"] == "BLOCKED"
    assert policy["automatic_wagering"] is False


def test_tennis_keeps_both_paid_apis_and_public_crosschecks():
    tennis = _load()["tennis"]
    paid = {x["id"] for x in tennis["primary_paid_structured"]}
    public = {x["id"] for x in tennis["public_free_browser_and_official"]}
    assert {"rapidapi_tennis", "api_tennis"} <= paid
    assert {"sofascore", "flashscore", "atp_official", "wta_official", "itf_official"} <= public
    assert tennis["paid_api_dual_use_required"] is True
    assert tennis["protected_cor0203_domain"] == "ATP Challenger + Hard + Singles + Match Winner"


def test_football_keeps_paid_primary_public_crosschecks_and_reference_separation():
    football = _load()["football"]
    paid = {x["id"] for x in football["primary_paid_structured"]}
    public = {x["id"] for x in football["public_free_browser_and_official"]}
    refs = {x["id"]: x for x in football["reference_price_sources"]}
    assert "api_football" in paid
    assert {"sofascore", "flashscore", "official_competition_team_sources"} <= public
    assert "pinnacle_reference" in refs
    assert refs["pinnacle_reference"]["execution_authorized"] is False


def test_reconciliation_contract_requires_status_identity_and_dedupe():
    contract = _load()["reconciliation_contract"]
    assert contract["discovery_fanout_before_world_inventory_close"] is True
    assert contract["source_counts_are_never_summed_without_deduplication"] is True
    assert contract["entity_identity_reconciliation_required"] is True
    assert contract["provider_aliases_must_be_persisted"] is True
    assert contract["timestamp_and_timezone_provenance_required"] is True
    assert contract["every_model_feature_requires_pit_provenance"] is True
    assert contract["browser_sources_may_expand_discovery_but_not_bypass_model_gates"] is True
    assert set(contract["exact_source_status_required"]) >= {
        "QUERIED", "PASS", "NO_COVERAGE", "BLOCKED", "UNAVAILABLE"
    }
