"""Conservative tennis cross-source candidate matching.

Never certify matches using fuzzy names alone. Produces review candidates only.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse
from tools.matrix_calendar_evidence_guard import normalize_calendar_links
from tools.matrix_tennis_calendar_reconciliation_gate import readiness, SOFA, FLASH

ROOT = Path(__file__).resolve().parents[1]
STOP = {"tennis", "match", "en", "vivo", "wta", "atp", "united", "kingdom", "slovakia", "russia", "canada", "usa"}

def tokens(value: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    return {t for t in re.findall(r"[a-z]{3,}", plain) if t not in STOP}

def sofa_tokens(record: dict) -> set[str]:
    path = urlparse(record["url"]).path
    slug = path.split("/match/", 1)[-1].split("/", 1)[0]
    return tokens(slug.replace("-", " "))

def flash_tokens(record: dict) -> set[str]:
    return tokens(record["name"])

def reconcile(sofa: dict, flash: dict, target_date: str) -> dict:
    gate = readiness(sofa, flash, user_calendar_date=target_date)
    if not gate["cross_source_matching_permitted"]:
        raise ValueError("Calendar capture context not established")
    valid = normalize_calendar_links(sofa["records"], target_date)
    by_id = {r["event_id"]: r for r in valid["events"]}
    eligible = [r for r in sofa["records"] if re.search(r"#id:(\d+)$", r["url"]) and
                (m := re.search(r"#id:(\d+)$", r["url"])).group(1) in by_id and
                by_id[m.group(1)]["status"] == "DISCOVERY_ONLY"]
    candidates = []
    for sr in eligible:
        st = sofa_tokens(sr)
        if len(st) < 2:
            continue
        matches = []
        for fr in flash["records"]:
            ft = flash_tokens(fr)
            common = sorted(st & ft)
            if len(common) >= 2:
                matches.append({"flashscore_url":fr["url"],"flashscore_name":fr["name"],
                                "shared_tokens":common,"shared_token_count":len(common)})
        if matches:
            matches.sort(key=lambda x:(-x["shared_token_count"],x["flashscore_url"]))
            candidates.append({"sofascore_url":sr["url"],"sofascore_name":sr["name"],
                               "candidates":matches[:5],"status":"REVIEW_ONLY",
                               "date_verified":False,"event_certified":False,"signal_authorized":False})
    return {"target_date":target_date,"sofascore_raw":len(sofa["records"]),
            "sofascore_validated":valid["accepted"],"sofascore_rejected":valid["rejected"],
            "sofascore_blocked":valid["blocked"],"flashscore_raw":len(flash["records"]),
            "candidate_sofascore_events":len(candidates),"candidates":candidates,
            "cross_source_matches_certified":0,"signals_authorized":0,
            "caution":"Token overlaps are review leads, not confirmed fixture matches."}

def main() -> None:
    sofa=json.loads(SOFA.read_text(encoding="utf-8"))
    flash=json.loads(FLASH.read_text(encoding="utf-8"))
    result=reconcile(sofa,flash,"2026-10-31")
    print(json.dumps({k:v for k,v in result.items() if k!="candidates"},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
