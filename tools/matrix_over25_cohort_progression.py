"""Verify the first genuinely new free-provider cohort without certifying betting.

All observations and settlement counts are read from immutable local evidence.
No network calls, backfills, market promotion or forecast changes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("evidence/football_research_freezes")
INVENTORY = Path("evidence/football_world_inventory")
SCORECARD = INVENTORY / "MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_LAST.json"
TARGET_SCHEMA = "MATRIX_OVER25_COHORT_PROGRESSION_V1"

def stamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)

def audit(root: Path, target_day: str) -> dict:
    folder = root / ROOT / target_day
    # The daily freeze report is REWRITTEN on subsequent cycles, sometimes
    # to zero after kickoff. Only the run-123 certificate and immutable
    # original forecasts can define the permanent preregistered cohort.
    certificate_path = root / INVENTORY / target_day / "MATRIX_PRODUCER_30_NEW_UNIQUE_RUN_123_CERTIFICATE.json"
    cert = json.loads(certificate_path.read_bytes())
    if (cert.get("schema") != "MATRIX_PRODUCER_NEW_UNIQUE_30_GITHUB_RUN_CERTIFICATE_V1"
        or cert.get("fixture_target_date_bogota") != target_day
        or cert.get("github_actions_run_id") != 45084248031
        or cert.get("production_p_matrix_authorized") is not False
        or cert.get("telegram_signal_authorized") is not False
        or cert.get("real_money") != "BLOCKED"
        or cert.get("new_immutable_forecasts") != len(cert.get("new_fixture_ids", []))
        or cert.get("new_immutable_forecasts") != 30):
        raise ValueError("UNTRUSTED_IMMUTABLE_COHORT_CERTIFICATE")
    manifest_path = root / INVENTORY / target_day / "MATRIX_PRODUCER_30_IMMUTABLE_SHA_MANIFEST.json"
    manifest = json.loads(manifest_path.read_bytes())
    expected_hashes = manifest.get("immutable_forecast_sha256_by_fixture_id", {})
    if (manifest.get("schema") != "MATRIX_PROSPECTIVE_28NOV_FIXED_SHA_MANIFEST_V1"
        or manifest.get("target_date_bogota") != target_day
        or manifest.get("github_run_id") != 45084248031
        or manifest.get("production_p_matrix_authorized") is not False
        or manifest.get("telegram_signal_authorized") is not False
        or manifest.get("real_money") != "BLOCKED"
        or not isinstance(expected_hashes, dict)
        or set(expected_hashes) != set(cert["new_fixture_ids"])):
        raise ValueError("UNTRUSTED_IMMUTABLE_SOURCE_HASH_MANIFEST")
    prior = set()
    for p in (root / ROOT).glob("20??-??-??/[0-9]*_*.json"):
        if p.parent.name == target_day or "_result_" in p.name:
            continue
        fid = p.name.split("_", 1)[0]
        if fid.isdecimal():
            prior.add(fid)
    count = Counter()
    identities = set()
    verified_forecast_shas = {}
    for raw_id in cert["new_fixture_ids"]:
        fid = str(raw_id)
        matching = list(folder.glob(fid + "_*.json"))
        matching = [p for p in matching if "_result_" not in p.name]
        if not fid.isdecimal() or fid in identities or fid in prior or len(matching) != 1:
            raise ValueError("DUPLICATE_OR_UNTRUSTED_PROSPECTIVE_FIXTURE")
        identities.add(fid)
        # SHA is re-computed from persisted files, not copied from mutable
        # reports. The original signed job certificate fixes cohort membership.
        original_file = matching[0]
        raw = original_file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hashes[fid]:
            raise ValueError("FROZEN_SHA256_MISMATCH")
        verified_forecast_shas[fid] = hashlib.sha256(raw).hexdigest()
        row = json.loads(raw)
        if (row.get("schema") != "MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1"
            or row.get("provider") != "FOOTBALL_DATA_ORG"
            or str(row.get("provider_fixture_id")) != fid
            or row.get("production_p_matrix_authorized") is not False
            or row.get("telegram_signal_authorized") is not False
            or row.get("real_money") != "BLOCKED"
            or not stamp(row["intake_captured_at_utc"]) <= stamp(row["history_captured_at_utc"]) <= stamp(row["model_calculated_at_utc"]) <= stamp(row["sealed_at_utc"]) < stamp(row["kickoff_utc"])):
            raise ValueError("FROZEN_PREMATCH_OR_GOVERNANCE_INVALID")
        count[str(row["provider_competition_id"])] += 1
    if len(identities) != cert["new_immutable_forecasts"]:
        raise ValueError("FREEZE_COUNT_INCONSISTENT")
    card = json.loads((root / SCORECARD).read_bytes())
    if (card.get("provider") != "FOOTBALL_DATA_ORG"
        or card.get("telegram_signal_authorized") is not False
        or card.get("production_p_matrix_authorized") is not False):
        raise ValueError("UNTRUSTED_SETTLEMENT_SCORECARD")
    settled = {str(g["source_competition_id"]): int(g["independent_out_of_sample_rows"])
               for g in card.get("provider_competitions", [])}
    if sum(settled.values()) != card["total_verified_settled_rows"]:
        raise ValueError("SCORECARD_TOTAL_INCONSISTENT")
    league_rows = []
    # This is coverage, NOT settled sample size, nor certification.
    for league in sorted(set(count) | set(settled)):
        n = count[league]
        s = settled.get(league, 0)
        league_rows.append({
            "provider_competition_id": league,
            "new_unique_28nov_cohort": n,
            "currently_verified_settled_research_rows": s,
            "verified_settlements_plus_new_cohort_upper_bound": s + n,
            "settled_count_at_least_30": s >= 30,
            "additional_settled_rows_needed_for_30": max(0, 30-s),
        })
    return {
        "schema": TARGET_SCHEMA,
        "target_date_bogota": target_day,
        "status": "SHA_VERIFIED_PROSPECTIVE_COHORT_NOT_YET_OOS_CERTIFIED",
        "verified_distinct_fixture_count": len(identities),
        "baseline_prior_archive_distinct_ids": len(prior),
        "cross_day_duplicate_count": 0,
        "verified_forecast_sha256_by_fixture_id": dict(sorted(verified_forecast_shas.items())),
        "cohort_certificate_sha256": hashlib.sha256(certificate_path.read_bytes()).hexdigest(),
        "immutable_sha_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "scorecard_sha256": hashlib.sha256((root / SCORECARD).read_bytes()).hexdigest(),
        "settled_research_total_across_provider_competitions": card["total_verified_settled_rows"],
        "provider_competitions": league_rows,
        "no_future_outcomes_used": True,
        "scientific_oos_certified": False,
        "original_provider_feature_parity_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--date", default="2026-11-28")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = audit(args.root, args.date)
    out = args.out or INVENTORY / args.date / "MATRIX_OVER25_COHORT_PROGRESSION.json"
    if "daily_prematch_reports" in out.parts or "telegram" in out.parts or "governance" in out.parts:
        raise SystemExit("RESEARCH_REPORT_MUST_NOT_WRITE_PRODUCTION")
    path = out if out.is_absolute() else args.root / out
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"new_cohort_unique": result["verified_distinct_fixture_count"],
        "verified_settled_research": result["settled_research_total_across_provider_competitions"],
        "production_p_matrix_authorized": False}, sort_keys=True))

if __name__ == "__main__":
    main()
