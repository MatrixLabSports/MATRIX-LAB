"""Strict, research-only reconciliation of authorized visible football calendar links.

Never treats a team-name pair as an independently certified fixture crosswalk.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


# No fuzzy matching. Aliases are for exploratory candidate comparison only,
# and each match still requires future independent ID and kickoff validation.
ALIASES = {
    "inter de bogota": "inter bogota",
    "america": "america de cali",
    "pais de gales": "gales",
    "lesoto": "lesotho",
    "corea del sur": "south korea",
    "costa de marfil": "cote divoire",
}


def alias(s: str) -> str:
    s = norm(s)
    return ALIASES.get(s, s)


def sofa_pair(row: dict, target_day: str):
    pieces = [x.strip() for x in str(row.get("visible_name") or "").splitlines() if x.strip()]
    if len(pieces) != 4:
        return None
    try:
        displayed = datetime.strptime(pieces[0], "%d/%m/%y").date().isoformat()
    except ValueError:
        return None
    if displayed != target_day or not re.fullmatch(r"\d{1,2}:\d{2}", pieces[1]):
        return None
    if not str(row.get("sofascore_event_id") or "").isdigit():
        return None
    return alias(pieces[2]), alias(pieces[3]), pieces[1]


def flash_pair(row: dict):
    label = str(row.get("visible_name") or "")
    mid = str(row.get("flashscore_mid") or "")
    if not re.fullmatch(r"[A-Za-z0-9]{8}", mid):
        return None
    pieces = label.split(" - ")
    if len(pieces) != 2 or not all(x.strip() for x in pieces):
        return None
    return alias(pieces[0]), alias(pieces[1])


def reconcile(sofa: dict, flash: dict, *, sofa_sha: str, flash_sha: str) -> dict:
    if (sofa.get("schema") != "MATRIX_FOOTBALL_AUTHORIZED_VISIBLE_BROWSER_LINKS_V1"
        or flash.get("schema") != "MATRIX_FOOTBALL_AUTHORIZED_VISIBLE_BROWSER_LINKS_V1"
        or sofa.get("source") != "SOFASCORE" or flash.get("source") != "FLASHSCORE"
        or sofa.get("real_money") != "BLOCKED" or flash.get("real_money") != "BLOCKED"
        or sofa.get("canonical_prematch_inputs_authorized") is not False
        or flash.get("canonical_prematch_inputs_authorized") is not False):
        raise ValueError("UNTRUSTED_BROWSER_CAPTURE_PROVENANCE")
    day = str(sofa.get("target_date_bogota") or "")
    if day != flash.get("target_date_bogota"):
        raise ValueError("TARGET_DAY_MISMATCH")
    if (flash.get("date_evidence_mode") != "RELATIVE_TOMORROW_PAGE_TITLE_ONLY_NOT_ABSOLUTE"
        and flash.get("date_evidence_mode") != "EXACT_VISIBLE_CALENDAR_CONTROL"):
        raise ValueError("FLASH_DATE_EVIDENCE_NOT_RECORDED")
    for digest in (sofa_sha, flash_sha):
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("SOURCE_SHA256_REQUIRED")
    sindex = defaultdict(list)
    findex = defaultdict(list)
    for row in sofa.get("links") or []:
        pair = sofa_pair(row, day)
        if pair:
            sindex[pair[:2]].append((row, pair[2]))
    for row in flash.get("links") or []:
        pair = flash_pair(row)
        if pair:
            findex[pair].append(row)
    candidates, ambiguous = [], []
    for key in sorted(set(sindex) & set(findex)):
        ss, ff = sindex[key], findex[key]
        if len(ss) != 1 or len(ff) != 1:
            ambiguous.append({"home": key[0], "away": key[1],
                              "sofa_rows": len(ss), "flash_rows": len(ff),
                              "reason": "NON_UNIQUE_TWO_SOURCE_IDENTITY"})
            continue
        srow, clock = ss[0]
        frow = ff[0]
        candidates.append({
            "home_normalized": key[0], "away_normalized": key[1],
            "sofascore_event_id": srow["sofascore_event_id"],
            "sofascore_url": srow["url"],
            "sofascore_visible_clock_unverified_timezone": clock,
            "flashscore_mid": frow["flashscore_mid"],
            "flashscore_url": frow["url"],
            "source_provider_fixture_id": None,
            "source_event_kickoff_utc_certified": False,
            "cross_provider_identity_certified": False,
            "original_enriched_pit_features_verified": False,
            "model_probability_authorized": False,
        })
    return {
        "schema": "MATRIX_AUTHORIZED_FOOTBALL_DUAL_BROWSER_RESEARCH_LINKS_V1",
        "status": "RESEARCH_TWO_SOURCE_CANDIDATES_ONLY_NOT_CALENDAR_CERTIFIED",
        "target_date_bogota": day,
        "source_sha256": {"sofascore": sofa_sha, "flashscore": flash_sha},
        "source_capture_at_utc": {
            "sofascore": sofa["captured_at_utc"],
            "flashscore": flash["captured_at_utc"],
        },
        "sofascore_visible_link_count": sofa["observed_link_count"],
        "flashscore_visible_link_count": flash["observed_link_count"],
        "research_candidate_count": len(candidates),
        "ambiguous_name_pair_count": len(ambiguous),
        "research_candidates": candidates,
        "ambiguous": ambiguous,
        "strict_three_source_crosswalk_count": 0,
        "canonical_prematch_inputs_authorized": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    base = args.root/"evidence/football_calendar_physical"/args.day
    paths = [base/"sofascore_visible_links.json", base/"flashscore_visible_links.json"]
    if not all(p.is_file() for p in paths):
        raise SystemExit("BOTH_PHYSICAL_BROWSER_SOURCES_REQUIRED")
    raw = [p.read_bytes() for p in paths]
    obj = [json.loads(x) for x in raw]
    r = reconcile(obj[0], obj[1],
                  sofa_sha=hashlib.sha256(raw[0]).hexdigest(),
                  flash_sha=hashlib.sha256(raw[1]).hexdigest())
    dest = base/"MATRIX_TWO_SOURCE_LINK_RESEARCH_LAST.json"
    dest.write_text(json.dumps(r, sort_keys=True, ensure_ascii=False, indent=2)+"\n",
                    encoding="utf-8")
    print(json.dumps({"research_candidate_count": r["research_candidate_count"],
                      "strict_three_source_crosswalk_count": 0,
                      "production_p_matrix_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
