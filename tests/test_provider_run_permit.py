import pytest

from app.core.provider_run_permit import (
    SQLiteProviderRunPermitStore,
)


def permit(store, run_id="run-1"):
    return store.build_permit(
        run_id=run_id,
        sport="football",
        provider_key="provider-x",
        mode="BOOTSTRAP_PROBE",
        queue_fingerprint="a" * 64,
        scheduling_evidence_fingerprint="b" * 64,
        rights_manifest_fingerprint="c" * 64,
        bootstrap_policy_fingerprint="d" * 64,
        max_items=3,
        max_requests=5,
    )


def test_run_bound_permit_is_one_use(tmp_path):
    store = SQLiteProviderRunPermitStore(
        tmp_path / "permit.db"
    )
    value = permit(store)
    store.issue(value)

    consumed = store.consume(
        permit_id=value.permit_id,
        run_id="run-1",
        sport="football",
        provider_key="provider-x",
        mode="BOOTSTRAP_PROBE",
        queue_fingerprint="a" * 64,
    )

    assert consumed["run_id"] == "run-1"

    with pytest.raises(
        ValueError,
        match="PROVIDER_RUN_PERMIT_ALREADY_CONSUMED",
    ):
        store.consume(
            permit_id=value.permit_id,
            run_id="run-1",
            sport="football",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            queue_fingerprint="a" * 64,
        )


def test_run_bound_permit_rejects_queue_replay(tmp_path):
    store = SQLiteProviderRunPermitStore(
        tmp_path / "permit.db"
    )
    value = permit(store)
    store.issue(value)

    with pytest.raises(
        ValueError,
        match="PROVIDER_RUN_PERMIT_BINDING_MISMATCH:queue_fingerprint",
    ):
        store.consume(
            permit_id=value.permit_id,
            run_id="run-1",
            sport="football",
            provider_key="provider-x",
            mode="BOOTSTRAP_PROBE",
            queue_fingerprint="e" * 64,
        )
