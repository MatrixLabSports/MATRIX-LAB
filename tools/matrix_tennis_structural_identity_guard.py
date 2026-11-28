"""Structural tennis participant matching for saved review leads.

Requires both sides of a Flashscore fixture, rejects partial doubles overlaps.
Even full identity is REVIEW_ONLY until date and tournament are verified.
"""
from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

INPUT=Path(__file__).resolve().parents[1]/"evidence/calendar/MATRIX_TENNIS_TOMORROW_REVIEW_20261031.json"
STOP={"tennis","match","wta","atp"}

def norm(s: str) -> str:
    return unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().casefold()

def sofa_surnames(url: str) -> set[str]:
    slug=urlparse(url).path.split("/match/",1)[-1].split("/",1)[0]
    return {x for x in re.findall(r"[a-z]{3,}",norm(slug).replace("-"," ")) if x not in STOP}

def flash_sides(name: str) -> list[set[str]]:
    parts=re.split(r"\s+-\s+",name.strip(),maxsplit=1)
    if len(parts)!=2:
        return []
    return [{x for x in re.findall(r"[a-z]{3,}",norm(p)) if x not in STOP} for p in parts]

def classify(data: dict) -> dict:
    if data.get("review_only") is not True or data.get("certified")!=0 or data.get("signals_authorized")!=0:
        raise ValueError("Only unverified source evidence permitted")
    rows=[]
    for row in data["candidates"]:
        st=sofa_surnames(row["sofascore_url"])
        opts=[]
        for opt in row["candidates"]:
            sides=flash_sides(opt["flashscore_name"])
            # A surname on each side is necessary, never sufficient.
            complete=bool(len(sides)==2 and all(side & st for side in sides))
            opts.append({"flashscore_url":opt["flashscore_url"],"flashscore_name":opt["flashscore_name"],
                         "both_sides_overlap":complete,"review_status":"PARTICIPANT_REVIEW_REQUIRED" if complete else "PARTIAL_OR_UNPARSEABLE",
                         "event_certified":False,"signal_authorized":False})
        rows.append({"sofascore_url":row["sofascore_url"],"sofascore_name":row["sofascore_name"],
                     "options":opts,"date_verified":False,"tournament_verified":False,
                     "event_certified":False,"signal_authorized":False})
    return {"target_date":data["target_date"],"candidate_events":len(rows),
            "options_both_sides_overlap":sum(o["both_sides_overlap"] for r in rows for o in r["options"]),
            "options_partial_or_unparseable":sum(not o["both_sides_overlap"] for r in rows for o in r["options"]),
            "event_dates_verified":0,"tournaments_verified":0,"certified":0,"signals_authorized":0,
            "records":rows}

def main() -> None:
    report=classify(json.loads(INPUT.read_text(encoding="utf-8")))
    print(json.dumps({k:v for k,v in report.items() if k!="records"},indent=2))

if __name__=="__main__":
    main()
