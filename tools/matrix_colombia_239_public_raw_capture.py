"""Bounded, research-only Colombia Primera A public provider capture.

Provider IDs are never interchangeable with API-Football, SofaScore or Flashscore.
The report is an observation, not an official pre-match prediction or a bet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_BYTES = 2_000_000
SCHEMA = "MATRIX_COLOMBIA_239_PUBLIC_RAW_CAPTURE_V1"
PROVIDERS = {
    "ESPN": "https://site.api.espn.com/apis/site/v2/sports/soccer/col.1/scoreboard?dates={compact}&limit=30",
    "THESPORTSDB": "https://www.thesportsdb.com/api/v1/json/123/eventsday.php?d={date}&l=4497",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def utc(token: object) -> datetime:
    if not isinstance(token, str):
        raise ValueError("TIMESTAMP_MISSING")
    dt = datetime.fromisoformat(token.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def parse_espn(data: dict) -> list[dict]:
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("ESPN_EVENTS_ARRAY_REQUIRED")
    result, seen = [], set()
    for e in events:
        if not isinstance(e, dict):
            raise ValueError("ESPN_INVALID_EVENT")
        ident = str(e.get("id") or "")
        competition = (e.get("competitions") or [])
        if not re.fullmatch(r"[0-9]+", ident) or ident in seen or len(competition) != 1:
            raise ValueError("ESPN_ID_OR_COMPETITION_AMBIGUOUS")
        seen.add(ident)
        sides = competition[0].get("competitors") or []
        home = [x for x in sides if x.get("homeAway") == "home"]
        away = [x for x in sides if x.get("homeAway") == "away"]
        if len(home) != 1 or len(away) != 1:
            raise ValueError("ESPN_HOME_AWAY_AMBIGUOUS")
        ht, at = home[0].get("team") or {}, away[0].get("team") or {}
        hname = ht.get("displayName"); aname = at.get("displayName")
        if not hname or not aname or hname == aname:
            raise ValueError("ESPN_TEAM_NAMES_INVALID")
        kickoff = utc(e.get("date"))
        result.append({"provider_event_id": ident, "kickoff_utc": kickoff.isoformat(),
                       "home": str(hname), "away": str(aname),
                       "provider_status": (e.get("status") or {}).get("type", {}).get("name"),
                       "provider_native_identity_only": True,
                       "cross_provider_identity_certified": False})
    return result


def parse_tsdb(data: dict, target_date: str) -> list[dict]:
    if "events" not in data or data["events"] is not None and not isinstance(data["events"], list):
        raise ValueError("TSDB_EVENTS_ARRAY_REQUIRED")
    rows, seen = [], set()
    for e in data["events"] or []:
        if not isinstance(e, dict):
            raise ValueError("TSDB_INVALID_EVENT")
        ident = str(e.get("idEvent") or "")
        if (not re.fullmatch(r"[0-9]+", ident) or ident in seen
            or str(e.get("idLeague")) != "4497"
            or e.get("strSport") != "Soccer"
            or e.get("dateEvent") != target_date):
            raise ValueError("TSDB_EVENT_ID_LEAGUE_DATE_INVALID")
        seen.add(ident)
        home, away = e.get("strHomeTeam"), e.get("strAwayTeam")
        if not home or not away or home == away:
            raise ValueError("TSDB_TEAM_NAMES_INVALID")
        stamp = e.get("strTimestamp")
        kickoff = None
        time_quality = "MISSING_PROVIDER_TIMESTAMP"
        if stamp:
            try:
                kickoff = utc(stamp).isoformat()
                time_quality = "PROVIDER_TIMESTAMP_AWARE"
            except ValueError:
                time_quality = "UNZONED_PROVIDER_TIMESTAMP_NOT_CERTIFIED"
        # TheSportsDB may supply an API-Football ID. This is a *hint* until
        # independently joined to a genuine API-Football fixture document.
        cross_hint = str(e.get("idAPIfootball") or "")
        if not re.fullmatch(r"[0-9]+", cross_hint):
            cross_hint = None
        rows.append({"provider_event_id": ident, "kickoff_utc": kickoff,
                     "provider_reported_timestamp": stamp,
                     "timestamp_quality": time_quality,
                     "api_football_fixture_id_unverified_hint": cross_hint,
                     "home": home, "away": away,
                     "provider_status": e.get("strStatus"),
                     "provider_native_identity_only": True,
                     "cross_provider_identity_certified": False})
    return rows


def capture(day: str, *, opener=urlopen, observed_at_utc: datetime | None = None) -> tuple[dict, dict[str, bytes]]:
    date.fromisoformat(day)
    observed = observed_at_utc or datetime.now(timezone.utc)
    if observed.utcoffset() is None:
        raise ValueError("CAPTURE_CLOCK_UNAWARE")
    results, blobs = {}, {}
    for provider, template in PROVIDERS.items():
        url = template.format(date=day, compact=day.replace("-", ""))
        try:
            req = Request(url, headers={"Accept": "application/json",
                                       "User-Agent": "MATRIX-Research-Capture/1.0"})
            with opener(req, timeout=20) as response:
                status = int(response.status)
                raw = response.read(MAX_BYTES + 1)
            if status != 200 or len(raw) > MAX_BYTES:
                raise ValueError("PROVIDER_HTTP_OR_SIZE_INVALID")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("PROVIDER_JSON_OBJECT_REQUIRED")
            normalized = parse_espn(data) if provider == "ESPN" else parse_tsdb(data, day)
            key = sha(raw)
            blobs[provider] = raw
            results[provider] = {
                "status": "AUTHENTIC_RAW_CAPTURE_RESEARCH_ONLY",
                "url": url,
                "observed_at_utc": observed.astimezone(timezone.utc).isoformat(),
                "raw_sha256": key,
                "raw_bytes": len(raw),
                "provider_native_events": normalized,
                "provider_event_count": len(normalized),
                "raw_payload_verified": True,
                "cross_provider_event_identity_certified": False,
            }
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            results[provider] = {"status": "SOURCE_UNAVAILABLE_OR_INVALID",
                                 "reason": type(exc).__name__,
                                 "provider_event_count": None,
                                 "raw_payload_verified": False}
    report = {"schema": SCHEMA, "date_requested": day,
              "observed_at_utc": observed.astimezone(timezone.utc).isoformat(),
              "source_order": ["SOFASCORE", "FLASHSCORE", "ESPN", "THESPORTSDB"],
              "sources": results,
              "raw_verified_source_count": len(blobs),
              "browser_source_crossmatch_verified": False,
              "historical_features_pit_certified": False,
              "production_p_matrix_authorized": False,
              "telegram_signal_authorized": False,
              "automatic_wagering": False, "real_money": "BLOCKED"}
    return report, blobs


def persist(out: Path, report: dict, blobs: dict[str, bytes]) -> None:
    if set(out.parts) & {"telegram", "notifications", "governance", "daily_prematch_reports"}:
        raise ValueError("CAPTURE_CANNOT_WRITE_PRODUCTION")
    out.mkdir(parents=True, exist_ok=True)
    for provider, raw in blobs.items():
        digest = sha(raw)
        raw_path = out / ("COLOMBIA239_" + provider + "_" + digest + ".json")
        if raw_path.exists() and raw_path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_RAW_ARCHIVE_CONFLICT")
        if not raw_path.exists():
            raw_path.write_bytes(raw)
        if sha(raw_path.read_bytes()) != digest:
            raise ValueError("RAW_BYTES_NOT_PERSISTED_EXACTLY")
        report["sources"][provider]["raw_archive_path"] = raw_path.name
    (out / "MATRIX_COLOMBIA_239_PUBLIC_RAW_CAPTURE_LAST.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--out", type=Path, default=Path("evidence/research/colombia239"))
    args = parser.parse_args()
    report, blobs = capture(args.day)
    persist(args.out, report, blobs)
    print(json.dumps({"raw_verified": report["raw_verified_source_count"],
                      "provider_statuses": {k:v["status"] for k,v in report["sources"].items()},
                      "signal_authorized": False}, sort_keys=True))


if __name__ == "__main__":
    main()
