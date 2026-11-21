"""Read-only reconciliation of 42 market freezes versus 13 exact final cohorts.

A prospective freeze is NOT a settled match. A formal proper-scoring PASS is
NOT production authorization; never promotes markets or modifies probabilities.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path("evidence")
REG = ROOT / "market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json"
EXACT = ROOT / "governance/MATRIX_13_MARKET_EXACT_COHORT_CALIBRATION_LAST.json"
SCORE = ROOT / "governance/MATRIX_13_MARKET_FORMAL_SCORING_GATE_LAST.json"

def reconcile(reg: dict, exact: dict, score: dict) -> dict:
    lanes = reg.get("lanes")
    cohorts = exact.get("lanes")
    scores = score.get("lanes")
    if (not isinstance(lanes, dict) or len(lanes) != 42
        or not isinstance(cohorts, list) or len(cohorts) != 13
        or not isinstance(scores, list) or len(scores) != 13
        or exact.get("summary", {}).get("markets_targeted") != 13
        or exact.get("status") != "RESEARCH_AUDIT_NO_PROMOTION"
        or score.get("status") != "PASS_READ_ONLY_NO_PROMOTION"):
        raise ValueError("RECONCILIATION_SOURCE_SCHEMA_OR_COUNTS_INVALID")
    e = {x["market_key"]: x for x in cohorts}
    s = {x["market_key"]: x for x in scores}
    if len(e) != 13 or len(s) != 13 or set(e) != set(s) or not set(e).issubset(lanes):
        raise ValueError("RECONCILIATION_MARKET_KEYS_NOT_IDENTICAL")
    rows = []
    for key in sorted(e):
        r, c, g = lanes[key], e[key], s[key]
        frozen = r["prospective_unique_count"]
        valid = c["prospective_valid_freezes"]
        final = c["exact_cohort_final_verified"]
        if (type(frozen) is not int or type(valid) is not int or type(final) is not int
            or frozen < 600 or frozen != valid or not 0 <= final <= frozen
            or g["exact_verified_ft_count"] != final
            or bool(g["eligible_to_test"]) != (final >= 600)
            or g.get("promoted") is not False
            or c.get("telegram_authorized_by_audit") is not False):
            raise ValueError("RECONCILIATION_PROSPECTIVE_VS_SETTLED_CONFLICT")
        metrics = g.get("proper_scoring")
        if final >= 600:
            if key in ("MATCH_RESULT_1X2", "DOUBLE_CHANCE_1X",
                       "DOUBLE_CHANCE_X2", "DOUBLE_CHANCE_12", "TOTAL_GOALS_OVER_UNDER"):
                if (not isinstance(metrics, dict)
                    or g.get("reference_evaluable_count") != final):
                    raise ValueError("RECONCILIATION_MISSING_FORMAL_METRICS")
        elif metrics:
            raise ValueError("RECONCILIATION_PREMATURE_SCORING")
        delta_brier = metrics.get("delta_brier_challenger_minus_poisson") if metrics else None
        delta_logloss = metrics.get("delta_log_loss_challenger_minus_poisson") if metrics else None
        if (delta_brier is not None and delta_logloss is not None
            and delta_brier < 0 and delta_logloss < 0):
            result = "PASS_PROPER_SCORING_ONLY_NOT_PRODUCTION"
        elif metrics:
            result = "NO_GO_PROPER_SCORING"
        else:
            result = "HOLD_AWAIT_EXACT_SETTLEMENT"
        rows.append({
            "lane": key, "name": r["display_name"],
            "prospective_freezes": frozen,
            "independently_verified_final_results": final,
            "unsettled_in_exact_cohort": frozen - final,
            "additional_certified_finals_required_for_600": max(0, 600 - final),
            "official_formal_verdict": g["verdict"],
            "proper_scoring_status": result,
            "delta_brier_challenger_minus_poisson": delta_brier,
            "delta_logloss_challenger_minus_poisson": delta_logloss,
            "production_authorized": False,
            "model_promoted": False,
        })
    count600 = sum(x["independently_verified_final_results"] >= 600 for x in rows)
    if (count600 != exact["summary"]["markets_with_600_exact_final"]
        or count600 != score["summary"]["gate600_final_count"]
        or sum(x["proper_scoring_status"] != "HOLD_AWAIT_EXACT_SETTLEMENT" for x in rows)
            != score["summary"]["formal_core_scoring_comparisons_completed"]):
        raise ValueError("RECONCILIATION_SUMMARY_DIVERGENCE")
    return {
        "schema": "MATRIX_13_MARKET_EXACT_FINAL_GAPS_RECONCILED_V1",
        "status": "PASS_READ_ONLY_NO_PROMOTION",
        "source_registry_as_of_utc": reg["generated_at_utc"],
        "formal_score_as_of_utc": score["generated_at_utc"],
        "summary": {
            "market_lanes_total": 42, "advanced_market_lanes": 13,
            "exact_final_600_achieved": count600,
            "exact_final_below_600": 13-count600,
            "formal_dual_metric_pass_not_promotion": sum(
                x["proper_scoring_status"] == "PASS_PROPER_SCORING_ONLY_NOT_PRODUCTION" for x in rows),
            "automatically_promoted": 0,
        },
        "entries": rows,
        "telegram_authorized": False,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    sources = [REG, EXACT, SCORE]
    blobs = [(args.root / p).read_bytes() for p in sources]
    result = reconcile(*(json.loads(b) for b in blobs))
    result["source_sha256"] = {
        str(p): hashlib.sha256(b).hexdigest() for p,b in zip(sources,blobs)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False,
                                      indent=2, sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result["summary"],sort_keys=True))

if __name__ == "__main__":
    main()
