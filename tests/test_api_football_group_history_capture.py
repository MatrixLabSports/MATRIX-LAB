from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from tools.api_football_group_history_capture import _group_targets, capture_group_history


def _benchmark():
    return {
        "benchmark_id": "b1",
        "provider": "api_football",
        "fixtures": {
            "api_football:fixture:900": {
                "fixture_id": "900",
                "observed_at_utc": "2026-09-28T04:43:53+00:00",
                "kickoff_utc": "2026-09-28T18:00:00+00:00",
                "pre_match_frozen": True,
                "league": {"id": "39", "name": "Premier League", "season": 2026, "round": "R7"},
                "home": {"id": "40", "name": "Home FC"},
                "away": {"id": "41", "name": "Away FC"},
                "venue": {"id": "1", "name": "S"},
                "source_payload_sha256": "a" * 64,
            }
        },
        "histories": {},
        "unresolved_targets": ["api_football:fixture:900"],
        "money_decisions_enabled": False,
        "real_money": "BLOCKED",
    }


def _fixture(fid, when, home_id, home_name, away_id, away_name, hg, ag, status="FT"):
    return {
        "fixture": {
            "id": fid,
            "date": when,
            "status": {"short": status},
        },
        "league": {"id": 39, "name": "Premier League", "season": 2026},
        "teams": {
            "home": {"id": home_id, "name": home_name},
            "away": {"id": away_id, "name": away_name},
        },
        "goals": {"home": hg, "away": ag},
    }


def _response(rows, remaining="80"):
    response = Mock()
    response.status_code = 200
    payload = {
        "get": "fixtures",
        "parameters": {"league": "39", "season": "2026"},
        "errors": [],
        "results": len(rows),
        "paging": {"current": 1, "total": 1},
        "response": rows,
    }
    raw = __import__("json").dumps(payload, separators=(",", ":")).encode()
    response.content = raw
    response.json.return_value = payload
    response.headers = {
        "content-type": "application/json",
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": remaining,
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "9",
    }
    return response


def test_group_targets_prioritize_requested_browser_first_leagues():
    benchmark = _benchmark()
    base = benchmark["fixtures"]["api_football:fixture:900"]
    for offset in range(3):
        benchmark["fixtures"][f"api_football:fixture:99{offset}"] = {
            **base,
            "fixture_id": f"99{offset}",
            "kickoff_utc": f"2026-09-28T1{5+offset}:00:00+00:00",
            "league": {"id": "999", "name": "Large Non Priority League", "season": 2026, "round": "R1"},
            "home": {"id": str(70 + offset), "name": f"NP Home {offset}"},
            "away": {"id": str(80 + offset), "name": f"NP Away {offset}"},
        }
    benchmark["fixtures"]["api_football:fixture:980"] = {
        **base,
        "fixture_id": "980",
        "kickoff_utc": "2026-09-28T17:30:00+00:00",
        "league": {"id": "239", "name": "Primera A", "season": 2026, "round": "R1"},
        "home": {"id": "90", "name": "COL Home"},
        "away": {"id": "91", "name": "COL Away"},
    }

    groups = _group_targets(benchmark)

    assert [row["league_id"] for row in groups[:2]] == ["39", "239"]
    assert groups[2]["league_id"] == "999"


def test_group_capture_builds_ready_history_without_future_leakage(tmp_path):
    rows = []
    for i in range(6):
        day = 10 + i
        rows.append(_fixture(
            100 + i,
            f"2026-09-{day:02d}T12:00:00+00:00",
            40,
            "Home FC",
            1000 + i,
            f"H Opp {i}",
            2,
            1,
        ))
        rows.append(_fixture(
            200 + i,
            f"2026-09-{day:02d}T15:00:00+00:00",
            2000 + i,
            f"A Opp {i}",
            41,
            "Away FC",
            0,
            1,
        ))
    rows.append(_fixture(
        999,
        "2026-09-28T20:00:00+00:00",
        40,
        "Home FC",
        41,
        "Away FC",
        1,
        1,
    ))

    session = Mock()
    session.get.return_value = _response(rows)
    ticks = iter([
        datetime(2026, 9, 28, 4, 50, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 1, tzinfo=timezone.utc),
    ])

    result = capture_group_history(
        api_key="test-key",
        benchmark=_benchmark(),
        out_dir=tmp_path,
        session=session,
        max_requests=1,
        min_daily_remaining_reserve=40,
        now_fn=lambda: next(ticks),
    )

    assert result["network_calls_performed"] == 1
    assert result["ready_minimum_history_count"] == 1
    assert result["blocked_minimum_history_count"] == 0
    assert result["real_money"] == "BLOCKED"

    enriched = __import__("json").loads((tmp_path / "benchmark_with_history.json").read_text())
    assert enriched["benchmark_status"] == "READY_MINIMUM_HISTORY"
    assert enriched["unresolved_targets"] == []
    histories = enriched["histories"]["api_football:fixture:900"]
    assert len(histories["home"]["completed_before_target"]) == 6
    assert len(histories["away"]["completed_before_target"]) == 6
    assert all(row["fixture_id"] != "999" for row in histories["home"]["completed_before_target"])
    assert histories["home"]["observed_at_utc"] == "2026-09-28T04:50:01+00:00"
    assert (tmp_path / "raw" / "league_39_season_2026.bin").exists()


def test_group_capture_blocks_when_history_is_below_minimum(tmp_path):
    rows = [
        _fixture(
            100 + i,
            f"2026-09-{10+i:02d}T12:00:00+00:00",
            40,
            "Home FC",
            1000 + i,
            f"Opp {i}",
            2,
            1,
        )
        for i in range(4)
    ]
    session = Mock()
    session.get.return_value = _response(rows)
    ticks = iter([
        datetime(2026, 9, 28, 4, 50, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 1, tzinfo=timezone.utc),
    ])

    result = capture_group_history(
        api_key="test-key",
        benchmark=_benchmark(),
        out_dir=tmp_path,
        session=session,
        max_requests=1,
        now_fn=lambda: next(ticks),
    )

    assert result["ready_minimum_history_count"] == 0
    assert result["blocked_minimum_history_count"] == 1
    blockers = result["readiness"][0]["blockers"]
    assert "HOME_HISTORY_BELOW_MINIMUM" in blockers
    assert "AWAY_HISTORY_BELOW_MINIMUM" in blockers


def test_group_capture_stops_before_spending_reserved_daily_budget(tmp_path):
    benchmark = _benchmark()
    benchmark["fixtures"]["api_football:fixture:901"] = {
        **benchmark["fixtures"]["api_football:fixture:900"],
        "fixture_id": "901",
        "kickoff_utc": "2026-09-28T19:00:00+00:00",
        "league": {"id": "40", "name": "Second League", "season": 2026, "round": "R1"},
    }
    session = Mock()
    session.get.return_value = _response([], remaining="40")
    ticks = iter([
        datetime(2026, 9, 28, 4, 50, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 1, tzinfo=timezone.utc),
    ])

    result = capture_group_history(
        api_key="test-key",
        benchmark=benchmark,
        out_dir=tmp_path,
        session=session,
        max_requests=2,
        min_daily_remaining_reserve=40,
        now_fn=lambda: next(ticks),
    )

    assert result["network_calls_performed"] == 1
    assert result["captured_group_count"] == 1
    assert result["stopped_reason"] == "DAILY_RESERVE_REACHED"


def test_group_capture_rejects_missing_key_before_network(tmp_path):
    session = Mock()
    with pytest.raises(ValueError, match="API_FOOTBALL_KEY_NOT_CONFIGURED"):
        capture_group_history(
            api_key="",
            benchmark=_benchmark(),
            out_dir=tmp_path,
            session=session,
        )
    session.get.assert_not_called()


def test_group_capture_rejects_request_budget_above_policy(tmp_path):
    with pytest.raises(ValueError, match="MAX_REQUESTS_OUT_OF_POLICY"):
        capture_group_history(
            api_key="test",
            benchmark=_benchmark(),
            out_dir=tmp_path,
            max_requests=41,
        )



def test_group_capture_quarantines_provider_error_and_continues(tmp_path):
    benchmark = _benchmark()
    benchmark["fixtures"]["api_football:fixture:901"] = {
        **benchmark["fixtures"]["api_football:fixture:900"],
        "fixture_id": "901",
        "kickoff_utc": "2026-09-28T19:00:00+00:00",
        "league": {"id": "40", "name": "Second League", "season": 2026, "round": "R1"},
        "home": {"id": "50", "name": "Second Home"},
        "away": {"id": "51", "name": "Second Away"},
    }

    error_response = Mock()
    error_payload = {
        "get": "fixtures",
        "parameters": {"league": "39", "season": "2026"},
        "errors": {"plan": "season unavailable"},
        "results": 0,
        "paging": {"current": 1, "total": 1},
        "response": [],
    }
    error_response.status_code = 200
    error_response.content = __import__("json").dumps(error_payload).encode()
    error_response.json.return_value = error_payload
    error_response.headers = {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "79",
        "X-RateLimit-Limit": "10",
        "X-RateLimit-Remaining": "9",
    }

    ok_response = _response([], remaining="78")
    session = Mock()
    session.get.side_effect = [error_response, ok_response]
    ticks = iter([
        datetime(2026, 9, 28, 4, 50, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 2, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 3, tzinfo=timezone.utc),
    ])

    result = capture_group_history(
        api_key="test-key",
        benchmark=benchmark,
        out_dir=tmp_path,
        session=session,
        max_requests=2,
        min_daily_remaining_reserve=40,
        now_fn=lambda: next(ticks),
    )

    assert result["status"] == "PASS"
    assert result["network_calls_performed"] == 2
    assert result["provider_error_group_count"] == 1
    assert result["captures"][0]["group_status"] == "PROVIDER_ERROR_BLOCKED"
    assert result["captures"][0]["provider_errors"] == {"plan": "season unavailable"}
    assert result["captures"][1]["group_status"] == "CAPTURED"
    first = next(row for row in result["readiness"] if row["target_key"] == "api_football:fixture:900")
    assert "HISTORY_PROVIDER_ERROR" in first["blockers"]
    assert (tmp_path / "raw" / "league_39_season_2026.bin").exists()
    assert (tmp_path / "raw" / "league_40_season_2026.bin").exists()



def test_free_plan_season_gate_stops_group_fanout_and_probes_team_last(tmp_path):
    error_response = Mock()
    error_payload = {
        "get": "fixtures",
        "parameters": {"league": "39", "season": "2026"},
        "errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."},
        "results": 0,
        "paging": {"current": 1, "total": 1},
        "response": [],
    }
    error_response.status_code = 200
    error_response.content = __import__("json").dumps(error_payload).encode()
    error_response.json.return_value = error_payload
    error_response.headers = {}

    team_rows = [
        _fixture(
            300 + i,
            f"2026-09-{10+i:02d}T12:00:00+00:00",
            40,
            "Home FC",
            3000 + i,
            f"Opp {i}",
            2,
            1,
        )
        for i in range(6)
    ]
    team_response = _response(team_rows, remaining="60")
    session = Mock()
    session.get.side_effect = [error_response, team_response]
    ticks = iter([
        datetime(2026, 9, 28, 4, 50, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 1, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 2, tzinfo=timezone.utc),
        datetime(2026, 9, 28, 4, 50, 3, tzinfo=timezone.utc),
    ])

    result = capture_group_history(
        api_key="test-key",
        benchmark=_benchmark(),
        out_dir=tmp_path,
        session=session,
        max_requests=40,
        min_daily_remaining_reserve=40,
        now_fn=lambda: next(ticks),
    )

    assert result["free_plan_season_range_blocked"] is True
    assert result["stopped_reason"] == "FREE_PLAN_SEASON_RANGE_BLOCKED"
    assert result["captured_group_count"] == 1
    assert result["provider_error_group_count"] == 1
    assert result["network_calls_performed"] == 2
    assert result["team_last_probe"]["provider_team_id"] == "40"
    assert result["team_last_probe"]["probe_status"] == "CAPTURED"
    assert result["team_last_probe"]["final_history_rows"] == 6
    assert result["team_last_probe"]["rate_limit"]["daily_remaining"] == "60"
    assert (tmp_path / "raw" / "team_40_last_20.bin").exists()
