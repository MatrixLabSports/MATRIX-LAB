from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_api_tennis_rank_bridge import (
    _ioc,
    _norm,
    _ranking_name_index,
    _wanted_api_players,
    fetch_cut_ranking,
)
from tools.cor0203_expand_identity_authority import merge_certified_aliases
from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path,value: Mapping[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(
        json.dumps(dict(value),indent=2,sort_keys=True,ensure_ascii=False)+"\n",
        encoding="utf-8",
    )


def _profile_data(payload: Mapping[str,Any])->Mapping[str,Any]:
    data=payload.get("data")
    return data if isinstance(data,Mapping) else payload


def _hand(value: object)->str:
    token=str(value or "").strip().casefold()
    if token.startswith("left") or token=="l":
        return "L"
    if token.startswith("right") or token=="r":
        return "R"
    return ""


def _dob(value: object)->str:
    return str(value or "").strip()[:10].replace("-","")


def recover_certified_authority_aliases(
    *,
    discovery: Mapping[str,Any],
    authority: Mapping[str,Any],
    aliases: Mapping[str,Any],
    ranking_rows: list[Mapping[str,Any]],
    profile_fetcher,
)->tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    if discovery.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError("API_TENNIS_DISCOVERY_NOT_READY")
    if authority.get("post_cut_competitive_data_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_POSTCUT_FLAG_INVALID")
    if authority.get("outcomes_used") is not False or authority.get("odds_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_GOVERNANCE_FLAG_INVALID")

    wanted=_wanted_api_players(discovery)
    rank_index=_ranking_name_index(ranking_rows)
    authority_records=[
        dict(row) for row in authority.get("records",[]) or []
        if isinstance(row,Mapping)
    ]
    authority_by_rapid={}
    known_ids=set()
    for row in authority_records:
        pid=str(row.get("provider_player_id") or "")
        if pid:
            known_ids.add(pid)
        if not pid.startswith("rapidapi-tennis:player:"):
            continue
        numeric=pid.rsplit(":",1)[-1]
        sealed=row.get("sealed_r706_history")
        precut=row.get("pre_cut_provider_history")
        if not isinstance(sealed,Mapping) or sealed.get("fully_history_ready") is not True:
            continue
        if not isinstance(precut,Mapping) or int(precut.get("eligible_pre_cut_matches") or 0)<=0:
            continue
        authority_by_rapid[numeric]=row

    alias_records=[
        dict(row) for row in aliases.get("records",[]) or []
        if isinstance(row,Mapping)
    ]
    alias_by_id={
        str(row.get("provider_player_id") or ""):row
        for row in alias_records
        if str(row.get("provider_player_id") or "")
    }

    recovered=[]
    blocked=[]
    profile_requests=0

    for provider_id in sorted(wanted):
        if provider_id in known_ids or provider_id in alias_by_id:
            continue
        player=wanted[provider_id]
        matches=rank_index.get(_norm(player["full_name"]),[])
        signatures={
            (
                str(row["rapidapi_player_id"]),
                str(row["name"]),
                str(row["ioc"]),
                str(row["place"]),
                str(row["points"]),
            )
            for row in matches
        }
        if len(signatures)!=1:
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"CUT_RANKING_NAME_NOT_UNIQUE_OR_NOT_FOUND",
                "match_count":len(signatures),
            })
            continue
        rank_row=matches[0]
        rapid_id=str(rank_row["rapidapi_player_id"])
        certified=authority_by_rapid.get(rapid_id)
        if not isinstance(certified,Mapping):
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"NO_CERTIFIED_R706_READY_RAPIDAPI_AUTHORITY",
                "rapidapi_player_id":"rapidapi-tennis:player:"+rapid_id,
            })
            continue

        canonical_name=str(
            certified.get("canonical_name")
            or certified.get("provider_display_name")
            or ""
        ).strip()
        certified_ioc=_ioc(
            certified.get("provider_ioc_canonical")
            or certified.get("provider_ioc_raw")
        )
        if _norm(canonical_name)!=_norm(rank_row["name"]):
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"CERTIFIED_NAME_MISMATCH",
            })
            continue
        if certified_ioc!=str(rank_row["ioc"]):
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"CERTIFIED_IOC_MISMATCH",
            })
            continue

        bio=[
            x for x in certified.get("biographical_candidates",[]) or []
            if isinstance(x,Mapping) and _norm(x.get("name"))==_norm(canonical_name)
        ]
        if len(bio)!=1:
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"CERTIFIED_BIOGRAPHY_NOT_UNIQUE",
            })
            continue
        expected=bio[0]
        expected_dob=_dob(expected.get("dob"))
        expected_hand=_hand(expected.get("hand"))
        if len(expected_dob)!=8 or expected_hand not in {"R","L"}:
            blocked.append({
                "provider_player_id":provider_id,
                "player":player["full_name"],
                "reason":"CERTIFIED_BIOGRAPHY_INCOMPLETE",
            })
            continue

        profile=_profile_data(profile_fetcher(rapid_id))
        profile_requests+=1
        profile_id=str(profile.get("id") or "")
        profile_name=str(profile.get("name") or "").strip()
        profile_ioc=_ioc(profile.get("countryAcr"))
        info=profile.get("information") if isinstance(profile.get("information"),Mapping) else {}
        profile_dob=_dob(profile.get("birthday"))
        profile_hand=_hand(info.get("plays") or info.get("hand"))
        if profile_id!=rapid_id:
            blocked.append({"provider_player_id":provider_id,"reason":"PROFILE_ID_MISMATCH"})
            continue
        if _norm(profile_name)!=_norm(canonical_name):
            blocked.append({"provider_player_id":provider_id,"reason":"PROFILE_NAME_MISMATCH"})
            continue
        if profile_ioc!=certified_ioc:
            blocked.append({"provider_player_id":provider_id,"reason":"PROFILE_IOC_MISMATCH"})
            continue
        if profile_dob!=expected_dob:
            blocked.append({"provider_player_id":provider_id,"reason":"PROFILE_DOB_MISMATCH"})
            continue
        if profile_hand and profile_hand!=expected_hand:
            blocked.append({"provider_player_id":provider_id,"reason":"PROFILE_HAND_MISMATCH"})
            continue

        record=json.loads(json.dumps(certified))
        record["provider_player_id"]=provider_id
        record["provider_display_name"]=rank_row["name"]
        record["canonical_name"]=canonical_name
        record["provider_ioc_raw"]=rank_row["ioc"]
        record["provider_ioc_canonical"]=rank_row["ioc"]
        record["ranking_cut"]="2026-09-21"
        record["provider_rank"]=str(rank_row["place"])
        record["provider_rank_points"]=str(rank_row["points"])
        record["authority_basis"]="API_TENNIS_TO_CERTIFIED_R706_RAPIDAPI_AUTHORITY_PROFILE_EXACT_CUT"
        record["cross_provider_authority_source_provider_player_id"]="rapidapi-tennis:player:"+rapid_id
        record["rapidapi_cut_identity"]={
            "provider_player_id":"rapidapi-tennis:player:"+rapid_id,
            "ranking_date":"2026-09-21",
            "rank":str(rank_row["place"]),
            "points":str(rank_row["points"]),
        }
        discarded=set(record.get("profile_competitive_fields_discarded") or [])
        discarded.update({
            "API_TENNIS_CURRENT_STANDINGS_RANK",
            "API_TENNIS_CURRENT_STANDINGS_POINTS",
        })
        record["profile_competitive_fields_discarded"]=sorted(discarded)
        alias_by_id[provider_id]=record
        recovered.append({
            "api_tennis_provider_player_id":provider_id,
            "rapidapi_provider_player_id":"rapidapi-tennis:player:"+rapid_id,
            "canonical_name":canonical_name,
            "sealed_r706_history_ready":True,
            "pre_cut_provider_matches":int(
                (certified.get("pre_cut_provider_history") or {}).get("eligible_pre_cut_matches") or 0
            ),
        })

    alias_payload={
        "schema":"MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1",
        "purpose":"API-Tennis aliases recovered only from pre-existing certified R706-ready RapidAPI authority plus exact 21-SEP ranking and biographical profile consistency.",
        "strict_before_period":20260921,
        "records":[alias_by_id[k] for k in sorted(alias_by_id)],
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    updated,added=merge_certified_aliases(authority,alias_payload)
    audit={
        "schema":"MATRIX_COR0203_API_TENNIS_CERTIFIED_AUTHORITY_RECOVERY_V1",
        "status":"PASS",
        "wanted_api_tennis_players":len(wanted),
        "certified_rapidapi_authority_candidates":len(authority_by_rapid),
        "recovered_count":len(recovered),
        "recovered":recovered,
        "blocked_count":len(blocked),
        "blocked":blocked,
        "aliases_added_to_authority":added,
        "profile_requests":profile_requests,
        "ranking_cut":"20260921",
        "join_by_name_only":False,
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return updated,alias_payload,audit


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--discovery",required=True)
    parser.add_argument("--authority",required=True)
    parser.add_argument("--aliases",required=True)
    parser.add_argument("--authority-out",required=True)
    parser.add_argument("--aliases-out",required=True)
    parser.add_argument("--audit-out",required=True)
    args=parser.parse_args()

    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    client=RapidApiTennisClient(key)
    ranking_rows,ranking_calls=fetch_cut_ranking(client)

    def profile_fetcher(pid: str)->Mapping[str,Any]:
        return client.player_profile(player_id=pid)

    updated,alias_payload,audit=recover_certified_authority_aliases(
        discovery=_load(Path(args.discovery)),
        authority=_load(Path(args.authority)),
        aliases=_load(Path(args.aliases)),
        ranking_rows=ranking_rows,
        profile_fetcher=profile_fetcher,
    )
    audit["ranking_network_calls"]=ranking_calls
    audit["provider_network_calls"]=client.request_count
    _write(Path(args.authority_out),updated)
    _write(Path(args.aliases_out),alias_payload)
    _write(Path(args.audit_out),audit)
    print(json.dumps({
        "status":audit["status"],
        "recovered_count":audit["recovered_count"],
        "blocked_count":audit["blocked_count"],
        "profile_requests":audit["profile_requests"],
        "provider_network_calls":audit["provider_network_calls"],
        "real_money":audit["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
