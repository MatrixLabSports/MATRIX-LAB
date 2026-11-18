"""Read only the visible Flashscore match-page clock after SofaScore browser proof.

Independent *display* comparison, never an actual UTC timezone assertion.
No backstage APIs, anti-bot bypass, betting odds, holdout writes or model promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path("evidence/tennis_calendar_physical")
SCHEMA = "MATRIX_TENNIS_FLASHSCORE_AUTHORIZED_VISIBLE_CLOCK_RESEARCH_V1"
CLOCK = re.compile(r"(?m)^\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{1,2}:\d{2})\s*$")

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def load(path: Path) -> tuple[dict, str]:
    data = path.read_bytes()
    if len(data) > 9_000_000:
        raise ValueError("MATCH_DETAILS_TOO_LARGE")
    doc = json.loads(data)
    if not isinstance(doc, dict):
        raise ValueError("MATCH_DETAILS_NOT_OBJECT")
    return doc, digest(data)

def clock_from_visible(text: str, day: str) -> tuple[str | None, str]:
    """Accept a single literal complete date+clock line; never infer from scores."""
    target = date.fromisoformat(day).strftime("%d.%m.%Y")
    matches = [(d, h) for d, h in CLOCK.findall(str(text or "")) if d == target]
    values = set()
    for d, h in matches:
        try:
            parsed = datetime.strptime(d + " " + h, "%d.%m.%Y %H:%M")
        except ValueError:
            continue
        values.add(parsed.strftime("%d.%m.%Y %H:%M"))
    if len(values) == 1:
        return next(iter(values)), "UNIQUE_VISIBLE_DATE_TIME_NO_TIMEZONE"
    if len(values) > 1:
        return None, "AMBIGUOUS_VISIBLE_MATCH_CLOCK"
    return None, "VISIBLE_MATCH_CLOCK_NOT_FOUND"

def normalized_visible_clock(clock: str) -> str:
    """Normalize strictly visible 6:30 and 06:30 without inferring timezone."""
    if not re.fullmatch(r"\d{1,2}:\d{2}", str(clock or "")):
        raise ValueError("LOCAL_VISIBLE_CLOCK_NOT_HH_MM")
    try:
        return datetime.strptime(clock, "%H:%M").strftime("%H:%M")
    except ValueError as exc:
        raise ValueError("LOCAL_VISIBLE_CLOCK_INVALID") from exc

def exact_match_page(url: str, mid: str) -> bool:
    p = urlparse(url)
    ids = parse_qs(p.query).get("mid") or []
    parts = [v for v in p.path.split("/") if v]
    return (p.scheme == "https" and p.netloc in ("www.flashscore.co","flashscore.co")
            and len(parts) == 4 and parts[:2] == ["partido","tenis"]
            and ids == [mid] and bool(re.fullmatch("[a-zA-Z0-9]{6,16}",mid))
            and p.username is None and p.password is None)

def research(root: Path, day: str, endpoint: str, *, max_events: int = 6) -> dict:
    from playwright.sync_api import Error, sync_playwright
    date.fromisoformat(day)
    if not 1 <= max_events <= 12:
        raise ValueError("MAX_EVENTS_LIMIT_INVALID")
    detail, detail_hash = load(root/BASE/day/"sofascore_verified_match_details.json")
    if (detail.get("schema") != "MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or detail.get("target_date_bogota") != day
        or detail.get("real_money") != "BLOCKED"
        or detail.get("new_model_observations_admitted") != 0
        or detail.get("telegram_signal_authorized") is not False):
        raise ValueError("SOURCE_DETAILS_UNTRUSTED")
    observed = datetime.fromisoformat(detail["observed_at_utc"].replace("Z","+00:00"))
    if observed.tzinfo is None:
        raise ValueError("SOURCE_DETAILS_TIMEZONE_MISSING")
    records = []
    seen = set()
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(endpoint, timeout=20000)
        if not browser.contexts:
            raise ValueError("USER_AUTHORIZED_BROWSER_MISSING")
        for event in (detail.get("events") or [])[:max_events]:
            sid = str(event["sofascore_event_id"])
            mid = str(event["flashscore_mid"])
            url = str(event["flashscore_url"])
            if sid in seen:
                raise ValueError("DUPLICATED_SOFA_EVENT_IN_DETAILS")
            seen.add(sid)
            if not exact_match_page(url,mid):
                raise ValueError("INVALID_FLASH_SCORE_PAGE_IDENTITY")
            kickoff = datetime.fromisoformat(event["kickoff_utc"].replace("Z","+00:00"))
            if kickoff.tzinfo is None or observed >= kickoff:
                raise ValueError("SOURCE_WAS_NOT_PRE_KICKOFF")
            entry = {
                "sofascore_id": sid,
                "flashscore_mid": mid,
                "flashscore_url": url,
                "source_detail_kickoff_utc": kickoff.isoformat(),
                "source_sofascore_visible_local_clock": str(event.get("local_visible_time") or ""),
                "flashscore_visible_match_datetime": None,
                "flashscore_visible_page_sha256": None,
                "flashscore_visible_capture_utc": None,
                "flashscore_display_agrees_if_same_timezone": None,
                "flashscore_timezone_explicitly_attested": False,
                "cross_provider_kickoff_utc_certified": False,
                "current_pit_verified": False,
                "official_holdout_admitted": False,
                "research_status": "NOT_OBSERVED",
            }
            page = browser.contexts[0].new_page()
            try:
                response = page.goto(url, wait_until="domcontentloaded",timeout=16000)
                if response and response.status in (401,403,429):
                    entry["research_status"] = "PROVIDER_RESTRICTED_" + str(response.status)
                    records.append(entry)
                    continue
                page.wait_for_timeout(900)
                body = page.locator("body").inner_text(timeout=8000)
                observed_at = datetime.now(timezone.utc)
                entry["flashscore_visible_capture_utc"] = observed_at.isoformat()
                entry["flashscore_visible_page_sha256"] = digest(body.encode("utf-8"))
                if observed_at >= kickoff:
                    entry["research_status"] = "FLASH_CAPTURE_AFTER_MATCH_START"
                elif urlparse(page.url).path != urlparse(url).path:
                    entry["research_status"] = "REDIRECT_WRONG_MATCH_PATH"
                else:
                    value, status = clock_from_visible(body,day)
                    entry["research_status"] = status
                    entry["flashscore_visible_match_datetime"] = value
                    if value is not None:
                        flash_clock = datetime.strptime(value,"%d.%m.%Y %H:%M").strftime("%H:%M")
                        sofa_clock = str(event.get("local_visible_time") or "")
                        try:
                            normalized_sofa = normalized_visible_clock(sofa_clock)
                        except ValueError:
                            entry["research_status"] = "SOFASCORE_LOCAL_CLOCK_INVALID"
                        else:
                            entry["flashscore_display_agrees_if_same_timezone"] = flash_clock == normalized_sofa
                            entry["research_status"] = ("VISIBLE_CLOCKS_AGREE_UNVERIFIED_TZ" if flash_clock == normalized_sofa
                                                        else "VISIBLE_CLOCKS_DISAGREE_OR_DIFFERENT_TZ")
            except (Error,ValueError,KeyError,TypeError) as e:
                entry["research_status"] = str(e) if isinstance(e,ValueError) else type(e).__name__
            finally:
                page.close()
            records.append(entry)
    result = {
        "schema": SCHEMA,"target_date_bogota": day,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_detail_sha256": detail_hash,
        "source_crossmatch_sha256": detail.get("source_crossmatch_sha256"),
        "source_order": ["SofaScore","Flashscore","third-party research"],
        "method": "USER_AUTHORIZED_VISIBLE_CDP_MATCH_PAGE",
        "page_count_attempted": len(records),
        "visible_clock_unique_count": sum(bool(r.get("flashscore_visible_match_datetime")) for r in records),
        "display_agreements_if_same_timezone": sum(r["flashscore_display_agrees_if_same_timezone"] is True for r in records),
        "display_disagreements_or_timezone_uncertainty": sum(r["flashscore_display_agrees_if_same_timezone"] is False for r in records),
        "clock_timezone_independently_attested": False,
        "cross_provider_actual_utc_kickoff_certified": False,
        "provider_id_crosswalk_certified": False,
        "current_pit_verified": False,
        "new_hard_holdout_observations": 0,
        "new_clay_holdout_observations": 0,
        "telegram_signal_authorized": False,
        "real_money":"BLOCKED","automatic_wagering":False,
        "rows": records,
    }
    dst = root/BASE/day/"MATRIX_TENNIS_FLASHSCORE_VISIBLE_CLOCK_RESEARCH_LAST.json"
    dst.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "day":day,"attempted":len(records),
        "clock_found":result["visible_clock_unique_count"],
        "same_display":result["display_agreements_if_same_timezone"],
        "different_display":result["display_disagreements_or_timezone_uncertainty"],
        "holdout_admitted":0
    },sort_keys=True))
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",required=True)
    ap.add_argument("--root",type=Path,default=Path.cwd())
    ap.add_argument("--endpoint",default="http://127.0.0.1:9222")
    ap.add_argument("--max-events",type=int,default=6)
    a=ap.parse_args()
    research(a.root,a.date,a.endpoint,max_events=a.max_events)

if __name__=="__main__":
    main()
