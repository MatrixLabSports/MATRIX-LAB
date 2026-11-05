"""Immutable Flashscore Opera connector link intake, no individual event-date invention.

The visible calendar date selector describes the PAGE, not each event.
These links remain research discovery only until exact per-event kickoff and
cross-provider identification can be independently confirmed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

SCHEMA = "MATRIX_OPERA_FLASHSCORE_FOOTBALL_LINK_CAPTURE_V1"
DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def page_label(day):
    d = date.fromisoformat(day)
    return f"{DAYS[d.weekday()]}, {d.day} de {MONTHS[d.month-1]} de {d.year}"


def scan(root: Path, day: str, *, now: datetime):
    out = {"schema": "MATRIX_FLASH_OPERA_LINK_ONLY_HANDOFF_V1",
           "target_date_bogota": day,
           "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
           "status": "NO_AUTHENTIC_FLASH_OPERA_SNAPSHOT",
           "snapshots_examined": 0, "snapshots_rejected": 0,
           "visible_link_count": 0, "valid_mid_link_count": 0,
           "individual_event_date_verified": False,
           "individual_event_utc_kickoff_verified": False,
           "sofa_flash_crosswalk_verified": False,
           "production_probability_authorized": False,
           "telegram_signal_authorized": False,
           "automatic_wagering": False, "real_money": "BLOCKED",
           "links": []}
    folder = root / "evidence" / "browser_capture_inbox" / "opera_football_flash" / day
    for path in sorted(folder.glob("*.json"))[-64:]:
        out["snapshots_examined"] += 1
        try:
            raw = path.read_bytes()
            if not 0 < len(raw) < 2_000_000:
                raise ValueError("FLASH_SNAPSHOT_SIZE_INVALID")
            doc = json.loads(raw)
            if (doc.get("schema") != SCHEMA or doc.get("source") != "FLASHSCORE"
                or doc.get("target_date_bogota") != day
                or doc.get("source_page_url") != "https://www.flashscore.co/"
                or doc.get("visible_date_selector") != page_label(day)
                or doc.get("source_order") != ["SOFASCORE", "FLASHSCORE", "APIS"]
                or doc.get("capture_method") != "OPERA_CONNECTOR_ACCESSIBILITY_LINKS"
                or doc.get("real_money") != "BLOCKED"
                or doc.get("signal_generation_authorized") is not False
                or doc.get("automatic_wagering") is not False):
                raise ValueError("FLASH_SNAPSHOT_UNTRUSTED")
            observed = datetime.fromisoformat(str(doc.get("observed_at_utc")).replace("Z","+00:00"))
            if observed.utcoffset() is None or not 0 <= (now - observed.astimezone(timezone.utc)).total_seconds() <= 86400:
                raise ValueError("FLASH_OBSERVATION_NOT_CURRENT")
            links = doc.get("links")
            if not isinstance(links, list) or doc.get("record_count") != len(links) or len(links) > 2000:
                raise ValueError("FLASH_SOURCE_LINK_COUNT_INVALID")
            accepted = []
            seen = set()
            for item in links:
                if not isinstance(item, dict):
                    continue
                url, name = item.get("url"), item.get("name")
                if not isinstance(url,str) or not isinstance(name,str) or len(url)>1200 or len(name)>500:
                    continue
                p = urlparse(url)
                mid = parse_qs(p.query).get("mid", [])
                if (p.scheme!="https" or p.hostname!="www.flashscore.co" or p.username
                    or p.password or not p.path.startswith("/partido/futbol/")
                    or len(mid)!=1 or not re.fullmatch(r"[A-Za-z0-9]{8}",mid[0])
                    or url in seen or " - " not in name):
                    continue
                seen.add(url)
                accepted.append({"url": url, "name": name, "mid": mid[0],
                                 "individual_event_date_verified": False,
                                 "individual_event_utc_kickoff_verified": False})
            if not accepted:
                raise ValueError("FLASH_NO_VALID_VISIBLE_EVENTS")
            if len(accepted) <= out["valid_mid_link_count"]:
                continue
            out.update({"status": "FLASH_OPERA_LINKS_RESEARCH_ONLY_EVENT_DATE_UNVERIFIED",
                        "visible_link_count": len(links),
                        "valid_mid_link_count": len(accepted),
                        "source_sha256": hashlib.sha256(raw).hexdigest(),
                        "source_relpath": str(path.relative_to(root)).replace("\\","/"),
                        "links": accepted})
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError):
            out["snapshots_rejected"] += 1
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--day", required=True)
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    root = args.root.resolve()
    folder = root/"evidence"/"football_world_inventory"/args.day
    if args.out.resolve() != folder/"MATRIX_FLASH_OPERA_LINK_ONLY_HANDOFF_LAST.json":
        raise SystemExit("FLASH_HANDOFF_CANNOT_WRITE_PRODUCTION")
    result = scan(root,args.day,now=datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","valid_mid_link_count",
                      "individual_event_date_verified","telegram_signal_authorized")},sort_keys=True))


if __name__ == "__main__":
    main()
