"""Authorized Windows CDP football calendar capture, research only.

Reads normal visible SofaScore and Flashscore pages; never makes provider API,
odds or bookmaker calls, never generates model inputs or probabilities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
OUT_ROOT = Path("evidence/football_calendar_physical")
SOURCES = {
    "SOFASCORE": ("www.sofascore.com", "/es/football/match/", "sofascore_visible_links.json"),
    "FLASHSCORE": ("www.flashscore.co", "/partido/futbol/", "flashscore_visible_links.json"),
}
LIMIT = 4500


def displayed_date(day: str, text: str) -> bool:
    d = date.fromisoformat(day)
    options = (
        f"{d.day:02d}/{d.month:02d}/{d.year % 100:02d}",
        f"{d.day:02d}/{d.month:02d}/{d.year}",
        f"{d.day:02d}.{d.month:02d}.{d.year}",
        f"{d.year}-{d.month:02d}-{d.day:02d}",
    )
    return any(re.search(r"(?<!\d)" + re.escape(s) + r"(?!\d)", text) for s in options)


def classify(day: str, source: str, rows: list, *, date_verified: bool,
             page_url: str, collected_at: datetime) -> dict:
    date.fromisoformat(day)
    if source not in SOURCES:
        raise ValueError("UNKNOWN_CALENDAR_PROVIDER")
    if not date_verified:
        raise ValueError("VISIBLE_SELECTED_DAY_NOT_CERTIFIED")
    if collected_at.utcoffset() is None:
        raise ValueError("CAPTURE_TIMEZONE_REQUIRED")
    host, prefix, _ = SOURCES[source]
    links, seen = [], set()
    for row in rows[:LIMIT]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "")
        p = urlparse(url)
        label = str(row.get("name") or "").strip()
        if p.scheme != "https" or p.hostname != host or not p.path.startswith(prefix):
            continue
        if p.username or p.password or url in seen:
            continue
        if source == "SOFASCORE":
            match = re.fullmatch(r"id:(\d+)", p.fragment)
            if not match or not displayed_date(day, label):
                continue
            id_data = {"sofascore_event_id": match.group(1)}
        else:
            # Only exact selected-day fixture rows, not news, H2H or sidebars.
            if row.get("is_calendar_row") is not True:
                continue
            mids = parse_qs(p.query).get("mid", [])
            id_data = {"flashscore_mid": mids[0] if len(mids)==1 and
                       re.fullmatch(r"[A-Za-z0-9]{8}", mids[0]) else None}
        seen.add(url)
        links.append({"url": url, "visible_name": label[:300], **id_data})
    return {
        "schema": "MATRIX_FOOTBALL_AUTHORIZED_VISIBLE_BROWSER_LINKS_V1",
        "source": source, "target_date_bogota": day,
        "captured_at_utc": collected_at.astimezone(timezone.utc).isoformat(),
        "observed_page_url": page_url, "selected_calendar_day_visible": True,
        "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
        "observed_link_count": len(links), "links": links,
        "capture_method": "USER_AUTHORIZED_WINDOWS_CDP_VISIBLE_DOM",
        "calendar_links_are_not_verified_kickoffs": True,
        "source_clock_timezone_certified": False,
        "independent_provider_crosswalk_certified": False,
        "canonical_prematch_inputs_authorized": False,
        "model_probability_generated": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }


def persist(root: Path, report: dict) -> dict:
    source, day = report["source"], report["target_date_bogota"]
    if source not in SOURCES or report.get("schema") != "MATRIX_FOOTBALL_AUTHORIZED_VISIBLE_BROWSER_LINKS_V1":
        raise ValueError("UNTRUSTED_BROWSER_SOURCE")
    if report.get("real_money") != "BLOCKED" or report.get("canonical_prematch_inputs_authorized") is not False:
        raise ValueError("UNTRUSTED_PRODUCTION_SCOPE")
    if not report.get("links") or len(report["links"]) != report.get("observed_link_count"):
        return {"source": source, "day": day, "status": "NO_ADMISSIBLE_VISIBLE_LINKS"}
    target = root / OUT_ROOT / day / SOURCES[source][2]
    target.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.fromisoformat(report["captured_at_utc"])
    if target.exists():
        old = target.read_bytes()
        previous = json.loads(old)
        if previous.get("source") != source or previous.get("target_date_bogota") != day:
            raise ValueError("PRIOR_CAPTURE_SOURCE_IDENTITY_MISMATCH")
        if datetime.fromisoformat(previous["captured_at_utc"]) >= now:
            return {"source": source, "day": day, "status": "OLDER_CAPTURE_REJECTED"}
        digest = hashlib.sha256(old).hexdigest()
        archived = target.parent / "archive" / (source.lower()+"_"+digest+".json")
        archived.parent.mkdir(exist_ok=True)
        if archived.exists() and archived.read_bytes() != old:
            raise ValueError("CAPTURE_ARCHIVE_HASH_MISMATCH")
        if not archived.exists():
            archived.write_bytes(old)
    target.write_text(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return {"source": source, "day": day, "status": "VISIBLE_RESEARCH_CAPTURE_PERSISTED",
            "observed_link_count": report["observed_link_count"]}


def capture(root: Path, endpoint: str, *, day: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright, Error
    today = date.fromisoformat(day) if day else datetime.now(BOGOTA).date()
    days = (today.isoformat(), (today+timedelta(days=1)).isoformat())
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint, timeout=12000)
        if not browser.contexts:
            raise ValueError("AUTHORIZED_CDP_CONTEXT_MISSING")
        for target in days:
            for source in ("SOFASCORE", "FLASHSCORE"):
                url = (f"https://www.sofascore.com/es/football/{target}" if source == "SOFASCORE"
                       else ("https://www.flashscore.co/manana/" if target == days[1]
                             else "https://www.flashscore.co/"))
                page = browser.contexts[0].new_page()
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=18000)
                    if response and response.status in (401, 403, 429):
                        results.append({"source": source, "day": target,
                                        "status": "SOURCE_ACCESS_DENIED", "http_status": response.status})
                        continue
                    report = None
                    for attempt in range(3):
                        page.wait_for_timeout(1200 if attempt == 0 else 1800)
                        info = page.evaluate("""() => ({
                          controls: Array.from(document.querySelectorAll(
                            '[class*="calendar__navigation"],[class*="calendar__datepicker"],' +
                            '[aria-haspopup="listbox"],[role="combobox"],time,input,button'
                          )).filter(e=>e.getClientRects().length).slice(0,1400).map(
                            e=>String(e.getAttribute('aria-label')||e.getAttribute('data-date')||
                              e.getAttribute('title')||e.getAttribute('datetime')||e.innerText||'').trim()
                          ),
                          links: Array.from(document.querySelectorAll('a[href]'))
                            .filter(e=>e.getClientRects().length).slice(0,4500).map(e=>({
                              url:e.href, name:String(e.innerText||e.getAttribute('aria-label')||'').trim(),
                              is_calendar_row:Boolean(e.closest('[class*="event__match"]')) &&
                                String(e.getAttribute('title')||e.getAttribute('aria-label')||'')
                                  .includes('click para detalles del partido')
                            }))
                        })""")
                        rows = info.get("links") or []
                        if source == "SOFASCORE":
                            date_ok = any(displayed_date(target, str(x.get("name") or ""))
                                          for x in rows)
                        else:
                            date_ok = any(displayed_date(target, str(x)) for x in info.get("controls") or [])
                        if not date_ok:
                            continue
                        report = classify(target, source, rows, date_verified=True,
                                          page_url=page.url,
                                          collected_at=datetime.now(timezone.utc))
                        break
                    if report is None:
                        results.append({"source": source, "day": target,
                                        "status": "VISIBLE_CALENDAR_DATE_NOT_VERIFIED"})
                    else:
                        results.append(persist(root, report))
                except (Error, OSError, ValueError, TypeError) as exc:
                    results.append({"source": source, "day": target,
                                    "status": "BROWSER_CAPTURE_BLOCKED", "error_type": type(exc).__name__})
                finally:
                    page.close()
    return {
        "schema": "MATRIX_FOOTBALL_AUTHORIZED_BROWSER_CAPTURE_CYCLE_V1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "days": list(days), "results": results,
        "provider_api_calls": 0, "odds_calls": 0, "model_parameters_modified": False,
        "canonical_prematch_inputs_authorized": False,
        "telegram_signal_authorized": False, "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--cdp", default="http://127.0.0.1:9222")
    args = parser.parse_args()
    result = capture(args.root, args.cdp)
    dest = args.root / "evidence/football_calendar_physical/MATRIX_BROWSER_CAPTURE_CYCLE_LAST.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
