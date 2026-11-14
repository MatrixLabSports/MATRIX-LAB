from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

FINAL_STATUSES = {"FT"}
MIN_GROUP_HISTORY = 20
MIN_TEAM_HISTORY = 5
MAX_TEAM_HISTORY = 20

DEFAULT_RAW_DIR = Path(
    "evidence/api_football/prospective_daily/2026-10-06/"
    "20261005T122152Z/history/raw"
)
DEFAULT_OUT = Path(
    "evidence/api_football/period_goals_lab/"
    "MATRIX_PERIOD_GOALS_LAB_LAST.json"
)

MARKET_KEYS = (
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER",
    "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
    "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME",
    "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
)


def _utc(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _poisson_over(lam: float, line: float) -> float:
    if lam < 0:
        raise ValueError("NEGATIVE_LAMBDA")
    if line == 0.5:
        return 1.0 - math.exp(-lam)
    if line == 1.5:
        return 1.0 - math.exp(-lam) * (1.0 + lam)
    raise ValueError("UNSUPPORTED_LINE")


def _mean(values: list[int]) -> float:
    if not values:
        raise ValueError("MEAN_REQUIRES_VALUES")
    return sum(values) / len(values)


def _parse_fixture(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    fixture = raw.get("fixture")
    teams = raw.get("teams")
    score = raw.get("score")
    if not isinstance(fixture, Mapping) or not isinstance(teams, Mapping) or not isinstance(score, Mapping):
        return None
    status = fixture.get("status")
    home = teams.get("home")
    away = teams.get("away")
    half = score.get("halftime")
    full = score.get("fulltime")
    if not all(isinstance(x, Mapping) for x in (status, home, away, half, full)):
        return None
    if str(status.get("short") or "").upper().strip() not in FINAL_STATUSES:
        return None
    try:
        fid = str(int(fixture.get("id")))
        hid = str(int(home.get("id")))
        aid = str(int(away.get("id")))
        kickoff = _utc(fixture.get("date"))
        h1 = int(half.get("home"))
        a1 = int(half.get("away"))
        hf = int(full.get("home"))
        af = int(full.get("away"))
    except (TypeError, ValueError):
        return None
    if min(h1, a1, hf, af) < 0:
        return None
    h2 = hf - h1
    a2 = af - a1
    if h2 < 0 or a2 < 0:
        return None
    return {
        "fixture_id": fid,
        "kickoff_utc": kickoff,
        "home_team_id": hid,
        "away_team_id": aid,
        "first_half_home": h1,
        "first_half_away": a1,
        "second_half_home": h2,
        "second_half_away": a2,
    }


def _load_group(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    response = payload.get("response") if isinstance(payload, Mapping) else None
    if not isinstance(response, list):
        raise ValueError("RAW_GROUP_RESPONSE_INVALID")
    rows = [parsed for item in response if isinstance(item, Mapping) for parsed in [_parse_fixture(item)] if parsed]
    rows.sort(key=lambda x: (x["kickoff_utc"], int(x["fixture_id"])))
    return rows, _sha_bytes(raw)


def _team_period_view(row: Mapping[str, Any], team_id: str, period: str) -> tuple[int, int]:
    home_key = f"{period}_home"
    away_key = f"{period}_away"
    if row["home_team_id"] == team_id:
        return int(row[home_key]), int(row[away_key])
    if row["away_team_id"] == team_id:
        return int(row[away_key]), int(row[home_key])
    raise ValueError("TEAM_NOT_IN_FIXTURE")


def _expected_period_goals(
    prior: list[dict[str, Any]],
    home_id: str,
    away_id: str,
    period: str,
) -> tuple[float, float] | None:
    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prior:
        by_team[row["home_team_id"]].append(row)
        by_team[row["away_team_id"]].append(row)

    home_hist = by_team.get(home_id, [])[-MAX_TEAM_HISTORY:]
    away_hist = by_team.get(away_id, [])[-MAX_TEAM_HISTORY:]
    if len(home_hist) < MIN_TEAM_HISTORY or len(away_hist) < MIN_TEAM_HISTORY:
        return None

    home_pairs = [_team_period_view(r, home_id, period) for r in home_hist]
    away_pairs = [_team_period_view(r, away_id, period) for r in away_hist]
    home_for = [x[0] for x in home_pairs]
    home_against = [x[1] for x in home_pairs]
    away_for = [x[0] for x in away_pairs]
    away_against = [x[1] for x in away_pairs]

    home_lambda = max(0.01, min(3.0, (_mean(home_for) + _mean(away_against)) / 2.0))
    away_lambda = max(0.01, min(3.0, (_mean(away_for) + _mean(home_against)) / 2.0))
    return home_lambda, away_lambda


def _brier(pairs: list[tuple[float, int]]) -> float | None:
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def build_period_goals_lab(raw_dir: Path, generated_at: datetime | None = None) -> dict[str, Any]:
    generated_at = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    files = sorted(raw_dir.glob("league_*_season_*.bin"))
    if not files:
        raise ValueError("PERIOD_GOALS_RAW_HISTORY_MISSING")

    rows_by_group: list[tuple[Path, list[dict[str, Any]], str]] = []
    source_final_rows = 0
    source_valid_period_rows = 0
    for path in files:
        group, digest = _load_group(path)
        source_final_rows += len(group)
        source_valid_period_rows += len(group)
        rows_by_group.append((path, group, digest))

    evals: dict[str, list[tuple[float, int]]] = {
        "first_half_over_0_5": [],
        "first_half_over_1_5": [],
        "second_half_over_0_5": [],
        "second_half_over_1_5": [],
        "first_half_home_team_over_0_5": [],
        "first_half_away_team_over_0_5": [],
        "second_half_home_team_over_0_5": [],
        "second_half_away_team_over_0_5": [],
    }
    eligible = 0
    blocked_group = 0
    blocked_team = 0
    samples: list[dict[str, Any]] = []

    for path, group, digest in rows_by_group:
        for idx, target in enumerate(group):
            prior = group[:idx]
            if len(prior) < MIN_GROUP_HISTORY:
                blocked_group += 1
                continue
            first = _expected_period_goals(
                prior, target["home_team_id"], target["away_team_id"], "first_half"
            )
            second = _expected_period_goals(
                prior, target["home_team_id"], target["away_team_id"], "second_half"
            )
            if first is None or second is None:
                blocked_team += 1
                continue

            fhl, fal = first
            shl, sal = second
            probs = {
                "first_half_over_0_5": _poisson_over(fhl + fal, 0.5),
                "first_half_over_1_5": _poisson_over(fhl + fal, 1.5),
                "second_half_over_0_5": _poisson_over(shl + sal, 0.5),
                "second_half_over_1_5": _poisson_over(shl + sal, 1.5),
                "first_half_home_team_over_0_5": _poisson_over(fhl, 0.5),
                "first_half_away_team_over_0_5": _poisson_over(fal, 0.5),
                "second_half_home_team_over_0_5": _poisson_over(shl, 0.5),
                "second_half_away_team_over_0_5": _poisson_over(sal, 0.5),
            }
            outcomes = {
                "first_half_over_0_5": int(target["first_half_home"] + target["first_half_away"] >= 1),
                "first_half_over_1_5": int(target["first_half_home"] + target["first_half_away"] >= 2),
                "second_half_over_0_5": int(target["second_half_home"] + target["second_half_away"] >= 1),
                "second_half_over_1_5": int(target["second_half_home"] + target["second_half_away"] >= 2),
                "first_half_home_team_over_0_5": int(target["first_half_home"] >= 1),
                "first_half_away_team_over_0_5": int(target["first_half_away"] >= 1),
                "second_half_home_team_over_0_5": int(target["second_half_home"] >= 1),
                "second_half_away_team_over_0_5": int(target["second_half_away"] >= 1),
            }
            for key, p in probs.items():
                evals[key].append((p, outcomes[key]))

            eligible += 1
            if len(samples) < 25:
                samples.append({
                    "fixture_id": target["fixture_id"],
                    "kickoff_utc": target["kickoff_utc"].isoformat(),
                    "source_group": path.name,
                    "source_raw_sha256": digest,
                    "prior_group_fixture_count": len(prior),
                    "expected_first_half_goals": {
                        "home": round(fhl, 8), "away": round(fal, 8)
                    },
                    "expected_second_half_goals": {
                        "home": round(shl, 8), "away": round(sal, 8)
                    },
                    "p_matrix_shadow": {k: round(v, 10) for k, v in probs.items()},
                    "target_outcome_used_to_generate_probability": False,
                    "odds_used_to_generate_probability": False,
                })

    metrics = {
        key: {
            "walk_forward_observations": len(values),
            "brier": None if _brier(values) is None else round(float(_brier(values)), 10),
        }
        for key, values in evals.items()
    }

    payload = {
        "schema": "MATRIX_FOOTBALL_PERIOD_GOALS_LAB_V1",
        "generated_at_utc": generated_at.replace(microsecond=0).isoformat(),
        "model": "PERIOD_TEAM_POISSON_PIT_V1",
        "mode": "RESEARCH_WALK_FORWARD_SHADOW",
        "market_lanes": list(MARKET_KEYS),
        "market_lane_count": len(MARKET_KEYS),
        "source_raw_dir": raw_dir.as_posix(),
        "source_file_count": len(files),
        "source_final_valid_period_rows": source_valid_period_rows,
        "eligible_walk_forward_rows": eligible,
        "blocked_group_history": blocked_group,
        "blocked_team_history": blocked_team,
        "probability_outputs": [
            "first_half_over_0_5",
            "first_half_over_1_5",
            "second_half_over_0_5",
            "second_half_over_1_5",
            "first_half_home_team_over_0_5",
            "first_half_away_team_over_0_5",
            "second_half_home_team_over_0_5",
            "second_half_away_team_over_0_5",
        ],
        "metrics": metrics,
        "samples": samples,
        "protections": {
            "minimum_group_history": MIN_GROUP_HISTORY,
            "minimum_team_history": MIN_TEAM_HISTORY,
            "maximum_team_history": MAX_TEAM_HISTORY,
            "strictly_prior_kickoff_only": True,
            "second_half_equals_fulltime_minus_halftime": True,
            "negative_period_goals_forbidden": True,
            "target_outcome_used_to_generate_probability": False,
            "odds_used_to_generate_probability": False,
            "parameter_refit": False,
            "parameter_search": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "production_authorized": False,
        "status": "PASS_LAB" if eligible > 0 else "BLOCKED_NO_ELIGIBLE_HISTORY",
    }
    payload["payload_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default=str(DEFAULT_RAW_DIR))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    args = p.parse_args()
    result = build_period_goals_lab(Path(args.raw_dir))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "market_lane_count": result["market_lane_count"],
        "source_file_count": result["source_file_count"],
        "eligible_walk_forward_rows": result["eligible_walk_forward_rows"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))
    if result["status"] != "PASS_LAB":
        raise SystemExit("PERIOD_GOALS_LAB_BLOCKED")


if __name__ == "__main__":
    main()
