from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL="https://v3.football.api-sports.io"
FINAL_DELAY_MINUTES=120
MAX_REQUESTS=120
TIMEOUT_SECONDS=20.0
STANDARD_FINAL={"FT"}
NONSTANDARD_TERMINAL={"AET","PEN","PST","CANC","ABD","AWD","WO","SUSP","INT"}


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _utc(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _canonical(value:Any)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)


def _sha(value:Any)->str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _record_sha(row:Mapping[str,Any])->str:
    body=dict(row); body.pop("record_sha256",None)
    return _sha(body)


def _load_ledger(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    rows=[]; prev=None; seen=set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip(): continue
        row=json.loads(raw)
        fid=str(row.get("fixture_id") or "")
        if not fid or fid in seen: raise ValueError("DUPLICATE_OR_MISSING_FIXTURE")
        if row.get("previous_record_sha256")!=prev: raise ValueError("LEDGER_HASH_CHAIN_BROKEN")
        if row.get("record_sha256")!=_record_sha(row): raise ValueError("LEDGER_RECORD_SHA_MISMATCH")
        if row.get("terminal_status")!="FT": raise ValueError("LEDGER_REQUIRES_STANDARD_FT")
        if row.get("metrics_opened") is not False: raise ValueError("METRICS_MUST_REMAIN_CLOSED")
        if row.get("used_for_metrics") is not False: raise ValueError("OUTCOME_MUST_NOT_AUTO_OPEN_METRICS")
        if row.get("p_matrix_status")!="NOT_GENERATED": raise ValueError("P_MATRIX_MUST_NOT_EXIST")
        if row.get("real_money")!="BLOCKED": raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")
        prev=row["record_sha256"]; seen.add(fid); rows.append(row)
    return rows


def _append(path:Path,payload:Mapping[str,Any])->dict[str,Any]:
    rows=_load_ledger(path)
    fid=str(payload.get("fixture_id") or "")
    if any(str(r["fixture_id"])==fid for r in rows): raise ValueError("DUPLICATE_SETTLEMENT")
    row=dict(payload)
    row["previous_record_sha256"]=rows[-1]["record_sha256"] if rows else None
    row["record_sha256"]=_record_sha(row)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as h:
        h.write(_canonical(row)+"\n")
    _load_ledger(path)
    return row


def _provider_errors_empty(v:Any)->bool:
    return v is None or (isinstance(v,(list,dict,str)) and len(v)==0)


def _exact_fixture(payload:Mapping[str,Any],fixture_id:str)->Mapping[str,Any]:
    if not _provider_errors_empty(payload.get("errors")):
        raise ValueError("API_FOOTBALL_PROVIDER_ERROR")
    rows=payload.get("response")
    if not isinstance(rows,list): raise ValueError("API_RESPONSE_NOT_LIST")
    exact=[r for r in rows if isinstance(r,Mapping) and isinstance(r.get("fixture"),Mapping) and str(r["fixture"].get("id"))==fixture_id]
    if len(exact)!=1: raise ValueError(f"EXACT_FIXTURE_REQUIRED:{fixture_id}:{len(exact)}")
    return exact[0]


def run(root:Path,api_key:str,now_utc:datetime|None=None,session:Any|None=None)->dict[str,Any]:
    freeze=_load(root/"prospective_market_freeze/freeze.json")
    rows=freeze.get("rows")
    if not isinstance(rows,list): raise ValueError("FREEZE_ROWS_MISSING")
    key=str(api_key or "").strip()
    if not key: raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    now=(now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    ledger_path=root/"prospective_market_freeze/settlement_ledger.jsonl"
    existing={str(r["fixture_id"]) for r in _load_ledger(ledger_path)}
    client=session or requests.Session()
    raw_dir=root/"prospective_market_freeze/settlement_raw"; raw_dir.mkdir(parents=True,exist_ok=True)
    settled=[]; pending=[]; blocked=[]; network_calls=0

    for row in rows:
        fid=str(row["fixture_id"])
        if fid in existing:
            continue
        kickoff=_utc(row["kickoff_utc"])
        ready_after=kickoff+timedelta(minutes=FINAL_DELAY_MINUTES)
        if now<ready_after:
            pending.append({"fixture_id":fid,"reason":"WAITING_FINAL_WINDOW","lookup_after_utc":ready_after.isoformat()})
            continue
        if network_calls>=MAX_REQUESTS:
            blocked.append({"fixture_id":fid,"reason":"REQUEST_BUDGET_REACHED"})
            continue
        response=client.get(BASE_URL+"/fixtures",headers={"x-apisports-key":key},params={"id":fid},timeout=TIMEOUT_SECONDS)
        network_calls+=1
        body=bytes(response.content)
        raw_path=raw_dir/f"fixture_{fid}.bin"; raw_path.write_bytes(body)
        payload_sha=hashlib.sha256(body).hexdigest()
        try:
            payload=response.json()
            pf=_exact_fixture(payload,fid)
        except Exception as e:
            blocked.append({"fixture_id":fid,"reason":str(e),"raw_sha256":payload_sha})
            continue

        fixture=pf.get("fixture"); teams=pf.get("teams"); score=pf.get("score")
        if not all(isinstance(x,Mapping) for x in (fixture,teams,score)):
            blocked.append({"fixture_id":fid,"reason":"FINAL_PAYLOAD_STRUCTURE_INVALID"}); continue
        status=fixture.get("status")
        short=str(status.get("short") if isinstance(status,Mapping) else "").upper().strip()
        if short in NONSTANDARD_TERMINAL:
            blocked.append({"fixture_id":fid,"reason":"NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION:"+short}); continue
        if short not in STANDARD_FINAL:
            pending.append({"fixture_id":fid,"reason":"RESULT_NOT_STANDARD_FINAL","provider_status":short}); continue

        home=teams.get("home"); away=teams.get("away")
        if not isinstance(home,Mapping) or not isinstance(away,Mapping):
            blocked.append({"fixture_id":fid,"reason":"TEAM_IDENTITY_MISSING"}); continue
        if str(home.get("id"))!=str(row["home_team_id"]) or str(away.get("id"))!=str(row["away_team_id"]):
            blocked.append({"fixture_id":fid,"reason":"TEAM_IDENTITY_MISMATCH"}); continue

        ft=score.get("fulltime")
        if not isinstance(ft,Mapping):
            blocked.append({"fixture_id":fid,"reason":"FULLTIME_SCORE_MISSING"}); continue
        hg,ag=ft.get("home"),ft.get("away")
        if isinstance(hg,bool) or isinstance(ag,bool) or not isinstance(hg,int) or not isinstance(ag,int):
            blocked.append({"fixture_id":fid,"reason":"FULLTIME_SCORE_INVALID"}); continue

        total=hg+ag
        record={
            "schema":"MATRIX_FOOTBALL_PROSPECTIVE_SETTLEMENT_RECORD_V1",
            "fixture_id":fid,
            "target_key":row["target_key"],
            "kickoff_utc":row["kickoff_utc"],
            "freeze_at_utc":row["freeze_at_utc"],
            "input_sha256":row["input_sha256"],
            "frozen_research_probabilities":row["frozen_research_probabilities"],
            "terminal_status":"FT",
            "fulltime_home_goals":hg,
            "fulltime_away_goals":ag,
            "outcomes":{"1x2":"H" if hg>ag else "D" if hg==ag else "A","over_2_5":total>=3,"btts":hg>0 and ag>0},
            "result_source_provider":"api_football",
            "result_source_reference":"/fixtures?id="+fid,
            "result_payload_sha256":payload_sha,
            "settled_at_utc":now.isoformat(),
            "metrics_opened":False,
            "used_for_metrics":False,
            "p_matrix_status":"NOT_GENERATED",
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
        _append(ledger_path,record); existing.add(fid); settled.append(fid)

    ledger=_load_ledger(ledger_path)
    result={
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_SETTLEMENT_SYNC_V1",
        "run_at_utc":now.isoformat(),
        "frozen_event_count":len(rows),
        "new_settlement_count":len(settled),
        "ledger_final_count":len(ledger),
        "pending_count":len(pending),
        "blocked_count":len(blocked),
        "network_calls":network_calls,
        "settled_fixture_ids":settled,
        "pending":pending,
        "blocked":blocked,
        "metrics_opened":False,
        "outcomes_used_for_metrics":0,
        "settlement_final_only":True,
        "p_matrix_status":"NOT_GENERATED",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }
    out=root/"prospective_market_freeze/settlement_sync_last.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return result


def main()->None:
    result=run(Path("evidence/api_football"),os.environ.get("API_FOOTBALL_KEY",""))
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
