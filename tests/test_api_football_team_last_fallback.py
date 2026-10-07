from datetime import datetime, timezone
from unittest.mock import Mock

from tools.api_football_team_last_fallback import run_capture


def _hist(fid, when, home_id, away_id):
    return {
        "fixture_id": str(fid),
        "kickoff_utc": when,
        "home_team_id": str(home_id),
        "away_team_id": str(away_id),
        "home_team": f"H{home_id}",
        "away_team": f"A{away_id}",
        "home_goals": 1,
        "away_goals": 0,
        "competition": "League",
        "provider_status": "FT",
        "source_payload_sha256": "a" * 64,
        "source_reference": "test",
    }


def _benchmark():
    return {
        "provider": "api_football",
        "fixtures": {
            "api_football:fixture:900": {
                "fixture_id": "900",
                "kickoff_utc": "2026-09-28T18:00:00+00:00",
                "league": {"id": "39", "name": "League", "season": 2026},
                "home": {"id": "40", "name": "Home FC"},
                "away": {"id": "41", "name": "Away FC"},
            }
        },
        "histories": {
            "api_football:fixture:900": {
                "home": {
                    "team_id": "40",
                    "team_name": "Home FC",
                    "observed_at_utc": "2026-09-28T04:00:00+00:00",
                    "completed_before_target": [
                        _hist(1, "2026-09-10T12:00:00+00:00", 40, 1001),
                        _hist(2, "2026-09-11T12:00:00+00:00", 1002, 40),
                        _hist(3, "2026-09-12T12:00:00+00:00", 40, 1003),
                        _hist(4, "2026-09-13T12:00:00+00:00", 1004, 40),
                        _hist(5, "2026-09-14T12:00:00+00:00", 40, 1005),
                    ],
                },
                "away": {
                    "team_id": "41",
                    "team_name": "Away FC",
                    "observed_at_utc": "2026-09-28T04:00:00+00:00",
                    "completed_before_target": [
                        _hist(11, "2026-09-10T15:00:00+00:00", 41, 2001),
                        _hist(12, "2026-09-11T15:00:00+00:00", 2002, 41),
                    ],
                },
            }
        },
        "unresolved_targets": ["api_football:fixture:900"],
        "money_decisions_enabled": False,
        "analysis_mode": "PREMATCH_RESEARCH_ONLY",
        "real_money": "BLOCKED",
    }


def _readiness():
    return {
        "rows": [
            {
                "target_key": "api_football:fixture:900",
                "ready_minimum_history": False,
                "blockers": ["AWAY_HISTORY_BELOW_MINIMUM"],
            }
        ]
    }


def _fixture(fid, when, home_id, away_id):
    return {
        "fixture": {"id": fid, "date": when, "status": {"short": "FT"}},
        "league": {"id": 39, "name": "League"},
        "teams": {
            "home": {"id": home_id, "name": f"H{home_id}"},
            "away": {"id": away_id, "name": f"A{away_id}"},
        },
        "goals": {"home": 1, "away": 0},
    }


def _response(rows, remaining="7400", status_code=200, minute_remaining="299", retry_after=None):
    response = Mock()
    response.status_code = status_code
    payload = {"errors": [], "response": rows}
    response.content = __import__("json").dumps(payload).encode()
    response.json.return_value = payload
    response.headers = {
        "x-ratelimit-requests-limit": "7500",
        "x-ratelimit-requests-remaining": remaining,
        "x-ratelimit-limit": "300",
        "x-ratelimit-remaining": minute_remaining,
    }
    if retry_after is not None:
        response.headers["Retry-After"] = str(retry_after)
    return response


def test_team_last_fallback_completes_deficient_side_and_preserves_pit(tmp_path):
    rows = [
        _fixture(20 + i, f"2026-09-{15+i:02d}T15:00:00+00:00", 3000 + i, 41)
        for i in range(6)
    ]
    rows.append(_fixture(999, "2026-09-28T20:00:00+00:00", 40, 41))

    session = Mock()
    session.get.return_value = _response(rows)
    ticks = iter([
        datetime(2026, 9, 28, 6, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 1, tzinfo=timezone.utc),
    ])

    result = run_capture(
        api_key="test-key",
        benchmark=_benchmark(),
        readiness=_readiness(),
        out_dir=tmp_path,
        session=session,
        now_fn=lambda: next(ticks),
    )

    assert result["deficient_unique_team_count"] == 1
    assert result["network_calls_performed"] == 1
    assert result["provider_error_team_count"] == 0
    assert result["ready_minimum_history_count"] == 1
    assert result["blocked_minimum_history_count"] == 0
    assert result["last_rate_limit"]["daily_remaining"] == "7400"
    assert result["real_money"] == "BLOCKED"

    enriched = __import__("json").loads((tmp_path / "benchmark_after_team_last.json").read_text())
    target = enriched["histories"]["api_football:fixture:900"]
    assert target["home"]["history_count"] == 5
    assert target["away"]["history_count"] >= 5
    assert all(
        row["fixture_id"] != "999"
        for row in target["away"]["completed_before_target"]
    )
    assert enriched["benchmark_status"] == "READY_MINIMUM_HISTORY"


def test_team_last_fallback_blocks_if_capture_occurs_after_kickoff(tmp_path):
    session = Mock()
    session.get.return_value = _response([
        _fixture(20 + i, f"2026-09-{15+i:02d}T15:00:00+00:00", 3000 + i, 41)
        for i in range(6)
    ])
    ticks = iter([
        datetime(2026, 9, 28, 18, 1, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 18, 1, 1, tzinfo=timezone.utc),
    ])

    result = run_capture(
        api_key="test-key",
        benchmark=_benchmark(),
        readiness=_readiness(),
        out_dir=tmp_path,
        session=session,
        now_fn=lambda: next(ticks),
    )

    assert result["ready_minimum_history_count"] == 0
    ready = __import__("json").loads((tmp_path / "history_readiness_after_team_last.json").read_text())
    blockers = ready["rows"][0]["blockers"]
    assert "AWAY_TEAM_LAST_NOT_PREMATCH" in blockers


def test_team_last_fallback_respects_daily_reserve(tmp_path):
    benchmark = _benchmark()
    benchmark["fixtures"]["api_football:fixture:901"] = {
        "fixture_id": "901",
        "kickoff_utc": "2026-09-28T19:00:00+00:00",
        "league": {"id": "39", "name": "League", "season": 2026},
        "home": {"id": "50", "name": "H50"},
        "away": {"id": "51", "name": "A51"},
    }
    benchmark["histories"]["api_football:fixture:901"] = {
        "home": {"completed_before_target": []},
        "away": {"completed_before_target": []},
    }
    readiness = _readiness()
    readiness["rows"].append({
        "target_key": "api_football:fixture:901",
        "ready_minimum_history": False,
        "blockers": ["HOME_HISTORY_BELOW_MINIMUM", "AWAY_HISTORY_BELOW_MINIMUM"],
    })

    session = Mock()
    session.get.return_value = _response([], remaining="7000")
    ticks = iter([
        datetime(2026, 9, 28, 6, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 1, tzinfo=timezone.utc),
    ])

    result = run_capture(
        api_key="test-key",
        benchmark=benchmark,
        readiness=readiness,
        out_dir=tmp_path,
        session=session,
        max_requests=120,
        min_daily_remaining_reserve=7000,
        now_fn=lambda: next(ticks),
    )

    assert result["network_calls_performed"] == 1
    assert result["stopped_reason"] == "DAILY_RESERVE_REACHED"


def test_team_last_fallback_no_deficient_teams_is_idempotent_passthrough(tmp_path):
    benchmark=_benchmark()
    readiness={
        "rows":[{
            "target_key":"api_football:fixture:900",
            "ready_minimum_history":True,
            "blockers":[],
        }]
    }
    session=Mock()
    result=run_capture(
        api_key="test-key",
        benchmark=benchmark,
        readiness=readiness,
        out_dir=tmp_path,
        session=session,
    )
    assert result["status"]=="PASS"
    assert result["deficient_unique_team_count"]==0
    assert result["network_calls_performed"]==0
    assert result["stopped_reason"]=="NO_DEFICIENT_TEAMS"
    session.get.assert_not_called()
    enriched=__import__("json").loads((tmp_path/"benchmark_after_team_last.json").read_text())
    assert enriched["benchmark_status"]=="READY_MINIMUM_HISTORY"
    assert enriched["real_money"]=="BLOCKED"


def test_team_last_fallback_retries_429_then_succeeds(tmp_path):
    rows = [
        _fixture(20 + i, f"2026-09-{15+i:02d}T15:00:00+00:00", 3000 + i, 41)
        for i in range(6)
    ]
    session = Mock()
    session.get.side_effect = [
        _response([], status_code=429, minute_remaining="0", retry_after="1"),
        _response(rows, minute_remaining="299"),
    ]
    ticks = iter([
        datetime(2026, 9, 28, 6, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 2, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 3, tzinfo=timezone.utc),
    ])
    sleeps = []

    result = run_capture(
        api_key="test-key",
        benchmark=_benchmark(),
        readiness=_readiness(),
        out_dir=tmp_path,
        session=session,
        now_fn=lambda: next(ticks),
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )

    assert result["status"] == "PASS"
    assert result["network_calls_performed"] == 2
    assert result["rate_limit_event_count"] == 1
    assert result["provider_error_team_count"] == 0
    assert result["ready_minimum_history_count"] == 1
    assert result["stopped_reason"] is None
    assert sleeps == [1.0]


def test_team_last_fallback_persistent_429_blocks_missing_without_crashing(tmp_path):
    session = Mock()
    session.get.side_effect = [
        _response([], status_code=429, minute_remaining="0", retry_after="0"),
        _response([], status_code=429, minute_remaining="0", retry_after="0"),
    ]
    ticks = iter([
        datetime(2026, 9, 28, 6, 5, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 2, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 6, 5, 3, tzinfo=timezone.utc),
    ])

    result = run_capture(
        api_key="test-key",
        benchmark=_benchmark(),
        readiness=_readiness(),
        out_dir=tmp_path,
        session=session,
        now_fn=lambda: next(ticks),
        sleep_fn=lambda seconds: None,
    )

    assert result["status"] == "PASS"
    assert result["network_calls_performed"] == 2
    assert result["rate_limit_event_count"] == 2
    assert result["provider_error_team_count"] == 1
    assert result["stopped_reason"] == "RATE_LIMIT_RETRY_EXHAUSTED"
    assert result["ready_minimum_history_count"] == 0
    assert result["blocked_minimum_history_count"] == 1
    assert result["captures"][0]["status"] == "RATE_LIMIT_BLOCKED"

    readiness = __import__("json").loads(
        (tmp_path / "history_readiness_after_team_last.json").read_text()
    )
    assert "AWAY_HISTORY_BELOW_MINIMUM" in readiness["rows"][0]["blockers"]
