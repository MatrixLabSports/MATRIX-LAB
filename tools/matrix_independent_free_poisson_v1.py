"""Original-parameter-independent, physically sourced Over2.5 Poisson challenger.

A separate research model, NOT a drop-in replacement for calibrated MATRIX.
Inputs must originate from an actual authenticated football-data.org historical
response preserved byte-for-byte in the independent shadow source envelope.
Scores, quoted odds, post-kickoff backfill and production writes are forbidden.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_football_independent_over25_shadow import historic_rows

MODEL = "MATRIX_FREE_POISSON_TEAM_V1"
SCHEMA = "MATRIX_FREE_POISSON_PROSPECTIVE_RESEARCH_V1"
MIN_LEAGUE_FINALS = 20
MIN_VENUE_TEAM_FINALS = 3
VENUE_WINDOW = 20
SMOOTHING_PRIOR_MATCHES = 5.0
MAX_PAYLOAD_BYTES = 5_000_000


def moment(raw):
    v = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if v.utcoffset() is None:
        raise ValueError("TIMEZONE_AWARE_TIMESTAMP_REQUIRED")
    return v.astimezone(timezone.utc)


def require(ok, code):
    if not ok:
        raise ValueError(code)


def validate_sources(intake, shadow, now):
    require(now.utcoffset() is not None, "CLOCK_NOT_AWARE")
    require(intake.get("schema") == "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
            "INTAKE_SCHEMA_INVALID")
    require(shadow.get("schema") == "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
            "SHADOW_SCHEMA_INVALID")
    for d in (intake, shadow):
        require(d.get("source") == "FOOTBALL_DATA_ORG" and
                d.get("real_money") == "BLOCKED", "GOVERNANCE_SOURCE_INVALID")
    require(intake.get("signal_generation_authorized") is False and
            shadow.get("market_signal_authorized") is False and
            shadow.get("parameter_refit") is False, "MODEL_RESEARCH_ONLY_REQUIRED")
    require(intake.get("target_date_bogota") == shadow.get("target_date_bogota"),
            "SOURCE_DAY_MISMATCH")
    if "generated_at_utc" in intake:
        require(moment(intake["generated_at_utc"]) <= now, "INTAKE_FUTURE_TIMESTAMP")
    require(moment(shadow["generated_at_utc"]) <= now, "SHADOW_FUTURE_TIMESTAMP")
    require(moment(shadow["completed_at_utc"]) <= now, "SHADOW_NOT_COMPLETED")
    fixtures = intake.get("fixtures")
    require(isinstance(fixtures, list), "FIXTURES_NOT_A_LIST")
    require(isinstance(shadow.get("authenticated_raw_group_replay_evidence"), dict),
            "AUTHENTIC_HISTORY_NOT_PRESENT")
    return fixtures


def decode_group(group, competition_id, now):
    require(group.get("competition_id") == int(competition_id), "HISTORY_COMPETITION_MISMATCH")
    observed = moment(group["observed_at_utc"])
    require(observed <= now, "HISTORY_CAPTURE_IN_FUTURE")
    raw = base64.b64decode(group["response_base64"], validate=True)
    require(len(raw) <= MAX_PAYLOAD_BYTES and
            hashlib.sha256(raw).hexdigest() == group.get("source_payload_sha256"),
            "HISTORY_RAW_SHA256_INVALID")
    payload = json.loads(raw)
    require(isinstance(payload, dict) and isinstance(payload.get("matches"), list),
            "HISTORY_RESPONSE_INVALID")
    safe, ignored_missing_update = [], 0
    for row in payload["matches"]:
        if not isinstance(row, dict) or row.get("status") != "FINISHED":
            continue
        if not row.get("lastUpdated"):
            ignored_missing_update += 1
            continue
        try:
            updated = moment(row["lastUpdated"])
            kickoff = moment(row["utcDate"])
        except (ValueError, TypeError, KeyError):
            continue
        if kickoff >= observed or updated > observed or updated < kickoff:
            continue
        safe.append(row)
    history = historic_rows({**payload, "matches": safe}, int(competition_id))
    require(len({x["fixture_id"] for x in history}) == len(history),
            "HISTORY_DUPLICATE_FINAL")
    return observed, history, ignored_missing_update


def score_one(fixture, group, now):
    require(fixture.get("source") == "FOOTBALL_DATA_ORG" and
            fixture.get("signal_generation_authorized") is False,
            "FORECAST_FIXTURE_NOT_RESEARCH_ONLY")
    require(fixture.get("api_football_fixture_id") is None, "PROVIDER_ID_NAMESPACE_VIOLATION")
    kickoff = moment(fixture["kickoff_utc"])
    require(now < kickoff, "FORECAST_AFTER_KICKOFF")
    cid = str(int(fixture["source_competition_id"]))
    observed, historical, ignored = decode_group(group, cid, now)
    require(observed < kickoff, "HISTORY_NOT_OBSERVED_PREMATCH")
    require(group.get("source_payload_sha256") is not None, "HISTORY_SHA_REQUIRED")
    # Do NOT use odds or other matches starting at/after this fixture.
    prior = [r for r in historical if r["kickoff_utc"] < kickoff]
    require(len(prior) >= MIN_LEAGUE_FINALS, "LEAGUE_HISTORY_TOO_SHORT")
    home_id = str(int(fixture["home_source_team_id"]))
    away_id = str(int(fixture["away_source_team_id"]))
    require(home_id != away_id, "SAME_TEAM_TARGET")
    homes = [r for r in prior if r["home_team_id"] == home_id][-VENUE_WINDOW:]
    aways = [r for r in prior if r["away_team_id"] == away_id][-VENUE_WINDOW:]
    require(len(homes) >= MIN_VENUE_TEAM_FINALS and
            len(aways) >= MIN_VENUE_TEAM_FINALS, "TEAM_VENUE_HISTORY_TOO_SHORT")
    mean_home = sum(x["home_goals"] for x in prior) / len(prior)
    mean_away = sum(x["away_goals"] for x in prior) / len(prior)
    require(mean_home > 0 and mean_away > 0, "INVALID_LEAGUE_GOAL_PRIOR")
    a = SMOOTHING_PRIOR_MATCHES
    # Independent, predetermined arithmetic: no original MATRIX coefficients.
    h_att = (sum(x["home_goals"] for x in homes) + a * mean_home) / (len(homes) + a)
    h_def = (sum(x["away_goals"] for x in homes) + a * mean_away) / (len(homes) + a)
    a_att = (sum(x["away_goals"] for x in aways) + a * mean_away) / (len(aways) + a)
    a_def = (sum(x["home_goals"] for x in aways) + a * mean_home) / (len(aways) + a)
    lambda_home = min(5.0, max(0.1, (h_att + a_def) / 2))
    lambda_away = min(5.0, max(0.1, (a_att + h_def) / 2))
    total = lambda_home + lambda_away
    p = 1 - math.exp(-total) * (1 + total + total**2 / 2)
    require(math.isfinite(p) and 0 < p < 1, "INVALID_INDEPENDENT_PROBABILITY")
    return {
        "schema": SCHEMA, "model_id": MODEL,
        "fixture_id": str(int(fixture["source_fixture_id"])),
        "provider": "FOOTBALL_DATA_ORG",
        "provider_competition_id": cid,
        "home": fixture["home"], "away": fixture["away"],
        "kickoff_utc": kickoff.isoformat(),
        "forecast_frozen_at_utc": now.isoformat(),
        "history_observed_at_utc": observed.isoformat(),
        "history_raw_sha256": group["source_payload_sha256"],
        "history_final_pre_target_count": len(prior),
        "home_venue_history_count": len(homes),
        "away_venue_history_count": len(aways),
        "home_lambda": round(lambda_home, 12),
        "away_lambda": round(lambda_away, 12),
        "research_probability_over25": round(p, 12),
        "policy_parameters": {
            "home_away_window": VENUE_WINDOW,
            "venue_minimum": MIN_VENUE_TEAM_FINALS,
            "league_minimum": MIN_LEAGUE_FINALS,
            "prior_matches": SMOOTHING_PRIOR_MATCHES},
        "source_rows_missing_provider_update": ignored,
        "source_equivalence_to_original_certified": False,
        "independent_model_prospective_oos_certified": False,
        "p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def forecast(intake, shadow, *, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    fixtures = validate_sources(intake, shadow, now)
    seen = set()
    out, blocked = [], []
    groups = shadow["authenticated_raw_group_replay_evidence"]
    for f in fixtures:
        if not isinstance(f, dict):
            blocked.append({"fixture_id": None, "reason": "INVALID_FIXTURE"}); continue
        fid = str(f.get("source_fixture_id"))
        if fid in seen:
            raise ValueError("DUPLICATE_FIXTURE")
        seen.add(fid)
        try:
            cid = str(int(f["source_competition_id"]))
            require(cid in groups, "COMPETITION_RAW_EVIDENCE_MISSING")
            out.append(score_one(f, groups[cid], now))
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            blocked.append({"fixture_id": fid, "reason": str(exc)[:125]})
    return {
        "schema": "MATRIX_FREE_POISSON_PREDICTION_CYCLE_V1",
        "model_id": MODEL, "generated_at_utc": now.isoformat(),
        "target_date_bogota": intake["target_date_bogota"],
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "scored_count": len(out), "blocked_count": len(blocked),
        "scored": out, "blocked": blocked,
        "no_original_calibration_modification": True,
        "model_has_own_independent_id": True,
        "independent_model_prospective_oos_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--intake", type=Path, required=True)
    p.add_argument("--shadow", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    disallowed = {"telegram", "daily_prematch_reports", "governance", "tennis_signals"}
    if disallowed & set(args.out.parts):
        raise SystemExit("RESEARCH_MODEL_CANNOT_WRITE_PRODUCTION")
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    shadow = json.loads(args.shadow.read_text(encoding="utf-8"))
    result = forecast(intake, shadow)
    result["source_file_sha256"] = {
        "intake": hashlib.sha256(args.intake.read_bytes()).hexdigest(),
        "shadow": hashlib.sha256(args.shadow.read_bytes()).hexdigest()
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Save each first true future freeze once. Repeated retries must not
    # replace the original frozen probability with a later one.
    frozen = args.out.parent / "MATRIX_FREE_POISSON_V1_IMMUTABLE"
    frozen.mkdir(exist_ok=True)
    new, preexisting = 0, 0
    for row in result["scored"]:
        file = frozen / (row["fixture_id"] + ".json")
        if file.exists():
            old = json.loads(file.read_text(encoding="utf-8"))
            require(old.get("schema") == SCHEMA and
                    old.get("telegram_signal_authorized") is False and
                    old.get("real_money") == "BLOCKED" and
                    old.get("fixture_id") == row["fixture_id"] and
                    old.get("model_id") == MODEL,
                    "FROZEN_FILE_CANNOT_BE_TRUSTED")
            preexisting += 1
        else:
            with file.open("x", encoding="utf-8") as fh:
                json.dump(row, fh, ensure_ascii=False, sort_keys=True)
                fh.write("\n")
            new += 1
    result["immutable_new_freezes"] = new
    result["immutable_preexisting_freezes"] = preexisting
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"scored": result["scored_count"], "new_freezes": new,
                      "blocked": result["blocked_count"], "telegram": False}, sort_keys=True))


if __name__ == "__main__":
    main()
