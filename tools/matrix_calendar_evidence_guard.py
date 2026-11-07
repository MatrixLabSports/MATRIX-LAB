"""Conservative validation for manually captured SofaScore/Flashscore calendars.

Calendar evidence is discovery only: it NEVER certifies odds or a bet.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse

DATE_RE = re.compile(r"^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{2})\s+(?P<rest>.+)$")
ID_RE = re.compile(r"#id:(\d+)$")
BLOCKED = ("cancelado", "cancelled", "aplazado", "postponed", "suspendido", "suspended")


def validate_sofascore_tennis_calendar_link(record: dict, target_date: str = "2026-10-31") -> dict | None:
    """Accept only date-matching event links; never infer timezone, surface or odds."""
    if not isinstance(record, dict):
        return None
    name, url = record.get("name"), record.get("url")
    if not isinstance(name, str) or not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.sofascore.com", "sofascore.com"}:
        return None
    if not parsed.path.startswith("/es/tennis/match/"):
        return None
    match = ID_RE.fullmatch("#" + parsed.fragment)
    date = DATE_RE.match(name.strip())
    if not match or not date:
        return None
    observed_date = f"20{date['year']}-{date['month']}-{date['day']}"
    if observed_date != target_date:
        return None
    status = "BLOCKED" if any(word in date["rest"].casefold() for word in BLOCKED) else "DISCOVERY_ONLY"
    return {
        "source": "SOFASCORE",
        "sport": "TENNIS",
        "date_label": observed_date,
        "event_id": match.group(1),
        "event_url": url,
        "display_text": name,
        "status": status,
        "timezone": None,
        "surface": None,
        "bookmaker_quote": None,
        "eligible_for_signal": False,
    }


def normalize_calendar_links(records: list[dict], target_date: str = "2026-10-31") -> dict:
    """Deduplicate by source event ID, reject conflicts and blocked fixtures."""
    unique = {}
    rejected = 0
    for record in records:
        row = validate_sofascore_tennis_calendar_link(record, target_date)
        if row is None:
            rejected += 1
            continue
        key = row["event_id"]
        if key in unique and unique[key]["event_url"] != row["event_url"]:
            unique[key]["status"] = "BLOCKED_CONFLICT"
        else:
            unique.setdefault(key, row)
    events = sorted(unique.values(), key=lambda row: int(row["event_id"]))
    return {"date": target_date, "events": events, "accepted": len(events),
            "blocked": sum(row["status"].startswith("BLOCKED") for row in events),
            "rejected": rejected, "signals_authorized": 0}
