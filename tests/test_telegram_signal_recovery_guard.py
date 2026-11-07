from datetime import datetime, timezone

from tools.telegram_signal_recovery_guard import (
    COMBINED_MINUTES,
    MAX_COMBINED_NOMINAL_GAP_MINUTES,
    build,
    next_combined_cycle,
    schedule_gaps,
)


def test_dual_cadence_has_no_nominal_gap_over_eight_minutes():
    assert COMBINED_MINUTES == (0, 7, 15, 22, 30, 37, 45, 52)
    assert max(schedule_gaps(COMBINED_MINUTES)) == 8
    assert MAX_COMBINED_NOMINAL_GAP_MINUTES == 8


def test_next_combined_cycle_covers_exact_window_open():
    at = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
    assert next_combined_cycle(at) == at


def test_guard_does_not_authorize_signal_or_lower_gates(monkeypatch, tmp_path):
    from tools import telegram_signal_recovery_guard as guard

    sup = tmp_path / "sup.yml"
    green = tmp_path / "green.yml"
    sup.write_text('cron: "*/15 * * * *"\npython -m tools.telegram_green_signal_alerts\n', encoding="utf-8")
    green.write_text('cron: "7,22,37,52 * * * *"\npython -m tools.telegram_green_signal_alerts\n', encoding="utf-8")
    monkeypatch.setattr(guard, "SUPERVISOR_WORKFLOW", sup)
    monkeypatch.setattr(guard, "GREEN_WORKFLOW", green)

    blocker = {"records": [{
        "fixture_id": "1",
        "match": "A vs B",
        "kickoff": "2026-10-28T10:00:00+00:00",
        "gate_state": "WAITING_FINAL_REVALIDATION_WINDOW",
    }]}
    readiness = {"status": "PASS"}
    quote = {
        "sample": {"real_quote_attempts_total": 4, "remaining_to_minimum": 46},
        "recommendation_gate": {"recommendation_authorized": False},
    }
    out = build(blocker, readiness, quote, datetime(2026, 10, 28, 7, 0, tzinfo=timezone.utc))
    assert out["status"] == "PASS"
    assert out["current_state"]["waiting_final_window_candidates"] == 1
    assert out["current_state"]["dual_cadence_covered_candidates"] == 1
    assert out["governance"]["lower_gates_to_force_signals"] is False
    assert out["governance"]["automatic_wagering"] is False
    assert out["governance"]["real_money"] == "BLOCKED"
    assert out["current_state"]["quote_recommendation_authorized"] is False
