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

from tools.cor0203_expand_identity_authority import merge_certified_aliases
from tools.cor0203_rapidapi_tennis_discovery import (
    PAGE_SIZE,
    RapidApiTennisClient,
    _data_rows,
)


CUT_DATE = date(2026, 9, 21)
CUT_TOKEN = 20260921
RANKING_DATE = "21.09.2026"
MAX_RANKING_PAGES = 4
COUNTRY_ALIASES = {"POR": "PRT"}


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(
        json.dumps(dict(value),indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )


def _norm(value: object) -> str:
    text=unicodedata.normalize("NFKD",str(value or ""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    text=text.casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _ioc(value: object) -> str:
    token=str(value or "").strip().upper()
    return COUNTRY_ALIASES.get(token,token)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _dob(value: object) -> str | None:
    token=str(value or "").strip()[:10].replace("-","")
    if len(token)!=8 or not token.isdigit():
        return None
    try:
        parsed=date(int(token[:4]),int(token[4:6]),int(token[6:8]))
    except ValueError:
        return None
    return token if parsed < CUT_DATE else None


def _hand(value: object) -> str | None:
    token=str(value or "").strip().casefold()
    if token.startswith("left"):
        return "L"
    if token.startswith("right"):
        return "R"
    return None


def _history_index(path: Path) -> dict[tuple[str,str],dict[str,Any]]:
    grouped: dict[tuple[str,str],dict[str,Any]]=defaultdict(
        lambda:{
            "canonical_source_ids":set(),
            "canonical_iocs":set(),
            "observed_hands":set(),
            "canonical_names":set(),
            "rows":0,
            "latest_row_date":0,
        }
    )
    rows=csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines())
    for row in rows:
        try:
            day=int(float(str(row.get("tourney_date") or "0")))
        except ValueError:
            continue
        if day >= CUT_TOKEN or str(row.get("tourney_level") or "").strip()!="C":
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


def _wanted_api_players(discovery: Mapping[str,Any]) -> dict[str,dict[str,str]]:
    out={}
    for event in discovery.get("eligible_candidates",[]) or []:
        if not isinstance(event,Mapping):
            continue
        for player in event.get("players",[]) or []:
            if not isinstance(player,Mapping):
                continue
            provider_id=str(player.get("provider_player_id") or "").strip()
            if not provider_id.startswith("api-tennis:player:"):
                continue
            ranking=player.get("provider_ranking")
            full_name=(
                str(ranking.get("player") or "").strip()
                if isinstance(ranking,Mapping)
                else ""
            )
            display=str(player.get("name") or "").strip()
            if not full_name:
                full_name=display
            if provider_id and full_name:
                out[provider_id]={
                    "provider_player_id":provider_id,
                    "full_name":full_name,
                    "display_name":display or full_name,
                }
    return out


def _ranking_name_index(rows: list[Mapping[str,Any]]) -> dict[str,list[dict[str,Any]]]:
    out: dict[str,list[dict[str,Any]]]=defaultdict(list)
    for row in rows:
        player=row.get("player") if isinstance(row.get("player"),Mapping) else {}
        pid=str(player.get("id") or "").strip()
        name=str(player.get("name") or "").strip()
        ioc=_ioc(player.get("countryAcr"))
        place=str(row.get("position") or "").strip()
        points=str(row.get("pts") or "").strip()
        if not pid.isdigit() or not name or not ioc or not place.isdigit() or not points.isdigit():
            continue
        out[_norm(name)].append({
            "rapidapi_player_id":pid,
            "name":name,
            "ioc":ioc,
            "place":place,
            "points":points,
        })
    return out


def fetch_cut_ranking(client: RapidApiTennisClient) -> tuple[list[Mapping[str,Any]],int]:
    rows=[]
    before=client.request_count
    for page in range(1,MAX_RANKING_PAGES+1):
        payload=client._get(
            "/tennis/v2/ranking/atp",
            {
                "date":RANKING_DATE,
                "group":"singles",
                "page":page,
                "limit":PAGE_SIZE,
            },
        )
        page_rows=_data_rows(payload)
        rows.extend(page_rows)
        if not page_rows or len(page_rows)<PAGE_SIZE:
            break
    return rows,client.request_count-before


def build_bridge(
    *,
    discovery: Mapping[str,Any],
    authority: Mapping[str,Any],
    history_csv: Path,
    ranking_rows: list[Mapping[str,Any]],
    profile_fetcher: Callable[[str],Mapping[str,Any]],
    base_aliases: Mapping[str,Any] | None=None,
    max_profiles: int=12,
) -> tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    if discovery.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError("API_TENNIS_DISCOVERY_NOT_READY")
    if authority.get("post_cut_competitive_data_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_POSTCUT_FLAG_INVALID")
    if authority.get("outcomes_used") is not False or authority.get("odds_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_GOVERNANCE_FLAG_INVALID")

    wanted=_wanted_api_players(discovery)
    rank_index=_ranking_name_index(ranking_rows)
    history=_history_index(history_csv)
    known={
        str(row.get("provider_player_id") or "")
        for row in authority.get("records",[]) or []
        if isinstance(row,Mapping)
    }
    base_records=[
        dict(row)
        for row in (
            base_aliases.get("records",[])
            if isinstance(base_aliases,Mapping)
            else []
        ) or []
        if isinstance(row,Mapping)
    ]
    alias_by_id={
        str(row.get("provider_player_id") or ""):row
        for row in base_records
        if str(row.get("provider_player_id") or "")
    }

    generated=[]
    blocked=[]
    profile_requests=0

    for provider_id in sorted(wanted):
        player=wanted[provider_id]
        if provider_id in known or provider_id in alias_by_id:
            continue
        matches=rank_index.get(_norm(player["full_name"]),[])
        signatures={
            (
                row["rapidapi_player_id"],row["name"],row["ioc"],
                row["place"],row["points"],
            )
            for row in matches
        }
        if len(signatures)!=1:
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"RAPIDAPI_CUT_RANKING_NAME_NOT_UNIQUE" if matches else "RAPIDAPI_CUT_RANKING_NAME_NOT_FOUND",
                "match_count":len(signatures),
            })
            continue
        rank_row=matches[0]
        hist=history.get((_norm(rank_row["name"]),rank_row["ioc"]))
        if not hist:
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"NO_PRE_CUT_CHALLENGER_HISTORY",
                "rapidapi_player_id":rank_row["rapidapi_player_id"],
            })
            continue
        source_ids=sorted(hist["canonical_source_ids"])
        iocs=sorted(hist["canonical_iocs"])
        hands=sorted(hist["observed_hands"])
        names=sorted(hist["canonical_names"])
        if len(source_ids)!=1:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PRE_CUT_SOURCE_ID_NOT_UNIQUE"})
            continue
        if iocs!=[rank_row["ioc"]]:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PRE_CUT_IOC_NOT_UNIQUE"})
            continue
        if len(hands)!=1 or hands[0] not in {"R","L"}:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PRE_CUT_HAND_NOT_FIXED"})
            continue
        if len({_norm(x) for x in names})!=1 or _norm(names[0])!=_norm(rank_row["name"]):
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PRE_CUT_NAME_NOT_UNIQUE"})
            continue
        if profile_requests>=max_profiles:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_BUDGET_REACHED"})
            continue

        profile=profile_fetcher(rank_row["rapidapi_player_id"])
        profile_requests+=1
        data=profile.get("data") if isinstance(profile.get("data"),Mapping) else profile
        if not isinstance(data,Mapping):
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_PAYLOAD_INVALID"})
            continue
        profile_id=str(data.get("id") or "").strip()
        profile_name=str(data.get("name") or "").strip()
        profile_ioc=_ioc(data.get("countryAcr"))
        info=data.get("information") if isinstance(data.get("information"),Mapping) else {}
        profile_hand=_hand(info.get("plays") or info.get("hand"))
        dob=_dob(data.get("birthday"))
        if profile_id!=rank_row["rapidapi_player_id"]:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_ID_MISMATCH"})
            continue
        if _norm(profile_name)!=_norm(rank_row["name"]):
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_NAME_MISMATCH"})
            continue
        if profile_ioc!=rank_row["ioc"]:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_IOC_MISMATCH"})
            continue
        if profile_hand in {"R","L"} and profile_hand!=hands[0]:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_HAND_CONFLICT"})
            continue
        if dob is None:
            blocked.append({"provider_player_id":provider_id,"player":player["full_name"],"reason":"PROFILE_DOB_INVALID"})
            continue

        competitive=[
            key for key in ("currentRank","points","progress","careerMoney")
            if key in data
        ]
        record={
            "provider_player_id":provider_id,
            "provider_display_name":rank_row["name"],
            "canonical_name":names[0],
            "provider_ioc_raw":rank_row["ioc"],
            "provider_ioc_canonical":rank_row["ioc"],
            "ranking_cut":"2026-09-21",
            "provider_rank":rank_row["place"],
            "provider_rank_points":rank_row["points"],
            "pre_cut_history":{
                "canonical_source_ids":source_ids,
                "canonical_iocs":iocs,
                "observed_hands":hands,
                "rows":int(hist["rows"]),
                "latest_row_date":int(hist["latest_row_date"]),
            },
            "biographical_candidates":[{
                "master_id":"RAPIDAPI_PROFILE_"+rank_row["rapidapi_player_id"],
                "name":profile_name,
                "hand":profile_hand or hands[0],
                "dob":dob,
                "ioc":profile_ioc,
                "height_cm":None,
                "wikidata_id":None,
                "provider_profile_sha256":_sha(profile),
            }],
            "biography_source":"RAPIDAPI_CUT_RANKING_PROFILE_PLUS_PRECUT_HISTORY",
            "authority_basis":"API_TENNIS_TO_RAPIDAPI_CUT_RANKING_EXACT_NAME_PLUS_PROFILE_AND_PRECUT_HISTORY",
            "rapidapi_cut_identity":{
                "provider_player_id":"rapidapi-tennis:player:"+rank_row["rapidapi_player_id"],
                "ranking_date":"2026-09-21",
                "rank":rank_row["place"],
                "points":rank_row["points"],
            },
            "profile_competitive_fields_discarded":competitive+[
                "API_TENNIS_CURRENT_STANDINGS_RANK",
                "API_TENNIS_CURRENT_STANDINGS_POINTS",
            ],
        }
        alias_by_id[provider_id]=record
        generated.append(record)

    aliases_payload={
        "schema":"MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1",
        "purpose":"Bridge API-Tennis player IDs to sealed pre-cut identities using exact RapidAPI 21-SEP ranking name, RapidAPI profile, and strict pre-cut Challenger history.",
        "strict_before_period":20260921,
        "records":[alias_by_id[k] for k in sorted(alias_by_id)],
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    updated_authority,added=merge_certified_aliases(authority,aliases_payload)
    audit={
        "schema":"MATRIX_COR0203_API_TENNIS_RAPIDAPI_CUT_IDENTITY_BRIDGE_V1",
        "status":"PASS",
        "api_tennis_players_seen":len(wanted),
        "rapidapi_cut_ranking_rows":len(ranking_rows),
        "new_aliases_generated":len(generated),
        "new_alias_provider_ids":[row["provider_player_id"] for row in generated],
        "aliases_added_to_authority":added,
        "blocked_count":len(blocked),
        "blocked":blocked,
        "profile_requests":profile_requests,
        "ranking_cut":"20260921",
        "post_cut_competitive_data_used":False,
        "api_tennis_current_rank_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return updated_authority,aliases_payload,audit


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--discovery",required=True)
    parser.add_argument("--history-csv",required=True)
    parser.add_argument("--authority",required=True)
    parser.add_argument("--base-aliases")
    parser.add_argument("--aliases-out",required=True)
    parser.add_argument("--authority-out",required=True)
    parser.add_argument("--audit-out",required=True)
    parser.add_argument("--max-profiles",type=int,default=12)
    args=parser.parse_args()

    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    client=RapidApiTennisClient(key)
    ranking_rows,ranking_calls=fetch_cut_ranking(client)

    def fetch_profile(pid: str) -> Mapping[str,Any]:
        payload=client._get(f"/tennis/v2/atp/player/profile/{pid}")
        return payload if isinstance(payload,Mapping) else {}

    authority,aliases,audit=build_bridge(
        discovery=_load(Path(args.discovery)),
        authority=_load(Path(args.authority)),
        history_csv=Path(args.history_csv),
        ranking_rows=ranking_rows,
        profile_fetcher=fetch_profile,
        base_aliases=(
            _load(Path(args.base_aliases))
            if args.base_aliases and Path(args.base_aliases).exists()
            else None
        ),
        max_profiles=max(0,int(args.max_profiles)),
    )
    audit["ranking_network_calls"]=ranking_calls
    audit["provider_network_calls"]=client.request_count
    _write(Path(args.aliases_out),aliases)
    _write(Path(args.authority_out),authority)
    _write(Path(args.audit_out),audit)
    print(json.dumps({
        "status":audit["status"],
        "api_tennis_players_seen":audit["api_tennis_players_seen"],
        "new_aliases_generated":audit["new_aliases_generated"],
        "aliases_added_to_authority":len(audit["aliases_added_to_authority"]),
        "blocked_count":audit["blocked_count"],
        "profile_requests":audit["profile_requests"],
        "provider_network_calls":audit["provider_network_calls"],
        "real_money":audit["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
