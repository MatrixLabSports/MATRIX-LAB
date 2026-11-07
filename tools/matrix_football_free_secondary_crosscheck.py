"""Bounded secondary free-football calendar crosscheck for MATRIX.

TheSportsDB's public v1 eventsday endpoint has a restrictive free result cap.
This is a supplementary, read-only evidence source AFTER SofaScore/Flashscore.
Never creates p_matrix, inferred source IDs, prices, or Telegram signals.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
ENDPOINT = "https://www.thesportsdb.com/api/v1/json/123/eventsday.php"
MAX_BYTES = 1_000_000
MAX_CALLS = 2  # UTC day and next UTC day; never retry a rate limit.
SCHEMA = "MATRIX_FREE_SECONDARY_FOOTBALL_CROSSCHECK_V1"


def stamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def norm(name):
    if not isinstance(name, str):
        return ""
    s = unicodedata.normalize("NFKD", name.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", s))


def crosscheck(intake, responses, *, target_day, observed_at):
    """Only fully equal teams AND native kickoff may count as a crosscheck."""
    date.fromisoformat(target_day)
    if (not isinstance(intake, dict) or intake.get("schema") != "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or intake.get("target_date_bogota") != target_day
        or intake.get("source") != "FOOTBALL_DATA_ORG"
        or intake.get("real_money") != "BLOCKED"
        or intake.get("signal_generation_authorized") is not False):
        raise ValueError("SECONDARY_UNTRUSTED_PRIMARY_INTAKE")
    fixtures = intake.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("SECONDARY_PRIMARY_FIXTURES_NOT_ARRAY")
    if not isinstance(responses, list):
        raise ValueError("SECONDARY_RESPONSES_NOT_ARRAY")
    if len(responses) > MAX_CALLS:
        raise ValueError("SECONDARY_RATE_BUDGET_EXCEEDED")
    indexed = {}
    provenance = []
    seen_ids = set()
    for entry in responses:
        if not isinstance(entry, dict):
            raise ValueError("SECONDARY_RESPONSE_NOT_OBJECT")
        provenance.append({k: entry.get(k) for k in ("query_day_utc", "http_status",
                   "response_sha256", "response_bytes", "provider_status", "event_count")})
        for event in entry.get("events") or []:
            if not isinstance(event, dict):
                continue
            native_id = str(event.get("idEvent") or "")
            if not native_id.isdecimal() or native_id in seen_ids:
                continue
            seen_ids.add(native_id)
            if str(event.get("strSport") or "").casefold() != "soccer":
                continue
            home = norm(event.get("strHomeTeam"))
            away = norm(event.get("strAwayTeam"))
            kickoff = stamp(event.get("strTimestamp"))
            if not home or not away or home == away or kickoff is None:
                continue  # No guessed times, venues or fuzzy matches.
            if kickoff.astimezone(BOGOTA).date().isoformat() != target_day:
                continue
            key = (home, away, kickoff)
            indexed.setdefault(key, []).append(native_id)
    matches, rejected = [], []
    known_primary = set()
    for row in fixtures:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("source_fixture_id") or "")
        key = (norm(row.get("home")), norm(row.get("away")), stamp(row.get("kickoff_utc")))
        if not fid or fid in known_primary:
            raise ValueError("SECONDARY_DUPLICATE_PRIMARY_ID")
        known_primary.add(fid)
        options = indexed.get(key, [])
        if len(options) == 1:
            matches.append({"source_fixture_id": fid,
                "secondary_event_id": options[0],
                "kickoff_utc": key[2].isoformat(),
                "identity_rule": "EXACT_HOME_AWAY_AND_UTC_KICKOFF",
                "match_status": "SECONDARY_EVENT_CORROBORATION_ONLY"})
        else:
            rejected.append({"source_fixture_id": fid,
                "reason": "NO_EXACT_SECONDARY_EVENT" if not options else "AMBIGUOUS_SECONDARY_EVENT"})
    matches.sort(key=lambda x: x["source_fixture_id"])
    return {
        "schema": SCHEMA, "target_date_bogota": target_day,
        "observed_at_utc": observed_at,
        "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
        "secondary_provider": "THESPORTSDB_PUBLIC_V1_FREE",
        "secondary_source_scope": "MAX_THREE_FREE_EVENTS_PER_QUERY_NOT_GLOBAL_COVERAGE",
        "primary_fixture_count": len(fixtures),
        "verified_identity_hint_count": len(matches),
        "matched": matches, "rejected": rejected,
        "sources": provenance,
        "status": "SECONDARY_CALENDAR_CHECK_ONLY_NO_MODEL_OR_QUOTES",
        "historical_feature_equivalence_verified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED"
    }


def capture(target_day, *, opener=urlopen, now=None):
    """At most two public GET requests; never retry 403, 429 or any error."""
    d = date.fromisoformat(target_day)
    out = []
    for utc_day in (d, d + timedelta(days=1)):
        query_day = utc_day.isoformat()
        url = ENDPOINT + "?" + urlencode({"d": query_day, "s": "Soccer"})
        item = {"query_day_utc": query_day, "events": [],
                "event_count": 0, "provider_status": "UNAVAILABLE"}
        try:
            with opener(Request(url, headers={"Accept": "application/json"}),
                        timeout=15) as response:
                item["http_status"] = int(response.status)
                raw = response.read(MAX_BYTES + 1)
            item["response_bytes"] = len(raw)
            item["response_sha256"] = hashlib.sha256(raw).hexdigest()
            if item["http_status"] != 200 or len(raw) > MAX_BYTES:
                item["provider_status"] = "HTTP_OR_SIZE_BLOCKED"
            else:
                payload = json.loads(raw.decode("utf-8"))
                events = payload.get("events") if isinstance(payload, dict) else None
                if isinstance(events, list):
                    item["events"] = events
                    item["event_count"] = len(events)
                    item["provider_status"] = "PUBLIC_EVENTS_RESPONSE"
                else:
                    item["provider_status"] = "EMPTY_OR_INVALID_EVENTS"
        except HTTPError as exc:
            item["http_status"] = exc.code
            item["provider_status"] = "RATE_LIMITED_NO_RETRY" if exc.code == 429 else "HTTP_ERROR_NO_RETRY"
        except (OSError, URLError, TimeoutError, ValueError, UnicodeError, TypeError):
            item["provider_status"] = "NETWORK_OR_FORMAT_ERROR_NO_RETRY"
        out.append(item)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if any(part in args.out.parts for part in ("daily_prematch_reports",
                                              "telegram", "tennis_signals", "governance")):
        raise SystemExit("SECONDARY_SOURCE_CANNOT_WRITE_PRODUCTION")
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    observed = datetime.now(timezone.utc).isoformat()
    document = crosscheck(intake, capture(args.date),
                          target_day=args.date, observed_at=observed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": document["status"],
                      "matched": document["verified_identity_hint_count"],
                      "primary_fixtures": document["primary_fixture_count"],
                      "providers": [row["provider_status"] for row in document["sources"]],
                      "telegram_signal_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
