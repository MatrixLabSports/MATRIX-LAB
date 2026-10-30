from datetime import date

import pytest

from tools.football_subscription_deadline_guard import evaluate, evaluate_independent_sources


def test_api_football_paid_window_active_through_october_28(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY","test-key")
    x=evaluate(date(2026,10,28),require_paid_use=True,require_key=True)
    assert x["paid_window_active"] is True
    assert x["days_remaining_inclusive"] == 1
    assert x["renewal_authorized"] is False


def test_api_football_paid_use_fails_closed_after_october_28(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY","test-key")
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED",raising=False)
    with pytest.raises(SystemExit,match="API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED"):
        evaluate(date(2026,10,29),require_paid_use=True,require_key=True)


def test_odds_api_net_is_not_blocked_by_api_football_expiry(monkeypatch):
    x=evaluate(date(2026,10,29))
    assert x["odds_api_net_covered_by_this_expiry_rule"] is False


def test_independent_sources_remain_governed_after_paid_expiry(monkeypatch):
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", raising=False)
    x = evaluate_independent_sources(date(2026, 10, 29))
    assert x["paid_api_football_usable"] is False
    assert x["independent_source_supervision_allowed"] is True
    assert x["independent_source_network_calls_authorized_by_this_check"] is False
    assert x["api_football_free_tier_current_season_coverage_verified"] is False
    assert x["real_money"] == "BLOCKED"
    assert x["automatic_wagering"] is False


def test_independent_source_readiness_does_not_override_paid_gate(monkeypatch):
    monkeypatch.delenv("MATRIX_API_FOOTBALL_POST_CUTOFF_AUTHORIZED", raising=False)
    evaluate_independent_sources(date(2026, 10, 29))
    with pytest.raises(SystemExit, match="API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED"):
        evaluate(date(2026, 10, 29), require_paid_use=True)


def test_supervisor_independent_source_diagnostic_is_offline(monkeypatch, capsys):
    import json
    from tools import telegram_green_signal_alerts as supervisor

    monkeypatch.setenv("MATRIX_INDEPENDENT_SOURCE_READINESS", "1")
    monkeypatch.delenv("MATRIX_SUPERVISOR_OFFLINE_PREFLIGHT", raising=False)
    monkeypatch.delenv("MATRIX_API_FOOTBALL_AUTHORIZED", raising=False)
    supervisor.main()
    result = json.loads(capsys.readouterr().out.strip())
    assert result["independent_source_supervision_allowed"] is True
    assert result["independent_source_network_calls_authorized_by_this_check"] is False
    assert result["telegram_messages_sent"] == 0
    assert result["api_calls_made"] == 0
    assert result["full_supervisor_certified"] is False
    assert result["real_money"] == "BLOCKED"


def test_telegram_workflow_runs_offline_readiness_before_paid_gate():
    from pathlib import Path

    workflow = Path(".github/workflows/telegram-green-signals.yml").read_text(encoding="utf-8")
    diagnostic = "Certify independent-source diagnostic without provider calls"
    paid_gate = "Enforce API-Football subscription deadline before supervisor"
    assert diagnostic in workflow
    assert paid_gate in workflow
    assert workflow.index(diagnostic) < workflow.index(paid_gate)
    section = workflow.split(diagnostic, 1)[1].split("      - name:", 1)[0]
    assert "MATRIX_INDEPENDENT_SOURCE_READINESS: '1'" in section
    assert "python -m tools.telegram_green_signal_alerts" in section
    assert "tests/test_football_subscription_deadline_guard.py" in section
    assert "--require-paid-use --require-key" in workflow


def test_expired_paid_fixture_http_transports_never_call_network(monkeypatch):
    from tools import telegram_green_signal_alerts as supervisor

    class NoNetwork:
        def get(self, *args, **kwargs):
            raise AssertionError("PAID_API_NETWORK_CALL_AFTER_EXPIRY")

    monkeypatch.setattr(supervisor, "paid_football_quote_transport_allowed", lambda: False)
    session = NoNetwork()
    assert supervisor.fixture_final(session, "expired", "123") is None
    diagnostic = {}
    assert supervisor.odds_api_net_exact_over25_offer(
        session, "configured-odds-key", "123", "2026-10-30T18:00:00Z",
        0.65, "expired", diagnostic=diagnostic,
    ) is None
    assert diagnostic["status"] == "BLOCKED_PAID_API_SUBSCRIPTION_EXPIRED_FIXTURE_LOOKUP"


def test_all_paid_football_http_endpoints_are_guarded():
    """Prevent newly introduced paid HTTP calls from bypassing expiry checks."""
    import ast
    from pathlib import Path

    source = Path("tools/telegram_green_signal_alerts.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    guarded_functions = {
        "odds_api_net_exact_over25_offer",
        "api_football_pinnacle_over25_reference",
        "exact_over25_offer",
        "fixture_final",
    }
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        calls_paid = any(
            isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and "v3.football.api-sports.io/" in value.value
            for value in ast.walk(node)
        )
        if not calls_paid:
            continue
        found.add(node.name)
        assert node.name in guarded_functions, f"Unreviewed paid endpoint in {node.name}"
        assert any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "paid_football_quote_transport_allowed"
            for call in ast.walk(node)
        ), f"Missing subscription guard in {node.name}"
    assert found == guarded_functions
