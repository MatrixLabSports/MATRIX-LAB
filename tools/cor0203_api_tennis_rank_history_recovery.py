from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote

from tools.cor0203_expand_identity_authority import merge_certified_aliases
from tools.cor0203_rapidapi_tennis_discovery import (
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
    _data_rows,
)

CUT_DATE=date(2026,9,21)
CUT_TOKEN=20260921
COUNTRY_ALIASES={"POR":"PRT"}


def _load(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path,value: Mapping[str,Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(dict(value),indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")


def _norm(value: object) -> str:
    text=unicodedata.normalize("NFKD",str(value or ""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _ioc(value: object) -> str:
    token=str(value or "").strip().upper()
    return COUNTRY_ALIASES.get(token,token)


def _hand(value: object) -> str | None:
    token=str(value or "").strip().casefold()
    if token.startswith("left"): return "L"
    if token.startswith("right"): return "R"
    return None


def _dob(value: object) -> str | None:
    token=str(value or "").strip()[:10].replace("-","")
    if len(token)!=8 or not token.isdigit():
        return None
    try:
        parsed=date(int(token[:4]),int(token[4:6]),int(token[6:8]))
    except ValueError:
        return None
    return token if parsed < CUT_DATE else None


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()


def _history_index(path: Path) -> dict[tuple[str,str],dict[str,Any]]:
    grouped: dict[tuple[str,str],dict[str,Any]]=defaultdict(lambda:{
        "canonical_source_ids":set(),"canonical_iocs":set(),"observed_hands":set(),
        "canonical_names":set(),"rows":0,"latest_row_date":0,
    })
    for row in csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()):
        try:
            day=int(float(str(row.get("tourney_date") or "0")))
        except ValueError:
            continue
        if day>=CUT_TOKEN or str(row.get("tourney_level") or "").strip()!="C":
            continue
        for side in ("winner","loser"):
            name=str(row.get(f"{side}_name") or "").strip()
            source_id=str(row.get(f"{side}_id") or "").strip()
            ioc=_ioc(row.get(f"{side}_ioc"))
            hand=str(row.get(f"{side}_hand") or "").strip().upper()
            if not name or not source_id or not ioc:
                continue
            item=grouped[(_norm(name),ioc)]
            item["canonical_source_ids"].add(source_id)
            item["canonical_iocs"].add(ioc)
            if hand:
                item["observed_hands"].add(hand)
            item["canonical_names"].add(name)
            item["rows"]+=1
            item["latest_row_date"]=max(item["latest_row_date"],day)
    return grouped


def _profile_data(payload: Mapping[str,Any]) -> Mapping[str,Any]:
    data=payload.get("data")
    if isinstance(data,Mapping):
        return data
    return payload


def _history_rows(payload: Mapping[str,Any]) -> list[Mapping[str,Any]]:
    rows=payload.get("history")
    if isinstance(rows,list):
        return [x for x in rows if isinstance(x,Mapping)]
    data=payload.get("data")
    if isinstance(data,Mapping) and isinstance(data.get("history"),list):
        return [x for x in data["history"] if isinstance(x,Mapping)]
    return []


def _exact_cut_rank(payload: Mapping[str,Any]) -> tuple[str,str] | None:
    matches=[]
    for row in _history_rows(payload):
        day=str(row.get("date") or "").strip()[:10]
        if day!="2026-09-21":
            continue
        position=str(row.get("position") or "").strip()
        pts=str(row.get("pts") if row.get("pts") is not None else row.get("point") or "").strip()
        if position.isdigit() and int(position)>0 and pts.isdigit() and int(pts)>=0:
            matches.append((position,pts))
    return matches[0] if len(set(matches))==1 and matches else None


def _directory_exact_player(
    *,
    name: str,
    ioc: str,
    page_fetcher: Callable[[str,int],Mapping[str,Any]],
    max_pages: int=10,
) -> tuple[str | None, int]:
    matches=[]
    calls=0
    for page in range(1,max_pages+1):
        payload=page_fetcher(ioc,page)
        calls+=1
        rows=_data_rows(payload)
        for row in rows:
            if not isinstance(row,Mapping):
                continue
            pid=str(row.get("id") or "").strip()
            pname=str(row.get("name") or "").strip()
            pioc=_ioc(row.get("countryAcr"))
            if pid.isdigit() and _norm(pname)==_norm(name) and pioc==ioc:
                matches.append(pid)
        has_next=payload.get("hasNextPage")
        if matches or has_next is False or not rows:
            break
    unique=sorted(set(matches))
    return (unique[0] if len(unique)==1 else None),calls


def recover_rank_history_aliases(
    *,
    bridge_audit: Mapping[str,Any],
    aliases: Mapping[str,Any],
    authority: Mapping[str,Any],
    history_csv: Path,
    profile_fetcher: Callable[[str],Mapping[str,Any]],
    ranking_history_fetcher: Callable[[str],Mapping[str,Any]],
    player_directory_fetcher: Callable[[str,int],Mapping[str,Any]] | None=None,
    profile_by_id_fetcher: Callable[[str],Mapping[str,Any]] | None=None,
    max_recoveries: int=20,
) -> tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    if bridge_audit.get("ranking_cut")!="20260921":
        raise ValueError("BRIDGE_RANKING_CUT_MISMATCH")
    if aliases.get("post_cut_competitive_data_used") is not False:
        raise ValueError("ALIASES_POSTCUT_FLAG_INVALID")
    if authority.get("post_cut_competitive_data_used") is not False:
        raise ValueError("AUTHORITY_POSTCUT_FLAG_INVALID")

    hist=_history_index(history_csv)
    records=[dict(x) for x in aliases.get("records",[]) or [] if isinstance(x,Mapping)]
    by_id={str(x.get("provider_player_id") or ""):x for x in records if str(x.get("provider_player_id") or "")}
    recovered=[]
    blocked=[]
    profile_calls=0
    directory_calls=0
    ranking_history_calls=0

    for row in bridge_audit.get("blocked",[]) or []:
        if not isinstance(row,Mapping):
            continue
        if row.get("reason")!="RAPIDAPI_CUT_RANKING_NAME_NOT_FOUND":
            continue
        provider_id=str(row.get("provider_player_id") or "")
        display=str(row.get("player") or "").strip()
        if not provider_id or not display or provider_id in by_id:
            continue
        if len(recovered)>=max_recoveries:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"RECOVERY_BUDGET_REACHED"})
            continue

        # Do not spend network calls unless exact-name pre-cut history exists for at least one IOC.
        possible=[(k,v) for k,v in hist.items() if k[0]==_norm(display)]
        if not possible:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"NO_EXACT_NAME_PRECUT_CHALLENGER_HISTORY"})
            continue

        try:
            profile=profile_fetcher(display)
            profile_calls+=1
        except Exception:
            profile={}
        data=_profile_data(profile) if isinstance(profile,Mapping) else {}
        pid=str(data.get("id") or data.get("playerId") or "").strip()
        pname=str(data.get("name") or "").strip()
        pioc=_ioc(data.get("countryAcr"))

        if not pid.isdigit():
            possible_iocs=sorted({key[1] for key,_ in possible})
            if player_directory_fetcher is None or profile_by_id_fetcher is None or len(possible_iocs)!=1:
                blocked.append({"provider_player_id":provider_id,"player":display,"reason":"NAME_PROFILE_IDENTITY_INCOMPLETE"})
                continue
            pid,used_calls=_directory_exact_player(
                name=display,
                ioc=possible_iocs[0],
                page_fetcher=player_directory_fetcher,
            )
            directory_calls+=used_calls
            if pid is None:
                blocked.append({"provider_player_id":provider_id,"player":display,"reason":"CORE_DIRECTORY_EXACT_ID_NOT_FOUND"})
                continue
            try:
                profile=profile_by_id_fetcher(pid)
                profile_calls+=1
            except Exception as error:
                blocked.append({"provider_player_id":provider_id,"player":display,"reason":"CORE_PROFILE_LOOKUP_FAILED:"+type(error).__name__})
                continue
            data=_profile_data(profile)
            pname=str(data.get("name") or "").strip()
            pioc=_ioc(data.get("countryAcr"))

        info=data.get("information") if isinstance(data.get("information"),Mapping) else {}
        phand=_hand(info.get("plays") or info.get("hand"))
        pdob=_dob(data.get("birthday"))
        if not pid.isdigit() or _norm(pname)!=_norm(display) or not pioc or pdob is None:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"PROFILE_IDENTITY_INCOMPLETE_AFTER_DIRECTORY"})
            continue

        h=hist.get((_norm(pname),pioc))
        if not h:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"PROFILE_IOC_PRECUT_HISTORY_MISMATCH"})
            continue
        source_ids=sorted(h["canonical_source_ids"])
        iocs=sorted(h["canonical_iocs"])
        hands=sorted(h["observed_hands"])
        names=sorted(h["canonical_names"])
        if len(source_ids)!=1 or iocs!=[pioc] or len(hands)!=1 or hands[0] not in {"R","L"}:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"PRECUT_IDENTITY_NOT_UNIQUE"})
            continue
        if len({_norm(x) for x in names})!=1 or _norm(names[0])!=_norm(pname):
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"PRECUT_NAME_NOT_UNIQUE"})
            continue
        if phand in {"R","L"} and phand!=hands[0]:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"PROFILE_HAND_CONFLICT"})
            continue

        try:
            rh=ranking_history_fetcher(pid)
            ranking_history_calls+=1
        except Exception as error:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"RANKING_HISTORY_LOOKUP_FAILED:"+type(error).__name__})
            continue
        cut=_exact_cut_rank(rh)
        if cut is None:
            blocked.append({"provider_player_id":provider_id,"player":display,"reason":"EXACT_20260921_RANKING_NOT_FOUND"})
            continue
        rank,points=cut

        competitive=[k for k in ("currentRank","points","progress","careerMoney") if k in data]
        rec={
            "provider_player_id":provider_id,
            "provider_display_name":pname,
            "canonical_name":names[0],
            "provider_ioc_raw":pioc,
            "provider_ioc_canonical":pioc,
            "ranking_cut":"2026-09-21",
            "provider_rank":rank,
            "provider_rank_points":points,
            "pre_cut_history":{
                "canonical_source_ids":source_ids,
                "canonical_iocs":iocs,
                "observed_hands":hands,
                "rows":int(h["rows"]),
                "latest_row_date":int(h["latest_row_date"]),
            },
            "biographical_candidates":[{
                "master_id":"RAPIDAPI_PROFILE_"+pid,
                "name":pname,
                "hand":phand or hands[0],
                "dob":pdob,
                "ioc":pioc,
                "height_cm":None,
                "wikidata_id":None,
                "provider_profile_sha256":_sha(profile),
            }],
            "biography_source":"RAPIDAPI_NAME_PROFILE_PLUS_EXACT_21SEP_RANK_HISTORY",
            "authority_basis":"API_TENNIS_EXACT_NAME_TO_RAPIDAPI_PROFILE_PLUS_EXACT_21SEP_RANK_HISTORY_PLUS_PRECUT_CHALLENGER_HISTORY",
            "rapidapi_cut_identity":{
                "provider_player_id":"rapidapi-tennis:player:"+pid,
                "ranking_date":"2026-09-21",
                "rank":rank,
                "points":points,
            },
            "profile_competitive_fields_discarded":competitive+[
                "API_TENNIS_CURRENT_STANDINGS_RANK",
                "API_TENNIS_CURRENT_STANDINGS_POINTS",
            ],
        }
        by_id[provider_id]=rec
        recovered.append(rec)

    out_aliases=dict(aliases)
    out_aliases["records"]=[by_id[k] for k in sorted(by_id)]
    out_aliases["purpose"]=str(out_aliases.get("purpose") or "")+" + exact per-player 21-SEP ranking-history recovery."
    updated_authority,added=merge_certified_aliases(authority,out_aliases)
    audit={
        "schema":"MATRIX_COR0203_API_TENNIS_RANK_HISTORY_RECOVERY_V1",
        "status":"PASS",
        "ranking_cut":"20260921",
        "recovered_count":len(recovered),
        "recovered_provider_ids":[x["provider_player_id"] for x in recovered],
        "aliases_added_to_authority":added,
        "blocked_count":len(blocked),
        "blocked":blocked,
        "profile_calls":profile_calls,
        "directory_calls":directory_calls,
        "ranking_history_calls":ranking_history_calls,
        "post_cut_competitive_data_used":False,
        "current_rank_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return updated_authority,out_aliases,audit


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--bridge-audit",required=True)
    parser.add_argument("--aliases",required=True)
    parser.add_argument("--authority",required=True)
    parser.add_argument("--history-csv",required=True)
    parser.add_argument("--aliases-out",required=True)
    parser.add_argument("--authority-out",required=True)
    parser.add_argument("--audit-out",required=True)
    parser.add_argument("--max-recoveries",type=int,default=20)
    args=parser.parse_args()

    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    client=RapidApiTennisClient(key)

    def profile_by_name(name: str) -> Mapping[str,Any]:
        payload=client._get("/tennis/v2/profile/"+quote(name,safe=""))
        return payload if isinstance(payload,Mapping) else {}

    def ranking_history(pid: str) -> Mapping[str,Any]:
        payload=client._get(f"/tennis/v2/ranking/atp/player/{pid}/history",{"months":3})
        return payload if isinstance(payload,Mapping) else {}

    def player_directory(ioc: str,page: int) -> Mapping[str,Any]:
        payload=client._get(
            "/tennis/v2/atp/player",
            {
                "filter":f"PlayerGroup:singles;PlayerCountry:{ioc}",
                "pageSize":500,
                "pageNo":page,
            },
        )
        return payload if isinstance(payload,Mapping) else {}

    def profile_by_id(pid: str) -> Mapping[str,Any]:
        payload=client._get(f"/tennis/v2/atp/player/profile/{pid}")
        return payload if isinstance(payload,Mapping) else {}

    authority,aliases,audit=recover_rank_history_aliases(
        bridge_audit=_load(Path(args.bridge_audit)),
        aliases=_load(Path(args.aliases)),
        authority=_load(Path(args.authority)),
        history_csv=Path(args.history_csv),
        profile_fetcher=profile_by_name,
        ranking_history_fetcher=ranking_history,
        player_directory_fetcher=player_directory,
        profile_by_id_fetcher=profile_by_id,
        max_recoveries=max(0,int(args.max_recoveries)),
    )
    audit["provider_network_calls"]=client.request_count
    _write(Path(args.aliases_out),aliases)
    _write(Path(args.authority_out),authority)
    _write(Path(args.audit_out),audit)
    print(json.dumps({
        "status":audit["status"],
        "recovered_count":audit["recovered_count"],
        "blocked_count":audit["blocked_count"],
        "provider_network_calls":audit["provider_network_calls"],
        "real_money":audit["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
