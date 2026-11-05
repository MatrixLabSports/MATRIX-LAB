"""Verify individually dated Flashscore match-page observations (research only).

An event link or page calendar date is never evidence of the match kickoff.
This validator requires a visible match-page date-time, exact event MID, explicit
teams, a timezone declared by the capture, and pre-kickoff capture time. It cannot
authorize production models, quotes, Telegram, or wagering.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
SCHEMA = "MATRIX_FLASH_OPERA_INDIVIDUAL_DETAIL_CAPTURE_V1"
DATE_CLOCK = re.compile(r"^([0-3]?\d)\.([01]?\d)\.(20\d{2}) ([0-2]\d):([0-5]\d)$")


def utc(value):
    value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.utcoffset() is None:
        raise ValueError("FLASH_TIMESTAMP_WITHOUT_OFFSET")
    return value.astimezone(timezone.utc)


def verify(doc: dict, *, expected_day: str, now: datetime) -> dict:
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("FLASH_UNVERIFIED_DETAIL_SCHEMA")
    if (doc.get("source") != "FLASHSCORE"
        or doc.get("target_date_bogota") != expected_day
        or doc.get("capture_method") != "OPERA_CONNECTOR_ACCESSIBILITY_TREE"
        or doc.get("display_timezone") != "America/Bogota"
        or doc.get("signal_generation_authorized") is not False
        or doc.get("automatic_wagering") is not False
        or doc.get("real_money") != "BLOCKED"):
        raise ValueError("FLASH_UNTRUSTED_DETAIL_PROVENANCE")
    parsed = urlparse(str(doc.get("event_url") or ""))
    mids = parse_qs(parsed.query).get("mid", [])
    if (parsed.scheme != "https" or parsed.netloc != "www.flashscore.co"
        or not parsed.path.startswith("/partido/futbol/")
        or len(mids) != 1 or not re.fullmatch(r"[A-Za-z0-9]{8}", mids[0])
        or mids[0] != doc.get("event_mid")):
        raise ValueError("FLASH_UNTRUSTED_EVENT_ID")
    home, away = doc.get("home"), doc.get("away")
    if not all(isinstance(v, str) and len(v.strip()) >= 3 and len(v) < 150 for v in (home, away)):
        raise ValueError("FLASH_TEAMS_NOT_VERIFIED")
    m = DATE_CLOCK.fullmatch(str(doc.get("visible_event_datetime") or ""))
    if not m:
        raise ValueError("FLASH_INDIVIDUAL_DATETIME_NOT_VISIBLE")
    dd, mm, yyyy, hh, minute = map(int, m.groups())
    local = datetime(yyyy, mm, dd, hh, minute, tzinfo=BOGOTA)
    if local.date().isoformat() != expected_day:
        raise ValueError("FLASH_EVENT_DATE_MISMATCH")
    kickoff = local.astimezone(timezone.utc)
    capture = utc(doc.get("observed_at_utc"))
    if (now.tzinfo is None or not 0 <= (now.astimezone(timezone.utc) - capture).total_seconds() <= 86400
        or capture >= kickoff):
        raise ValueError("FLASH_STALE_FUTURE_OR_POST_KICKOFF_CAPTURE")
    return {
        "schema": "MATRIX_FLASH_INDIVIDUAL_DETAIL_VERIFIED_V1",
        "status": "FLASH_INDIVIDUAL_DATE_TIME_VERIFIED_RESEARCH_ONLY",
        "source": "FLASHSCORE", "target_date_bogota": expected_day,
        "event_mid": mids[0], "event_url": doc["event_url"],
        "home": home, "away": away,
        "kickoff_utc_from_declared_display_timezone": kickoff.isoformat(),
        "observed_at_utc": capture.isoformat(),
        "source_sha256": hashlib.sha256(json.dumps(doc, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "cross_provider_fixture_identity_verified": False,
        "model_probability_authorized": False, "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }


def scan(root: Path, day: str, *, now: datetime) -> dict:
    folder = root / "evidence/browser_capture_inbox/opera_football_flash_detail" / day
    accepted, rejected, seen = [], 0, set()
    for p in sorted(folder.glob("*.json"))[-64:]:
        try:
            raw = p.read_bytes()
            if not 0 < len(raw) <= 1_000_000:
                raise ValueError("FLASH_DETAIL_OVERSIZED")
            doc = json.loads(raw)
            result = verify(doc, expected_day=day, now=now)
            if result["event_mid"] in seen:
                continue
            seen.add(result["event_mid"])
            result["source_relpath"] = str(p.relative_to(root)).replace("\\\\", "/")
            result["source_file_sha256"] = hashlib.sha256(raw).hexdigest()
            accepted.append(result)
        except (ValueError, TypeError, KeyError, OSError):
            rejected += 1
    return {
        "schema": "MATRIX_FLASH_DETAIL_VERIFICATION_REPORT_V1",
        "target_date_bogota": day, "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "status": "RESEARCH_ONLY_NOT_TRIPLE_CERTIFIED" if accepted else "NO_VERIFIED_INDIVIDUAL_DETAILS",
        "verified_individual_count": len(accepted), "rejected_snapshot_count": rejected,
        "events": accepted, "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }
