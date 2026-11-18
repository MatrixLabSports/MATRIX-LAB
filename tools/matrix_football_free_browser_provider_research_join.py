"""Offline three-source research join: dated visible browser pairs vs football-data.org.

Never equates name-only pairs to certified fixture identity, UTC clock, PIT
or model production. No HTTP calls; raw source files and SHA are bound.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
SCHEMA = "MATRIX_FREE_BROWSER_PROVIDER_RESEARCH_JOIN_V1"
BROWSER_SCHEMA = "MATRIX_AUTHORIZED_FOOTBALL_DUAL_BROWSER_RESEARCH_LINKS_V1"
INTAKE_SCHEMA = "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
# Explicit, narrow provider name forms seen on original 18-NOV source.
# Aliases are only hints and never promote official identity.
PROVIDER_ALIASES = {
    "coritiba fbc":"coritiba",
    "santos fc":"santos",
    "clube do remo":"remo",
    "chapecoense af":"chapecoense",
    "cruzeiro ec":"cruzeiro",
    "se palmeiras":"palmeiras",
    "cr flamengo":"flamengo",
    "ca paranaense":"paranaense",
}
def norm(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value or "")).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return PROVIDER_ALIASES.get(s, s)

def utc(value: str) -> datetime:
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("RESEARCH_TIMESTAMP_MUST_HAVE_TIMEZONE")
    return d.astimezone(timezone.utc)

def join(browser: dict, intake: dict, *, browser_sha256: str, intake_sha256: str) -> dict:
    if (browser.get("schema") != BROWSER_SCHEMA
        or browser.get("status") != "RESEARCH_TWO_SOURCE_CANDIDATES_ONLY_NOT_CALENDAR_CERTIFIED"
        or browser.get("real_money") != "BLOCKED"
        or browser.get("canonical_prematch_inputs_authorized") is not False
        or browser.get("production_p_matrix_authorized") is not False
        or intake.get("schema") != INTAKE_SCHEMA
        or intake.get("source") != "FOOTBALL_DATA_ORG"
        or intake.get("real_money") != "BLOCKED"
        or intake.get("signal_generation_authorized") is not False):
        raise ValueError("RESEARCH_SOURCES_NOT_FAIL_CLOSED")
    day = browser.get("target_date_bogota")
    if day != intake.get("target_date_bogota"):
        raise ValueError("RESEARCH_SOURCE_DATE_MISMATCH")
    for sha in (browser_sha256, intake_sha256):
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("SOURCE_SHA256_REQUIRED")
    captures = browser.get("source_capture_at_utc") or {}
    capture_moments = [utc(captures[k]) for k in ("sofascore", "flashscore")]
    provider_capture = utc(intake["generated_at_utc"])
    fixtures = intake.get("fixtures")
    candidates = browser.get("research_candidates")
    if not isinstance(fixtures, list) or not isinstance(candidates, list):
        raise ValueError("RESEARCH_SOURCE_ROWS_MISSING")
    index = {}
    for f in fixtures:
        if not isinstance(f, dict) or f.get("signal_generation_authorized") is not False:
            raise ValueError("PROVIDER_ROW_UNTRUSTED")
        key = (norm(f.get("home")), norm(f.get("away")))
        if not all(key):
            raise ValueError("EMPTY_PROVIDER_TEAM")
        index.setdefault(key, []).append(f)
    rows = []
    used_provider_ids = set()
    for item in candidates:
        if not isinstance(item, dict) or item.get("cross_provider_identity_certified") is not False:
            raise ValueError("BROWSER_CANDIDATE_UNTRUSTED")
        key = (norm(item.get("home_normalized")), norm(item.get("away_normalized")))
        hits = index.get(key, [])
        hit = hits[0] if len(hits) == 1 else None
        fid = str(hit["source_fixture_id"]) if hit else None
        if fid and fid in used_provider_ids:
            raise ValueError("REUSED_PROVIDER_ID_IN_BROWSER_RESEARCH")
        if fid:
            used_provider_ids.add(fid)
        kickoff = utc(hit["kickoff_utc"]) if hit else None
        # Input UTC date must genuinely correspond to that Bogotá calendar day.
        if kickoff and kickoff.astimezone(BOGOTA).date().isoformat() != day:
            raise ValueError("PROVIDER_DATE_NOT_BROWSER_DAY")
        capture_before = bool(kickoff and all(t < kickoff for t in capture_moments)
                              and provider_capture < kickoff)
        clock = str(item.get("sofascore_visible_clock_unverified_timezone") or "")
        clock_agrees_if_bogota = bool(kickoff and
            kickoff.astimezone(BOGOTA).strftime("%H:%M") == clock.zfill(5))
        rows.append({
            "sofascore_event_id": item.get("sofascore_event_id"),
            "flashscore_mid": item.get("flashscore_mid"),
            "provider_fixture_id_name_match_only": fid,
            "provider_league": hit.get("league") if hit else None,
            "provider_kickoff_utc": kickoff.isoformat() if kickoff else None,
            "all_capture_receipts_before_provider_kickoff": capture_before,
            "clock_agrees_if_sofascore_displays_bogota": clock_agrees_if_bogota,
            "source_name_pair_unique": bool(hit),
            "source_browser_timezone_independently_attested": False,
            "source_provider_fixture_crosswalk_certified": False,
            "original_enriched_pit_features_certified": False,
            "production_p_matrix_authorized": False,
            "telegram_signal_authorized": False,
            "reason": (
                "PROVIDER_NAME_PAIR_NOT_FOUND_IN_LIMITED_SCOPE" if not hits
                else "PROVIDER_DUPLICATE_NAME_PAIR" if len(hits) > 1
                else "PRE_KICKOFF_SOURCE_CAPTURE_NOT_PROVEN" if not capture_before
                else "VISIBLE_CLOCK_DIFFERENT_OR_UNVERIFIED_TIMEZONE"
                   if not clock_agrees_if_bogota else
                     "CANDIDATE_ONLY_NEEDS_INDEPENDENT_TZ_IDENTITY_AND_PIT"
            ),
        })
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY_NO_PRODUCTION_PROMOTION",
        "target_date_bogota": day,
        "source_sha256": {
            "sofascore_flashscore_research": browser_sha256,
            "football_data_org_intake": intake_sha256,
        },
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "browser_candidate_count": len(rows),
        "provider_fixture_count": len(fixtures),
        "unique_provider_name_pair_matches": sum(r["source_name_pair_unique"] for r in rows),
        "prematch_three_source_name_clock_hints": sum(
            r["source_name_pair_unique"] and r["all_capture_receipts_before_provider_kickoff"]
            and r["clock_agrees_if_sofascore_displays_bogota"] for r in rows),
        "certified_provider_crosswalks": 0,
        "certified_original_pit_rows": 0,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "rows": rows,
    }

def load(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    if len(raw) > 3_000_000:
        raise ValueError("RESEARCH_SOURCE_TOO_LARGE")
    j = json.loads(raw)
    if not isinstance(j, dict):
        raise ValueError("RESEARCH_SOURCE_NOT_OBJECT")
    return j, hashlib.sha256(raw).hexdigest()

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--day", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    a = p.parse_args()
    browser = a.root / "evidence/football_calendar_physical" / a.day / "MATRIX_TWO_SOURCE_LINK_RESEARCH_LAST.json"
    intake = a.root / "evidence/football_world_inventory" / a.day / "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"
    b, bsha = load(browser)
    i, isha = load(intake)
    result = join(b, i, browser_sha256=bsha, intake_sha256=isha)
    output = browser.parent / "MATRIX_FOOTBALL_FREE_BROWSER_PROVIDER_RESEARCH_JOIN_LAST.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"day":a.day,"research_name_matches":result["unique_provider_name_pair_matches"],
                      "research_timed_hints":result["prematch_three_source_name_clock_hints"],
                      "certified":0,"signals":0},sort_keys=True))

if __name__ == "__main__":
    main()
