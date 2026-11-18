"""Free TheSportsDB match-ID research after authorized SofaScore + Flashscore.

Conservative research bridge. No score model, PIT, price or Telegram authorization.
The free eventsday response may be capped to three events and is NOT world coverage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
SCHEMA = "MATRIX_FREE_THIRD_SOURCE_DUAL_BROWSER_RESEARCH_V1"
ROOT = Path("evidence/football_calendar_physical")
ENDPOINT = "https://www.thesportsdb.com/api/v1/json/123/eventsday.php"
MAX_BYTES = 2_000_000
ALIASES = {
    "gales": "wales", "dinamarca": "denmark", "noruega": "norway",
    "ucrania": "ukraine", "coritiba": "coritiba", "cruzeiro": "cruzeiro",
}

def normalize(value: str) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(x for x in s if not unicodedata.combining(x)).casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return ALIASES.get(s, s)

def aware(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("SOURCE_CAPTURE_TIMESTAMP_HAS_NO_ZONE")
    return dt.astimezone(timezone.utc)

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def source_research(folder: Path, day: str) -> tuple[dict, str]:
    f = folder / "MATRIX_TWO_SOURCE_LINK_RESEARCH_LAST.json"
    raw = f.read_bytes()
    data = json.loads(raw)
    if (data.get("schema") != "MATRIX_AUTHORIZED_FOOTBALL_DUAL_BROWSER_RESEARCH_LINKS_V1"
        or data.get("target_date_bogota") != day
        or data.get("status") != "RESEARCH_TWO_SOURCE_CANDIDATES_ONLY_NOT_CALENDAR_CERTIFIED"
        or data.get("real_money") != "BLOCKED"
        or data.get("production_p_matrix_authorized") is not False
        or data.get("telegram_signal_authorized") is not False
        or data.get("canonical_prematch_inputs_authorized") is not False):
        raise ValueError("TWO_BROWSER_SOURCE_NOT_AUTHORIZED_FOR_RESEARCH")
    rows = data.get("research_candidates")
    if not isinstance(rows, list) or len(rows) != data.get("research_candidate_count"):
        raise ValueError("TWO_BROWSER_RESEARCH_COUNT_MISMATCH")
    digests = data.get("source_sha256") or {}
    for provider, filename in (("sofascore", "sofascore_visible_links.json"),
                               ("flashscore", "flashscore_visible_links.json")):
        if not re.fullmatch("[0-9a-f]{64}", str(digests.get(provider) or "")):
            raise ValueError("BROWSER_CAPTURE_HASH_MISSING")
        if sha((folder / filename).read_bytes()) != digests[provider]:
            raise ValueError("BROWSER_CAPTURE_HASH_CHANGED_AFTER_CROSSMATCH")
        aware(data["source_capture_at_utc"][provider])
    keys = [(str(r.get("sofascore_event_id")), str(r.get("flashscore_mid")))
            for r in rows if isinstance(r, dict)]
    if len(keys) != len(rows) or len(set(keys)) != len(keys):
        raise ValueError("DUPLICATE_BROWSER_IDENTITY")
    return data, sha(raw)

def research(browser: dict, provider: dict, *, observed_at_utc: datetime,
             browser_sha256: str, provider_sha256: str) -> dict:
    day = str(browser["target_date_bogota"])
    date.fromisoformat(day)
    now = observed_at_utc.astimezone(timezone.utc)
    if observed_at_utc.tzinfo is None:
        raise ValueError("PROVIDER_CAPTURE_TIMESTAMP_HAS_NO_ZONE")
    if not isinstance(provider, dict) or not isinstance(provider.get("events"), list):
        raise ValueError("FREE_PROVIDER_EVENTS_ARRAY_MISSING")
    events = provider["events"]
    index: dict[tuple[str, str], list[dict]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        if (event.get("dateEvent") != day or event.get("strSport") != "Soccer"
            or not re.fullmatch(r"[0-9]+", str(event.get("idEvent") or ""))):
            continue
        key = (normalize(event.get("strHomeTeam")), normalize(event.get("strAwayTeam")))
        if all(key):
            index.setdefault(key, []).append(event)
    matches, rows = 0, []
    for candidate in browser["research_candidates"]:
        key = (normalize(candidate["home_normalized"]), normalize(candidate["away_normalized"]))
        hits = index.get(key, [])
        hit = hits[0] if len(hits) == 1 else None
        event_id = hit.get("idEvent") if hit else None
        status = hit.get("strStatus") if hit else None
        time_consistent = False
        future_under_provider_clock = False
        timestamp = hit.get("strTimestamp") if hit else None
        if hit:
            matches += 1
            try:
                # TheSportsDB's strTimestamp is documented as UTC but contains no suffix.
                # SofaScore's display timezone was NOT captured, so equality is a
                # research comparison, never a certified two-source kickoff.
                if not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}", str(timestamp)):
                    raise ValueError("NO_UNAMBIGUOUS_PROVIDER_TIMESTAMP")
                ts = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
                displayed = str(candidate.get("sofascore_visible_clock_unverified_timezone") or "")
                time_consistent = (ts.astimezone(BOGOTA).strftime("%H:%M") == displayed)
                future_under_provider_clock = now < ts
            except (ValueError, TypeError):
                pass
        rows.append({
            "sofascore_event_id": candidate["sofascore_event_id"],
            "flashscore_mid": candidate["flashscore_mid"],
            "home": candidate["home_normalized"], "away": candidate["away_normalized"],
            "thesportsdb_event_id_name_match_only": event_id,
            "thesportsdb_api_football_crossref_unverified": hit.get("idAPIfootball") if hit else None,
            "thesportsdb_league": hit.get("strLeague") if hit else None,
            "thesportsdb_status": status,
            "thesportsdb_timestamp_unzoned_claimed_utc": timestamp,
            "clock_consistent_if_sofa_is_bogota": time_consistent,
            "future_if_provider_timestamp_is_utc": future_under_provider_clock,
            "research_identity_only": bool(hit),
            "calendar_kickoff_certified": False,
            "original_enriched_pit_verified": False,
            "six_league_prospective_certified": False,
            "production_p_matrix_authorized": False,
            "telegram_signal_authorized": False,
            "reason": ("PROVIDER_DUPLICATE_NAME_MATCH" if len(hits)>1 else
                       "NO_FREE_PROVIDER_NAME_MATCH_IN_CAPPED_RESPONSE" if not hit else
                       "PROVIDER_ALREADY_STARTED_OR_FINISHED" if status != "NS" or not future_under_provider_clock else
                       "TIMEZONE_AND_ORIGINAL_PIT_STILL_UNVERIFIED"),
        })
    return {
        "schema": SCHEMA, "status": "RESEARCH_THIRD_SOURCE_MATCHES_ONLY_NO_PRODUCTION",
        "target_date_bogota": day, "observed_at_utc": now.isoformat(),
        "research_browser_candidate_count": len(browser["research_candidates"]),
        "free_provider_returned_event_count": len(events),
        "provider_name_match_count": matches,
        "provider_name_no_match_in_response_count": len(rows)-matches,
        "provider_unique_unstarted_name_matches": sum(
            1 for x in rows if x["research_identity_only"] and x["thesportsdb_status"] == "NS"
            and x["future_if_provider_timestamp_is_utc"]),
        "time_consistent_research_matches": sum(1 for x in rows if x["clock_consistent_if_sofa_is_bogota"]),
        "strict_triple_source_certified_count": 0, "pit_complete_count": 0,
        "producer_authorized": False, "telegram_signal_authorized": False,
        "source_priority": ["SofaScore", "Flashscore", "TheSportsDB"],
        "free_eventsday_globally_exhaustive": False,
        "reported_provider_clock_is_utc_but_unzoned": True,
        "sofascore_display_timezone_certified": False,
        "source_sha256": {"browser_crossmatch": browser_sha256,
                          "thesportsdb_response": provider_sha256},
        "rows": rows, "automatic_wagering": False, "real_money": "BLOCKED",
    }

def fetch_free_day(day: str, *, opener=urlopen) -> tuple[dict, str]:
    url = ENDPOINT + "?" + urlencode({"d": day, "s": "Soccer"})
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with opener(req, timeout=20) as response:
            if int(response.status) != 200:
                raise ValueError("FREE_PROVIDER_HTTP_NON_200")
            raw = response.read(MAX_BYTES+1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise ValueError("FREE_PROVIDER_UNAVAILABLE_FAIL_CLOSED") from exc
    if len(raw) > MAX_BYTES:
        raise ValueError("FREE_PROVIDER_RESPONSE_TOO_LARGE")
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("FREE_PROVIDER_RESPONSE_NOT_JSON") from exc
    return parsed, sha(raw)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    date.fromisoformat(args.day)
    folder = args.root / ROOT / args.day
    browser, browser_hash = source_research(folder, args.day)
    provider, provider_hash = fetch_free_day(args.day)
    report = research(browser, provider, observed_at_utc=datetime.now(timezone.utc),
                      browser_sha256=browser_hash, provider_sha256=provider_hash)
    dest = folder / "MATRIX_FREE_THIRD_SOURCE_RESEARCH_LAST.json"
    dest.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)+"\\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "day":args.day,
        "browser_pairs":report["research_browser_candidate_count"],
        "free_provider_name_matches":report["provider_name_match_count"],
        "future_name_matches":report["provider_unique_unstarted_name_matches"],
        "certified":0,"signals":0,"real_money":"BLOCKED"},sort_keys=True))

if __name__ == "__main__":
    main()
