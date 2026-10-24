from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ROOT=Path("evidence/calendar_physical")
DEFAULT_OUT=Path("evidence/calendar_reconciliation/MATRIX_FOOTBALL_WORLD_CALENDAR_RECONCILIATION_LAST.json")

ALIASES={
    "man utd":"manchester united",
    "man city":"manchester city",
    "bayern munich":"bayern munchen",
    "bayern munchen":"bayern munchen",
    "friburgo":"freiburg",
    "monaco":"as monaco",
    "marsella":"marseille",
    "estrasburgo":"strasbourg",
    "atletico nacional":"atl nacional",
    "independiente medellin":"ind medellin",
    "deportivo pasto":"dep pasto",
    "deportivo cali":"dep cali",
    "barcelona":"fc barcelona",
    "leverkusen":"bayer leverkusen",
    "real betis":"betis",
}
STOP={"fc","cf","club","sc","afc","ac","cd","fk","ca","de","del","la","el","the","united","city","sporting"}


def _load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return v


def _fold(s:str)->str:
    s=unicodedata.normalize("NFKD",s)
    s="".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s=re.sub(r"\([^)]*\)"," ",s)
    s=re.sub(r"[^a-z0-9]+"," ",s)
    s=re.sub(r"\s+"," ",s).strip()
    for a,b in ALIASES.items():
        s=s.replace(a,b)
    return s


def _tokens(s:str)->set[str]:
    return {x for x in _fold(s).split() if len(x)>=3 and x not in STOP and not x.isdigit()}


def _flash_pair(name:str)->tuple[str,str]|None:
    if " - " not in name:
        return None
    a,b=name.split(" - ",1)
    if not a.strip() or not b.strip():
        return None
    return a.strip(),b.strip()


def _sofa_body(raw:str)->str:
    x=re.sub(r"^25/10/26\s+(?:Cancelado|\d{1,2}:\d{2})\s+","",raw).strip()
    x=re.sub(r"\s+1\s+\d+(?:\.\d+)?\s+X\s+\d+(?:\.\d+)?\s+2\s+\d+(?:\.\d+)?\s*$","",x)
    return x.strip()


def _side_hit(side:str,sofa_body:str)->float:
    st=_tokens(side)
    if not st:
        return 0.0
    bt=_tokens(sofa_body)
    return len(st & bt)/len(st)


def _pair_score(home:str,away:str,sofa_body:str)->float:
    h=_side_hit(home,sofa_body); a=_side_hit(away,sofa_body)
    if h==0 or a==0:
        return 0.0
    return (h+a)/2.0


def reconcile(sofa:dict[str,Any],flash:dict[str,Any],generated_at:datetime|None=None)->dict[str,Any]:
    if sofa.get("target_date_bogota")!=flash.get("target_date_bogota"):
        raise ValueError("TARGET_DATE_MISMATCH")
    target=sofa["target_date_bogota"]
    sofa_obs=list(dict.fromkeys(str(x) for x in sofa.get("observations") or [] if str(x).strip()))
    flash_obs=list(dict.fromkeys(str(x) for x in flash.get("observations") or [] if str(x).strip()))
    sofa_bodies=[_sofa_body(x) for x in sofa_obs]
    used_sofa:set[int]=set()
    matches=[]
    flash_only=[]
    ambiguous=[]
    for name in flash_obs:
        pair=_flash_pair(name)
        if pair is None:
            flash_only.append({"flashscore":name,"reason":"FLASH_NAME_NOT_PAIR"})
            continue
        home,away=pair
        scored=[]
        for i,body in enumerate(sofa_bodies):
            s=_pair_score(home,away,body)
            if s>0:
                scored.append((s,i))
        scored.sort(reverse=True)
        if not scored or scored[0][0]<0.55:
            flash_only.append({"flashscore":name,"best_score":scored[0][0] if scored else 0.0,"reason":"NO_CONSERVATIVE_SOFA_IDENTITY_MATCH"})
            continue
        best_score,best_idx=scored[0]
        second=scored[1][0] if len(scored)>1 else 0.0
        if second>=best_score-0.05:
            ambiguous.append({
                "flashscore":name,
                "best_score":round(best_score,6),
                "second_score":round(second,6),
                "reason":"MULTIPLE_NEAR_EQUAL_SOFA_MATCHES",
            })
            continue
        used_sofa.add(best_idx)
        matches.append({
            "flashscore":name,
            "sofascore":sofa_obs[best_idx],
            "identity_score":round(best_score,6),
            "match_basis":"TEAM_IDENTITY_TOKEN_MATCH_ONLY",
        })
    sofa_only=[{"sofascore":raw,"reason":"NO_CONSERVATIVE_FLASH_IDENTITY_MATCH"} for i,raw in enumerate(sofa_obs) if i not in used_sofa]
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return {
        "schema":"MATRIX_FOOTBALL_WORLD_CALENDAR_RECONCILIATION_V1",
        "generated_at_utc":now,
        "target_date_bogota":target,
        "status":"PASS_OPEN_RECONCILIATION",
        "source_order":["SOFASCORE","FLASHSCORE","APIS"],
        "source_counts":{"sofascore":len(sofa_obs),"flashscore":len(flash_obs)},
        "reconciliation":{
            "confirmed_both":len(matches),
            "sofascore_only":len(sofa_only),
            "flashscore_only":len(flash_only),
            "ambiguous":len(ambiguous),
        },
        "confirmed_both":matches,
        "sofascore_only":sofa_only,
        "flashscore_only":flash_only,
        "ambiguous":ambiguous,
        "policy":{
            "missing_not_zero":True,
            "no_silent_imputation":True,
            "no_forced_count_equality":True,
            "time_match_certified":False,
            "identity_match_threshold":0.55,
            "ambiguous_margin":0.05,
            "api_absence_does_not_delete_open_source_event":True,
            "post_start_backfill_forbidden":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def _latest_capture_dir(root:Path)->Path:
    dirs=sorted(p for p in root.iterdir() if p.is_dir())
    if not dirs:
        raise FileNotFoundError("NO_CALENDAR_CAPTURE_DIR")
    return dirs[-1]


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--root",default=str(DEFAULT_ROOT))
    p.add_argument("--target-date")
    p.add_argument("--out",default=str(DEFAULT_OUT))
    a=p.parse_args()
    root=Path(a.root)
    day=root/a.target_date if a.target_date else _latest_capture_dir(root)
    sofa=_load(day/"sofascore_opera_capture.json")
    flash=_load(day/"flashscore_opera_capture.json")
    result=reconcile(sofa,flash)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "target_date_bogota":result["target_date_bogota"],
        "source_counts":result["source_counts"],
        "reconciliation":result["reconciliation"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
