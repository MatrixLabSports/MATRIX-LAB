from datetime import datetime, timezone
from pathlib import Path

import tools.api_football_prospective_horizon as horizon


def test_horizon_runs_three_dates_and_preserves_governance(tmp_path, monkeypatch):
    calls = []

    def fake_cycle(*, root, api_key, target_date):
        calls.append(target_date)
        cycle_root = Path("evidence/api_football/prospective_daily") / target_date / "cycle"
        (tmp_path / cycle_root).mkdir(parents=True, exist_ok=True)
        return {
            "cycle_root": cycle_root.as_posix(),
            "fixture_capture": {"fixtures_received": 100, "eligible_future_fixtures": 80},
            "canonical": {"ready_input_count": 70},
            "freeze": {"new_event_count": 60},
            "network_calls_performed": 10,
        }

    monkeypatch.setattr(horizon, "run_daily_cycle", fake_cycle)
    d = horizon.run_horizon(
        root=tmp_path,
        api_key="k",
        days=3,
        now_utc=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert calls == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert d["new_freezes_total"] == 180
    assert d["network_calls_total"] == 30
    assert d["p_matrix_status"] == "NOT_GENERATED"
    assert d["automatic_wagering"] is False
    assert d["real_money"] == "BLOCKED"


def test_horizon_treats_no_future_as_healthy_skip(tmp_path, monkeypatch):
    def fake_cycle(*, root, api_key, target_date):
        raise ValueError("NO_ELIGIBLE_FUTURE_FIXTURES")

    monkeypatch.setattr(horizon, "run_daily_cycle", fake_cycle)
    d = horizon.run_horizon(
        root=tmp_path,
        api_key="k",
        days=1,
        now_utc=datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc),
    )
    assert d["targets"][0]["status"] == "HEALTHY_SKIP_NO_ELIGIBLE_FUTURE_FIXTURES"
    assert d["new_freezes_total"] == 0
    assert d["real_money"] == "BLOCKED"
