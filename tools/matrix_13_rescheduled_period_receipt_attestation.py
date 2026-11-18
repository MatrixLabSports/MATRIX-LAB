"""Read-only hash-bound event-time drift attestation for original 13-market period labels.

A provider's final fixture timestamp may differ from the *original frozen*
scheduled kickoff. This program detects strict, high-integrity candidates but
does NOT silently rewrite the canonical kickoff, infer rescheduling reasons,
modify the original calibrated model, count labels, or authorize signals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_prospective_api_settlement import _load_ledger
from tools.matrix_13_cohort_independent_settlement import validated_ledger
from tools.matrix_13_period_original_receipt_research import (
    inspect, PORTFOLIO, REGISTRY, ORIGINAL, INDEPENDENT, RAW,
)
from tools.matrix_13_market_exact_cohort_calibration import utc

FROZEN = Path("evidence/api_football/prospective_market_freeze/freeze.json")
SCHEMA = "MATRIX_13_RESCHEDULED_HALFTIME_RECEIPT_RESEARCH_ATTESTATION_V1"


def verify_original_event_time_drift(
    fid: str, immutable: dict, result: dict, rawdir: Path
) -> dict:
    """Require original identity, pre-start freeze, hash, FT and explicit period scores."""
    def excluded(reason: str) -> dict:
        return {"fixture_id": fid, "status": "NOT_ADMITTED", "blocker": reason}
    if str(immutable.get("fixture_id")) != fid or str(result.get("fixture_id")) != fid:
        return excluded("ORIGINAL_FIXTURE_ID_MISMATCH")
    try:
        frozen_kickoff = utc(immutable["kickoff_utc"])
        frozen_at = utc(immutable["freeze_at_utc"])
        canonical_kickoff = utc(result["kickoff_utc"])
        canonical_at = utc(result["freeze_at_utc"])
        settled = utc(result["settled_at_utc"])
    except (KeyError, ValueError, TypeError):
        return excluded("ORIGINAL_IMMUTABLE_TIME_INVALID")
    if (frozen_kickoff != canonical_kickoff or frozen_at != canonical_at
        or frozen_at >= frozen_kickoff):
        return excluded("ORIGINAL_PREMATCH_LINEAGE_CONFLICT")
    if (result.get("terminal_status") != "FT"
        or result.get("result_source_provider") != "api_football"
        or not isinstance(immutable.get("input_sha256"), str)
        or len(immutable["input_sha256"]) != 64):
        return excluded("ORIGINAL_FINAL_OR_FEATURE_PROVENANCE_INVALID")
    path = rawdir / f"fixture_{fid}.bin"
    if not path.is_file():
        return excluded("SOURCE_ARCHIVE_NOT_FOUND")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != result.get("result_payload_sha256"):
        return excluded("SOURCE_ARCHIVE_HASH_MISMATCH")
    try:
        payload = json.loads(raw)
        if (payload.get("errors") not in ([], {}, None)
            or payload.get("results") != 1
            or not isinstance(payload.get("response"), list)
            or len(payload["response"]) != 1):
            return excluded("SOURCE_RESPONSE_NOT_UNIQUE_OR_HAS_ERRORS")
        match = payload["response"][0]
        fixture = match.get("fixture") or {}
        teams = match.get("teams") or {}
        source_start = utc(fixture["date"])
        if (str(fixture.get("id")) != fid
            or (fixture.get("status") or {}).get("short") != "FT"):
            return excluded("SOURCE_FIXTURE_ID_OR_STANDARD_STATUS_MISMATCH")
        if (str((teams.get("home") or {}).get("id")) != str(immutable["home_team_id"])
            or str((teams.get("away") or {}).get("id")) != str(immutable["away_team_id"])):
            return excluded("SOURCE_TEAMS_NOT_FROZEN_IDENTITY")
        if source_start == frozen_kickoff:
            return excluded("NOT_AN_EVENT_TIME_DRIFT")
        if frozen_at >= min(source_start, frozen_kickoff) or settled < source_start:
            return excluded("FORECAST_NOT_BEFORE_BOTH_STARTS_OR_SETTLED_PRESTART")
        score = match.get("score") or {}
        half = score.get("halftime") or {}
        full = score.get("fulltime") or {}
        hh, ah = half.get("home"), half.get("away")
        hg, ag = full.get("home"), full.get("away")
        if (not all(type(x) is int and x >= 0 for x in [hh, ah, hg, ag])
            or hh > hg or ah > ag):
            return excluded("EXPLICIT_HALFTIME_OR_FINAL_SCORE_MISSING_OR_INVALID")
        if ((hg, ag) != (result["fulltime_home_goals"], result["fulltime_away_goals"])
            or (match.get("goals") or {}).get("home") != hg
            or (match.get("goals") or {}).get("away") != ag):
            return excluded("FINAL_SCORE_NOT_EQUAL_TO_ORIGINAL_HASHCHAIN")
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        return excluded("SOURCE_DATA_SCHEMA_OR_TIMESTAMP_INVALID")
    return {
        "fixture_id": fid,
        "status": "RESEARCH_ATTESTATION_NOT_ADMITTED_TO_CALIBRATION",
        "frozen_scheduled_kickoff_utc": frozen_kickoff.isoformat(),
        "source_final_fixture_kickoff_utc": source_start.isoformat(),
        "original_prediction_freeze_utc": frozen_at.isoformat(),
        "source_final_receipt_captured_utc": settled.isoformat(),
        "source_minus_frozen_start_minutes": round(
            (source_start-frozen_kickoff).total_seconds()/60.0, 3
        ),
        "original_source_receipt_sha256": sha,
        "original_feature_sha256": immutable["input_sha256"],
        "original_frozen_home_team_id": str(immutable["home_team_id"]),
        "original_frozen_away_team_id": str(immutable["away_team_id"]),
        "source_home_team_id": str(teams["home"]["id"]),
        "source_away_team_id": str(teams["away"]["id"]),
        "original_final_goals": {"home": hg, "away": ag},
        "original_explicit_halftime_goals": {"home": hh, "away": ah},
        "prediction_frozen_before_both_kickoffs": True,
        "original_model_parameters_changed": False,
        "cross_provider_event_time_confirmed": False,
        "formal_period_cohort_admission": False,
    }


def evaluate(registry: dict, portfolio: list[dict], frozen: dict, canonical: list[dict],
             independent: list[dict], rawdir: Path) -> dict:
    source_report = inspect(registry, portfolio, canonical, independent, rawdir=rawdir)
    exact_ids = [
        row["fixture_id"] for row in source_report["source_problem_details"]
        if row["original_receipt_issue"] == "ORIGINAL_FIXTURE_DATE_MISMATCH"
    ]
    frozen_by_id = {str(r["fixture_id"]): r for r in frozen["rows"]}
    canonical_by_id = {str(r["fixture_id"]): r for r in canonical}
    if len(frozen_by_id) != len(frozen["rows"]) or len(canonical_by_id) != len(canonical):
        raise ValueError("SOURCE_DUPLICATE_CANONICAL_EVENT")
    rows = []
    for fid in sorted(set(exact_ids)):
        if fid not in frozen_by_id or fid not in canonical_by_id:
            raise ValueError("SOURCE_MISSING_ORIGINAL_FREEZE_OR_FINAL")
        rows.append(verify_original_event_time_drift(
            fid, frozen_by_id[fid], canonical_by_id[fid], rawdir))
    ready = [r for r in rows if r["status"] == "RESEARCH_ATTESTATION_NOT_ADMITTED_TO_CALIBRATION"]
    denied = [r for r in rows if r["status"] == "NOT_ADMITTED"]
    return {
        "schema": SCHEMA,
        "status": "PASS_RESEARCH_ONLY_ORIGINAL_SOURCE_EVENT_TIME_DRIFT",
        "original_date_mismatch_fixture_count": len(set(exact_ids)),
        "original_source_qualified_candidates_not_promoted": len(ready),
        "source_blocked": len(denied),
        "source_rejected_reasons": dict(Counter(r["blocker"] for r in denied)),
        "rows": rows,
        "original_501_period_settlement_labels_not_modified": True,
        "new_formal_period_labels_written": 0,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "telegram_signal_authorized": False,
        "model_parameters_changed": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    root = a.root
    reg = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    portfolio = [
        json.loads(x) for x in (root / PORTFOLIO).read_text(encoding="utf-8").splitlines()
        if x.strip()
    ]
    frozen = json.loads((root / FROZEN).read_text(encoding="utf-8"))
    canonical = _load_ledger(root / ORIGINAL)
    independent = validated_ledger(root / INDEPENDENT)
    result = evaluate(reg, portfolio, frozen, canonical, independent, root / RAW)
    result["source_immutable_sha256"] = {
        str(p): hashlib.sha256((root / p).read_bytes()).hexdigest()
        for p in [REGISTRY, PORTFOLIO, FROZEN, ORIGINAL, INDEPENDENT]
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "date_mismatch": result["original_date_mismatch_fixture_count"],
        "eligible_research_only": result["original_source_qualified_candidates_not_promoted"],
        "source_blocked": result["source_blocked"],
        "formal_added": result["new_formal_period_labels_written"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
