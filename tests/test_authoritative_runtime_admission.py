from datetime import datetime, timezone
from types import SimpleNamespace
import pytest

from app.core.authoritative_runtime_admission import evaluate_authoritative_runtime_admission
from app.core.provider_run_mode_evidence import SQLiteProviderRunModeEvidenceStore

NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _store(tmp_path, mode):
    store = SQLiteProviderRunModeEvidenceStore(tmp_path / "mode.db")
    store.record(
        run_id="run-1",
        sport="football",
        provider_key="api_football",
        mode=mode,
        preflight_decision_fingerprint="a" * 64,
        authorized_at=NOW,
    )
    return store


def test_production_delegates_to_base_gate(tmp_path, monkeypatch):
    module = __import__("app.core.authoritative_runtime_admission", fromlist=["x"])
    sentinel = object()
    monkeypatch.setattr(module, "evaluate_reconciled_runtime_admission", lambda **kwargs: sentinel)
    result = evaluate_authoritative_runtime_admission(
        report=SimpleNamespace(run_id="run-1"),
        audit_ledger=object(),
        run_mode_evidence_store=_store(tmp_path, "PRODUCTION"),
        expected_sport="football",
    )
    assert result is sentinel


def test_bootstrap_and_missing_mode_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="BOOTSTRAP_RUNTIME_ADMISSION_FORBIDDEN"):
        evaluate_authoritative_runtime_admission(
            report=SimpleNamespace(run_id="run-1"),
            audit_ledger=object(),
            run_mode_evidence_store=_store(tmp_path, "BOOTSTRAP_PROBE"),
            expected_sport="football",
        )

    empty = SQLiteProviderRunModeEvidenceStore(tmp_path / "empty.db")
    with pytest.raises(ValueError, match="RUN_MODE_EVIDENCE_REQUIRED"):
        evaluate_authoritative_runtime_admission(
            report=SimpleNamespace(run_id="missing"),
            audit_ledger=object(),
            run_mode_evidence_store=empty,
            expected_sport="football",
        )



def test_run_mode_sport_mismatch_fails_closed(
    tmp_path,
):
    store = SQLiteProviderRunModeEvidenceStore(
        tmp_path / "mode-sport.db"
    )

    store.record(
        run_id="run-1",
        sport="tennis",
        provider_key="test_tennis_provider",
        mode="PRODUCTION",
        preflight_decision_fingerprint="b" * 64,
        authorized_at=NOW,
    )

    with pytest.raises(
        ValueError,
        match="RUN_MODE_SPORT_MISMATCH",
    ):
        evaluate_authoritative_runtime_admission(
            report=SimpleNamespace(
                run_id="run-1"
            ),
            audit_ledger=object(),
            run_mode_evidence_store=store,
            expected_sport="football",
        )
