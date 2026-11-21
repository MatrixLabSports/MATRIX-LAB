import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.api_football_period_goals_lab import (
    MARKET_KEYS,
    _parse_fixture,
    build_period_goals_lab,
)


def _fixture(fid: int, kickoff: datetime, home: int, away: int, h1: int, a1: int, hf: int, af: int):
    return {
        "fixture": {
            "id": fid,
            "date": kickoff.isoformat(),
            "status": {"short": "FT"},
        },
        "teams": {
            "home": {"id": home},
            "away": {"id": away},
        },
        "score": {
            "halftime": {"home": h1, "away": a1},
            "fulltime": {"home": hf, "away": af},
        },
    }


def test_parse_fixture_derives_second_half_from_fulltime_minus_halftime():
    row = _fixture(
        1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        10,
        20,
        1,
        0,
        2,
        2,
    )
    parsed = _parse_fixture(row)
    assert parsed is not None
    assert parsed["first_half_home"] == 1
    assert parsed["first_half_away"] == 0
    assert parsed["second_half_home"] == 1
    assert parsed["second_half_away"] == 2


def test_invalid_negative_second_half_is_rejected():
    row = _fixture(
        1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        10,
        20,
        2,
        0,
        1,
        0,
    )
    assert _parse_fixture(row) is None


def test_period_goals_lab_builds_all_six_lanes_with_strict_pit(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    response = []
    teams = [10, 20, 30, 40]
    for i in range(48):
        home = teams[i % 4]
        away = teams[(i + 1) % 4]
        h1 = i % 2
        a1 = (i // 2) % 2
        h2 = (i // 3) % 2
        a2 = (i // 5) % 2
        response.append(
            _fixture(
                1000 + i,
                start + timedelta(days=i),
                home,
                away,
                h1,
                a1,
                h1 + h2,
                a1 + a2,
            )
        )
    (raw_dir / "league_1_season_2026.bin").write_text(
        json.dumps({"response": response}),
        encoding="utf-8",
    )

    out = build_period_goals_lab(
        raw_dir,
        generated_at=datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc),
    )

    assert out["status"] == "PASS_LAB"
    assert out["market_lane_count"] == 6
    assert set(out["market_lanes"]) == set(MARKET_KEYS)
    assert out["eligible_walk_forward_rows"] > 0
    assert out["protections"]["strictly_prior_kickoff_only"] is True
    assert out["protections"]["target_outcome_used_to_generate_probability"] is False
    assert out["protections"]["odds_used_to_generate_probability"] is False
    assert out["protections"]["automatic_wagering"] is False
    assert out["protections"]["real_money"] == "BLOCKED"
    assert all(
        x["target_outcome_used_to_generate_probability"] is False
        for x in out["samples"]
    )
    assert all(
        x["odds_used_to_generate_probability"] is False
        for x in out["samples"]
    )
