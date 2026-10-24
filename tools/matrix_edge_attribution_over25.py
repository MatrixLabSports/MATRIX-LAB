from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SOURCE = Path("evidence/api_football/daily_prematch_reports/2026-10-16/over25_shadow_ev/MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV.json")
OUT = Path("evidence/api_football/edge_attribution/2026-10-16/MATRIX_EDGE_ATTRIBUTION_OVER25_V2.json")


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build(source: Mapping[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    rows = source.get("all_rows")
    if not isinstance(rows, list):
        rows = source.get("bet_shadow")
    if not isinstance(rows, list):
        raise ValueError("ATTRIBUTION_SOURCE_ROWS_MISSING")

    out_rows = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("p_over_2_5") is None:
            continue
        offer = row.get("best_policy_offer")
        p = float(row["p_over_2_5"])
        fair_odds = 1.0 / p
        if isinstance(offer, Mapping):
            odds = float(offer["decimal_odds"])
            break_even = 1.0 / odds
            ev = p * odds - 1.0
            price_edge_ratio = odds / fair_odds - 1.0
        else:
            odds = None
            break_even = None
            ev = None
            price_edge_ratio = None
        trace = row.get("over25_feature_trace")
        drivers = None
        driver_status = "NOT_AVAILABLE_IN_SOURCE_TRACE"
        reconstructed = None
        if isinstance(trace, Mapping) and trace.get("trace_schema") == "MATRIX_OVER25_FEATURE_TRACE_V1":
            reconstructed = float(trace["reconstructed_probability"])
            drivers = [
                {
                    "driver": "POISSON_OVER25",
                    "input_probability": float(trace["poisson_probability"]),
                    "weight": float(trace["poisson_weight"]),
                    "raw_logit": float(trace["poisson_logit"]),
                    "weighted_logit_contribution": float(trace["poisson_weighted_logit_contribution"]),
                    "direction": "UP" if float(trace["poisson_weighted_logit_contribution"]) > 0 else ("DOWN" if float(trace["poisson_weighted_logit_contribution"]) < 0 else "NEUTRAL"),
                },
                {
                    "driver": "GROUP_BASELINE_OVER25",
                    "input_probability": float(trace["baseline_probability"]),
                    "weight": float(trace["baseline_weight"]),
                    "raw_logit": float(trace["baseline_logit"]),
                    "weighted_logit_contribution": float(trace["baseline_weighted_logit_contribution"]),
                    "direction": "UP" if float(trace["baseline_weighted_logit_contribution"]) > 0 else ("DOWN" if float(trace["baseline_weighted_logit_contribution"]) < 0 else "NEUTRAL"),
                },
                {
                    "driver": "INTERCEPT",
                    "weight": 1.0,
                    "weighted_logit_contribution": float(trace["intercept_logit_contribution"]),
                    "direction": "UP" if float(trace["intercept_logit_contribution"]) > 0 else ("DOWN" if float(trace["intercept_logit_contribution"]) < 0 else "NEUTRAL"),
                },
            ]
            driver_status = "AVAILABLE_REAL_ENGINE_TRACE"
        out_rows.append({
            "fixture_id": str(row["fixture_id"]),
            "match": row.get("match"),
            "kickoff_utc": row.get("kickoff_utc"),
            "market": "OVER_2_5",
            "p_matrix": p,
            "fair_decimal_odds": fair_odds,
            "execution_house": offer.get("bookmaker_name") if isinstance(offer, Mapping) else None,
            "execution_house_key": offer.get("house_key") if isinstance(offer, Mapping) else None,
            "quoted_decimal_odds": odds,
            "break_even_probability": break_even,
            "edge_probability_points": ((p - break_even) * 100.0) if break_even is not None else None,
            "expected_value": ev,
            "price_edge_ratio": price_edge_ratio,
            "quote_evidence_sha256": offer.get("quote_evidence_sha256") if isinstance(offer, Mapping) else None,
            "source_raw_sha256": offer.get("raw_sha256") if isinstance(offer, Mapping) else row.get("raw_sha256"),
            "odds_captured_at_utc": offer.get("odds_captured_at_utc") if isinstance(offer, Mapping) else row.get("odds_captured_at_utc"),
            "provider_quote_updated_at_utc": offer.get("provider_quote_updated_at_utc") if isinstance(offer, Mapping) else None,
            "edge_attribution": {
                "model_probability_component": p,
                "market_break_even_component": break_even,
                "measurable_probability_edge": (p - break_even) if break_even is not None else None,
                "feature_level_drivers": drivers,
                "feature_level_driver_status": driver_status,
                "feature_trace_space": "LOGIT" if drivers is not None else None,
                "reconstructed_probability": reconstructed,
                "interpretation": "Model-component contributions are reported exactly in the logit space used by the frozen engine; executable price remains post-probability."
            },
            "protections": {
                "odds_used_to_generate_probability": False,
                "feature_contributions_invented": False,
                "p_matrix_modified": False,
                "real_money": "BLOCKED"
            }
        })

    out_rows.sort(key=lambda x: (x["expected_value"] is None, -(x["expected_value"] or -999.0), x["fixture_id"]))
    artifact = {
        "schema": "MATRIX_EDGE_ATTRIBUTION_OVER25_V2",
        "generated_at_utc": generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_artifact": SOURCE.as_posix(),
        "source_artifact_sha256_without_external_metadata": _sha(source),
        "market": "OVER_2_5",
        "attribution_scope": "MODEL_COMPONENT_LOGIT_AND_PRICE_EDGE",
        "row_count": len(out_rows),
        "feature_trace_available_count": sum(1 for x in out_rows if x["edge_attribution"]["feature_level_driver_status"] == "AVAILABLE_REAL_ENGINE_TRACE"),
        "priced_row_count": sum(1 for x in out_rows if x["quoted_decimal_odds"] is not None),
        "rows": out_rows,
        "governance": {
            "p_matrix_is_input_not_modified": True,
            "odds_are_post_probability": True,
            "feature_attribution_requires_future_engine_trace": False,
            "feature_attribution_source": "FROZEN_ENGINE_LOGIT_COMPONENT_TRACE",
            "no_synthetic_drivers": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED"
        }
    }
    artifact["artifact_sha256"] = _sha({k:v for k,v in artifact.items() if k != "artifact_sha256"})
    return artifact


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    artifact = build(source)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "row_count": artifact["row_count"],
        "artifact_sha256": artifact["artifact_sha256"],
        "real_money": artifact["governance"]["real_money"]
    }, sort_keys=True))


if __name__ == "__main__":
    main()
