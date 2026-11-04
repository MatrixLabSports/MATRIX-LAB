"""Browser-first tennis discovery from real persisted Opera observations.

Deliberately NEVER converts a link or odds into a calibrated observation.
SofaScore/Flashscore are the discovery authority; individual exact native
player identity, surface, kickoff and PIT remain mandatory for admission.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date,datetime,timezone
from pathlib import Path

BASE=Path("evidence/tennis_calendar_physical")
OUT=Path("evidence/tennis_calendar_reconciliation/MATRIX_TENNIS_FREE_BROWSER_DISCOVERY_LAST.json")
SOURCES={"SOFASCORE":"sofascore_opera_full_link_observations.json",
         "FLASHSCORE":"flashscore_opera_full_link_observations.json"}

def canon(x):
    return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()

def sha(x):
    return hashlib.sha256(x).hexdigest()

def iso(value):
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.utcoffset() is None:raise ValueError("MISSING_TIMEZONE")
    return parsed.astimezone(timezone.utc)

def collect(root:Path,day:str,now:datetime)->dict:
    date.fromisoformat(day)
    now=now.astimezone(timezone.utc)
    sources=[];items=[];rejected=[]
    for source,file in SOURCES.items():
        p=root/BASE/day/file
        if not p.exists():
            sources.append({"source":source,"status":"NO_PERSISTED_OPERA_CAPTURE","count":0})
            continue
        try:
            raw=p.read_bytes()
            if len(raw)>8_000_000:raise ValueError("SOURCE_BYTES_TOO_LARGE")
            capture=json.loads(raw)
            if (capture.get("schema")!="MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1"
                or capture.get("source")!=source
                or capture.get("target_date_bogota")!=day
                or capture.get("canonical_fixture_export_authorized") is not False
                or capture.get("probability_generation_authorized") is not False
                or capture.get("real_money")!="BLOCKED"):
                raise ValueError("CAPTURE_GOVERNANCE_NOT_COMPATIBLE")
            observed=iso(capture["collected_at_utc"])
            if observed>now:raise ValueError("CAPTURE_TIMESTAMP_IN_FUTURE")
            entries=capture.get("matches")
            if not isinstance(entries,list):raise ValueError("MATCH_LINK_LIST_MISSING")
            seen=set();added=0
            for m in entries:
                if not isinstance(m,dict):continue
                url=m.get("url")
                if not isinstance(url,str):continue
                if source=="SOFASCORE" and not url.startswith("https://www.sofascore.com/es/tennis/match/"):
                    continue
                if source=="FLASHSCORE" and not url.startswith("https://www.flashscore.co/partido/tenis/"):
                    continue
                native=str(m.get("source_event_id") or m.get("visible_mid_query") or "")
                if not native:
                    # URL is still an authentic discovery link, not a match ID
                    native=sha(url.encode())[:20]
                key=(source,native)
                if key in seen:continue
                seen.add(key);added+=1
                items.append({"source":source,"source_event_id":native,
                    "url":url,"display_name":str(m.get("display_name") or "")[:260],
                    "source_capture_sha256":sha(raw),
                    "target_date_label_visible":m.get("explicit_target_date_label") is True,
                    "native_player_identity_verified":False,
                    "surface_verified":False,"kickoff_utc_verified":False,
                    "hard_holdout_admitted":False,"clay_holdout_admitted":False,
                    "live_probability_authorized":False})
            sources.append({"source":source,"status":"AUTHENTIC_LINKS_CAPTURED_NOT_MATCH_CERTIFIED",
                "capture_sha256":sha(raw),"capture_at_utc":observed.isoformat(),
                "count":added})
        except (OSError,ValueError,TypeError,KeyError) as exc:
            sources.append({"source":source,"status":"REJECTED_UNTRUSTED_SOURCE","count":0})
            rejected.append({"source":source,"reason":str(exc)[:140]})
    # Keep native identifiers separate: do not assume same event across sites
    items.sort(key=lambda e:(e["source"],e["source_event_id"]))
    return {"schema":"MATRIX_TENNIS_FREE_BROWSER_DISCOVERY_V1",
      "target_date_bogota":day,"source_priority":["SOFASCORE","FLASHSCORE","OPTIONAL_AUTHORIZED_API"],
      "sources":sources,"observed_source_links":len(items),
      "unverified_source_links":len(items),"rejections":rejected,
      "hard_verified_candidates":0,"clay_verified_candidates":0,
      "hard_new_prospective_observations":0,"clay_new_prospective_observations":0,
      "admission_status":"SOURCE_LINKS_ONLY_NO_GOVERNED_ADMISSION",
      "model_calibration_mutated":False,"source_crosswalk_certified":False,
      "telegram_signal_authorized":False,"automatic_wagering":False,
      "real_money":"BLOCKED","source_links":items}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--date",required=True)
    p.add_argument("--out",type=Path,default=OUT)
    a=p.parse_args()
    value=collect(a.root,a.date,datetime.now(timezone.utc))
    target=a.out if a.out.is_absolute() else a.root/a.out
    if any(x in target.parts for x in ("telegram","governance","holdout","prospective")):
        raise SystemExit("FREE_DISCOVERY_OUTPUT_MUST_BE_ISOLATED")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(canon(value))
    print(json.dumps({"date":a.date,"links":value["observed_source_links"],
                      "hard_admitted":0,"clay_admitted":0,
                      "providers":[x["status"] for x in value["sources"]]},sort_keys=True))

if __name__=="__main__":main()
