"""Pre-registered team-aware Bayesian research challenger, separate from MATRIX.

V1 assigns the same probability to each game in a league. V2 preserves that
league-level baseline but applies outcome-history shrinkage to the actual home
team's HOME fixtures and the actual away team's AWAY fixtures, using only
SHA-authenticated matches that predate both the capture and the target kickoff.

This is a research hypothesis, not evidence of improved betting performance.
No automatic model promotion, Telegram or real-money wagering.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.matrix_hybrid_elite_research_pair_bridge import source_envelope
from tools.matrix_hybrid_free_bayesian_v1 import (
    validate_pairs_manifest, read_bound, score_one as audit_v1_input,
)
from tools.matrix_independent_free_poisson_v1 import decode_group
from tools.matrix_independent_free_poisson_oos import stamp

MODEL = "MATRIX_HYBRID_TEAM_VENUE_BETA_V2"
SCHEMA = "MATRIX_HYBRID_TEAM_VENUE_BETA_V2_PREMATCH_RESEARCH_V1"
CYCLE = "MATRIX_HYBRID_TEAM_VENUE_BETA_V2_RESEARCH_CYCLE_V1"
MANIFEST = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json")
REPORT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_TEAM_VENUE_BETA_V2_LAST.json")
MIN_LEAGUE_HISTORY = 20
MIN_TEAM_VENUE_HISTORY = 3
LEAGUE_BETA_ALPHA = 3.0
LEAGUE_BETA_BETA = 3.0
TEAM_PRIOR_MATCHES = 6.0
HOME_ROLE_WEIGHT = 0.5
AWAY_ROLE_WEIGHT = 0.5


def require(x, reason):
    if not x:
        raise ValueError(reason)


def secure_date(row):
    dt = stamp(row["event_start_at_utc"])
    return dt.astimezone(ZoneInfo("America/Bogota")).date().isoformat()


def filename(root: Path, row: dict) -> Path:
    fid = str(row["physical_event_id"])
    require(fid.isdecimal(), "INVALID_V2_EVENT_ID")
    return (root / "evidence/football_world_inventory" /
            secure_date(row) / "MATRIX_HYBRID_TEAM_VENUE_BETA_V2_IMMUTABLE" /
            (fid + ".json"))


def _logit(p: float) -> float:
    require(0 < p < 1 and math.isfinite(p), "INVALID_BAYESIAN_INPUT_PROBABILITY")
    return math.log(p / (1.0 - p))


def p_team_venue(*, league_games: int, league_over: int,
                 home_games: int, home_over: int,
                 away_games: int, away_over: int) -> dict:
    """Fixed (not fitted) shrinkage; use historical Bernoulli team-role labels."""
    for name, v in (("league_games", league_games), ("league_over", league_over),
                    ("home_games", home_games), ("home_over", home_over),
                    ("away_games", away_games), ("away_over", away_over)):
        require(type(v) is int and v >= 0, "BAD_HISTORICAL_COUNT_" + name)
    require(league_games >= MIN_LEAGUE_HISTORY and
            home_games >= MIN_TEAM_VENUE_HISTORY and
            away_games >= MIN_TEAM_VENUE_HISTORY,
            "INSUFFICIENT_PREMATCH_TEAM_OR_LEAGUE_HISTORY")
    require(league_over <= league_games and home_over <= home_games and
            away_over <= away_games, "HISTORICAL_SUCCESS_COUNT_INVALID")
    p_league = (league_over + LEAGUE_BETA_ALPHA) / (
        league_games + LEAGUE_BETA_ALPHA + LEAGUE_BETA_BETA)
    p_home = (home_over + TEAM_PRIOR_MATCHES * p_league) / (
        home_games + TEAM_PRIOR_MATCHES)
    p_away = (away_over + TEAM_PRIOR_MATCHES * p_league) / (
        away_games + TEAM_PRIOR_MATCHES)
    lp = (_logit(p_league) +
          HOME_ROLE_WEIGHT * (_logit(p_home) - _logit(p_league)) +
          AWAY_ROLE_WEIGHT * (_logit(p_away) - _logit(p_league)))
    p = 1.0 / (1.0 + math.exp(-lp))
    require(0 < p < 1 and math.isfinite(p), "INVALID_V2_OUTPUT_PROBABILITY")
    return {
        "league_prior_p": round(p_league, 12),
        "home_role_p": round(p_home, 12),
        "away_role_p": round(p_away, 12),
        "p_over25": round(p, 12),
    }


def one(root: Path, entry: dict, now: datetime, memo: dict,
        cached_histories: dict) -> dict:
    kickoff = stamp(entry["event_start_at_utc"])
    require(now < kickoff, "TEAM_VENUE_FORECAST_AFTER_KICKOFF")
    # The existing V1 source gate is used ONLY for provenance verification,
    # never its V1 model probability or the target game's outcome.
    audit = audit_v1_input(root, entry, now, memo, cached_histories)
    original = read_bound(root, entry["original_freeze_path"],
                          entry["original_freeze_sha256"])
    shadow, intake = source_envelope(root, original, memo)
    cid = str(entry["competition_id"])
    groups = shadow["authenticated_raw_group_replay_evidence"]
    require(cid in groups, "LEAGUE_NOT_IN_AUTHENTICATED_RAW_HISTORY")
    group = groups[cid]
    observed, history, missing_updates = decode_group(group, cid, now)
    require(observed < now and observed < kickoff,
            "GROUP_HISTORY_NOT_CAPTURED_PREMATCH")
    require(group["source_payload_sha256"] == entry["common_history_raw_sha256"],
            "TEAM_VENUE_SOURCE_HISTORY_SHA_MISMATCH")
    matches = [r for r in intake.get("fixtures", [])
               if str(r.get("source_fixture_id")) ==
               str(entry["physical_event_id"])]
    require(len(matches) == 1, "TEAM_VENUE_EVENT_IDENTITY_AMBIGUOUS")
    target = matches[0]
    require(str(target["source_competition_id"]) == cid and
            stamp(target["kickoff_utc"]) == kickoff and
            target.get("api_football_fixture_id") is None,
            "TEAM_VENUE_TARGET_PROVIDER_ID_INVALID")
    hid, aid = str(target["home_source_team_id"]), str(target["away_source_team_id"])
    require(hid != aid, "SAME_HOME_AND_AWAY_TEAM")
    past = [r for r in history
            if r["kickoff_utc"] < observed and r["kickoff_utc"] < kickoff]
    require(len({r["fixture_id"] for r in past}) == len(past),
            "DUPLICATED_AUTHENTIC_HISTORIC_MATCH")
    home = [r for r in past if r["home_team_id"] == hid]
    away = [r for r in past if r["away_team_id"] == aid]
    def total(x):
        return int(x["home_goals"] + x["away_goals"] > 2)
    counts = {
        "league_games": len(past),
        "league_over": sum(map(total, past)),
        "home_games": len(home),
        "home_over": sum(map(total, home)),
        "away_games": len(away),
        "away_over": sum(map(total, away)),
    }
    probabilities = p_team_venue(**counts)
    return {
        "schema": SCHEMA,
        "model_id": MODEL,
        "physical_event_id": str(entry["physical_event_id"]),
        "provider": "FOOTBALL_DATA_ORG",
        "competition_id": cid,
        "home_provider_team_id": hid,
        "away_provider_team_id": aid,
        "event_start_at_utc": kickoff.isoformat(),
        "forecast_frozen_at_utc": now.isoformat(),
        "history_observed_at_utc": observed.isoformat(),
        "source_historical_payload_sha256": entry["common_history_raw_sha256"],
        "source_original_research_freeze_sha256": entry["original_freeze_sha256"],
        "source_poisson_research_freeze_sha256": entry["poisson_freeze_sha256"],
        "source_shadow_file_sha256": original["source_shadow_file_sha256"],
        "source_intake_file_sha256": original["source_intake_file_sha256"],
        "history_groups_validated_by_existing_v1_provenance": True,
        "history_row_count": len(past),
        "history_source_rows_without_provider_update_rejected":
            missing_updates,
        "v1_provenance_scope_pooled_history_count":
            audit["certified_before_prediction_historical_pool_count"],
        "policy_fixed_before_observing_future_result": {
            "league_beta": [LEAGUE_BETA_ALPHA, LEAGUE_BETA_BETA],
            "team_prior_matches": TEAM_PRIOR_MATCHES,
            "min_league_games": MIN_LEAGUE_HISTORY,
            "min_team_role_games": MIN_TEAM_VENUE_HISTORY,
            "home_logit_weight": HOME_ROLE_WEIGHT,
            "away_logit_weight": AWAY_ROLE_WEIGHT,
        },
        "observed_counts": counts,
        "probabilities": probabilities,
        "p_team_venue_over25": probabilities["p_over25"],
        "target_future_result_used": False,
        "research_only": True,
        "original_official_p_matrix_certified": False,
        "prospective_oos_certified": False,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def run(root: Path, manifest: dict, now: datetime) -> dict:
    require(now.utcoffset() is not None, "AWARE_CLOCK_REQUIRED")
    now = now.astimezone(timezone.utc)
    rows = validate_pairs_manifest(manifest)
    seen, forecast, existing, expired, blocked = set(), [], [], [], []
    memo, histories = {}, {}
    for entry in rows:
        fid = str(entry["physical_event_id"])
        require(fid not in seen, "DUPLICATE_V2_EVENT_IN_MANIFEST")
        seen.add(fid)
        location = filename(root, entry)
        kickoff = stamp(entry["event_start_at_utc"])
        if location.is_file():
            try:
                row = json.loads(location.read_bytes())
                p = row.get("p_team_venue_over25")
                require(row.get("schema") == SCHEMA and
                        row.get("model_id") == MODEL and
                        row.get("physical_event_id") == fid and
                        row.get("source_historical_payload_sha256") ==
                        entry["common_history_raw_sha256"] and
                        row.get("source_original_research_freeze_sha256") ==
                        entry["original_freeze_sha256"] and
                        row.get("source_poisson_research_freeze_sha256") ==
                        entry["poisson_freeze_sha256"] and
                        stamp(row["forecast_frozen_at_utc"]) < kickoff and
                        type(p) in (float, int) and 0 < p < 1 and
                        row.get("automatic_model_promotion") is False and
                        row.get("telegram_signal_authorized") is False and
                        row.get("real_money") == "BLOCKED",
                        "V2_PRIOR_IMMUTABLE_FREEZE_CONFLICT")
                existing.append(fid)
            except (OSError, ValueError, KeyError, TypeError) as err:
                blocked.append({"fixture_id": fid, "reason": str(err)[:150]})
            continue
        if now >= kickoff:
            expired.append(fid)
            continue
        try:
            forecast.append(one(root, entry, now, memo, histories))
        except (OSError, ValueError, TypeError, KeyError,
                json.JSONDecodeError) as err:
            blocked.append({"fixture_id": fid, "reason": str(err)[:150]})
    return {
        "schema": CYCLE,
        "model_id": MODEL,
        "generated_at_utc": now.isoformat(),
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "new_forecast_count": len(forecast),
        "existing_forecast_count": len(existing),
        "expired_unfrozen_count": len(expired),
        "blocked_count": len(blocked),
        "scored": forecast,
        "existing_fixture_ids": existing,
        "expired_unfrozen_fixture_ids": expired,
        "blocked": blocked,
        "competition_unique_prediction_counts": {
            k: len(set(r["p_team_venue_over25"] for r in forecast
                       if r["competition_id"] == k))
            for k in sorted(set(x["competition_id"] for x in forecast))
        },
        "scientific_improvement_certified": False,
        "original_parameters_mutated": False,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--pairs", type=Path, default=MANIFEST)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    require(not ({"telegram", "notifications", "tennis_signals",
                  "daily_prematch_reports"} & set(args.out.parts)),
            "NO_V2_RESEARCH_WRITES_TO_PRODUCTION")
    now = datetime.now(timezone.utc)
    manifest = json.loads((args.root/args.pairs).read_bytes())
    report = run(args.root, manifest, now)
    for item in report["scored"]:
        dest = filename(args.root, item)
        require(not dest.exists(), "V2_CANNOT_OVERWRITE_IMMUTABLE")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("x", encoding="utf-8") as fp:
            json.dump(item, fp, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
    target = args.out if args.out.is_absolute() else args.root / args.out
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not report["new_forecast_count"] and not report["blocked_count"]:
        previous = json.loads(target.read_bytes())
        if (previous.get("new_forecast_count", 0) +
            previous.get("existing_forecast_count", 0) ==
            report["existing_forecast_count"] and
            previous.get("expired_unfrozen_count", 0) ==
            report["expired_unfrozen_count"]):
            print(json.dumps({"unchanged": True,
                              "existing": report["existing_forecast_count"],
                              "real_money": "BLOCKED"}))
            return
    target.write_text(json.dumps(report, ensure_ascii=False,
                                 indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"new": report["new_forecast_count"],
                      "existing": report["existing_forecast_count"],
                      "expired_unfrozen": report["expired_unfrozen_count"],
                      "blocked": report["blocked_count"],
                      "model_promoted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
