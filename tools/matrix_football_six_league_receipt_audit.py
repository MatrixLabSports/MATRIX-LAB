"""Offline six-league receipt coverage audit, no network or model admission.

Reports exactly which original leagues have SHA-bound responses on disk.
An old RAW.json without its immutable receipt is legacy evidence, not proof
that the current scheduled cycle queried that league.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from tools.matrix_football_free_six_league_crosscheck import LEAGUES, ROOT

SCHEMA = "MATRIX_FREE_SIX_LEAGUE_RECEIPT_AUDIT_V1"
MAX_RAW_BYTES = 2_000_000


def audit(root: Path, day: str) -> dict:
    date.fromisoformat(day)
    folder = root / ROOT / day
    rows = []
    for original_id, league_id, name in LEAGUES:
        raw_path = folder / f"MATRIX_THESPORTSDB_DAY_LEAGUE_{league_id}_RAW.json"
        row = {
            "original_league_id": original_id,
            "thesportsdb_league_id": league_id,
            "league_name": name,
            "raw_present": raw_path.is_file(),
            "sha_bound_immutable_receipt_valid": False,
            "status": "NO_SOURCE_RAW_CAPTURE",
            "events_returned": None,
            "source_sha256": None,
        }
        if not raw_path.is_file():
            rows.append(row)
            continue
        raw = raw_path.read_bytes()
        if len(raw) > MAX_RAW_BYTES:
            raise ValueError("SIX_LEAGUE_RAW_OVERSIZED:" + league_id)
        digest = hashlib.sha256(raw).hexdigest()
        row["source_sha256"] = digest
        receipt_path = folder / (
            f"MATRIX_THESPORTSDB_DAY_LEAGUE_{league_id}_SHA256_{digest}_RECEIPT.json"
        )
        if not receipt_path.is_file():
            row["status"] = "LEGACY_RAW_WITHOUT_IMMUTABLE_RECEIPT"
            rows.append(row)
            continue
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (not isinstance(receipt, dict)
            or receipt.get("schema") != "MATRIX_TSDB_LEAGUE_SOURCE_HASH_RECEIPT_V1"
            or receipt.get("thesportsdb_league_id") != league_id
            or receipt.get("target_date_bogota") != day
            or receipt.get("raw_sha256") != digest
            or receipt.get("raw_bytes") != len(raw)
            or receipt.get("real_money") != "BLOCKED"
            or receipt.get("research_only") is not True
            or receipt.get("fixture_identity_certified") is not False
            or receipt.get("production_p_matrix_authorized") is not False):
            raise ValueError("SIX_LEAGUE_RECEIPT_INTEGRITY_FAILURE:" + league_id)
        raw_doc = json.loads(raw)
        if not isinstance(raw_doc, dict) or "events" not in raw_doc:
            raise ValueError("SIX_LEAGUE_PROVIDER_RAW_SCHEMA_INVALID:" + league_id)
        events = raw_doc["events"]
        if events is not None and not isinstance(events, list):
            raise ValueError("SIX_LEAGUE_PROVIDER_EVENTS_INVALID:" + league_id)
        row["sha_bound_immutable_receipt_valid"] = True
        row["events_returned"] = len(events) if events is not None else None
        row["status"] = (
            "AUTHENTIC_NULL_EVENTS_NOT_WORLD_ZERO" if events is None
            else "AUTHENTIC_PROVIDER_RESPONSE_RESEARCH_ONLY"
        )
        rows.append(row)
    verified = sum(x["sha_bound_immutable_receipt_valid"] for x in rows)
    return {
        "schema": SCHEMA,
        "target_date_bogota": day,
        "status": "ALL_SIX_RECEIPTS_VERIFIED_RESEARCH_ONLY" if verified == 6
                  else "INCOMPLETE_SIX_LEAGUE_RECEIPT_COVERAGE",
        "verified_league_receipts": verified,
        "unverified_league_receipts": 6 - verified,
        "network_calls": 0,
        "source_availability_is_not_fixture_identity": True,
        "original_pit_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "leagues": rows,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--day", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    args = p.parse_args()
    report = audit(args.root, args.day)
    dest = args.root / ROOT / args.day / "MATRIX_FREE_SIX_LEAGUE_RECEIPT_AUDIT_LAST.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    print(json.dumps({"day": args.day, "verified": report["verified_league_receipts"],
                      "status": report["status"], "admissions": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
