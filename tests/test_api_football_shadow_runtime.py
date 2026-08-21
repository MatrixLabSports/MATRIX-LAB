from datetime import datetime, timezone

import pytest

from app.core.provider_request_contract import (
    SQLiteProviderRequestContractRegistry,
)
from app.core.secret_reference import (
    build_secret_reference,
)
from app.providers.api_football.shadow_runtime import (
    ApiFootballShadowRuntime,
)


NOW = datetime(
    2026,
    8,
    20,
    tzinfo=timezone.utc,
)


def runtime(tmp_path, *, mode="SHADOW"):
    return ApiFootballShadowRuntime(
        mode=mode,
        registry=SQLiteProviderRequestContractRegistry(
            tmp_path / "contracts.db"
        ),
        secret_reference=build_secret_reference(
            provider_key="api_football",
            environment_variable="MATRIX_TEST_API_KEY",
            secret_type="API_KEY",
        ),
        clock=lambda: NOW,
        valid_from=NOW,
        rights_decision=None,
    )


def test_shadow_runtime_builds_full_contract_plan_without_network(
    tmp_path,
):
    shadow = runtime(tmp_path)

    assert (
        shadow.readiness.external_network_allowed
        is False
    )
    assert (
        shadow.readiness.real_provider_execution_authorized
        is False
    )
    assert (
        "PROVIDER_RIGHTS_NOT_AUTHORIZED"
        in shadow.readiness.blockers
    )
    assert (
        "REAL_PROVIDER_EXECUTION_DISABLED"
        in shadow.readiness.blockers
    )

    preview = shadow.preview(
        contract_name="fixtures_by_date",
        params={
            "date": "2026-08-20",
            "league": 39,
            "season": 2026,
        },
    )

    assert preview.path == "/fixtures"
    assert preview.network_call_performed is False
    assert preview.secret_resolved is False
    assert (
        preview.real_provider_execution_authorized
        is False
    )


def test_shadow_preview_changes_with_request_values(
    tmp_path,
):
    shadow = runtime(tmp_path)

    one = shadow.preview(
        contract_name="fixture_by_id",
        params={"id": 100},
    )
    two = shadow.preview(
        contract_name="fixture_by_id",
        params={"id": 101},
    )

    assert (
        one.authorization_fingerprint
        != two.authorization_fingerprint
    )


def test_shadow_runtime_refuses_live_or_production_mode(
    tmp_path,
):
    with pytest.raises(
        ValueError,
        match="INVALID_SHADOW_RUNTIME_MODE",
    ):
        runtime(
            tmp_path,
            mode="PRODUCTION",
        )
