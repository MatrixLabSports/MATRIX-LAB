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



def exact_sofa_crosscheck(flash: dict, sofa: dict, *, now: datetime) -> dict:
    """Corroborate independent browser details without authorizing production."""
    from tools.matrix_football_sofa_fixture_crosscheck import norm
    from urllib.parse import urlparse
    if (flash.get("schema") != "MATRIX_FLASH_INDIVIDUAL_DETAIL_VERIFIED_V1"
        or sofa.get("schema") != "MATRIX_SOFA_OPERA_INDIVIDUAL_DETAIL_CAPTURE_V1"
        or sofa.get("source") != "SOFASCORE"
        or sofa.get("capture_method") != "OPERA_CONNECTOR_ACCESSIBILITY_TREE"
        or sofa.get("real_money") != "BLOCKED"
        or sofa.get("automatic_wagering") is not False
        or sofa.get("signal_generation_authorized") is not False
        or sofa.get("display_timezone") != "America/Bogota"):
        raise ValueError("FLASH_SOFA_CROSSCHECK_UNTRUSTED_PROVENANCE")
    u = urlparse(str(sofa.get("source_page_url") or ""))
    sid = str(sofa.get("source_event_id") or "")
    if (u.scheme != "https" or u.netloc != "www.sofascore.com"
        or not u.path.startswith("/es/football/match/")
        or not sid.isdigit() or u.fragment != "id:" + sid):
        raise ValueError("FLASH_SOFA_CROSSCHECK_BAD_SOFA_EVENT_ID")
    aliases = {"ferencvaros tc": "ferencvaros"}
    def official_name(v):
        n = norm(v)
        return aliases.get(n, n)
    if (official_name(sofa.get("home")) != official_name(flash.get("home"))
        or official_name(sofa.get("away")) != official_name(flash.get("away"))):
        raise ValueError("FLASH_SOFA_CROSSCHECK_TEAM_MISMATCH")
    local_date = datetime.strptime(str(sofa.get("visible_event_date") or ""), "%d/%m/%Y").date()
    local_time = str(sofa.get("visible_event_time") or "")
    if (local_date.isoformat() != flash["target_date_bogota"]
        or local_time != datetime.fromisoformat(
            flash["kickoff_utc_from_declared_display_timezone"]).astimezone(BOGOTA).strftime("%H:%M")):
        raise ValueError("FLASH_SOFA_CROSSCHECK_DATE_TIME_MISMATCH")
    observed = utc(sofa.get("observed_at_utc"))
    kickoff = utc(flash["kickoff_utc_from_declared_display_timezone"])
    age = (now.astimezone(timezone.utc) - observed).total_seconds()
    if observed >= kickoff or not 0 <= age <= 86400:
        raise ValueError("FLASH_SOFA_CROSSCHECK_STALE_OR_POST_KICKOFF")
    return {
        "schema": "MATRIX_FLASH_SOFA_TWO_SOURCE_EVENT_CROSSCHECK_V1",
        "status": "PASS_TWO_SOURCE_EVENT_DATE_TEAM_TIME_RESEARCH_ONLY",
        "flashscore_mid": flash["event_mid"], "sofascore_event_id": sid,
        "target_date_bogota": flash["target_date_bogota"],
        "local_clock_bogota_declared": local_time,
        "home": flash["home"], "away": flash["away"],
        "flashscore_source_sha256": flash["source_sha256"],
        "sofascore_source_sha256": hashlib.sha256(json.dumps(sofa, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "third_provider_fixture_identity_verified": False,
        "official_p_matrix_authorized": False, "telegram_signal_authorized": False,
        "automatic_wagering": False, "real_money": "BLOCKED",
    }


def scan_two_source(root: Path, day: str, *, now: datetime) -> dict:
    flash = scan(root, day, now=now)
    directory = root / "evidence/browser_capture_inbox/opera_football_sofa_detail" / day
    matched, rejected, seen = [], 0, set()
    for path in sorted(directory.glob("*.json"))[-64:]:
        try:
            raw = path.read_bytes()
            if not 0 < len(raw) <= 1_000_000:
                raise ValueError("SOFA_DETAIL_OVERSIZED")
            sofa = json.loads(raw)
            for event in flash["events"]:
                try:
                    result = exact_sofa_crosscheck(event, sofa, now=now)
                    key = (result["flashscore_mid"], result["sofascore_event_id"])
                    if key not in seen:
                        seen.add(key)
                        result["sofascore_capture_sha256"] = hashlib.sha256(raw).hexdigest()
                        matched.append(result)
                except (ValueError, TypeError, KeyError):
                    continue
        except (ValueError, TypeError, OSError, KeyError):
            rejected += 1
    return {
        "schema": "MATRIX_FLASH_SOFA_TWO_SOURCE_REPORT_V1",
        "status": "TWO_SOURCE_RESEARCH_MATCHES_NO_PRODUCTION_AUTHORIZATION" if matched else "NO_TWO_SOURCE_EVENT_MATCHES",
        "target_date_bogota": day, "verified_event_pair_count": len(matched),
        "rejected_snapshot_count": rejected, "matched": matched,
        "third_provider_fixture_identity_verified": False,
        "telegram_signal_authorized": False, "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    expected = root / "evidence" / "football_world_inventory" / args.day / "MATRIX_FLASH_INDIVIDUAL_DETAIL_VERIFICATION_LAST.json"
    if args.out.resolve() != expected:
        raise SystemExit("FLASH_DETAIL_OUTPUT_SCOPE_FORBIDDEN")
    report = scan(root, args.day, now=datetime.now(timezone.utc))
    if report["verified_individual_count"]:
        expected.parent.mkdir(parents=True, exist_ok=True)
        expected.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    pairs = scan_two_source(root, args.day, now=datetime.now(timezone.utc))
    pair_output = expected.parent / "MATRIX_FLASH_SOFA_TWO_SOURCE_REPORT_LAST.json"
    if pairs["verified_event_pair_count"]:
        pair_output.write_text(json.dumps(pairs, ensure_ascii=False, indent=2, sort_keys=True) + "\\n",
                               encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "verified_individual_count",
                                           "rejected_snapshot_count", "telegram_signal_authorized")}, sort_keys=True))


if __name__ == "__main__":
    main()
