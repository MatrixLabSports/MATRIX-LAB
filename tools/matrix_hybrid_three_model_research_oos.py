"""Strict prospective 3-model research comparison for MATRIX Híbrida Élite.

This evaluator NEVER builds a forecast. It reads:
  1. the source-bound prelabel two-model research manifest,
  2. physically frozen Bayesian predictions, and
  3. the original independently verified outcome scorecard.
No results are admitted before kickoff, and no research output is P_MATRIX.
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

from tools.matrix_hybrid_free_bayesian_v1 import (
    SCHEMA as BAYES_SCHEMA, MODEL as BAYES_MODEL, validate_pairs_manifest,
)
from tools.matrix_independent_free_poisson_oos import evaluate as verify_outcomes, stamp

MANIFEST = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json")
REPORT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_THREE_MODEL_OOS_LAST.json")
SCHEMA = "MATRIX_HYBRID_THREE_MODEL_PROSPECTIVE_RESEARCH_OOS_V1"
PREDICTORS = ("original_formula_research", "independent_free_poisson", "hybrid_free_bayesian")
MIN_LEAGUE_OOS = 30
MIN_POOLED_OOS = 200


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def official_scope_blocked(obj):
    for field in ("telegram_signal_authorized", "automatic_wagering"):
        require(obj.get(field) is False, "FORECAST_ILLEGAL_PROMOTION:" + field)
    require(obj.get("real_money") == "BLOCKED", "FORECAST_MONEY_NOT_BLOCKED")


def bayesian_file(root: Path, pair: dict) -> Path:
    fid = str(pair["physical_event_id"])
    require(fid.isdecimal(), "EVENT_ID_MUST_BE_NUMERIC")
    dt = stamp(pair["event_start_at_utc"])
    local_day = dt.astimezone(ZoneInfo("America/Bogota")).date().isoformat()
    return (root / "evidence/football_world_inventory" / local_day /
            "MATRIX_HYBRID_FREE_BAYESIAN_V1_IMMUTABLE" / (fid + ".json"))


def verify_bayesian(root: Path, pair: dict, now: datetime):
    path = bayesian_file(root, pair)
    if not path.is_file():
        return None
    raw = path.read_bytes()
    require(len(raw) < 150000 and raw.endswith(b"\n"),
            "BAYESIAN_FILE_MALFORMED")
    b = json.loads(raw)
    official_scope_blocked(b)
    require(b.get("schema") == BAYES_SCHEMA and b.get("model_id") == BAYES_MODEL,
            "WRONG_BAYESIAN_MODEL_OR_SCHEMA")
    require(str(b.get("physical_event_id")) == str(pair["physical_event_id"]) and
            str(b.get("provider_competition_id")) == str(pair["competition_id"]) and
            b.get("provider") == "FOOTBALL_DATA_ORG", "BAYESIAN_PHYSICAL_IDENTITY_MISMATCH")
    require(b.get("source_original_research_freeze_sha256") ==
            pair["original_freeze_sha256"] and
            b.get("source_independent_poisson_freeze_sha256") ==
            pair["poisson_freeze_sha256"] and
            b.get("same_authenticated_target_history_sha256") ==
            pair["common_history_raw_sha256"], "BAYESIAN_SOURCE_PROVENANCE_MISMATCH")
    hashes = b.get("source_history_response_sha256_by_competition")
    require(isinstance(hashes, dict) and
            hashes.get(str(pair["competition_id"])) == pair["common_history_raw_sha256"],
            "BAYESIAN_TARGET_HISTORY_MISSING_OR_CHANGED")
    kickoff = stamp(pair["event_start_at_utc"])
    frozen = stamp(b["forecast_frozen_at_utc"])
    require(stamp(b["event_start_at_utc"]) == kickoff and
            stamp(pair["original_formula_research_frozen_at_utc"]) < kickoff and
            stamp(pair["independent_poisson_frozen_at_utc"]) < kickoff and
            frozen < kickoff and frozen <= now,
            "BAYESIAN_NOT_AUTHENTIC_PREMATCH_FREEZE")
    require(b.get("target_outcome_not_used") is True and
            b.get("model_promotion_authorized") is False and
            b.get("independent_hybrid_future_oos_certified") is False,
            "BAYESIAN_OUTCOME_LEAKAGE_OR_PROMOTION")
    prob = b.get("p_bayesian_research_over25")
    require(type(prob) in (int, float) and math.isfinite(prob) and 0 < prob < 1,
            "BAYESIAN_RESEARCH_P_INVALID")
    require(b.get("certified_before_prediction_league_count", 0) >= 20 and
            b.get("certified_before_prediction_historical_pool_count", 0) >= 30,
            "BAYESIAN_RESEARCH_HISTORY_INSUFFICIENT")
    return {"forecast": b, "sha256": hashlib.sha256(raw).hexdigest(),
            "path": path.relative_to(root).as_posix()}


def compare_one(pair: dict, outcome: dict, bayes: dict):
    """Score only an actual result row previously certified by verify_outcomes.

    The caller, not this function, must authenticate the outcome bytes.
    Unit tests may call this with *synthetic* label rows, which are never
    persisted to physical calibration or science ledgers.
    """
    require(str(outcome["fixture_id"]) == str(pair["physical_event_id"]) and
            str(outcome["provider_competition_id"]) == str(pair["competition_id"]),
            "VERIFIED_OUTCOME_WRONG_FIXTURE")
    require(outcome.get("original_frozen_forecast_sha256") ==
            pair["original_freeze_sha256"] and
            outcome.get("poisson_forecast_sha256") == pair["poisson_freeze_sha256"] and
            outcome.get("poisson_source_history_sha256") ==
            pair["common_history_raw_sha256"] and
            outcome.get("original_source_history_sha256") ==
            pair["common_history_raw_sha256"] and
            outcome.get("identical_authenticated_history_capture") is True,
            "VERIFIED_OUTCOME_RESEARCH_SOURCE_NOT_IDENTICAL")
    require(isinstance(outcome.get("settlement_sha256"), str) and
            isinstance(outcome.get("provider_result_sha256"), str) and
            len(outcome["settlement_sha256"]) == len(outcome["provider_result_sha256"]) == 64,
            "VERIFIED_OUTCOME_UNBOUND_RESULT_SHA")
    y = outcome["outcome"]
    require(type(y) is int and y in (0, 1), "VERIFIED_OUTCOME_BINARY_ONLY")
    p_original, p_poisson, p_bayes = (
        pair["original_formula_research_p"],
        pair["independent_free_poisson_p"],
        bayes["forecast"]["p_bayesian_research_over25"])
    for p in (p_original, p_poisson, p_bayes):
        require(type(p) in (int, float) and math.isfinite(p) and 0 < p < 1,
                "RESEARCH_P_INVALID")
    require(abs(p_original - outcome["original_research_p"]) < 1e-12 and
            abs(p_poisson - outcome["poisson_p"]) < 1e-12,
            "EXISTING_VERIFIED_PROBABILITIES_DISAGREE")
    scores = {}
    for label, p in zip(PREDICTORS, (p_original, p_poisson, p_bayes)):
        scores[label] = {
            "p_over25": p,
            "brier": (p - y) ** 2,
            "logloss": -(y * math.log(p) + (1 - y) * math.log1p(-p)),
        }
    return {
        "fixture_id": str(pair["physical_event_id"]),
        "competition_id": str(pair["competition_id"]),
        "kickoff_utc": pair["event_start_at_utc"],
        "outcome_over25": y,
        "source_original_forecast_sha256": pair["original_freeze_sha256"],
        "source_poisson_forecast_sha256": pair["poisson_freeze_sha256"],
        "source_bayesian_forecast_sha256": bayes["sha256"],
        "source_provider_final_sha256": outcome["provider_result_sha256"],
        "source_settlement_sha256": outcome["settlement_sha256"],
        "same_authenticated_input": True,
        "predictors": scores,
    }


def aggregate(rows):
    n = len(rows)
    if not n:
        return None
    result = {}
    for name in PREDICTORS:
        result[name] = {
            "mean_brier": round(sum(r["predictors"][name]["brier"] for r in rows)/n, 9),
            "mean_logloss": round(sum(r["predictors"][name]["logloss"] for r in rows)/n, 9),
        }
    return result


def evaluate(root: Path, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    require(now.utcoffset() is not None, "OOS_AWARE_CLOCK_REQUIRED")
    now = now.astimezone(timezone.utc)
    raw = (root / MANIFEST).read_bytes()
    manifest = json.loads(raw)
    pairs = validate_pairs_manifest(manifest)
    verified = verify_outcomes(root, now)
    require(verified.get("real_money") == "BLOCKED" and
            verified.get("telegram_signal_authorized") is False and
            verified.get("production_p_matrix_authorized") is False and
            verified.get("canonical_model_parity_certified") is False,
            "RESEARCH_DOUBLE_MODEL_SCORECARD_UNTRUSTED")
    outcomes = {}
    for row in verified["pairs"]:
        fid = str(row["fixture_id"])
        require(fid not in outcomes, "DUPLICATE_VERIFIED_OUTCOME_FIXTURE")
        outcomes[fid] = row
    approved, rejected, waiting_results, missing_bayes, pending, seen = [], [], [], [], [], set()
    for pair in pairs:
        fid = str(pair["physical_event_id"])
        try:
            require(fid not in seen, "DUPLICATE_HYBRID_MANIFEST_FIXTURE")
            seen.add(fid)
            # Read the frozen Bayesian model even for an upcoming fixture:
            # future predictions remain pending, not labeled as correct.
            b = verify_bayesian(root, pair, now)
            kickoff = stamp(pair["event_start_at_utc"])
            if b is None:
                missing_bayes.append({"fixture_id": fid,
                                      "status": "NOT_YET_FROZEN" if now < kickoff
                                      else "EXPIRED_UNFROZEN_NEVER_BACKFILL"})
                continue
            if now <= kickoff:
                pending.append(fid)
                continue
            if fid not in outcomes:
                waiting_results.append(fid)
                continue
            approved.append(compare_one(pair, outcomes[fid], b))
        except (KeyError, ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({"fixture_id": fid, "reason": str(exc)[:150]})
    groups = defaultdict(list)
    for row in approved:
        groups[row["competition_id"]].append(row)
    competitions = [
        {"competition_id": cid, "same_fixture_verified_results": len(group),
         "gate_30_per_league_met": len(group) >= MIN_LEAGUE_OOS,
         "scores": aggregate(group),
         "certified_original_p_matrix_comparison": False,
         "automatic_promotion": False}
        for cid, group in sorted(groups.items())
    ]
    # A missing Bayesian freeze or source-integrity rejection is a refusal,
    # never a silent increase in research sample size.
    return {
        "schema": SCHEMA,
        "generated_at_utc": now.isoformat(),
        "status": "THREE_RESEARCH_MODELS_PROSPECTIVE_EVALUATION_NO_PROMOTION",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "prospective_paired_research_fixture_count": len(pairs),
        "three_model_authenticated_settled_count": len(approved),
        "three_model_pending_fixture_count": len(pending),
        "three_model_missing_bayesian_forecasts": missing_bayes,
        "three_model_started_without_verified_final": waiting_results,
        "three_model_rejected": rejected,
        "underlying_two_model_rejected_count":
            len(verified["rejected_forecasts_or_settlements"]),
        "league_results": competitions,
        "pooled_results": aggregate(approved),
        "pooled_review_minimum_met": len(approved) >= MIN_POOLED_OOS,
        "research_league_threshold": MIN_LEAGUE_OOS,
        "research_pooled_threshold": MIN_POOLED_OOS,
        "result_rows": approved,
        "original_official_p_matrix_present": False,
        "original_hybrid_lab_model_certified": False,
        "model_winner_authorized": False,
        "research_automated_model_promotion": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    require(not ({"telegram", "notifications", "tennis_signals",
                  "daily_prematch_reports"} & set(args.out.parts)),
            "NO_RESEARCH_OOS_WRITES_TO_PRODUCTION")
    report = evaluate(args.root)
    dest = args.out if args.out.is_absolute() else args.root / args.out
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        previous = json.loads(dest.read_bytes())
        if ({k: v for k, v in previous.items() if k != "generated_at_utc"} ==
            {k: v for k, v in report.items() if k != "generated_at_utc"}):
            print(json.dumps({"unchanged": True,
                              "settled": report["three_model_authenticated_settled_count"],
                              "pending": report["three_model_pending_fixture_count"],
                              "real_money": "BLOCKED"}, sort_keys=True))
            return
    dest.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)+"\n",
                    encoding="utf-8")
    print(json.dumps({"settled": report["three_model_authenticated_settled_count"],
                      "pending": report["three_model_pending_fixture_count"],
                      "missing_bayesian": len(report["three_model_missing_bayesian_forecasts"]),
                      "waiting_final": len(report["three_model_started_without_verified_final"]),
                      "rejected": len(report["three_model_rejected"]),
                      "research_only": True, "real_money": "BLOCKED"}, sort_keys=True))


if __name__ == "__main__":
    main()
