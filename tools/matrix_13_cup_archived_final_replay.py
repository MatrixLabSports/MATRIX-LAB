"""Offline 13-market research replay of already captured ESPN cup results.

Only raw source bytes with a SHA-256 receipt from an earlier authenticated
capture are eligible. Existing original prematch freezes, canonical FT ledger,
independent FT ledger, and every market parameter are read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_prospective_api_settlement import _load_ledger as api_final_ledger
from tools.matrix_13_cohort_independent_settlement import build_candidates, validated_ledger, append
from tools.matrix_13_cohort_espn_mls_results import compare, dt, BOGOTA
from tools.matrix_13_cohort_espn_cup_results import LEAGUES
from tools.matrix_13_cohort_independent_settlement import (
    TRIAGE, FREEZE, API_LEDGER, LEDGER, SOURCES, ROOT,
)

SOURCE_REPORT = SOURCES / "MATRIX_ESPN_CUPS_EXACT_FINAL_LAST.json"
SCHEMA = "MATRIX_13_ARCHIVED_ESPN_CUP_FT_REPLAY_V1"


def replay(*, root: Path = ROOT, append_certified: bool = False) -> dict:
    rel = lambda path: root / path.relative_to(ROOT)
    triage = json.loads(rel(TRIAGE).read_text(encoding="utf-8"))
    freeze = json.loads(rel(FREEZE).read_text(encoding="utf-8"))
    historic = json.loads(rel(SOURCE_REPORT).read_text(encoding="utf-8"))
    if (triage.get("target_market_count") != 13
        or historic.get("real_money") != "BLOCKED"
        or historic.get("canonical_ledger_appends") != 0):
        raise ValueError("CUP_ARCHIVE_REPLAY_GOVERNANCE_INVALID")
    reports = []
    unmatched = []
    verified_archives = []
    for q in historic.get("queries_scheduled", []):
        competition, day = q["competition"], q["date"]
        if competition not in LEAGUES or not isinstance(day, str) or len(day) != 8 or not day.isdecimal():
            raise ValueError("CUP_ARCHIVED_SOURCE_SCOPE_INVALID")
        archive = ("ESPN_CUP_" + LEAGUES[competition].replace(".", "_")
                   + "_" + day + "_RAW.json")
        src = root / "evidence/football_cohort_recovery" / archive
        if not src.is_file():
            raise ValueError("CUP_ARCHIVED_SOURCE_BYTES_MISSING")
        raw = src.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        key = competition + "|" + day
        if sha != historic.get("source_response_sha256", {}).get(key):
            raise ValueError("CUP_ARCHIVED_SOURCE_SHA_MISMATCH")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("CUP_ARCHIVED_SOURCE_SCHEMA_INVALID")
        group = [
            x for x in triage["unsettled_fixture_triage"]
            if x.get("competition_name") == competition
            and dt(x["kickoff_utc"]).astimezone(BOGOTA).strftime("%Y%m%d") == day
        ]
        matched, rejected = compare(group, payload, sha)
        for row in matched:
            row["competition_name"] = competition
            row["independent_source"] = "ESPN_" + LEAGUES[competition]
            row["raw_archive_path"] = (
                "evidence/football_cohort_recovery/" + archive)
        reports.extend(matched)
        unmatched.extend({"competition": competition, **r} for r in rejected)
        verified_archives.append({
            "archive": archive, "source_sha256": sha,
            "exact_ft": len(matched), "source_event_count": len(payload["events"]),
        })
    provider_report = {
        "real_money": "BLOCKED",
        "canonical_ledger_appends": 0,
        "matched": reports,
    }
    old = validated_ledger(rel(LEDGER))
    canonical = api_final_ledger(rel(API_LEDGER))
    candidates, rejected = build_candidates(
        triage, freeze, [("ESPN_CUP", provider_report)], root=root,
        api_settled=canonical, already=old,
    )
    ledger_result = None
    if append_certified:
        if os.environ.get("MATRIX_APPEND_VERIFIED_ARCHIVED_FT") != "EXPLICIT_PARALLEL_LEDGER_ONLY":
            raise ValueError("REPLAY_APPEND_EXPLICIT_ENV_REQUIRED")
        original_sha = hashlib.sha256(rel(API_LEDGER).read_bytes()).hexdigest()
        original_freeze_sha = hashlib.sha256(rel(FREEZE).read_bytes()).hexdigest()
        ledger_result = append(rel(LEDGER), candidates)
        if (hashlib.sha256(rel(API_LEDGER).read_bytes()).hexdigest() != original_sha
            or hashlib.sha256(rel(FREEZE).read_bytes()).hexdigest() != original_freeze_sha):
            raise ValueError("REPLAY_ORIGINAL_CANONICAL_BYTES_MUTATED")
    return {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "VERIFIED_ARCHIVAL_CANDIDATES_ONLY_NOT_LEDGER_APPEND",
        "source_archives_sha256_verified": verified_archives,
        "prior_independent_final_count": len(old),
        "original_canonical_final_count": len(canonical),
        "new_independently_replayed_standard_ft_count": len(candidates),
        "new_candidates": [
            {
                "canonical_fixture_id": x["fixture_id"],
                "source_fixture_id": x["source_fixture_id"],
                "source_archive_path": x["source_raw_path"],
                "source_sha256": x["source_raw_sha256"],
                "kickoff_utc": x["kickoff_utc"],
                "source_provider": x["source_provider"],
                "standard_fulltime_home_goals": x["fulltime_home_goals"],
                "standard_fulltime_away_goals": x["fulltime_away_goals"],
                "original_feature_sha256": x["input_sha256"],
                "prematch_frozen_at_utc": x["freeze_at_utc"],
                "no_original_prediction_mutation": True,
            } for x in candidates
        ],
        "unmatched_source_identities": unmatched,
        "settlement_replay_rejections": rejected,
        "ledger_mutated": bool(append_certified and candidates),
        "parallel_independent_ledger_append_result": ledger_result,
        "original_parameters_mutated": False,
        "production_p_matrix_promoted": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--append-certified", action="store_true")
    a = ap.parse_args()
    report = replay(append_certified=a.append_certified)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report["status"],
        "new": report["new_independently_replayed_standard_ft_count"],
        "prior_independent": report["prior_independent_final_count"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
