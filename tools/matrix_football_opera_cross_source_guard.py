"""Fail-closed validation of user-authorized, research-only football calendar links.

This checker never promotes fixtures, calls paid APIs, recalculates p_matrix,
writes canonical candidate files or sends Telegram messages.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = "MATRIX_FOOTBALL_OPERA_CROSS_SOURCE_RESEARCH_MATCHES_V1"
ID_RE = re.compile(r"^[0-9]+$")


def check(document: dict, day: str) -> dict:
    if not isinstance(document, dict):
        raise ValueError("RESEARCH_DOCUMENT_NOT_OBJECT")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ValueError("TARGET_DAY_FORMAT_INVALID")
    if (document.get("schema") != SCHEMA
            or document.get("target_date_bogota") != day
            or document.get("source_order") != ["SOFASCORE", "FLASHSCORE"]
            or document.get("real_money") != "BLOCKED"
            or document.get("automatic_wagering") is not False
            or document.get("paid_api_used") is not False
            or document.get("p_matrix_authorized") is not False
            or document.get("telegram_signal_authorized") is not False
            or document.get("production_candidate_count") != 0):
        raise ValueError("RESEARCH_GOVERNANCE_MISMATCH")
    rows = document.get("matches")
    if not isinstance(rows, list) or len(rows) == 0:
        raise ValueError("NO_AUTHENTIC_NAME_PAIR_ROWS")
    if len(rows) != document.get("matched_name_pair_count"):
        raise ValueError("RESEARCH_ROW_COUNT_MISMATCH")
    seen_sofa, seen_flash = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("RESEARCH_ROW_NOT_OBJECT")
        sofa_id = str(row.get("sofascore_event_id") or "")
        s = urlparse(str(row.get("sofascore_url") or ""))
        f = urlparse(str(row.get("flashscore_url") or ""))
        if (not ID_RE.fullmatch(sofa_id)
                or s.scheme != "https" or s.hostname != "www.sofascore.com"
                or not s.path.startswith("/es/football/match/")
                or s.fragment != "id:" + sofa_id
                or f.scheme != "https" or f.hostname != "www.flashscore.co"
                or not f.path.startswith("/partido/futbol/")
                or not row.get("home") or not row.get("away")):
            raise ValueError("SOURCE_IDENTITY_OR_URL_INVALID")
        if (row.get("source_identity_status") != "RESEARCH_NAME_PAIR_ONLY"
                or row.get("source_event_equivalence_certified") is not False
                or row.get("kickoff_timezone_certified") is not False
                or row.get("original_provider_crosswalk_certified") is not False
                or row.get("original_enriched_features_equivalent") is not False):
            raise ValueError("UNAUTHORIZED_PROMOTION_OR_PARITY_CLAIM")
        if sofa_id in seen_sofa or f.geturl() in seen_flash:
            raise ValueError("DUPLICATED_SOURCE_EVENT")
        seen_sofa.add(sofa_id)
        seen_flash.add(f.geturl())
    return {
        "schema": "MATRIX_FOOTBALL_OPERA_CROSS_SOURCE_GUARD_V1",
        "target_date_bogota": day,
        "source_link_pairs_verified": len(rows),
        "event_identity_certified": False,
        "kickoff_certified": False,
        "original_feature_parity_certified": False,
        "production_candidates_authorized": 0,
        "telegram_signal_authorized": False,
        "real_money": "BLOCKED",
        "status": "PASS_RESEARCH_LINK_INTEGRITY_ONLY_NO_PRODUCTION",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--input", type=Path, required=True)
    args = p.parse_args()
    result = check(json.loads(args.input.read_text(encoding="utf-8")), args.date)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
