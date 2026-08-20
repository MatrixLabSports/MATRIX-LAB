from types import SimpleNamespace

import app.application.football.runtime_admission_gate as football_gate
import app.application.tennis.runtime_admission_gate as tennis_gate


def test_football_adapter_uses_authoritative_gate_and_binds_sport(
    monkeypatch,
):
    captured = {}
    sentinel = object()

    def fake(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        football_gate,
        "evaluate_authoritative_runtime_admission",
        fake,
    )

    report = SimpleNamespace(
        run_id="run-football"
    )
    audit = object()
    mode_store = object()

    result = (
        football_gate.evaluate_football_runtime_admission(
            report=report,
            audit_ledger=audit,
            run_mode_evidence_store=(
                mode_store
            ),
        )
    )

    assert result is sentinel
    assert captured == {
        "report": report,
        "audit_ledger": audit,
        "run_mode_evidence_store": (
            mode_store
        ),
        "expected_sport": "football",
    }


def test_tennis_adapter_uses_authoritative_gate_and_binds_sport(
    monkeypatch,
):
    captured = {}
    sentinel = object()

    def fake(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        tennis_gate,
        "evaluate_authoritative_runtime_admission",
        fake,
    )

    report = SimpleNamespace(
        run_id="run-tennis"
    )
    audit = object()
    mode_store = object()

    result = (
        tennis_gate.evaluate_tennis_runtime_admission(
            report=report,
            audit_ledger=audit,
            run_mode_evidence_store=(
                mode_store
            ),
        )
    )

    assert result is sentinel
    assert captured == {
        "report": report,
        "audit_ledger": audit,
        "run_mode_evidence_store": (
            mode_store
        ),
        "expected_sport": "tennis",
    }
