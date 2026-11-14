"""Audit historical and prospective evidence already committed to MATRIX.

Never synthesize a prediction, retrofit a timestamp, or equate a historical
raw-group archive with a frozen pair. Only SHA-bound full OOS manifests can
increase certified counts. File/path discovery is evidence inventory only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from tools.matrix_six_league_prospective_preflight import (
    DISCOVERY, PROSPECTIVE, REGISTRY, ROOT, load,
)
from tools.matrix_six_league_enriched_oos_audit import audit

OUTPUT = Path("evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_EXISTING_EVIDENCE_RECOVERY_LAST.json")
CATEGORIES = {
    "original_archived_raw_groups": "HISTORICAL_ONLY",
    "original_canonical_analysis_files": "UNVERIFIED_PREMATCH_ORIGINAL",
    "alternative_shadow_files": "RESEARCH_ONLY",
    "prospective_manifest_files": "MUST_PASS_STRICT_AUDIT",
    "settlement_files": "UNVERIFIED_RESULT",
}
RAW = re.compile(r"/history/raw/league_(\d+)_season_(\d+)\.bin$")
OOS_SCHEMA = "MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE_V1"
MAX_JSON_BYTES = 3 * 1024 * 1024

def relative_paths(root: Path) -> list[str]:
    """Use tracked Git files, not transient files, credentials, or runner workspace."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "evidence/"],
            check=True, capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("MATRIX_TRACKED_EVIDENCE_INDEX_UNAVAILABLE") from exc
    return sorted(set(p.decode("utf-8") for p in result.stdout.split(b"\0") if p))

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def evaluate(root: Path, paths: list[str]) -> dict:
    original = load(root / DISCOVERY)
    registry = load(root / REGISTRY)
    ids = registry["original_six_league_ids"]
    if not (
        registry.get("schema") == "MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
        and registry.get("scope_approved") is True
        and registry.get("real_money") == "BLOCKED"
        and registry.get("telegram_signal_authorized") is False
        and isinstance(ids, list) and len(ids) == 6 and len(set(ids)) == 6
        and all(isinstance(i, str) and i.isdecimal() for i in ids)
    ):
        raise ValueError("MATRIX_SIX_LEAGUES_UNGOVERNED")
    archival = {ident: [] for ident in ids}
    for group in original["reference_groups"]:
        ident = str(group["original_league_id"])
        if ident in archival:
            archival[ident].extend(group["archive_files"])
    if any(not archival[i] for i in ids):
        raise ValueError("MATRIX_SIX_LEAGUE_ORIGINAL_ARCHIVE_INCOMPLETE")

    counts = Counter()
    candidate_files = []
    manifest_paths = []
    # Only examine tracked JSON under research folders; never read raw .bin history.
    for name in paths:
        norm = name.replace("\\", "/")
        if not norm.startswith("evidence/") or norm.startswith("evidence/notifications/telegram/browser_cdp/"):
            continue
        if RAW.search("/" + norm):
            counts["all_original_raw_group_files"] += 1
        if "/canonical_analysis/" in norm and norm.endswith(".json"):
            counts["original_canonical_analysis_files"] += 1
        if "/football_world_inventory/" in norm and norm.endswith(".json"):
            counts["world_inventory_json_files"] += 1
        if any(piece in norm.lower() for piece in ("shadow", "research_history")) and norm.endswith(".json"):
            counts["research_shadow_json_files"] += 1
        if norm.endswith(".json") and any(v in norm for v in (
            "PROSPECTIVE_EVIDENCE", "prospective_evidence", "PREMATCH_SNAPSHOT", "prematch_snapshot",
        )):
            candidate_files.append(norm)
        if "MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE" in norm and norm.endswith(".json"):
            manifest_paths.append(norm)
    certified = {i: 0 for i in ids}
    discovered = []
    for name in sorted(set(manifest_paths)):
        path = root / name
        if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
            discovered.append({"path": name, "status": "UNREADABLE_OR_OVERSIZED"})
            continue
        try:
            document = load(path)
            if document.get("schema") != OOS_SCHEMA:
                discovered.append({"path": name, "status": "SCHEMA_NOT_OOS"})
                continue
            if document.get("original_six_league_ids") != ids:
                discovered.append({"path": name, "status": "REGISTRY_SCOPE_MISMATCH"})
                continue
            # Audit verifies SHA-attested original, alternative and result
            # evidence. The scanner has no authority to infer missing fields.
            metric = audit(path)
            for league in metric["leagues"]:
                certified[str(league["league"])] = max(
                    certified[str(league["league"])],
                    league["validated_prospective_rows"],
                )
            discovered.append({
                "path": name,
                "sha256": sha(path),
                "status": metric["status"],
                "six_league_scientific_validation_passed": metric["six_league_scientific_validation_passed"],
            })
        except (ValueError, TypeError, KeyError, OSError, json.JSONDecodeError) as exc:
            discovered.append({"path": name, "status": "FAIL_CLOSED", "error": type(exc).__name__})
    report = {
        "schema": "MATRIX_SIX_LEAGUE_EXISTING_EVIDENCE_RECOVERY_V1",
        "status": "RESEARCH_INVENTORY_ONLY_NO_PRODUCTION_AUTHORIZATION",
        "selected_original_league_ids": ids,
        "tracked_evidence_file_count": len(paths),
        "category_counts_all_leagues": dict(sorted(counts.items())),
        "prospective_filename_candidates": sorted(set(candidate_files))[:100],
        "prospective_filename_candidate_count": len(set(candidate_files)),
        "strict_oos_manifest_paths": sorted(set(manifest_paths)),
        "strict_oos_manifest_results": discovered,
        "leagues": [{
            "league_id": i,
            "original_archived_raw_group_files_in_discovery": len(archival[i]),
            "certified_prospective_rows_from_strict_manifest": certified[i],
            "prospective_minimum_per_league": 30,
            "remaining_verified_rows_to_minimum": max(0, 30-certified[i]),
            "archived_raw_groups_not_counted_as_prospective": True,
            "unclassified_or_missing_sources_not_counted_as_invalid_parties": True,
        } for i in ids],
        "original_source_registry_sha256": sha(root / REGISTRY),
        "original_archive_discovery_sha256": sha(root / DISCOVERY),
        "complete_repo_file_discovery_only_not_proof_of_data_contents": True,
        "historical_championship_11_of_11_unrelated_to_prospective": True,
        "raw_group_archive_not_promoted_to_p_matrix": True,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return report

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out", type=Path, default=OUTPUT)
    args = p.parse_args()
    if any(part in args.out.parts for part in ("daily_prematch_reports", "telegram", "tennis_signals", "governance")):
        raise SystemExit("MATRIX_RECOVERY_CANNOT_WRITE_PRODUCTION")
    result = evaluate(args.root, relative_paths(args.root))
    destination = args.out if args.out.is_absolute() else args.root / args.out
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "league_counts": {
            r["league_id"]: r["certified_prospective_rows_from_strict_manifest"]
            for r in result["leagues"]
        },
        "prospective_filename_candidate_count": result["prospective_filename_candidate_count"],
        "strict_oos_manifest_count": len(result["strict_oos_manifest_paths"]),
        "production_p_matrix_authorized": False,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
