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

def _tokens(v: object) -> list[str]:
    return norm(v).split()


def _player_compatible(provider_abbrev: object, provider_full: object) -> bool:
    a=_tokens(provider_abbrev)
    b=_tokens(provider_full)
    if not a or not b:
        return False
    if a==b:
        return True
    if a[0][0] != b[0][0]:
        return False
    # API-Tennis commonly abbreviates given names while preserving surnames.
    # Every non-initial token from the abbreviated name must exist in the full
    # provider name; this rejects pure first-initial-only matches.
    meaningful=[x for x in a[1:] if len(x)>1]
    if not meaningful:
        meaningful=[a[-1]] if len(a[-1])>1 else []
    if not meaningful:
        return False
    return all(x in b for x in meaningful)


def _pair_compatible(api_event: dict[str,Any], rapid_event: dict[str,Any]) -> bool:
    a1=(api_event.get("player1") or {}).get("name")
    a2=(api_event.get("player2") or {}).get("name")
    r1=(rapid_event.get("player1") or {}).get("name")
    r2=(rapid_event.get("player2") or {}).get("name")
    return (
        _player_compatible(a1,r1) and _player_compatible(a2,r2)
    ) or (
        _player_compatible(a1,r2) and _player_compatible(a2,r1)
    )


def _tournament_core(v: object) -> str:
    drop={"challenger","qualification","qualifications","italy","china","men","singles"}
    return " ".join(x for x in _tokens(v) if x not in drop)


def _same_calendar_identity(api_event: dict[str,Any], rapid_event: dict[str,Any]) -> tuple[bool,float|None]:
    if _tournament_core(api_event.get("tournament_name")) != _tournament_core(rapid_event.get("tournament_name")):
        return False,None
    try:
        a=datetime.fromisoformat(str(api_event["event_start_bogota"]))
        r=datetime.fromisoformat(str(rapid_event["event_start_bogota"]))
    except Exception:
        return False,None
    if a.date()!=r.date():
        return False,None
    delta=abs((a-r).total_seconds())/60.0
    if delta>30:
        return False,delta
    if not _pair_compatible(api_event,rapid_event):
        return False,delta
    return True,delta


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

    now=datetime.now(timezone.utc)
    bindings=[]; blocked=[]
    rapid_referenced=set()

    for a in aa:
        identity=[]
        for r in rr:
            ok,delta=_same_calendar_identity(a,r)
            if ok:
                identity.append((r,delta))
        if len(identity)!=1:
            blocked.append({
                "api_tennis_source_event_id":a.get("source_event_id"),
                "api_surface":a.get("surface_family"),
                "tournament":a.get("tournament_name"),
                "players":[(a.get("player1") or {}).get("name"),(a.get("player2") or {}).get("name")],
                "event_start_bogota":a.get("event_start_bogota"),
                "rapid_identity_candidate_count":len(identity),
                "reason":"NO_RAPIDAPI_EVENT_MATCH" if not identity else "EVENT_LEVEL_BINDING_AMBIGUOUS",
            })
            continue

        r,delta=identity[0]
        rid=str(r.get("physical_event_key") or r.get("source_event_id"))
        rapid_referenced.add(rid)
        rsf=surface_family(r.get("surface")); asf=a.get("surface_family")
        if rsf!=asf:
            blocked.append({
                "api_tennis_source_event_id":a.get("source_event_id"),
                "rapid_source_event_id":r.get("source_event_id"),
                "rapid_physical_event_key":r.get("physical_event_key"),
                "tournament_api":a.get("tournament_name"),
                "tournament_rapid":r.get("tournament_name"),
                "players_api":[(a.get("player1") or {}).get("name"),(a.get("player2") or {}).get("name")],
                "players_rapid":[(r.get("player1") or {}).get("name"),(r.get("player2") or {}).get("name")],
                "start_time_delta_minutes":delta,
                "reason":"SURFACE_DISAGREEMENT",
                "rapid_surface":rsf,
                "api_surface":asf,
            })
            continue

        rstart=datetime.fromisoformat(str(r["event_start_utc"]))
        astart=datetime.fromisoformat(str(a["event_start_utc"]))
        chosen=min(rstart,astart)
        future=chosen>now
        row={
            "surface_family":rsf,
            "rapid_source_event_id":r.get("source_event_id"),
            "api_tennis_source_event_id":a.get("source_event_id"),
            "rapid_physical_event_key":r.get("physical_event_key"),
            "tournament":r.get("tournament_name") or a.get("tournament_name"),
            "players_rapid":[(r.get("player1") or {}).get("name"),(r.get("player2") or {}).get("name")],
            "players_api":[(a.get("player1") or {}).get("name"),(a.get("player2") or {}).get("name")],
            "rapid_start_utc":r.get("event_start_utc"),
            "api_tennis_start_utc":a.get("event_start_utc"),
            "start_time_delta_minutes":delta,
            "future_at_reconciliation":future,
            "identity_binding":"PASS_TOURNAMENT_TIME_PLAYER_PAIR_UNIQUE",
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

    for r in rr:
        rid=str(r.get("physical_event_key") or r.get("source_event_id"))
        if rid in rapid_referenced:
            continue
        blocked.append({
            "rapid_source_event_id":r.get("source_event_id"),
            "rapid_physical_event_key":r.get("physical_event_key"),
            "rapid_surface":surface_family(r.get("surface")),
            "tournament":r.get("tournament_name"),
            "players":[(r.get("player1") or {}).get("name"),(r.get("player2") or {}).get("name")],
            "event_start_bogota":r.get("event_start_bogota"),
            "reason":"RAPIDAPI_ONLY_NO_API_TENNIS_BINDING",
        })

    clay=[x for x in bindings if x["surface_family"]=="CLAY"]
    hard=[x for x in bindings if x["surface_family"]=="HARD"]
    payload={
        "schema":"MATRIX_TENNIS_DUAL_LANE_EVENT_RECONCILIATION_V2",
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
            "identity_requires_tournament_date_start_and_pair":True,
            "abbreviated_name_matching_requires_initial_and_surname_tokens":True,
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
        "binding_blocked":len(blocked),
        "surface_disagreements":sum(x.get("reason")=="SURFACE_DISAGREEMENT" for x in blocked),
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
