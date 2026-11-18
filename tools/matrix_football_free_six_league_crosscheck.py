"""Six original-league research-only TheSportsDB expansion after both browser receipts.

The free global eventsday endpoint is capped. Six *documented league-filtered*
calls improve opportunities to see a fixture, never certify world coverage.
A matched league fixture is not original API-Football identity, PIT or P_MATRIX.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tools.matrix_football_free_third_source_research import (
    ROOT, BOGOTA, ENDPOINT, MAX_BYTES, normalize, sha, source_research,
)

# Original API-Football competition namespace -> TheSportsDB league namespace.
# Competition mapping NEVER implies an event identity crosswalk.
LEAGUES = (
    ("39", "4328", "English Premier League"),
    ("61", "4334", "French Ligue 1"),
    ("78", "4331", "German Bundesliga"),
    ("135", "4332", "Italian Serie A"),
    ("140", "4335", "Spanish La Liga"),
    ("239", "4497", "Colombian Liga DIMAYOR"),
)
SCHEMA = "MATRIX_FREE_ORIGINAL_SIX_LEAGUE_LINK_RESEARCH_V1"

def permitted_scope(now: datetime) -> tuple[str, ...]:
    """At most three league-filtered calls per operational day per half-hour.

    Alternates all six across consecutive 30-minute schedule slots, never
    claims that deferred leagues returned zero events. Handles 429 separately.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("RATE_BUDGET_NEEDS_AWARE_TIME")
    bucket = now.astimezone(timezone.utc).minute // 30
    return tuple(item[1] for idx, item in enumerate(LEAGUES) if idx % 2 == bucket)

def fetch_league(day: str, league_id: str, *, opener=urlopen) -> tuple[dict, bytes]:
    date.fromisoformat(day)
    if league_id not in {row[1] for row in LEAGUES}:
        raise ValueError("LEAGUE_NOT_IN_APPROVED_SIX")
    url = ENDPOINT + "?" + urlencode({"d": day, "l": league_id})
    try:
        with opener(Request(url, headers={"Accept": "application/json"}), timeout=20) as response:
            if int(response.status) != 200:
                raise ValueError("FREE_PROVIDER_HTTP_NON_200")
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        raise ValueError("FREE_PROVIDER_LEAGUE_HTTP_" + str(exc.code)) from exc
    except (URLError, OSError, TimeoutError) as exc:
        raise ValueError("FREE_PROVIDER_LEAGUE_NETWORK_" + type(exc).__name__) from exc
    if len(raw) > MAX_BYTES:
        raise ValueError("FREE_PROVIDER_RESPONSE_TOO_LARGE")
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("FREE_PROVIDER_INVALID_JSON") from exc
    if not isinstance(obj, dict) or "events" not in obj:
        raise ValueError("FREE_PROVIDER_NO_EVENTS_KEY")
    if obj["events"] is not None and not isinstance(obj["events"], list):
        raise ValueError("FREE_PROVIDER_EVENTS_NOT_ARRAY")
    return obj, raw

def validate_provider(day: str, league_id: str, doc: dict) -> list[dict]:
    arr = doc.get("events")
    if arr is None:
        return []
    if not isinstance(arr, list):
        raise ValueError("FREE_PROVIDER_EVENTS_NOT_ARRAY")
    result, seen = [], set()
    for event in arr:
        if not isinstance(event, dict):
            raise ValueError("INVALID_EVENT_ROW")
        if (str(event.get("idLeague") or "") != league_id
            or event.get("dateEvent") != day or event.get("strSport") != "Soccer"):
            raise ValueError("EVENT_OUTSIDE_REQUESTED_LEAGUE_OR_DAY")
        event_id = str(event.get("idEvent") or "")
        if not re.fullmatch("[0-9]+", event_id) or event_id in seen:
            raise ValueError("PROVIDER_EVENT_ID_MISSING_OR_DUPLICATE")
        if not all((normalize(event.get("strHomeTeam")),
                    normalize(event.get("strAwayTeam")))):
            raise ValueError("PROVIDER_TEAM_NAMES_MISSING")
        seen.add(event_id)
        result.append(event)
    return result

def assemble(browser: dict, source_rows: dict[str, list[dict]], *,
             seen_at: datetime, receipts: dict) -> dict:
    if seen_at.tzinfo is None or seen_at.utcoffset() is None:
        raise ValueError("OBSERVATION_MUST_BE_TIMEZONE_AWARE")
    day = browser["target_date_bogota"]
    source_map = {r[1]: r[0] for r in LEAGUES}
    idx: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    for league_id, rows in source_rows.items():
        if league_id not in source_map:
            raise ValueError("UNAPPROVED_SOURCE_LEAGUE")
        for e in rows:
            if str(e.get("idLeague") or "") != league_id:
                raise ValueError("MISMATCHED_LEAGUE_IN_ASSEMBLY")
            key = (normalize(e["strHomeTeam"]), normalize(e["strAwayTeam"]))
            idx.setdefault(key, []).append((league_id, e))
    output = []
    for row in browser["research_candidates"]:
        key = (normalize(row["home_normalized"]), normalize(row["away_normalized"]))
        hits = idx.get(key, [])
        hit = hits[0] if len(hits) == 1 else None
        league = hit[0] if hit else None
        e = hit[1] if hit else None
        stamp = str(e.get("strTimestamp") or "") if e else None
        clock_match = False
        future = False
        if e and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", stamp):
            event_dt = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
            clock_match = event_dt.astimezone(BOGOTA).strftime("%H:%M") == str(
                row.get("sofascore_visible_clock_unverified_timezone") or "")
            future = seen_at.astimezone(timezone.utc) < event_dt
        output.append({
            "sofascore_event_id": row["sofascore_event_id"],
            "flashscore_mid": row["flashscore_mid"],
            "home": row["home_normalized"], "away": row["away_normalized"],
            "thesportsdb_event_id_name_only": str(e["idEvent"]) if e else None,
            "source_league_id": league,
            "original_league_id_hint_not_fixture_certification": source_map.get(league),
            "provider_status": e.get("strStatus") if e else None,
            "provider_clock_as_reported_no_zone": stamp,
            "clock_matches_if_sofascore_displays_bogota": clock_match,
            "provider_event_is_future_if_utc": future,
            "provider_unique_name_match": bool(e),
            "research_future_candidate_only": bool(e and e.get("strStatus") == "NS" and future),
            "fixture_identity_certified": False,
            "sofascore_timezone_certified": False,
            "original_enriched_pit_verified": False,
            "original_six_league_30_each_validated": False,
            "production_p_matrix_authorized": False,
            "telegram_signal_authorized": False,
            "reason": ("SOURCE_NAME_AMBIGUITY" if len(hits)>1 else
                       "NOT_RETURNED_IN_FREE_LEAGUE_RESPONSE" if not e else
                       "PROVIDER_NOT_UNSTARTED_OR_TIMESTAMP_PAST" if e.get("strStatus") != "NS" or not future else
                       "NEEDS_INDEPENDENT_KICKOFF_AND_ORIGINAL_PIT"),
        })
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY_NO_CALENDAR_OR_MODEL_CERTIFICATION",
        "target_date_bogota": day, "observed_at_utc": seen_at.astimezone(timezone.utc).isoformat(),
        "source_order": ["SofaScore", "Flashscore", "TheSportsDB"],
        "source_receipts": receipts,
        "free_provider_league_filtered_requests": sum(
            1 for x in receipts.values()
            if x.get("status") in ("FREE_LEAGUE_SOURCE_BLOCKED",
                                   "AUTHENTIC_FREE_LEAGUE_CAPTURE_RESEARCH_ONLY")),
        "six_league_sources": [
            {"original_league_id": original, "thesportsdb_league_id": tsdb,
             "name": label, "response_rows": len(source_rows[tsdb]) if tsdb in source_rows else None,
             "provider_call_complete": tsdb in source_rows}
            for original, tsdb, label in LEAGUES
        ],
        "two_browser_candidates": len(browser["research_candidates"]),
        "league_scoped_name_matches": sum(x["provider_unique_name_match"] for x in output),
        "future_research_name_matches": sum(x["research_future_candidate_only"] for x in output),
        "kickoff_and_identity_certified": 0, "pit_certified": 0,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "free_api_results_world_complete": False,
        "events_not_returned_are_not_claimed_absent": True,
        "source_competition_ids_are_not_fixture_ids": True,
        "rows": output, "real_money": "BLOCKED", "automatic_wagering": False,
    }

def persist_raw(folder: Path, league_id: str, raw: bytes) -> dict:
    expected = sha(raw)
    target = folder / ("MATRIX_THESPORTSDB_DAY_LEAGUE_" + league_id + "_RAW.json")
    if target.exists():
        previous = target.read_bytes()
        old_hash = sha(previous)
        if old_hash != expected:
            saved = folder / "archive" / ("thesportsdb_league_" + league_id + "_" + old_hash + ".json")
            saved.parent.mkdir(parents=True, exist_ok=True)
            if saved.exists() and saved.read_bytes() != previous:
                raise ValueError("FREE_PROVIDER_ARCHIVE_HASH_CONFLICT")
            if not saved.exists():
                saved.write_bytes(previous)
    target.write_bytes(raw)
    if sha(target.read_bytes()) != expected:
        raise ValueError("FREE_PROVIDER_RAW_HASH_MISMATCH")
    return {"path": str(target.as_posix()), "sha256": expected, "bytes": len(raw)}

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    date.fromisoformat(args.day)
    folder = args.root / ROOT / args.day
    browser, browser_digest = source_research(folder, args.day)
    observations, receipts = {}, {}
    selected = permitted_scope(datetime.now(timezone.utc))
    provider_rate_limited = False
    for original, league_id, name in LEAGUES:
        if league_id not in selected:
            receipts[league_id] = {
                "status": "DEFERRED_BY_RATE_BUDGET_NEXT_30M_SLOT",
                "reason": "NOT_QUERIED_IN_THIS_CYCLE",
                "source_event_count": None,
            }
            continue
        if provider_rate_limited:
            receipts[league_id] = {
                "status": "SKIPPED_AFTER_PROVIDER_HTTP_429",
                "reason": "FREE_PROVIDER_QUOTA_NO_FURTHER_REQUESTS_THIS_CYCLE",
                "source_event_count": None,
            }
            continue
        try:
            doc, raw = fetch_league(args.day, league_id)
            valid = validate_provider(args.day, league_id, doc)
            receipt = persist_raw(folder, league_id, raw)
            observations[league_id] = valid
            receipts[league_id] = {
                **receipt, "status": "AUTHENTIC_FREE_LEAGUE_CAPTURE_RESEARCH_ONLY",
                "source_event_count": len(valid), "null_events_response": doc["events"] is None
            }
        except (ValueError, TypeError) as exc:
            reason = str(exc)[:160]
            if reason == "FREE_PROVIDER_LEAGUE_HTTP_429":
                provider_rate_limited = True
            receipts[league_id] = {
                "status": "FREE_LEAGUE_SOURCE_BLOCKED",
                "reason": reason, "source_event_count": None,
            }
    report = assemble(browser, observations, seen_at=datetime.now(timezone.utc),
                      receipts=receipts)
    report["browser_research_sha256"] = browser_digest
    report["free_provider_half_hour_scope"] = list(selected)
    report["free_provider_calls_budget_per_day_this_cycle"] = 3
    report["six_original_league_sources_examined_this_cycle"] = len(selected)
    report["all_six_leagues_queried_in_this_cycle"] = False
    report["free_provider_rate_limit_hit"] = provider_rate_limited
    report["free_provider_error_counts"] = {
        key: sum(1 for x in receipts.values() if x.get("reason") == key)
        for key in sorted({x.get("reason") for x in receipts.values() if x.get("reason")})
    }
    dest = folder / "MATRIX_FREE_SIX_LEAGUE_RESEARCH_LAST.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "day": args.day, "sources_attempted": len(LEAGUES),
        "sources_with_receipt": sum(x["status"] == "AUTHENTIC_FREE_LEAGUE_CAPTURE_RESEARCH_ONLY"
                                    for x in receipts.values()),
        "candidates": report["two_browser_candidates"],
        "league_matches": report["league_scoped_name_matches"],
        "futures": report["future_research_name_matches"],
        "certified": 0, "telegram_signals": 0
    }, sort_keys=True))

if __name__ == "__main__":
    main()
