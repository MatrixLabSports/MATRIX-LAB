from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

INBOX=Path("evidence/browser_capture_inbox/team_total")
OUT_ROOT=Path("evidence/football_world_inventory")
AUDIT=Path("evidence/browser_capture_inbox/MATRIX_TEAM_TOTAL_PHYSICAL_CAPTURE_BRIDGE_LAST.json")
SCHEMA_IN="MATRIX_BROWSER_TEAM_TOTAL_CAPTURE_V1"
SCHEMA_OUT="MATRIX_PHYSICAL_BOOK_QUOTE_V1"
AUTHORIZED={"betano":"Betano","betplay":"BetPlay","rushbet":"Rushbet","bwin":"bwin"}
LANES={"TEAM_TOTAL_GOALS_HOME","TEAM_TOTAL_GOALS_AWAY"}
SIDES={"over","under"}
MAX_CAPTURE_TO_KICKOFF_SECONDS=7*24*3600


def _dt(v:Any)->datetime:
    s=str(v or "").strip()
    if s.endswith("Z"): s=s[:-1]+"+00:00"
    d=datetime.fromisoformat(s)
    if d.tzinfo is None: d=d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def _norm(v:Any)->str:
    return " ".join(str(v or "").strip().casefold().split())


def _house(v:Any)->tuple[str,str]|None:
    t=_norm(v).replace(" ","")
    aliases={"betano":"betano","betplay":"betplay","rushbet":"rushbet","rushbetco":"rushbet","bwin":"bwin"}
    key=aliases.get(t)
    return (key,AUTHORIZED[key]) if key else None


def _validate(row:Mapping[str,Any])->tuple[dict[str,Any]|None,str]:
    if row.get("schema")!=SCHEMA_IN: return None,"SCHEMA"
    house=_house(row.get("house"))
    if house is None: return None,"HOUSE"
    fixture=str(row.get("fixture_id") or "").strip()
    lane=str(row.get("market_lane") or "").strip().upper()
    team=str(row.get("team_name") or "").strip()
    side=str(row.get("selection_side") or "").strip().casefold()
    match=str(row.get("match") or "").strip()
    source_url=str(row.get("source_url") or "").strip()
    source_sha=str(row.get("source_text_sha256") or "").strip().lower()
    if not fixture or lane not in LANES or not team or side not in SIDES or not match: return None,"IDENTITY"
    if not source_url.startswith(("https://","http://")): return None,"SOURCE_URL"
    if len(source_sha)!=64 or any(ch not in "0123456789abcdef" for ch in source_sha): return None,"SOURCE_HASH"
    try:
        line=float(row.get("line")); odds=float(row.get("decimal_odds"))
        captured=_dt(row.get("captured_at_utc") or row.get("captured_at_bogota"))
        kickoff=_dt(row.get("kickoff_utc"))
    except Exception:
        return None,"PARSE"
    if line not in {0.5,1.5,2.5}: return None,"LINE"
    if odds<=1.0: return None,"ODDS"
    if captured>=kickoff: return None,"POST_KICKOFF"
    if (kickoff-captured).total_seconds()>MAX_CAPTURE_TO_KICKOFF_SECONDS: return None,"TOO_EARLY"
    key,display=house
    artifact={
        "schema":SCHEMA_OUT,
        "captured_at_utc":captured.isoformat(),
        "fixture_id":fixture,
        "kickoff_utc":kickoff.isoformat(),
        "sport":"football",
        "match":match,
        "league":row.get("league"),
        "market":"Team Total Goals",
        "market_key":lane,
        "team_name":team,
        "team_subject":team,
        "selection_side":side,
        "selection":f"{'Over' if side=='over' else 'Under'} {line:g}",
        "line":line,
        "house":display,
        "house_key":key,
        "decimal_odds":odds,
        "source":"Opera Browser Connector physical accessibility tree",
        "source_url":source_url,
        "source_text_sha256":source_sha,
        "identity_status":"PASS_EXACT_FIXTURE_TEAM_LANE_SIDE_LINE",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "protections":{
            "physical_quote_only":True,
            "probability_from_odds":False,
            "post_kickoff_forbidden":True,
            "quote_revalidated_downstream":True,
        },
    }
    return artifact,"PASS"


def _name(a:Mapping[str,Any])->str:
    stamp=_dt(a["captured_at_utc"]).strftime("%H%M%S")
    slug=str(a["house_key"]).upper()
    return f"MATRIX_TEAM_TOTAL_{a['fixture_id']}_{a['market_key']}_{slug}_QUOTE_{stamp}_UTC.json"


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--inbox",default=str(INBOX))
    ap.add_argument("--out-root",default=str(OUT_ROOT))
    ap.add_argument("--audit",default=str(AUDIT))
    args=ap.parse_args()
    inbox=Path(args.inbox); out_root=Path(args.out_root); audit_path=Path(args.audit)
    accepted=[]; rejected=[]; duplicate=0
    paths=sorted(inbox.glob("*.json")) if inbox.exists() else []
    for p in paths:
        try: row=json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            rejected.append({"path":p.as_posix(),"reason":"JSON"}); continue
        artifact,reason=_validate(row)
        if artifact is None:
            rejected.append({"path":p.as_posix(),"reason":reason}); continue
        day=_dt(artifact["captured_at_utc"]).date().isoformat()
        target=out_root/day/_name(artifact)
        target.parent.mkdir(parents=True,exist_ok=True)
        payload=json.dumps(artifact,indent=2,sort_keys=True,ensure_ascii=False)+"\n"
        if target.exists():
            if target.read_text(encoding="utf-8")==payload:
                duplicate+=1
                accepted.append({"inbox":p.as_posix(),"artifact":target.as_posix(),"status":"DUPLICATE_IDENTICAL"})
                continue
            rejected.append({"path":p.as_posix(),"reason":"TARGET_CONFLICT"}); continue
        target.write_text(payload,encoding="utf-8")
        accepted.append({"inbox":p.as_posix(),"artifact":target.as_posix(),"status":"CREATED"})
    audit={
        "schema":"MATRIX_TEAM_TOTAL_PHYSICAL_CAPTURE_BRIDGE_AUDIT_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"PASS",
        "input_count":len(paths),
        "accepted_count":len(accepted),
        "rejected_count":len(rejected),
        "duplicate_identical_count":duplicate,
        "accepted":accepted[-200:],
        "rejected":rejected[-200:],
        "source_contract":{
            "schema":SCHEMA_IN,
            "source":"Opera Browser Connector physical accessibility tree",
            "required_identity":["fixture_id","kickoff_utc","market_lane","team_name","selection_side","line","house","decimal_odds"],
            "required_proof":["source_url","source_text_sha256","captured_at_utc"],
            "authorized_houses":sorted(AUTHORIZED),
        },
        "protections":{"automatic_wagering":False,"real_money":"BLOCKED","probability_from_odds":False,"post_kickoff_forbidden":True},
    }
    audit_path.parent.mkdir(parents=True,exist_ok=True)
    audit_path.write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","input":len(paths),"accepted":len(accepted),"rejected":len(rejected)},sort_keys=True))


if __name__=="__main__":
    main()
