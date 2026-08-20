from datetime import datetime, timezone
import pytest
from app.core.provider_run_mode_evidence import SQLiteProviderRunModeEvidenceStore

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def test_run_mode_is_immutable_and_verified(tmp_path):
    store = SQLiteProviderRunModeEvidenceStore(tmp_path / "mode.db")
    first = store.record(
        run_id="run-1",
        sport="football",
        provider_key="api_football",
        mode="BOOTSTRAP_PROBE",
        preflight_decision_fingerprint="a" * 64,
        authorized_at=NOW,
    )
    replay = store.record(
        run_id="run-1",
        sport="football",
        provider_key="api_football",
        mode="BOOTSTRAP_PROBE",
        preflight_decision_fingerprint="a" * 64,
        authorized_at=NOW,
    )
    assert replay.evidence_id == first.evidence_id
    assert store.get_verified("run-1").mode == "BOOTSTRAP_PROBE"
    assert store.audit_integrity()
    with pytest.raises(ValueError, match="RUN_MODE_MUTATION_VIOLATION"):
        store.record(
            run_id="run-1",
            sport="football",
            provider_key="api_football",
            mode="PRODUCTION",
            preflight_decision_fingerprint="a" * 64,
            authorized_at=NOW,
        )
