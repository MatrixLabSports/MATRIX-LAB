"""Research-only, exact frozen prediction scoring of source-attested kickoff drift.

The original six period market result counters stay at 501 until independent
admission policy is approved. Brier and LogLoss can be combined by sample-size
weight; ECE cannot be reconstructed without original per-observation bins.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

from tools.api_football_prospective_api_settlement import _load_ledger
from tools.matrix_13_cohort_independent_settlement import validated_ledger
from tools.matrix_13_market_exact_cohort_calibration import (
    PERIOD_LANES, _prediction_and_targets, statistics, utc,
    build, probability,
)
from tools.matrix_13_rescheduled_period_receipt_attestation import (
    evaluate, FROZEN, ORIGINAL, INDEPENDENT, PORTFOLIO, REGISTRY, RAW,
)

SCHEMA = "MATRIX_13_PERIOD_RESCHEDULED_RESEARCH_SHADOW_SCORING_V1"


def shadow_score(baseline: dict, attestation: dict,
                 portfolio: list[dict]) -> dict:
    by_lane = {x["market_key"]: x for x in baseline["lanes"]
               if x["market_key"] in PERIOD_LANES}
    if len(by_lane) != 6:
        raise ValueError("SHADOW_REQUIRES_SIX_PERIOD_LANES")
    candidates = {
        str(x["fixture_id"]): x for x in attestation["rows"]
        if x["status"] == "RESEARCH_ATTESTATION_NOT_ADMITTED_TO_CALIBRATION"
    }
    if len(candidates) != attestation["original_source_qualified_candidates_not_promoted"]:
        raise ValueError("SHADOW_DUPLICATE_SOURCE_ATTESTATION")
    by_market: dict[str, dict[str, dict]] = {k: {} for k in PERIOD_LANES}
    for row in portfolio:
        lane = row.get("market_lane")
        fid = str(row.get("fixture_id") or row.get("event_id") or "")
        if lane not in PERIOD_LANES or fid not in candidates:
            continue
        if fid in by_market[lane]:
            raise ValueError("SHADOW_DUPLICATE_PROSPECTIVE_FIXTURE")
        by_market[lane][fid] = row
    reports = []
    for lane in sorted(PERIOD_LANES):
        original = by_lane[lane]
        if original.get("exact_cohort_final_verified") is None:
            raise ValueError("SHADOW_ORIGINAL_SETTLEMENT_COUNT_MISSING")
        sample = {}
        for fid, candidate in candidates.items():
            row = by_market[lane].get(fid)
            if row is None:
                raise ValueError("SHADOW_MISSING_FROZEN_FORECAST")
            if (row.get("record_type") != "PROSPECTIVE_PREMATCH_FREEZE"
                or row.get("prospective_admitted") is not True
                or row.get("real_money") != "BLOCKED"
                or row.get("automatic_wagering") is not False
                or row.get("odds_used_to_generate_probability") is not False
                or row.get("target_outcome") is not None
                or row.get("settlement") is not None
                or not row.get("prediction_snapshot_sha256")
                or not isinstance(row.get("prediction"), dict)
                or utc(row["event_start_utc"]) != utc(candidate["frozen_scheduled_kickoff_utc"])
                or utc(row["freeze_timestamp_utc"]) != utc(candidate["original_prediction_freeze_utc"])
                or utc(row["freeze_timestamp_utc"]) >= utc(candidate["source_final_fixture_kickoff_utc"])):
                raise ValueError("SHADOW_UNTRUSTED_PROSPECTIVE_FORECAST_LINEAGE")
            hg, ag = candidate["original_final_goals"]["home"], candidate["original_final_goals"]["away"]
            hh, ah = candidate["original_explicit_halftime_goals"]["home"], candidate["original_explicit_halftime_goals"]["away"]
            if not all(type(k) is int and k >= 0 for k in [hg,ag,hh,ah]) or hh>hg or ah>ag:
                raise ValueError("SHADOW_UNTRUSTED_GOAL_OUTCOME")
            result = {"fulltime_home_goals": hg, "fulltime_away_goals": ag}
            for k,(p,outcome) in _prediction_and_targets(lane,row,result,halftime=(hh,ah)).items():
                probability(p)
                sample.setdefault(k,[]).append((p,outcome))
        projected = {}
        for name,values in sorted(sample.items()):
            addition = statistics([v[0] for v in values],[v[1] for v in values])
            historic = original["calibration_metrics_unpromoted"].get(name)
            if (not isinstance(historic, dict)
                or historic["n"] != original["exact_cohort_final_verified"]
                or len(values) != len(candidates)):
                raise ValueError("SHADOW_NON_MATCHING_ORIGINAL_METRIC_COHORT")
            n0, n1 = historic["n"], addition["n"]
            projected[name] = {
                "research_combined_n": n0+n1,
                "research_combined_brier": (historic["brier"]*n0 + addition["brier"]*n1)/(n0+n1),
                "research_combined_log_loss": (historic["log_loss"]*n0 + addition["log_loss"]*n1)/(n0+n1),
                "research_combined_ece": None,
                "reason_ece_omitted": "UNAVAILABLE_ORIGINAL_PER_EVENT_CALIBRATION_BINS",
                "extra_verified_original_source_n_research_only": n1,
                "original_metrics_remain_unchanged": True,
            }
        reports.append({
            "market_key": lane,
            "original_formal_exact_final_count": original["exact_cohort_final_verified"],
            "research_only_attested_extra": len(candidates),
            "research_only_potential_exact_final_count": (
                original["exact_cohort_final_verified"] + len(candidates)),
            "research_only_proper_scoring": projected,
            "eligible_for_formal_gate600": False,
            "promoted": False,
        })
    return {
        "schema": SCHEMA,
        "status": "SOURCE_ATTESTED_SHADOW_ONLY_NO_FORMAL_COHORT_CHANGE",
        "research_source_candidate_fixture_ids": sorted(candidates),
        "research_source_candidate_count": len(candidates),
        "six_period_markets": reports,
        "original_formal_cohort_mutated": False,
        "added_to_42_lane_prospective_ledger": 0,
        "added_to_canonical_final_settlement": 0,
        "retrospective_model_parameter_refit": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    root = a.root
    sourcepaths = [REGISTRY, PORTFOLIO, FROZEN, ORIGINAL, INDEPENDENT]
    reg = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    portfolio = [
        json.loads(x) for x in (root / PORTFOLIO).read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    frozen = json.loads((root / FROZEN).read_text(encoding="utf-8"))
    canonical = _load_ledger(root / ORIGINAL)
    independent = validated_ledger(root / INDEPENDENT)
    base = build(reg, portfolio, canonical, raw_dir=root / RAW,
                 secondary_settlements=independent)
    att = evaluate(reg, portfolio, frozen, canonical, independent, root / RAW)
    result = shadow_score(base,att,portfolio)
    result["source_immutable_sha256"] = {
        str(p): hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sourcepaths
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "extra_research_only": result["research_source_candidate_count"],
        "counts": {x["market_key"]: x["research_only_potential_exact_final_count"]
                   for x in result["six_period_markets"]},
    },sort_keys=True))


if __name__ == "__main__":
    main()
