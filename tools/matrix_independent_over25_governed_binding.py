"""Bind independent fixture discovery to existing governed Over 2.5 scores.

Strictly read-only for the signal pipeline: this is an auditable handoff, NOT
an alternative probability model. Scoring must come from a separately certified
market-scoped engine; fixture calendars alone never supply model features.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

SCHEMA = "MATRIX_INDEPENDENT_OVER25_GOVERNED_BINDING_V1"
PROMOTION = Path("evidence/api_football/governance/over_2_5_p_matrix_promotion.json")


def bind(discovery: dict, scores: dict, promotion: dict) -> dict:
    allowed = (
        promotion.get("market") == "OVER_2_5"
        and promotion.get("promotion_status") == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY"
        and promotion.get("engine_executable_for_p_matrix") is True
        and promotion.get("promotion_scope") == "MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY"
        and (promotion.get("protections") or {}).get("real_money") == "BLOCKED"
        and (promotion.get("protections") or {}).get("automatic_wagering") is False
    )
    if discovery.get("schema") != "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1":
        raise ValueError("UNTRUSTED_DISCOVERY_SCHEMA")
    if scores.get("schema") != "MATRIX_GOVERNED_OVER25_SCORE_EXPORT_V1":
        raise ValueError("UNTRUSTED_SCORE_EXPORT_SCHEMA")
    fixtures = discovery.get("fixtures")
    rows = scores.get("rows")
    if not isinstance(fixtures, list) or not isinstance(rows, list):
        raise ValueError("ROWS_REQUIRED")
    scored = {}
    duplicates = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (row.get("home"), row.get("away"), row.get("kickoff_utc"))
        if key in scored:
            duplicates.add(key)
        scored[key] = row
    output = []
    rejected = []
    for fixture in fixtures:
        key = (fixture.get("home"), fixture.get("away"), fixture.get("kickoff_utc"))
        row = scored.get(key)
        reason = None
        if not allowed:
            reason = "MARKET_PROMOTION_INVALID"
        elif key in duplicates:
            reason = "DUPLICATE_SCORE_IDENTITY"
        elif row is None:
            reason = "NO_GOVERNED_SCORE_FOR_FIXTURE"
        elif row.get("market") != "OVER_2_5" or row.get("governance_status") != "FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY":
            reason = "SCORE_NOT_GOVERNED"
        elif row.get("engine_id") != "calibrated_log_pool_v1_over_2_5":
            reason = "ENGINE_ID_MISMATCH"
        elif row.get("frozen_parameters") != {"a": 0.6, "b": 0.0, "c": 0.4}:
            reason = "FROZEN_PARAMETERS_MISMATCH"
        elif row.get("odds_used_to_generate_probability") is not False or row.get("target_outcome_used") is not False:
            reason = "PROBABILITY_PROVENANCE_UNSAFE"
        elif not isinstance(row.get("model_evidence_path"), str) or not row["model_evidence_path"].strip():
            reason = "MODEL_EVIDENCE_MISSING"
        elif row.get("fixture_binding_verified") is not True or row.get("source_freeze_verified") is not True:
            reason = "FIXTURE_BINDING_UNVERIFIED"
        else:
            p = row.get("p_matrix")
            if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 < p < 1:
                reason = "INVALID_P_MATRIX"
        if reason:
            rejected.append({"home": key[0], "away": key[1], "reason": reason})
            continue
        output.append({
            "home": key[0], "away": key[1], "kickoff_utc": key[2],
            "p_matrix": row["p_matrix"],
            "model_evidence_path": row["model_evidence_path"],
            "physical_quote_verified": False, "decimal_odds": None,
            "ev": None, "signal_generation_authorized": False,
        })
    return {
        "schema": SCHEMA, "status": "GOVERNED_SCORE_BINDING_ONLY_NO_QUOTES_NO_SIGNAL",
        "rows": output, "rejected": rejected,
        "signal_generation_authorized": False,
        "provider_network_calls": 0, "telegram_messages_sent": 0,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--scores", required=True)
    parser.add_argument("--promotion", default=str(PROMOTION))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if "daily_prematch_reports" in out.parts or "tennis_signals" in out.parts:
        raise SystemExit("BINDING_CANNOT_WRITE_SIGNAL_CANDIDATES")
    load = lambda path: json.loads(Path(path).read_text(encoding="utf-8"))
    result = bind(load(args.discovery), load(args.scores), load(args.promotion))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "bound": len(result["rows"]), "rejected": len(result["rejected"])}))


if __name__ == "__main__":
    main()
