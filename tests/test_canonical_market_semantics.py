from dataclasses import replace
import pytest
from app.core.canonical_market_semantics import (
    ExecutableMarketDefinition, LineSemantics, VoidabilityClass,
    canonical_candidate_market_definitions, validate_market_registry,
)


def test_all_12_candidate_families_have_explicit_executable_identity():
    rows = canonical_candidate_market_definitions()
    assert len(rows) == 12
    assert len({row.key for row in rows}) == 12
    assert all(row.market_variant and row.period and row.subject_scope for row in rows)
    assert all(len(row.fingerprint) == 64 for row in rows)


def test_market_version_binds_sport_family_and_variant():
    row = canonical_candidate_market_definitions()[0]
    with pytest.raises(ValueError, match="MARKET_VERSION_IDENTITY_MISMATCH"):
        replace(row, market_variant="tampered")


def test_line_semantics_require_line_and_unit():
    row = canonical_candidate_market_definitions()[2]
    with pytest.raises(ValueError, match="LINE_SEMANTICS_REQUIRE_LINE_AND_UNIT"):
        replace(row, line_unit=None)
    with pytest.raises(ValueError, match="LINE_SEMANTICS_REQUIRE_LINE_AND_UNIT"):
        replace(row, selection_schema=("OVER", "UNDER"))


def test_non_line_market_rejects_hidden_line_unit():
    row = canonical_candidate_market_definitions()[0]
    with pytest.raises(ValueError, match="LINE_UNIT_FORBIDDEN_WITHOUT_LINE"):
        replace(row, line_unit="GOALS")


def test_provider_defined_metric_requires_explicit_metric_key():
    row = canonical_candidate_market_definitions()[1]
    with pytest.raises(ValueError, match="METRIC_KEY_REQUIRED"):
        replace(row, metric_key=None)


def test_registry_rejects_duplicate_executable_identity():
    rows = canonical_candidate_market_definitions()
    with pytest.raises(ValueError, match="DUPLICATE_EXECUTABLE_MARKET_IDENTITY"):
        validate_market_registry((*rows, rows[0]))


def test_every_market_has_explicit_metric_key_and_rejects_cross_sport_family():
    rows = canonical_candidate_market_definitions()
    assert all(row.metric_key for row in rows)
    football = rows[0]
    with pytest.raises(ValueError, match="MARKET_FAMILY_SPORT_MISMATCH"):
        replace(football, sport="tennis", version="MATRIX-MARKET-R2/tennis/BOTH_TEAMS_TO_SCORE/yes-no")


def test_metric_key_is_required_even_for_non_provider_defined_markets():
    row = canonical_candidate_market_definitions()[0]
    with pytest.raises(ValueError, match="METRIC_KEY_REQUIRED"):
        replace(row, metric_key=None)
