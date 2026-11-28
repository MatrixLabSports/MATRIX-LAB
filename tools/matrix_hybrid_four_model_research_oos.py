"""Four-way fixed-cohort prospective OOS; no new model, odds or outcomes.

Only after authenticated final scores exist, compare the same 37 fixtures:
original-formula alternative-input research; free Poisson V1; pooled Bayesian
league baseline V1; and team-venue Beta V2. Earliest vs later original
forecast lineage MUST be physically reconciled and match SHA-backed history
and exactly the same research probability. Never count duplicate snapshots.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_hybrid_original_dual_freeze_lineage import run as source_lineage
from tools.matrix_hybrid_three_model_research_oos import evaluate as three_evaluate
from tools.matrix_hybrid_team_venue_beta_v2 import (
    SCHEMA as V2_SCHEMA, MODEL as V2_MODEL, filename as v2_path)
from tools.matrix_hybrid_free_bayesian_v1 import validate_pairs_manifest
from tools.matrix_independent_free_poisson_oos import stamp

MANIFEST = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json")
OUT = Path("evidence/matrix_hybrid_elite/MATRIX_HYBRID_FOUR_MODEL_OOS_LAST.json")
SCHEMA = "MATRIX_HYBRID_FOUR_MODEL_RESEARCH_OOS_V1"
MODELS = ("original_formula_research", "independent_free_poisson",
          "hybrid_free_bayesian", "hybrid_team_venue_beta_v2")
MIN_LEAGUE = 30
MIN_POOLED = 200


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def v2_forecast(root: Path, pair: dict, now: datetime):
    file = v2_path(root, pair)
    if not file.exists():
        return None
    raw = file.read_bytes()
    require(64 <= len(raw) <= 150000 and raw.endswith(b"\n"),
            "TEAM_V2_FILE_INVALID")
    p = json.loads(raw)
    require(p.get("schema") == V2_SCHEMA and p.get("model_id") == V2_MODEL,
            "TEAM_V2_MODEL_CHANGED")
    kickoff = stamp(pair["event_start_at_utc"])
    require(str(p.get("physical_event_id")) == str(pair["physical_event_id"]) and
            str(p.get("competition_id")) == str(pair["competition_id"]) and
            p.get("provider") == "FOOTBALL_DATA_ORG" and
            stamp(p["event_start_at_utc"]) == kickoff,
            "TEAM_V2_SOURCE_EVENT_ID_MISMATCH")
    require(stamp(p["history_observed_at_utc"]) <
            stamp(p["forecast_frozen_at_utc"]) < kickoff and
            stamp(p["forecast_frozen_at_utc"]) <= now,
            "TEAM_V2_FORECAST_NOT_PROSPECTIVE")
    require(p.get("source_original_research_freeze_sha256") ==
            pair["original_freeze_sha256"] and
            p.get("source_poisson_research_freeze_sha256") ==
            pair["poisson_freeze_sha256"] and
            p.get("source_historical_payload_sha256") ==
            pair["common_history_raw_sha256"] and
            p.get("source_intake_file_sha256") ==
            pair["original_source_intake_sha256"] and
            p.get("source_shadow_file_sha256") ==
            pair["original_source_shadow_sha256"],
            "TEAM_V2_SHA_SOURCE_LINEAGE_MISMATCH")
    require(p.get("target_future_result_used") is False and
            p.get("research_only") is True and
            p.get("prospective_oos_certified") is False and
            p.get("original_official_p_matrix_certified") is False and
            p.get("automatic_model_promotion") is False and
            p.get("telegram_signal_authorized") is False and
            p.get("automatic_wagering") is False and
            p.get("real_money") == "BLOCKED",
            "TEAM_V2_ILLEGAL_MODEL_PROMOTION")
    policy = p.get("policy_fixed_before_observing_future_result") or {}
    require(policy.get("league_beta") == [3.0, 3.0] and
            policy.get("team_prior_matches") == 6.0 and
            policy.get("min_team_role_games") == 3 and
            policy.get("home_logit_weight") == 0.5 and
            policy.get("away_logit_weight") == 0.5,
            "TEAM_V2_POST_HOC_PARAMETER_CHANGE")
    prob = p.get("p_team_venue_over25")
    require(type(prob) in (int, float) and math.isfinite(prob) and
            0 < prob < 1 and
            prob == (p.get("probabilities") or {}).get("p_over25"),
            "TEAM_V2_INVALID_RESEARCH_PROBABILITY")
    return {"p": prob, "file_sha256": hashlib.sha256(raw).hexdigest(),
            "path": file.relative_to(root).as_posix()}


def score_pair(three_row: dict, v2: dict, original_lineage: dict):
    require(three_row["fixture_id"] == original_lineage["fixture_id"] and
            three_row["source_original_forecast_sha256"] ==
            original_lineage["selected_research_forecast_file_sha256"] and
            three_row["source_primary_settlement_original_forecast_sha256"] ==
            original_lineage["earliest_forecast_file_sha256"] and
            original_lineage["same_authenticated_source_history"] is True and
            original_lineage["same_formula_probability"] is True and
            original_lineage["one_physical_fixture_count"] == 1,
            "FOUR_MODEL_EARLIEST_FREEZE_LINEAGE_NOT_VERIFIED")
    y = three_row["outcome_over25"]
    require(type(y) is int and y in (0, 1), "OUTCOME_NOT_VALID_BINARY")
    prior = three_row["predictors"]
    require(set(prior) == set(MODELS[:-1]), "ORIGINAL_THREE_RESEARCH_MODELS_MISSING")
    p = v2["p"]
    values = {k: prior[k]["p_over25"] for k in MODELS[:-1]}
    values[MODELS[-1]] = p
    scores = {
        k: {
            "research_p": prob,
            "brier": (prob-y)**2,
            "logloss": -(y*math.log(prob)+(1-y)*math.log1p(-prob)),
        }
        for k,prob in values.items()
    }
    return {
        "fixture_id": three_row["fixture_id"],
        "provider_competition_id": three_row["competition_id"],
        "outcome": y,
        "source_provider_result_sha256": three_row["source_provider_final_sha256"],
        "source_settlement_sha256": three_row["source_settlement_sha256"],
        "source_primary_formula_sha256":
            original_lineage["earliest_forecast_file_sha256"],
        "source_secondary_formula_sha256":
            original_lineage["selected_research_forecast_file_sha256"],
        "source_poisson_sha256": three_row["source_poisson_forecast_sha256"],
        "source_bayesian_v1_sha256": three_row["source_bayesian_forecast_sha256"],
        "source_bayesian_v2_sha256": v2["file_sha256"],
        "physical_observation_increment": 1,
        "predictors": scores,
    }


def stats(rows):
    if not rows:
        return None
    n = len(rows)
    return {k: {
        "brier": round(sum(r["predictors"][k]["brier"] for r in rows)/n, 9),
        "logloss": round(sum(r["predictors"][k]["logloss"] for r in rows)/n, 9)}
        for k in MODELS}


def evaluate(root: Path, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    require(now.utcoffset() is not None, "AWARE_OOS_EVALUATION_CLOCK")
    now = now.astimezone(timezone.utc)
    manifest = json.loads((root / MANIFEST).read_bytes())
    pairs = validate_pairs_manifest(manifest)
    lineage = source_lineage(root)
    require(lineage["lineage_rejected_fixture_count"] == 0 and
            lineage["lineage_matched_fixture_count"] == len(pairs) and
            lineage["physical_fixture_count"] == len(pairs),
            "PRIMARY_AND_SECONDARY_ORIGINAL_SOURCE_LINEAGE_FAILED")
    by_lineage = {x["fixture_id"]:x for x in lineage["matched"]}
    three = three_evaluate(root, now)
    require(three["real_money"] == "BLOCKED" and
            three["telegram_signal_authorized"] is False and
            three["model_winner_authorized"] is False and
            three["original_official_p_matrix_present"] is False,
            "THREE_MODEL_RESULT_NOT_RESEARCH_ONLY")
    settled = {x["fixture_id"]:x for x in three["result_rows"]}
    require(len(settled) == len(three["result_rows"]),
            "THREE_MODEL_DUPLICATE_SETTLED_EVENT")
    completed, unlabelled, unfrozen, rejected, future = [], [], [], [], []
    for pair in pairs:
        fid = str(pair["physical_event_id"])
        try:
            v2 = v2_forecast(root, pair, now)
            kickoff = stamp(pair["event_start_at_utc"])
            if v2 is None:
                unfrozen.append({"fixture_id":fid,"state":"FUTURE_NOT_FROZEN"
                                if now < kickoff else "MISSED_NEVER_BACKFILL"})
                continue
            if now <= kickoff:
                future.append(fid)
                continue
            if fid not in settled:
                unlabelled.append(fid)
                continue
            completed.append(score_pair(settled[fid],v2,by_lineage[fid]))
        except (ValueError, OSError, KeyError, TypeError,
                json.JSONDecodeError) as err:
            rejected.append({"fixture_id":fid,"reason":str(err)[:145]})
    grouped = defaultdict(list)
    for row in completed:
        grouped[row["provider_competition_id"]].append(row)
    return {
        "schema": SCHEMA,
        "generated_at_utc": now.isoformat(),
        "status": "FOUR_RESEARCH_MODELS_NO_OFFICIAL_CERTIFICATION",
        "source_order": ["SOFASCORE","FLASHSCORE","FOOTBALL_DATA_ORG"],
        "physical_prelabeled_fixture_count": len(pairs),
        "verified_original_dual_freeze_lineages": len(by_lineage),
        "four_model_frozen_future_count": len(future),
        "four_model_missing_v2_forecasts": unfrozen,
        "four_model_awaiting_verified_final": unlabelled,
        "four_model_rejected": rejected,
        "three_model_upstream_rejected": len(three["three_model_rejected"]),
        "three_model_upstream_result_count":
            three["three_model_authenticated_settled_count"],
        "four_model_verified_settled_count": len(completed),
        "global_metrics": stats(completed),
        "league_metrics": [
            {"competition_id":cid, "n":len(rows),
             "minimum_30_reached":len(rows)>=MIN_LEAGUE,
             "scores":stats(rows)}
            for cid,rows in sorted(grouped.items())],
        "gate_pooled_200_reached": len(completed) >= MIN_POOLED,
        "settled_rows": completed,
        "original_p_matrix_official_probability_present": False,
        "model_superiority_claim_authorized": False,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--out",type=Path,default=OUT)
    a=p.parse_args()
    require(not ({"notifications", "telegram", "tennis_signals",
                  "daily_prematch_reports"} & set(a.out.parts)),
            "FOUR_MODEL_RESEARCH_MUST_NOT_WRITE_TO_SIGNALS")
    report=evaluate(a.root)
    dest=a.out if a.out.is_absolute() else a.root / a.out
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        old=json.loads(dest.read_bytes())
        if ({k:v for k,v in old.items() if k!="generated_at_utc"} ==
            {k:v for k,v in report.items() if k!="generated_at_utc"}):
            print(json.dumps({"unchanged":True,
                              "settled":report["four_model_verified_settled_count"],
                              "future":report["four_model_frozen_future_count"],
                              "real_money":"BLOCKED"}))
            return
    dest.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n",
                    encoding="utf-8")
    print(json.dumps({"four_model_settled":report["four_model_verified_settled_count"],
                      "future_frozen":report["four_model_frozen_future_count"],
                      "missing_v2":len(report["four_model_missing_v2_forecasts"]),
                      "rejected":len(report["four_model_rejected"]),
                      "winner_authorized":False,"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
