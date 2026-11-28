"""Read-only diagnostic of original API-Football half-time receipts for 13 market cohorts.

Checks the original pre-match identity and the archived result hashes; never
imputes half-time from FT, goal incidents, odds, ESPN final scores, or future
information. Does not append to any ledger or promote models.
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
from tools.matrix_13_market_exact_cohort_calibration import (
    PERIOD_LANES, verified_half_time, utc, build,
)

PORTFOLIO = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
REGISTRY = Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
ORIGINAL = Path("evidence/api_football/prospective_market_freeze/settlement_ledger.jsonl")
INDEPENDENT = Path("evidence/football_cohort_recovery/MATRIX_INDEPENDENT_VERIFIED_FT_LEDGER.jsonl")
RAW = Path("evidence/api_football/prospective_market_freeze/settlement_raw")
SCHEMA = "MATRIX_13_PERIOD_ORIGINAL_HALFTIME_RECEIPT_DIAGNOSTIC_V1"


def quality_detail(fid: str, receipt: dict, rawdir: Path) -> dict:
    """Classify existing, hash-bound source fields without creating a goal label."""
    path = rawdir / f"fixture_{fid}.bin"
    if not path.is_file():
        return {"classification": "MISSING_ORIGINAL_MATCH_RECEIPT",
                "source_sha256_matches": False}
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != receipt.get("result_payload_sha256"):
        return {"classification": "ORIGINAL_MATCH_RECEIPT_SHA256_MISMATCH",
                "source_sha256_matches": False}
    try:
        payload = json.loads(raw)
        resp = payload["response"]
        match = resp[0]
        fixture = match.get("fixture") or {}
        raw_kickoff = fixture.get("date")
        frozen_kickoff = receipt.get("kickoff_utc")
        if (raw_kickoff is not None and frozen_kickoff is not None):
            source_dt = utc(raw_kickoff)
            frozen_dt = utc(frozen_kickoff)
            kickoff_drift_minutes = round((source_dt-frozen_dt).total_seconds()/60.0, 3)
        else:
            kickoff_drift_minutes = None
        fixture_id_in_receipt_matches = str(fixture.get("id")) == fid
        provider_ft_status_matches = (fixture.get("status") or {}).get("short") == "FT"
        half = (match.get("score") or {}).get("halftime") or {}
        full = (match.get("score") or {}).get("fulltime") or {}
        half_vals = [half.get("home"), half.get("away")]
        full_vals = [full.get("home"), full.get("away")]
    except (TypeError, ValueError, KeyError, IndexError, AttributeError):
        return {"classification": "ARCHIVED_RAW_SCHEMA_UNREADABLE",
                "source_sha256_matches": True}
    if any(v is None for v in half_vals):
        kind = "PROVIDER_HALFTIME_NULL_OR_MISSING"
    elif any(type(v) is not int or v < 0 for v in half_vals):
        kind = "PROVIDER_HALFTIME_WRONG_TYPE_OR_NEGATIVE"
    elif any(v is None for v in full_vals):
        kind = "PROVIDER_FULLTIME_NULL_OR_MISSING"
    elif any(type(v) is not int or v < 0 for v in full_vals):
        kind = "PROVIDER_FULLTIME_WRONG_TYPE_OR_NEGATIVE"
    else:
        kind = "PRESENT_BUT_REQUIRES_INDEPENDENT_IDENTITY_VALIDATION"
    return {
        "classification": kind,
        "source_sha256_matches": True,
        "halftime_fields_present_non_null": all(v is not None for v in half_vals),
        "fulltime_fields_present_non_null": all(v is not None for v in full_vals),
        "raw_fixture_id_equals_frozen_id": fixture_id_in_receipt_matches,
        "raw_status_is_standard_ft": provider_ft_status_matches,
        "raw_kickoff_minus_frozen_kickoff_minutes": kickoff_drift_minutes,
        "not_a_usable_halftime_label": True,
    }


def inspect(registry: dict, portfolio: list[dict], canonical: list[dict],
            independent: list[dict], *, rawdir: Path) -> dict:
    """Compare six period cohorts and isolate unique fixture-level blockers."""
    baseline = build(registry, portfolio, canonical, raw_dir=rawdir,
                     secondary_settlements=independent)
    expected = {x["market_key"]: x for x in baseline["lanes"] if x["market_key"] in PERIOD_LANES}
    if len(expected) != 6:
        raise ValueError("MISSING_SIX_PERIOD_LANES")
    lookup = {}
    for record in canonical + independent:
        fid = str(record.get("fixture_id") or "")
        if not fid or fid in lookup:
            raise ValueError("DUPLICATE_OR_EMPTY_RESULT_FIXTURE")
        lookup[fid] = record
    all_groups = {}
    for row in portfolio:
        if row.get("market_lane") not in PERIOD_LANES:
            continue
        fid = str(row.get("fixture_id") or row.get("event_id") or "")
        all_groups.setdefault(fid, []).append(row)
    entries = []
    issues = Counter()
    for fid, group in sorted(all_groups.items()):
        if not fid or len(group) != 6 or {r["market_lane"] for r in group} != PERIOD_LANES:
            issues["PERIOD_COHORT_INCOMPLETE_OR_DUPLICATE"] += 1
            continue
        source = lookup.get(fid)
        if source is None:
            issues["NO_STANDARD_FT"] += 1
            continue
        try:
            if (utc(group[0]["event_start_utc"]) != utc(source["kickoff_utc"])
                or utc(group[0]["freeze_timestamp_utc"]) != utc(source["freeze_at_utc"])):
                issues["FROZEN_KICKOFF_OR_FREEZE_LINEAGE_MISMATCH"] += 1
                continue
        except (ValueError, TypeError, KeyError):
            issues["FROZEN_KICKOFF_OR_FREEZE_LINEAGE_MISMATCH"] += 1
            continue
        if source.get("result_source_provider") != "api_football":
            issues["INDEPENDENT_FT_NO_VERIFIED_HALFTIME"] += 1
            continue
        try:
            verified_half_time(fid, source, rawdir)
            issues["ORIGINAL_HALFTIME_CERTIFIED"] += 1
            continue
        except (ValueError, TypeError, KeyError) as err:
            reason = str(err)
            detail = quality_detail(fid, source, rawdir)
            issues[reason] += 1
            entries.append({
                "fixture_id": fid,
                "original_receipt_issue": reason,
                "raw_field_diagnostic": detail,
                "source_provider": "api_football",
                "fixture_in_all_six_period_lanes": True,
                "historical_result_repaired": False,
                "halftime_promoted": False,
            })
    return {
        "schema": SCHEMA,
        "status": "ORIGINAL_HALFTIME_RECEIPT_TRIAGE_NO_INFERRED_SCORE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "market_lanes_examined": 6,
        "cohort_common_fixture_count": len(all_groups),
        "unique_fixture_issue_counts": dict(sorted(issues.items())),
        "source_problem_details": entries,
        "original_period_lane_blockers": {
            k: expected[k]["blockers"] for k in sorted(expected)
        },
        "reusable_90_minute_result_from_final_only": False,
        "counts_toward_new_prospective_observations": False,
        "new_halftime_labels_written": 0,
        "model_parameters_changed": False,
        "telegram_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    arg = argparse.ArgumentParser()
    arg.add_argument("--root", type=Path, default=Path("."))
    arg.add_argument("--output", type=Path, required=True)
    a = arg.parse_args()
    root = a.root
    reg = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    portfolio = [
        json.loads(line) for line in (root / PORTFOLIO).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    first = _load_ledger(root / ORIGINAL)
    second = validated_ledger(root / INDEPENDENT)
    result = inspect(reg, portfolio, first, second, rawdir=root / RAW)
    result["source_file_sha256"] = {
        str(p): hashlib.sha256((root / p).read_bytes()).hexdigest()
        for p in (REGISTRY, PORTFOLIO, ORIGINAL, INDEPENDENT)
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False,
                                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "issues": result["unique_fixture_issue_counts"],
                      "source_problem_count": len(result["source_problem_details"])}))


if __name__ == "__main__":
    main()
