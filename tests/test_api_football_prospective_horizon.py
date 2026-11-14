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


def test_horizon_retries_same_day_cycle_blocked_only_by_daily_reserve(tmp_path, monkeypatch):
    target = "2026-10-01"
    cycle_root = tmp_path / "evidence/api_football/prospective_daily" / target / "prior"
    (cycle_root / "history").mkdir(parents=True, exist_ok=True)
    (cycle_root / "team_last_fallback").mkdir(parents=True, exist_ok=True)
    (cycle_root / "cycle_summary.json").write_text(
        """{
  "status": "PASS",
  "target_date_bogota": "2026-10-01",
  "started_at_utc": "2026-10-01T11:00:00+00:00",
  "canonical": {"ready_input_count": 0},
  "freeze": {"new_event_count": 0}
}
""",
        encoding="utf-8",
    )
    (cycle_root / "history/history_capture_manifest.json").write_text(
        """{"stopped_reason":"DAILY_RESERVE_REACHED"}
""",
        encoding="utf-8",
    )

    calls = []

    def fake_cycle(*, root, api_key, target_date):
        calls.append(target_date)
        fresh = Path("evidence/api_football/prospective_daily") / target_date / "fresh"
        (tmp_path / fresh).mkdir(parents=True, exist_ok=True)
        return {
            "cycle_root": fresh.as_posix(),
            "fixture_capture": {"fixtures_received": 12, "eligible_future_fixtures": 10},
            "canonical": {"ready_input_count": 8},
            "freeze": {"new_event_count": 8},
            "network_calls_performed": 5,
        }

    monkeypatch.setattr(horizon, "run_daily_cycle", fake_cycle)
    d = horizon.run_horizon(
        root=tmp_path,
        api_key="k",
        target_date=target,
        now_utc=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert calls == [target]
    assert d["targets"][0]["status"] == "PASS"
    assert d["targets"][0]["ready_input_count"] == 8
    assert d["new_freezes_total"] == 8


def test_horizon_does_not_retry_valid_completed_cycle(tmp_path, monkeypatch):
    target = "2026-10-01"
    cycle_root = tmp_path / "evidence/api_football/prospective_daily" / target / "prior"
    cycle_root.mkdir(parents=True, exist_ok=True)
    (cycle_root / "cycle_summary.json").write_text(
        """{
  "status": "PASS",
  "target_date_bogota": "2026-10-01",
  "started_at_utc": "2026-10-01T11:00:00+00:00",
  "canonical": {"ready_input_count": 5},
  "freeze": {"new_event_count": 5}
}
""",
        encoding="utf-8",
    )

    def should_not_run(**kwargs):
        raise AssertionError("valid completed cycle must remain idempotent")

    monkeypatch.setattr(horizon, "run_daily_cycle", should_not_run)
    d = horizon.run_horizon(
        root=tmp_path,
        api_key="k",
        target_date=target,
        now_utc=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert d["targets"][0]["status"] == "ALREADY_COMPLETED_TODAY"
    assert d["new_freezes_total"] == 0


def test_horizon_extends_to_paid_cutoff_without_crossing_it(tmp_path, monkeypatch):
    calls = []

    def fake_cycle(*, root, api_key, target_date):
        calls.append(target_date)
        cycle_root = Path("evidence/api_football/prospective_daily") / target_date / "cycle"
        (tmp_path / cycle_root).mkdir(parents=True, exist_ok=True)
        return {
            "cycle_root": cycle_root.as_posix(),
            "fixture_capture": {"fixtures_received": 10, "eligible_future_fixtures": 8},
            "canonical": {"ready_input_count": 6},
            "freeze": {"new_event_count": 6},
            "network_calls_performed": 3,
        }

    monkeypatch.setattr(horizon, "run_daily_cycle", fake_cycle)
    d = horizon.run_horizon(
        root=tmp_path,
        api_key="k",
        days=5,
        now_utc=datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc),
    )
    assert calls == ["2026-10-25", "2026-10-26", "2026-10-27", "2026-10-28"]
    assert d["days_requested"] == 4
    assert d["paid_through_bogota_date"] == "2026-10-28"
    assert d["paid_window_target_cap_enforced"] is True


def test_horizon_on_oct24_covers_full_remaining_paid_window(tmp_path, monkeypatch):
    calls = []

    def fake_cycle(*, root, api_key, target_date):
        calls.append(target_date)
        cycle_root = Path("evidence/api_football/prospective_daily") / target_date / "cycle"
        (tmp_path / cycle_root).mkdir(parents=True, exist_ok=True)
        return {
            "cycle_root": cycle_root.as_posix(),
            "fixture_capture": {"fixtures_received": 10, "eligible_future_fixtures": 8},
            "canonical": {"ready_input_count": 6},
            "freeze": {"new_event_count": 6},
            "network_calls_performed": 3,
        }

    monkeypatch.setattr(horizon, "run_daily_cycle", fake_cycle)
    d = horizon.run_horizon(
        root=tmp_path,
        api_key="k",
        days=5,
        now_utc=datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc),
    )
    assert calls == [
        "2026-10-24",
        "2026-10-25",
        "2026-10-26",
        "2026-10-27",
        "2026-10-28",
    ]
    assert d["days_requested"] == 5


def test_after_paid_cutoff_automatic_horizon_is_safe_empty_not_failure(tmp_path, monkeypatch):
    def must_not_call_paid_provider(**kwargs):
        raise AssertionError("NO_PAID_CALLS_AFTER_CUTOFF")
    monkeypatch.setattr(horizon, "run_daily_cycle", must_not_call_paid_provider)
    result = horizon.run_horizon(
        root=tmp_path, api_key="stale-but-present", days=5,
        now_utc=datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc),
    )
    assert result["local_date_bogota"] == "2026-11-02"
    assert result["days_requested"] == 0
    assert result["targets"] == []
    assert result["network_calls_total"] == 0
    assert result["new_freezes_total"] == 0
    assert result["p_matrix_status"] == "NOT_GENERATED"
    assert result["real_money"] == "BLOCKED"


def test_manual_post_cutoff_target_cannot_override_expired_paid_entitlement(tmp_path, monkeypatch):
    import pytest
    def must_not_call_paid_provider(**kwargs):
        raise AssertionError("MANUAL_TARGET_MUST_NOT_CALL_PAID_PROVIDER")
    monkeypatch.setattr(horizon, "run_daily_cycle", must_not_call_paid_provider)
    with pytest.raises(ValueError, match="PAID_WINDOW_CLOSED_NO_CALLS"):
        horizon.run_horizon(
            root=tmp_path, api_key="old-key", target_date="2026-11-03",
            now_utc=datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc),
        )
    with pytest.raises(ValueError, match="PAID_WINDOW_CLOSED_NO_CALLS"):
        horizon.run_horizon(
            root=tmp_path, api_key="old-key", target_date="2026-10-28",
            now_utc=datetime(2026, 11, 3, 2, 0, tzinfo=timezone.utc),
        )


def test_manual_past_target_before_cutoff_is_rejected_as_backfill(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(horizon, "run_daily_cycle",
                        lambda **kwargs: (_ for _ in ()).throw(
                            AssertionError("BACKFILL_MUST_NOT_CALL_PAID_PROVIDER")))
    with pytest.raises(ValueError, match="HISTORICAL_PREMATCH_BACKFILL_FORBIDDEN"):
        horizon.run_horizon(
            root=tmp_path, api_key="key", target_date="2026-10-25",
            now_utc=datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc),
        )
