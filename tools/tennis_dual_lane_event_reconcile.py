from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def norm(v: object) -> str:
    s=unicodedata.normalize("NFKD",str(v or ""))
    s="".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+"," ",s).split())

def surface_family(v: object) -> str:
    t=str(v or "").strip().upper()
    if t in {"HARD","I.HARD","INDOOR HARD","INDOOR_HARD"}: return "HARD"
    if t=="CLAY": return "CLAY"
    if t=="GRASS": return "GRASS"
    return "OTHER"

def neutral(e: dict[str,Any], rapid: bool) -> str | None:
    if rapid:
        p1=norm((e.get("player1") or {}).get("name"))
        p2=norm((e.get("player2") or {}).get("name"))
    else:
        p1=norm((e.get("player1") or {}).get("name"))
        p2=norm((e.get("player2") or {}).get("name"))
    if not p1 or not p2: return None
    try:
        d=datetime.fromisoformat(str(e["event_start_bogota"])).date().isoformat()
    except Exception:
        return None
    raw=json.dumps({"date":d,"players":sorted([p1,p2]),"format":"SINGLES"},sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def run(rapid_path:Path,api_path:Path,clay_holdout:Path,clay_bootstrap:Path,out:Path)->dict[str,Any]:
    rapid=json.loads(rapid_path.read_text())
    api=json.loads(api_path.read_text())
    hold=json.loads(clay_holdout.read_text())
    boot=json.loads(clay_bootstrap.read_text())
    pit_max=int(boot["source"]["source_max_tourney_date"])

    rr=[
        e for e in rapid.get("events",[])
        if e.get("circuit_detail")=="ATP_CHALLENGER"
        and e.get("event_format")=="SINGLES"
        and surface_family(e.get("surface")) in {"HARD","CLAY"}
    ]
    aa=[
        e for e in api.get("events",[])
        if e.get("event_format")=="SINGLES"
        and e.get("surface_family") in {"HARD","CLAY"}
        and not e.get("blockers")
    ]
    rb=defaultdict(list); ab=defaultdict(list)
    for e in rr:
        k=neutral(e,True)
        if k: rb[k].append(e)
    for e in aa:
        k=neutral(e,False)
        if k: ab[k].append(e)

    now=datetime.now(timezone.utc)
    bindings=[]; blocked=[]
    for k in sorted(set(rb)|set(ab)):
        rs=rb.get(k,[]); aps=ab.get(k,[])
        if len(rs)!=1 or len(aps)!=1:
            blocked.append({"neutral_key":k,"rapid_count":len(rs),"api_tennis_count":len(aps),"reason":"EVENT_LEVEL_BINDING_NOT_UNIQUE"})
            continue
        r=rs[0]; a=aps[0]
        rsf=surface_family(r.get("surface")); asf=a.get("surface_family")
        if rsf!=asf:
            blocked.append({"neutral_key":k,"rapid_source_event_id":r.get("source_event_id"),"api_source_event_id":a.get("source_event_id"),"reason":"SURFACE_DISAGREEMENT","rapid_surface":rsf,"api_surface":asf})
            continue
        rstart=datetime.fromisoformat(str(r["event_start_utc"]))
        astart=datetime.fromisoformat(str(a["event_start_utc"]))
        delta=abs((rstart-astart).total_seconds())/60
        chosen=min(rstart,astart)
        future=chosen>now
        row={
            "neutral_key":k,
            "surface_family":rsf,
            "rapid_source_event_id":r.get("source_event_id"),
            "api_tennis_source_event_id":a.get("source_event_id"),
            "rapid_physical_event_key":r.get("physical_event_key"),
            "tournament":r.get("tournament_name") or a.get("tournament_name"),
            "players":[(r.get("player1") or {}).get("name"),(r.get("player2") or {}).get("name")],
            "rapid_start_utc":r.get("event_start_utc"),
            "api_tennis_start_utc":a.get("event_start_utc"),
            "start_time_delta_minutes":delta,
            "future_at_reconciliation":future,
            "identity_binding":"PASS_ONE_TO_ONE_PLAYER_PAIR_DATE",
            "surface_binding":"PASS",
        }
        blockers=[]
        if not future: blockers.append("EVENT_NOT_FUTURE")
        if rsf=="CLAY":
            event_date=int(chosen.strftime("%Y%m%d"))
            if pit_max < event_date:
                blockers.append("PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT")
            row["lane_id"]="ATP_CHALLENGER_MEN_SINGLES_CLAY"
            row["holdout_id"]=hold["holdout_id"]
            row["prospective_counter_increment_allowed"]=not blockers
        else:
            row["lane_id"]="ATP_CHALLENGER_MEN_SINGLES_HARD"
            row["holdout_id"]="A22_POST_AUDIT_VIRGIN_HOLDOUT_V1"
            row["prospective_counter_increment_allowed"]="DELEGATED_TO_EXISTING_COR0203_GATES"
        row["blockers"]=blockers
        bindings.append(row)

    clay=[x for x in bindings if x["surface_family"]=="CLAY"]
    hard=[x for x in bindings if x["surface_family"]=="HARD"]
    payload={
        "schema":"MATRIX_TENNIS_DUAL_LANE_EVENT_RECONCILIATION_V1",
        "generated_at_utc":now.replace(microsecond=0).isoformat(),
        "target_date_bogota":rapid.get("target_date_bogota"),
        "rapidapi_domain_rows":len(rr),
        "api_tennis_domain_rows":len(aa),
        "bound_one_to_one":len(bindings),
        "hard_bound_count":len(hard),
        "clay_bound_count":len(clay),
        "clay_freeze_ready_count":sum(1 for x in clay if x["prospective_counter_increment_allowed"] is True),
        "clay_blocked_count":sum(1 for x in clay if x["blockers"]),
        "bindings":bindings,
        "binding_blocked":blocked,
        "protections":{
            "no_name_only_join":True,
            "neutral_join_requires_unique_pair_and_date":True,
            "surface_agreement_required":True,
            "clay_pit_caught_up_required":True,
            "missing_not_zero":True,
            "silent_imputation":False,
            "odds_to_probability":False,
            "metrics_opened":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED"
        }
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n")
    print(json.dumps({
        "bound":len(bindings),
        "hard":len(hard),
        "clay":len(clay),
        "clay_freeze_ready":payload["clay_freeze_ready_count"],
        "binding_blocked":len(blocked)
    },sort_keys=True))
    return payload

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rapid",required=True);p.add_argument("--api-tennis",required=True)
    p.add_argument("--clay-holdout",required=True);p.add_argument("--clay-bootstrap",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    run(Path(a.rapid),Path(a.api_tennis),Path(a.clay_holdout),Path(a.clay_bootstrap),Path(a.out))
if __name__=="__main__": main()
