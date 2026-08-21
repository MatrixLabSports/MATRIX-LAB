
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (
        ROOT / relative
    ).read_text(
        encoding="utf-8-sig"
    )


def test_p137_p141_ci_boundary_is_wired():
    source = read(
        "scripts/matrix_ci_gate.py"
    )

    assert (
        "def _p137_p141_history_identity_lifecycle_boundary("
        in source
    )
    assert (
        "_p137_p141_history_identity_lifecycle_boundary(ROOT)"
        in source
    )


def test_identity_lifecycle_is_append_only_and_name_join_forbidden():
    canonical = read(
        "app/core/canonical_identity_lifecycle.py"
    )
    provider = read(
        "app/core/provider_identity_lifecycle.py"
    )

    for source in (
        canonical,
        provider,
    ):
        upper = source.upper()
        assert '"UPDATE ' not in upper
        assert '"DELETE ' not in upper
        assert "def resolve_by_name(" not in source
        assert "def get_by_alias(" not in source
        assert "name_join_allowed" in source


def test_identity_lifecycle_is_bitemporal_and_explicit():
    canonical = read(
        "app/core/canonical_identity_lifecycle.py"
    )
    provider = read(
        "app/core/provider_identity_lifecycle.py"
    )

    for token in (
        "effective_at",
        "known_at",
        "resolve_terminal_canonical_id_as_of",
        "ALIAS_ADDED",
        "DISPLAY_NAME_CHANGED",
        "SUPERSEDED",
    ):
        assert token in canonical

    for token in (
        "valid_from",
        "valid_to",
        "known_at",
        "predecessor_binding_id",
        "corrects_binding_id",
        "def resolve_as_of(",
        "def remap(",
    ):
        assert token in provider


def test_sport_identity_lifecycle_adapters_are_separate():
    football = read(
        "app/application/football/identity_lifecycle.py"
    )
    tennis = read(
        "app/application/tennis/identity_lifecycle.py"
    )

    assert 'sport="football"' in football
    assert 'sport="tennis"' not in football
    assert "app.application.tennis" not in football

    assert 'sport="tennis"' in tennis
    assert 'sport="football"' not in tennis
    assert "app.application.football" not in tennis


def test_existing_history_foundations_remain_distinct():
    observation = read(
        "app/core/canonical_observation_store.py"
    )
    point_in_time = read(
        "app/core/point_in_time_history.py"
    )
    football_repository = read(
        "app/sports/football/repository.py"
    )

    assert "append_admitted_record" in observation
    assert "list_as_of" in observation
    assert "build_point_in_time_history" in point_in_time
    assert "as_of" in point_in_time
    assert "upsert" in football_repository
    assert "reconcile" in football_repository


def test_new_identity_modules_have_no_safety_true_binding():
    targets = {
        "name_join_allowed",
        "automatic_model_promotion",
        "automatic_provider_switch",
        "automatic_wagering",
    }

    for relative in (
        "app/core/canonical_identity_lifecycle.py",
        "app/core/provider_identity_lifecycle.py",
        "app/application/football/identity_lifecycle.py",
        "app/application/tennis/identity_lifecycle.py",
    ):
        source = read(
            relative
        )
        tree = ast.parse(
            source,
            filename=relative,
        )

        for node in ast.walk(
            tree
        ):
            if (
                isinstance(
                    node,
                    ast.keyword,
                )
                and node.arg in targets
                and isinstance(
                    node.value,
                    ast.Constant,
                )
                and node.value.value is True
            ):
                raise AssertionError(
                    (
                        relative,
                        node.lineno,
                        node.arg,
                    )
                )

            if isinstance(
                node,
                ast.Dict,
            ):
                for key, value in zip(
                    node.keys,
                    node.values,
                ):
                    if not (
                        isinstance(
                            key,
                            ast.Constant,
                        )
                        and isinstance(
                            key.value,
                            str,
                        )
                        and key.value
                        in targets
                    ):
                        continue

                    if (
                        isinstance(
                            value,
                            ast.Constant,
                        )
                        and value.value is True
                    ):
                        raise AssertionError(
                            (
                                relative,
                                node.lineno,
                                key.value,
                            )
                        )


def test_provider_successor_knowledge_order_is_ci_governed():
    provider = read(
        "app/core/provider_identity_lifecycle.py"
    )
    ci = read(
        "scripts/matrix_ci_gate.py"
    )

    token = (
        "TEMPORAL_PROVIDER_MAPPING_SUCCESSOR_KNOWN_BEFORE_PREDECESSOR"
    )

    assert token in provider
    assert token in ci


def test_linked_predecessor_freeze_is_ci_governed():
    provider = read(
        "app/core/provider_identity_lifecycle.py"
    )
    ci = read(
        "scripts/matrix_ci_gate.py"
    )

    token = (
        "TEMPORAL_PROVIDER_MAPPING_PREDECESSOR_WITH_SUCCESSOR_IS_FROZEN"
    )

    assert token in provider
    assert token in ci


def test_v3_stale_predecessor_and_supersession_graph_guards_are_ci_governed():
    provider = read(
        "app/core/provider_identity_lifecycle.py"
    )
    canonical = read(
        "app/core/canonical_identity_lifecycle.py"
    )
    ci = read(
        "scripts/matrix_ci_gate.py"
    )

    provider_token = (
        "TEMPORAL_PROVIDER_MAPPING_STALE_PREDECESSOR_FORBIDDEN"
    )
    canonical_token = (
        "IDENTITY_SUPERSESSION_GRAPH_ACYCLIC"
    )

    assert provider_token in provider
    assert provider_token in ci
    assert canonical_token in canonical
    assert canonical_token in ci


def test_v4_global_supersession_acyclicity_is_ci_governed():
    canonical = read(
        "app/core/canonical_identity_lifecycle.py"
    )
    ci = read(
        "scripts/matrix_ci_gate.py"
    )

    token = (
        "IDENTITY_SUPERSESSION_LEDGER_GLOBALLY_ACYCLIC"
    )

    assert token in canonical
    assert token in ci


def test_v5_append_only_tail_guard_is_ci_governed():
    helper = read("app/core/append_only_tail_guard.py")
    canonical = read("app/core/canonical_identity_lifecycle.py")
    provider = read("app/core/provider_identity_lifecycle.py")
    ci = read("scripts/matrix_ci_gate.py")
    for token in (
        "SQLiteAppendOnlyTailGuard",
        "APPEND_ONLY_TAIL_GUARD_SEQUENCE_HIGH_WATER",
        "sqlite_sequence",
        "AUTOINCREMENT",
    ):
        assert token in helper
        assert token in ci
    assert "canonical_identity_lifecycle_tail_guard" in canonical
    assert "temporal_provider_identity_tail_guard" in provider


def test_v6_rebaseline_and_provider_canonical_composition_are_ci_governed():
    helper = read("app/core/append_only_tail_guard.py")
    football = read("app/application/football/identity_lifecycle.py")
    tennis = read("app/application/tennis/identity_lifecycle.py")
    ci = read("scripts/matrix_ci_gate.py")

    for token in (
        "APPEND_ONLY_TAIL_GUARD_REBASELINE_FORBIDDEN",
        "initialization_marker_sha256",
    ):
        assert token in helper
        assert token in ci

    football_token = "resolve_football_provider_terminal_canonical_as_of"
    tennis_token = "resolve_tennis_provider_terminal_canonical_as_of"
    assert football_token in football
    assert football_token in ci
    assert tennis_token in tennis
    assert tennis_token in ci
