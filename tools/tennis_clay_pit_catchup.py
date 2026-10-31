from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient
from tools.tennis_clay_lane_bootstrap import evaluate_elo

K=32.0
SCALE=400.0
LANE_ID="ATP_CHALLENGER_MEN_SINGLES_CLAY"


def _load(path: Path) -> dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dt(value: object) -> datetime | None:
    try:
        out=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None
    if out.tzinfo is None:
        out=out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _rows(payload: Mapping[str,Any]) -> list[Mapping[str,Any]]:
    raw=payload.get("data")
    return [x for x in raw if isinstance(x,Mapping)] if isinstance(raw,list) else []


def _player_id(row: Mapping[str,Any], side: int) -> str:
    p=row.get(f"player{side}")
    p=p if isinstance(p,Mapping) else {}
    raw=p.get("id") or row.get(f"player{side}Id")
    token=str(raw or "").strip()
    return token if token.isdigit() and int(token)>0 else ""


def _player_meta(row: Mapping[str,Any], side: int) -> dict[str,str]:
    p=row.get(f"player{side}")
    p=p if isinstance(p,Mapping) else {}
    return {
        "name":str(p.get("name") or row.get(f"player{side}Name") or "").strip(),
        "ioc":str(p.get("countryAcr") or p.get("country") or row.get(f"player{side}Country") or "").strip().upper(),
    }


def _is_standard_clay(row: Mapping[str,Any]) -> bool:
    result_type=str(row.get("result_type") or row.get("resultType") or "").strip().casefold()
    if result_type!="completed":
        return False
    tournament=row.get("tournament") if isinstance(row.get("tournament"),Mapping) else {}
    court=tournament.get("court") if isinstance(tournament.get("court"),Mapping) else {}
    if str(court.get("name") or "").strip().casefold() not in {"clay","i.clay","indoor clay"}:
        return False
    rank=tournament.get("rankId")
    try:
        if int(rank)!=1:
            return False
    except (TypeError,ValueError):
        return False
    return bool(_player_id(row,1) and _player_id(row,2))


def _date_token(row: Mapping[str,Any]) -> int | None:
    d=_dt(row.get("date"))
    return int(d.strftime("%Y%m%d")) if d else None


def load_historical_rows(path: Path) -> list[dict[str,Any]]:
    with path.open(newline="",encoding="utf-8") as fh:
        out=[]
        for row in csv.DictReader(fh):
            item=dict(row)
            item["tourney_date"]=int(item["tourney_date"])
            item["match_num"]=int(item["match_num"])
            item["label_a_win"]=int(item["label_a_win"])
            out.append(item)
        return out


def authority_index(
    authority: Mapping[str,Any],
    supplemental_crosswalk: Mapping[str,Any] | None = None,
) -> dict[str,dict[str,Any]]:
    out={}
    for row in authority.get("records",[]) or []:
        if not isinstance(row,Mapping):
            continue
        pid=str(row.get("provider_player_id") or "")
        if not pid.startswith("rapidapi-tennis:player:"):
            continue
        cid=str(row.get("canonical_source_id") or "").strip()
        if not cid:
            history=row.get("pre_cut_history")
            source_ids=[
                str(x).strip()
                for x in (history.get("canonical_source_ids",[]) if isinstance(history,Mapping) else [])
                if str(x).strip()
            ]
            if len(set(source_ids))==1:
                cid=source_ids[0]
        name=str(row.get("canonical_name") or row.get("provider_display_name") or "").strip()
        if not cid or not name:
            continue
        out[pid.split(":")[-1]]={
            "canonical_source_id":cid,
            "canonical_name":name,
            "authority_basis":row.get("authority_basis"),
        }

    if isinstance(supplemental_crosswalk,Mapping):
        passed_provider_ids={
            str(pid)
            for event in supplemental_crosswalk.get("events",[]) or []
            if isinstance(event,Mapping) and event.get("status")=="PASS"
            for pid in event.get("provider_player_ids",[]) or []
            if str(pid)
        }
        for row in supplemental_crosswalk.get("mappings",[]) or []:
            if not isinstance(row,Mapping) or row.get("status")!="PASS":
                continue
            provider_id=str(row.get("provider_player_id") or "")
            if provider_id not in passed_provider_ids:
                continue
            if not provider_id.startswith("rapidapi-tennis:player:"):
                continue
            cid=str(row.get("canonical_source_id") or "").strip()
            name=str(row.get("canonical_name") or "").strip()
            if not cid or not name:
                continue
            numeric=provider_id.split(":")[-1]
            existing=out.get(numeric)
            if existing is not None and existing["canonical_source_id"]!=cid:
                raise ValueError("CLAY_SUPPLEMENTAL_IDENTITY_COLLISION:"+provider_id)
            out.setdefault(numeric,{
                "canonical_source_id":cid,
                "canonical_name":name,
                "authority_basis":"SUPPLEMENTAL_IDENTITY_ONLY_CROSSWALK",
            })
    return out

def normalize_catchup_rows(rows: Iterable[Mapping[str,Any]]) -> list[dict[str,Any]]:
    seen=set(); out=[]
    for row in rows:
        if not _is_standard_clay(row):
            continue
        mid=str(row.get("matchId") or row.get("id") or "").strip()
        if not mid or mid in seen:
            continue
        token=_date_token(row)
        if token is None:
            continue
        p1=_player_id(row,1); p2=_player_id(row,2)
        if not p1 or not p2 or p1==p2:
            continue
        seen.add(mid)
        tournament=row.get("tournament") if isinstance(row.get("tournament"),Mapping) else {}
        m1=_player_meta(row,1); m2=_player_meta(row,2)
        out.append({
            "match_id":mid,
            "tourney_date":token,
            "winner_provider_id":p1,
            "winner_name":m1["name"],
            "winner_ioc":m1["ioc"],
            "loser_provider_id":p2,
            "loser_name":m2["name"],
            "loser_ioc":m2["ioc"],
            "tournament_id":str(tournament.get("id") or row.get("tournamentId") or ""),
            "tournament_name":str(tournament.get("name") or ""),
            "source_sha256":hashlib.sha256(
                json.dumps(dict(row),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
            ).hexdigest(),
        })
    out.sort(key=lambda x:(x["tourney_date"],x["match_id"]))
    return out


def build_graph(matches: list[dict[str,Any]]) -> dict[str,set[str]]:
    graph=defaultdict(set)
    for row in matches:
        a=row["winner_provider_id"]; b=row["loser_provider_id"]
        graph[a].add(b); graph[b].add(a)
    return graph


def component(graph: Mapping[str,set[str]], start: str) -> set[str]:
    seen={start}; q=deque([start])
    while q:
        cur=q.popleft()
        for nxt in graph.get(cur,set()):
            if nxt not in seen:
                seen.add(nxt); q.append(nxt)
    return seen


def causal_component(matches: list[dict[str,Any]], start: str) -> set[str]:
    """Return only identities that can causally affect start's final rating.

    Ratings update in day batches. A player newly introduced by a match on day D
    needs its pre-D rating, so only matches from earlier days can feed that
    requirement. Later-only branches in the undirected match graph cannot
    retroactively affect the target and must not block a prospective freeze.
    """
    needed={start}
    grouped=defaultdict(list)
    for row in matches:
        grouped[int(row["tourney_date"])].append(row)
    for day in sorted(grouped,reverse=True):
        needed_at_end=set(needed)
        active=[
            row for row in grouped[day]
            if row["winner_provider_id"] in needed_at_end
            or row["loser_provider_id"] in needed_at_end
        ]
        for row in active:
            needed.add(row["winner_provider_id"])
            needed.add(row["loser_provider_id"])
    return needed


def replay(
    *,
    base_ratings: Mapping[str,float],
    matches: list[dict[str,Any]],
    authority: Mapping[str,dict[str,Any]],
) -> dict[str,float]:
    ratings=defaultdict(lambda:1500.0,{str(k):float(v) for k,v in base_ratings.items()})
    grouped=defaultdict(list)
    for row in matches:
        a=authority.get(row["winner_provider_id"])
        b=authority.get(row["loser_provider_id"])
        if not a or not b:
            continue
        grouped[row["tourney_date"]].append((row,a["canonical_source_id"],b["canonical_source_id"]))
    for day in sorted(grouped):
        deltas=defaultdict(float)
        for row,wid,lid in grouped[day]:
            if wid==lid:
                continue
            rw=ratings[wid]; rl=ratings[lid]
            p=1.0/(1.0+10.0**((rl-rw)/SCALE))
            delta=K*(1.0-p)
            deltas[wid]+=delta
            deltas[lid]-=delta
        for pid,delta in deltas.items():
            ratings[pid]+=delta
    return dict(ratings)


def build_state(
    *,
    historical_rows: list[dict[str,Any]],
    result_rows: list[Mapping[str,Any]],
    authority_payload: Mapping[str,Any],
    target_provider_ids: set[str],
    source_start: date,
    source_stop: date,
    supplemental_crosswalk_payload: Mapping[str,Any] | None = None,
) -> dict[str,Any]:
    _,base=evaluate_elo(historical_rows,k=K,score_split=None)
    matches=normalize_catchup_rows(result_rows)
    auth=authority_index(authority_payload,supplemental_crosswalk_payload)
    ratings=replay(base_ratings=base,matches=matches,authority=auth)
    targets=[]
    for raw in sorted(target_provider_ids):
        pid=raw.split(":")[-1] if raw.startswith("rapidapi-tennis:player:") else raw
        comp=causal_component(matches,pid)
        missing=sorted(x for x in comp if x not in auth)
        mapping=auth.get(pid)
        ready=bool(mapping) and not missing
        canonical_id=mapping["canonical_source_id"] if mapping else None
        targets.append({
            "provider_player_id":"rapidapi-tennis:player:"+pid,
            "canonical_source_id":canonical_id,
            "canonical_name":mapping["canonical_name"] if mapping else None,
            "component_player_count":len(comp),
            "component_unmapped_provider_ids":["rapidapi-tennis:player:"+x for x in missing],
            "catchup_match_count":sum(
                1 for row in matches
                if row["winner_provider_id"] in comp or row["loser_provider_id"] in comp
            ),
            "base_rating":float(base.get(canonical_id,1500.0)) if canonical_id else None,
            "rating_after_catchup":float(ratings.get(canonical_id,1500.0)) if ready and canonical_id else None,
            "ready":ready,
            "blocker":None if ready else (
                "TARGET_IDENTITY_MISSING" if mapping is None
                else "CATCHUP_COMPONENT_HAS_UNMAPPED_IDENTITIES"
            ),
        })
    target_components=[]
    for raw in sorted(target_provider_ids):
        pid=raw.split(":")[-1] if raw.startswith("rapidapi-tennis:player:") else raw
        target_components.append(causal_component(matches,pid))
    target_component_hits=defaultdict(int)
    for comp in target_components:
        for pid in comp:
            if pid not in auth:
                target_component_hits[pid]+=1
    observed=defaultdict(lambda:{"names":set(),"iocs":set(),"matches":0})
    for row in matches:
        for prefix in ("winner","loser"):
            pid=str(row[f"{prefix}_provider_id"])
            item=observed[pid]
            name=str(row.get(f"{prefix}_name") or "").strip()
            ioc=str(row.get(f"{prefix}_ioc") or "").strip().upper()
            if name:
                item["names"].add(name)
            if ioc:
                item["iocs"].add(ioc)
            item["matches"]+=1
    backlog=[]
    for pid,hits in sorted(target_component_hits.items(), key=lambda kv:(-kv[1],-observed[kv[0]]["matches"],kv[0])):
        names=sorted(observed[pid]["names"])
        iocs=sorted(observed[pid]["iocs"])
        backlog.append({
            "provider_player_id":"rapidapi-tennis:player:"+pid,
            "numeric_player_id":pid,
            "observed_names":names,
            "observed_iocs":iocs,
            "catchup_matches":int(observed[pid]["matches"]),
            "target_component_hits":int(hits),
            "identity_observation_status":"CONSISTENT" if len(names)==1 and len(iocs)<=1 else "CONFLICT",
        })
    return {
        "schema":"MATRIX_TENNIS_CLAY_ELO_PIT_CATCHUP_STATE_V1",
        "lane_id":LANE_ID,
        "model_identity":"ATP_CHALLENGER_CLAY_ELO_V1",
        "chosen_k":K,
        "probability_scale":SCALE,
        "rating_initial_for_truly_unseen_canonical_player":1500.0,
        "same_day_update_policy":"BATCH_AFTER_ALL_MATCHES_ON_TOURNEY_DATE",
        "historical_dataset_max_tourney_date":max(x["tourney_date"] for x in historical_rows),
        "catchup_source_start":source_start.isoformat(),
        "catchup_source_stop":source_stop.isoformat(),
        "catchup_standard_clay_matches":len(matches),
        "catchup_match_ids_sha256":hashlib.sha256("\n".join(x["match_id"] for x in matches).encode()).hexdigest(),
        "authority_provider_ids":len(auth),
        "identity_closure_policy":"REVERSE_TIME_CAUSAL_BATCH_DAY",
        "supplemental_identity_crosswalk_used":isinstance(supplemental_crosswalk_payload,Mapping),
        "targets":targets,
        "ready_targets":sum(1 for x in targets if x["ready"]),
        "blocked_targets":sum(1 for x in targets if not x["ready"]),
        "unmapped_identity_backlog":backlog,
        "unmapped_identity_backlog_count":len(backlog),
        "metrics_opened":False,
        "outcomes_used_for_model_parameter_tuning":0,
        "historical_backfill_into_prospective_holdout":False,
        "odds_used":False,
        "silent_imputation":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--historical-dataset",required=True)
    p.add_argument("--identity-authority",required=True)
    p.add_argument("--prefeature",required=True)
    p.add_argument("--supplemental-crosswalk")
    p.add_argument("--out",required=True)
    a=p.parse_args()
    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    historical=load_historical_rows(Path(a.historical_dataset))
    authority=_load(Path(a.identity_authority))
    pre=_load(Path(a.prefeature))
    supplemental=(
        _load(Path(a.supplemental_crosswalk))
        if a.supplemental_crosswalk and Path(a.supplemental_crosswalk).exists()
        else None
    )
    target_ids={
        str(identity.get("provider_player_id") or "")
        for event in pre.get("events",[]) or []
        for identity in event.get("player_identities",[]) or []
        if isinstance(identity,Mapping)
    }
    max_hist=max(x["tourney_date"] for x in historical)
    start=date(max_hist//10000,(max_hist//100)%100,max_hist%100)+timedelta(days=1)
    stop=datetime.now(timezone.utc).date()-timedelta(days=1)
    client=RapidApiTennisClient(key)
    raw=[]
    cursor=start
    windows=[]
    while cursor<=stop:
        end=min(stop,cursor+timedelta(days=13))
        if cursor==end:
            path=f"/tennis/v2/atp/results/{cursor.isoformat()}"
        else:
            path=f"/tennis/v2/atp/results/{cursor.isoformat()}/{end.isoformat()}"
        window_rows=[]
        page=1
        while page<=20:
            payload=client._get(path,{
                "pageNo":page,
                "pageSize":100,
                "filter":"PlayerGroup:singles;TourRank:1",
                "include":"round,tournament.court,tournament.rank",
            })
            rows=_rows(payload)
            window_rows.extend(rows)
            if not bool(payload.get("hasNextPage")):
                break
            page+=1
        if page>20:
            raise SystemExit("CLAY_CATCHUP_RESULT_PAGE_LIMIT_REACHED")
        raw.extend(window_rows)
        windows.append({"start":cursor.isoformat(),"stop":end.isoformat(),"rows":len(window_rows),"pages":page})
        cursor=end+timedelta(days=1)
    state=build_state(
        historical_rows=historical,
        result_rows=raw,
        authority_payload=authority,
        target_provider_ids=target_ids,
        source_start=start,
        source_stop=stop,
        supplemental_crosswalk_payload=supplemental,
    )
    state["provider"]="rapidapi_tennis"
    state["provider_network_calls"]=client.request_count
    state["source_windows"]=windows
    state["generated_at_utc"]=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(state,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "standard_clay_matches":state["catchup_standard_clay_matches"],
        "targets":len(state["targets"]),
        "ready_targets":state["ready_targets"],
        "blocked_targets":state["blocked_targets"],
        "unmapped_identity_backlog_count":state["unmapped_identity_backlog_count"],
        "provider_network_calls":state["provider_network_calls"],
        "real_money":"BLOCKED"
    },sort_keys=True))


if __name__=="__main__":
    main()
