"""Conservative reconciliation of saved browser links; never generates betting signals."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

SOFA = Path("evidence/browser_capture_inbox/MATRIX_SOFASCORE_TENNIS_20261031_FULL_LINK_DISCOVERY.json")
FLASH = Path("evidence/browser_capture_inbox/MATRIX_FLASHSCORE_TENNIS_VISIBLE_LINK_DISCOVERY.json")
OUT = Path("evidence/browser_capture_inbox/MATRIX_TENNIS_CROSS_SOURCE_RECONCILIATION_LAST.json")


def flash_identity(url: str) -> str | None:
    """Strip presentation variants, preserving the provider's player IDs."""
    parts = urlsplit(url).path.strip("/").split("/")
    if len(parts) < 4 or parts[:2] != ["partido", "tenis"]:
        return None
    return "|".join(sorted(parts[2:4]))


def reconcile(sofa: dict, flash: dict) -> dict:
    if sofa.get("schema") != "MATRIX_BROWSER_TENNIS_CALENDAR_DISCOVERY_V1":
        raise ValueError("SOFA_SCHEMA")
    if flash.get("schema") != "MATRIX_BROWSER_FLASHSCORE_TENNIS_LINK_DISCOVERY_V1":
        raise ValueError("FLASH_SCHEMA")
    sofa_events = {}
    for row in sofa.get("events", []):
        event_id = str(row.get("event_id", ""))
        url = str(row.get("source_url", ""))
        if not event_id.isdigit() or f"#id:{event_id}" not in url:
            continue
        sofa_events.setdefault(event_id, {"event_id": event_id, "display_text": row.get("display_text"), "source_url": url})
    flash_events = {}
    invalid_flash = 0
    for row in flash.get("links", []):
        key = flash_identity(str(row.get("url", "")))
        if key is None:
            invalid_flash += 1
            continue
        flash_events.setdefault(key, {"provider_identity": key, "display_text": row.get("name"), "source_url": row.get("url")})
    return {
        "schema": "MATRIX_BROWSER_TENNIS_RECONCILIATION_V1",
        "status": "DISCOVERY_ONLY_UNMATCHED_PROVIDER_IDENTITIES",
        "sofascore_calendar_date": sofa.get("calendar_date"),
        "sofascore_unique_events": len(sofa_events),
        "flashscore_unique_player_pair_urls": len(flash_events),
        "flashscore_invalid_links": invalid_flash,
        "cross_provider_confirmed_matches": 0,
        "cross_provider_matching_status": "NOT_CERTIFIED_DIFFERENT_IDENTITY_SCHEMES",
        "sofascore_events": sorted(sofa_events.values(), key=lambda r: r["event_id"]),
        "flashscore_events": sorted(flash_events.values(), key=lambda r: r["provider_identity"]),
        "limitations": [
            "Flashscore URL player-pair identity is not an event identifier; repeat meetings may collapse.",
            "Source snapshots may include live, past and future matches, and different calendar dates.",
            "No provider-to-provider identity mapping or timezone verified.",
            "No model probability, bookmaker quote or signal eligibility certified.",
        ],
        "candidate_eligible": False,
        "telegram_send_authorized": False,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sofa", type=Path, default=SOFA)
    parser.add_argument("--flash", type=Path, default=FLASH)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    result = reconcile(json.loads(args.sofa.read_text(encoding="utf-8")), json.loads(args.flash.read_text(encoding="utf-8")))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "sofascore_unique_events", "flashscore_unique_player_pair_urls", "cross_provider_confirmed_matches")}, sort_keys=True))


if __name__ == "__main__":
    main()
