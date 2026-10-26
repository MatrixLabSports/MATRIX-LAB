from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SCHEMA="MATRIX_TELEGRAM_QUOTE_ATTEMPT_V1"
GENESIS="0"*64
AUTHORIZED=("betano","betplay","rushbet")


def _canonical(value:Any)->str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)


def _sha(value:Any)->str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)


def _load(path:Path)->list[dict[str,Any]]:
    if not path.exists():
        return []
    rows=[]; prev=GENESIS; seen=set()
    for n,raw in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not raw.strip(): continue
        row=json.loads(raw)
        if row.get("schema")!=SCHEMA: raise ValueError(f"QUOTE_ATTEMPT_SCHEMA_INVALID:{n}")
        attempt_id=str(row.get("attempt_id") or "")
        if not attempt_id or attempt_id in seen: raise ValueError(f"QUOTE_ATTEMPT_DUPLICATE_OR_MISSING_ID:{n}")
        if row.get("previous_record_sha256")!=prev: raise ValueError(f"QUOTE_ATTEMPT_CHAIN_BROKEN:{n}")
        body=dict(row); record_sha=body.pop("record_sha256",None)
        if record_sha!=_sha(body): raise ValueError(f"QUOTE_ATTEMPT_SHA_MISMATCH:{n}")
        prev=record_sha; seen.add(attempt_id); rows.append(row)
    return rows


def _market_is_total(item:Mapping[str,Any])->bool:
    text=" ".join(str(item.get(k) or "").casefold() for k in ("market_key","bet_type","metric"))
    return "total" in text or "over under" in text


def _side_is_over(item:Mapping[str,Any])->bool:
    text=" ".join(str(item.get(k) or "").casefold() for k in ("side","selection_name","selection_key","market_key"))
    return "over" in text


def _house_view(diag:Mapping[str,Any],house:str)->dict[str,Any]:
    rows_by_book=diag.get("rows_by_book") if isinstance(diag.get("rows_by_book"),Mapping) else {}
    line_map=diag.get("candidate_lines_by_book") if isinstance(diag.get("candidate_lines_by_book"),Mapping) else {}
    items=[dict(x) for x in (line_map.get(house) or []) if isinstance(x,Mapping)]
    totals=[x for x in items if _market_is_total(x)]
    exact_lines=sorted({float(x["line"]) for x in totals if isinstance(x.get("line"),(int,float))})
    over25=[x for x in totals if float(x.get("line") or -999)==2.5 and _side_is_over(x)]
    exact_odds=sorted({float(x["odds"]) for x in over25 if isinstance(x.get("odds"),(int,float))})
    return {
        "seen":int(rows_by_book.get(house) or 0)>0,
        "row_count":int(rows_by_book.get(house) or 0),
        "totals_market_seen":bool(totals),
        "available_lines":exact_lines,
        "nearby_lines_2_25_2_75":[x for x in exact_lines if x in {2.25,2.75}],
        "over_2_5_seen":bool(over25),
        "exact_over_2_5_odds":exact_odds,
    }


def _identity(diag:Mapping[str,Any])->dict[str,Any]:
    status=str(diag.get("status") or "")
    scores=diag.get("identity_top_scores") if isinstance(diag.get("identity_top_scores"),list) else []
    top=diag.get("identity_top_candidates") if isinstance(diag.get("identity_top_candidates"),list) else []
    if status=="BLOCKED_EVENT_NOT_COVERED": state="NOT_COVERED"
    elif status=="BLOCKED_IDENTITY_LOW_SCORE": state="LOW_SCORE"
    elif status=="BLOCKED_IDENTITY_AMBIGUOUS": state="AMBIGUOUS"
    elif diag.get("odds_api_event_id"): state="MATCHED"
    else: state="NOT_COVERED"
    return {
        "state":state,
        "score":float(scores[0]) if scores else None,
        "provider_event_id":str(diag.get("odds_api_event_id") or "") or None,
        "top_candidates":top[:5],
    }


def build_attempt(*,fixture_id:str,signal_key:str,query_at_utc:datetime,kickoff:Any,
                  odds_diag:Mapping[str,Any],api_diag:Mapping[str,Any],
                  selected_offer:Mapping[str,Any]|None,final_discard_reason:str,
                  run_token:str|None=None)->dict[str,Any]:
    q=query_at_utc.astimezone(timezone.utc).replace(microsecond=0)
    k=_utc(kickoff)
    houses={h:_house_view(odds_diag,h) for h in AUTHORIZED}
    evidence={
        "odds_api_net_diagnostic":dict(odds_diag),
        "api_football_offer_diagnostic":dict(api_diag),
        "selected_offer":dict(selected_offer) if isinstance(selected_offer,Mapping) else None,
    }
    evidence_sha=_sha(evidence)
    attempt_id=_sha({
        "fixture_id":str(fixture_id),
        "signal_key":str(signal_key),
        "query_at_utc":q.isoformat(),
        "evidence_sha256":evidence_sha,
    })
    return {
        "schema":SCHEMA,
        "attempt_id":attempt_id,
        "run_token":run_token,
        "fixture_id":str(fixture_id),
        "signal_key":str(signal_key),
        "query_at_utc":q.isoformat(),
        "kickoff_utc":k.isoformat(),
        "seconds_to_kickoff":int((k-q).total_seconds()),
        "identity_match":_identity(odds_diag),
        "houses":houses,
        "totals_market_seen_any_authorized":any(v["totals_market_seen"] for v in houses.values()),
        "exact_lines_available_any_authorized":sorted({line for v in houses.values() for line in v["available_lines"]}),
        "over_2_5_seen_any_authorized":any(v["over_2_5_seen"] for v in houses.values()),
        "exact_over_2_5_odds_by_house":{h:v["exact_over_2_5_odds"] for h,v in houses.items()},
        "final_discard_reason":str(final_discard_reason),
        "evidence_sha256":evidence_sha,
        "evidence_snapshot":evidence,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def append_attempt(path:Path,row:Mapping[str,Any])->dict[str,Any]:
    rows=_load(path)
    item=dict(row)
    if item.get("schema")!=SCHEMA: raise ValueError("QUOTE_ATTEMPT_SCHEMA_INVALID")
    if any(x["attempt_id"]==item.get("attempt_id") for x in rows):
        raise ValueError("QUOTE_ATTEMPT_ALREADY_PERSISTED")
    item["previous_record_sha256"]=rows[-1]["record_sha256"] if rows else GENESIS
    item["record_sha256"]=_sha(item)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8",newline="\n") as fh:
        fh.write(_canonical(item)+"\n")
    _load(path)
    return item


def _summary_core(rows:list[Mapping[str,Any]])->dict[str,Any]:
    coverage={h:0 for h in AUTHORIZED}; all_three_fail=0; identity_problem=0; nearby_without_exact=0
    for row in rows:
        ident=(row.get("identity_match") or {}).get("state")
        if ident in {"LOW_SCORE","AMBIGUOUS","NOT_COVERED"}:
            identity_problem+=1
        houses=row.get("houses") or {}
        exact_any=False; near_any=False
        for h in AUTHORIZED:
            hv=houses.get(h) or {}
            if hv.get("over_2_5_seen"):
                coverage[h]+=1
                exact_any=True
            if hv.get("nearby_lines_2_25_2_75"):
                near_any=True
        if not exact_any:
            all_three_fail+=1
        if near_any and not exact_any:
            nearby_without_exact+=1
    return {
        "attempt_count":len(rows),
        "exact_over25_coverage_by_house":coverage,
        "all_three_without_exact_over25":all_three_fail,
        "identity_problem_count":identity_problem,
        "nearby_2_25_or_2_75_without_exact_2_5":nearby_without_exact,
    }


def _timing_disappearance(rows:list[Mapping[str,Any]])->dict[str,Any]:
    by_fixture:dict[str,list[Mapping[str,Any]]]={}
    for row in rows:
        fid=str(row.get("fixture_id") or "")
        if fid:
            by_fixture.setdefault(fid,[]).append(row)
    affected=[]
    for fid,attempts in by_fixture.items():
        ordered=sorted(
            attempts,
            key=lambda x:(
                int(x.get("seconds_to_kickoff") or -10**12),
                str(x.get("query_at_utc") or ""),
            ),
            reverse=True,
        )
        seen_exact=False
        first_exact_seconds=None
        for row in ordered:
            exact=bool(row.get("over_2_5_seen_any_authorized"))
            seconds=int(row.get("seconds_to_kickoff") or 0)
            if exact:
                seen_exact=True
                if first_exact_seconds is None:
                    first_exact_seconds=seconds
                continue
            if seen_exact and seconds>=0:
                affected.append({
                    "fixture_id":fid,
                    "exact_seen_earlier_seconds_to_kickoff":first_exact_seconds,
                    "missing_later_seconds_to_kickoff":seconds,
                    "later_attempt_id":row.get("attempt_id"),
                })
                break
    return {
        "timing_disappearance_fixture_count":len(affected),
        "timing_disappearance_fixtures":affected,
    }


def summarize_run(rows:list[Mapping[str,Any]],run_token:str)->dict[str,Any]:
    current=[x for x in rows if str(x.get("run_token") or "")==str(run_token)]
    core=_summary_core(current)
    return {
        "quote_attempts_live_this_run":core.pop("attempt_count"),
        **core,
    }


def summarize_cumulative(rows:list[Mapping[str,Any]],minimum_target:int=50,maximum_target:int=100)->dict[str,Any]:
    core=_summary_core(rows)
    timing=_timing_disappearance(rows)
    n=int(core["attempt_count"])
    return {
        "real_quote_attempts_total":n,
        "target_window_minimum":int(minimum_target),
        "target_window_maximum":int(maximum_target),
        "sample_gate_status":"READY_FOR_CAUSAL_RECOMMENDATION" if n>=minimum_target else "ACCUMULATING_REAL_REVALIDATIONS",
        "remaining_to_minimum":max(0,int(minimum_target)-n),
        **{k:v for k,v in core.items() if k!="attempt_count"},
        **timing,
        "synthetic_attempts_included":False,
    }


def load_verified(path:Path)->list[dict[str,Any]]:
    return _load(path)
