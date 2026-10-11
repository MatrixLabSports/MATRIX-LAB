from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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


def _round(value: object) -> str:
    token=" ".join(
        str(value or "").strip().casefold().replace("_"," ").replace("-"," ").split()
    )
    aliases={
        "1/4":"QF","quarter final":"QF","quarter finals":"QF","quarterfinal":"QF",
        "quarterfinals":"QF","qf":"QF",
        "1/2":"SF","semi final":"SF","semi finals":"SF","semifinal":"SF",
        "semifinals":"SF","sf":"SF",
        "final":"F","finals":"F","f":"F",
        "first":"R1","first round":"R1","round 1":"R1","r1":"R1",
        "second":"R2","second round":"R2","round 2":"R2","r2":"R2",
        "q1":"Q1","qualifying 1":"Q1","q2":"Q2","qualifying 2":"Q2",
        "q3":"Q3","qualifying 3":"Q3",
    }
    match=re.search(r"(?:^|\s)(1/16|1/8|1/4|1/2)\s*finals?$",token)
    if match:
        fraction=match.group(1)
        fraction_aliases={
            "1/16":"R32",
            "1/8":"R16",
            "1/4":"QF",
            "1/2":"SF",
        }
        return fraction_aliases[fraction]
    return aliases.get(token,token.upper())


def _date(value: object) -> str | None:
    try:
        parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except (TypeError,ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc).date().isoformat()


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),sort_keys=True,separators=(",",":"),ensure_ascii=False
        ).encode("utf-8")
    ).hexdigest()


def _static_index(static_cut: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    if str(static_cut.get("ranking_cut"))!="20260921":
        raise ValueError("STATIC_CUT_RANKING_CUT_MISMATCH")
    if static_cut.get("post_cut_data_used") is not False:
        raise ValueError("STATIC_CUT_POSTCUT_FLAG_INVALID")
    if static_cut.get("silent_imputation") is not False:
        raise ValueError("STATIC_CUT_IMPUTATION_FLAG_INVALID")
    out={}
    collisions=set()
    for row in (static_cut.get("players") or {}).values():
        if not isinstance(row,Mapping):
            continue
        name=_norm(row.get("canonical_name"))
        if not name:
            continue
        if name in out:
            collisions.add(name)
        else:
            out[name]=row
    for key in collisions:
        out.pop(key,None)
    return out


def _certified_aliases(payload: Mapping[str, Any] | None) -> dict[str,str]:
    out={}
    if not isinstance(payload,Mapping):
        return out
    if int(payload.get("strict_before_period") or 0)!=20260921:
        raise ValueError("CERTIFIED_ALIAS_CUT_MISMATCH")
    if payload.get("post_cut_competitive_data_used") is not False:
        raise ValueError("CERTIFIED_ALIAS_POSTCUT_FLAG_INVALID")
    for row in payload.get("records",[]) or []:
        if not isinstance(row,Mapping):
            continue
        canonical=str(row.get("canonical_name") or "").strip()
        if not canonical:
            continue
        for key in ("provider_display_name","canonical_name"):
            alias=_norm(row.get(key))
            if alias:
                out[alias]=canonical
    return out



def _authority_index(
    authority: Mapping[str, Any] | None,
    aliases: Mapping[str,str],
) -> dict[str, Mapping[str,Any]]:
    if not isinstance(authority,Mapping):
        return {}
    raw: dict[str, list[Mapping[str,Any]]] = {}
    for row in authority.get("records",[]) or []:
        if not isinstance(row,Mapping):
            continue
        rank=str(row.get("provider_rank") or "").strip()
        points=str(row.get("provider_rank_points") or "").strip()
        history=row.get("pre_cut_history")
        bios=row.get("biographical_candidates")
        if not rank.isdigit() or not points.isdigit():
            continue
        if not isinstance(history,Mapping):
            continue
        source_ids=sorted({
            str(x) for x in history.get("canonical_source_ids",[]) or [] if str(x)
        })
        if len(source_ids)!=1:
            continue
        if not isinstance(bios,list) or len(bios)!=1 or not isinstance(bios[0],Mapping):
            continue
        canonical=(
            str(row.get("canonical_name") or "").strip()
            or aliases.get(_norm(row.get("provider_display_name")),"")
            or str(bios[0].get("name") or "").strip()
            or str(row.get("provider_display_name") or "").strip()
        )
        if not canonical:
            continue
        names={
            canonical,
            str(row.get("provider_display_name") or "").strip(),
            str(bios[0].get("name") or "").strip(),
        }
        for name in list(names):
            alias=aliases.get(_norm(name))
            if alias:
                names.add(alias)
        enriched=dict(row)
        enriched["_dual_canonical_name"]=canonical
        enriched["_dual_canonical_source_id"]=source_ids[0]
        for name in names:
            key=_norm(name)
            if key:
                raw.setdefault(key,[]).append(enriched)

    out={}
    for key,rows in raw.items():
        signatures={
            (
                str(row.get("_dual_canonical_source_id") or ""),
                str(row.get("provider_rank") or ""),
                str(row.get("provider_rank_points") or ""),
                _norm(row.get("_dual_canonical_name")),
            )
            for row in rows
        }
        if len(signatures)==1:
            out[key]=rows[0]
    return out


def _canonical_from_authority(
    player: Mapping[str,Any],
    *,
    authority_by_name: Mapping[str,Mapping[str,Any]],
    aliases: Mapping[str,str],
) -> tuple[Mapping[str,Any] | None,str]:
    ranking=player.get("provider_ranking")
    ranking_name=(
        str(ranking.get("player") or "").strip()
        if isinstance(ranking,Mapping)
        else ""
    )
    for raw in (ranking_name,str(player.get("name") or "").strip()):
        key=_norm(raw)
        if not key:
            continue
        alias=aliases.get(key)
        if alias:
            key=_norm(alias)
        row=authority_by_name.get(key)
        if row is not None:
            return row,"EXACT_UNIQUE_PRECUT_AUTHORITY_NAME"
    return None,"AUTHORITY_NAME_NOT_RESOLVED"


def _authority_alias_record(
    *,
    player: Mapping[str,Any],
    authority_row: Mapping[str,Any],
    canonical_name: str,
) -> dict[str,Any]:
    ranking=player.get("provider_ranking")
    provider_name=(
        str(ranking.get("player") or "").strip()
        if isinstance(ranking,Mapping)
        else ""
    ) or str(player.get("name") or "").strip()
    return {
        "provider_player_id":str(player.get("provider_player_id") or ""),
        "provider_display_name":provider_name,
        "canonical_name":canonical_name,
        "provider_ioc_raw":(
            str(ranking.get("country") or "").strip()
            if isinstance(ranking,Mapping)
            else ""
        ),
        "provider_ioc_canonical":str(
            authority_row.get("provider_ioc_canonical")
            or authority_row.get("provider_ioc_raw")
            or ""
        ),
        "provider_rank":str(authority_row.get("provider_rank") or ""),
        "provider_rank_points":str(authority_row.get("provider_rank_points") or ""),
        "ranking_cut":"2026-09-21",
        "pre_cut_history":json.loads(json.dumps(authority_row.get("pre_cut_history") or {})),
        "biographical_candidates":json.loads(json.dumps(authority_row.get("biographical_candidates") or [])),
        "biography_source":str(authority_row.get("biography_source") or "PRECUT_IDENTITY_AUTHORITY"),
        "authority_basis":"CROSS_PROVIDER_EXACT_UNIQUE_PRECUT_AUTHORITY_NAME",
        "profile_competitive_fields_discarded":[
            "API_TENNIS_CURRENT_STANDINGS_RANK",
            "API_TENNIS_CURRENT_STANDINGS_POINTS",
        ],
    }

def _canonical_from_static(
    player: Mapping[str, Any],
    *,
    static_by_name: Mapping[str, Mapping[str, Any]],
    aliases: Mapping[str,str],
) -> tuple[Mapping[str,Any] | None,str]:
    ranking=player.get("provider_ranking")
    ranking_name=(
        str(ranking.get("player") or "").strip()
        if isinstance(ranking,Mapping)
        else ""
    )
    candidates=[
        ranking_name,
        str(player.get("name") or "").strip(),
    ]
    checked=[]
    for raw in candidates:
        key=_norm(raw)
        if not key or key in checked:
            continue
        checked.append(key)
        canonical_alias=aliases.get(key)
        if canonical_alias:
            key=_norm(canonical_alias)
        row=static_by_name.get(key)
        if row is not None:
            return row,"EXACT_UNIQUE_STATIC_NAME"
    return None,"STATIC_NAME_NOT_RESOLVED"


def _crosswalk_canonical_names(runtime_dir: Path) -> dict[str,str]:
    out={}
    for path in sorted(runtime_dir.glob("MATRIX_COR0203_IDENTITY_CROSSWALK_R*.json")):
        try:
            payload=_load(path)
        except Exception:
            continue
        for row in payload.get("mappings",[]) or []:
            if not isinstance(row,Mapping) or row.get("status")!="PASS":
                continue
            pid=str(row.get("provider_player_id") or "")
            name=str(row.get("canonical_name") or "").strip()
            if pid and name:
                out[pid]=name
    return out


def _candidate_names(
    candidate: Mapping[str,Any],
    *,
    static_by_name: Mapping[str,Mapping[str,Any]] | None=None,
    aliases: Mapping[str,str] | None=None,
) -> tuple[list[str],list[Mapping[str,Any] | None]]:
    names=[]
    static_rows=[]
    for player in candidate.get("players",[]) or []:
        if not isinstance(player,Mapping):
            return [],[]
        row=None
        if static_by_name is not None:
            row,_=_canonical_from_static(
                player,
                static_by_name=static_by_name,
                aliases=aliases or {},
            )
        if row is not None:
            name=str(row.get("canonical_name") or "").strip()
        else:
            ranking=player.get("provider_ranking")
            name=(
                str(ranking.get("player") or "").strip()
                if isinstance(ranking,Mapping)
                else ""
            )
            if not name:
                name=str(player.get("name") or "").strip()
        if not name:
            return [],[]
        names.append(name)
        static_rows.append(row)
    return names,static_rows


def _neutral_key(
    *,
    names: list[str],
    round_name: object,
    start_utc: object,
) -> str | None:
    if len(names)!=2:
        return None
    day=_date(start_utc)
    players=sorted({_norm(name) for name in names if _norm(name)})
    if day is None or len(players)!=2:
        return None
    return _sha({
        "schema":"MATRIX_COR0203_PROVIDER_NEUTRAL_PHYSICAL_ID_V1",
        "event_date_utc":day,
        "round":_round(round_name),
        "players":players,
        "surface":"HARD",
    })


def _existing_neutral_keys(runtime_dir: Path) -> set[str]:
    canonical=_crosswalk_canonical_names(runtime_dir)
    keys=set()
    for path in runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"):
        try:
            payload=_load(path)
        except Exception:
            continue
        for event in payload.get("events",[]) or []:
            if not isinstance(event,Mapping):
                continue
            names=[]
            identities=event.get("player_identities",[]) or []
            if len(identities)==2:
                for identity in identities:
                    if not isinstance(identity,Mapping):
                        continue
                    pid=str(identity.get("provider_player_id") or "")
                    names.append(
                        canonical.get(pid)
                        or str(identity.get("display_name") or "").strip()
                    )
            if len(names)!=2:
                raw=event.get("players",[]) or []
                names=[str(x) for x in raw] if len(raw)==2 else []
            key=_neutral_key(
                names=names,
                round_name=event.get("round"),
                start_utc=event.get("event_start_utc"),
            )
            if key:
                keys.add(key)
    return keys


def _enrich_api_candidate(
    candidate: Mapping[str,Any],
    *,
    static_by_name: Mapping[str,Mapping[str,Any]],
    authority_by_name: Mapping[str,Mapping[str,Any]],
    aliases: Mapping[str,str],
) -> tuple[dict[str,Any] | None,list[str],list[dict[str,Any]]]:
    copy=json.loads(json.dumps(candidate))
    players=copy.get("players",[]) or []
    blockers=[]
    canonical_names=[]
    generated_aliases=[]
    if len(players)!=2:
        return None,["TWO_PROVIDER_IDENTITIES_REQUIRED"],[]
    for player in players:
        if not isinstance(player,dict):
            blockers.append("PLAYER_OBJECT_INVALID")
            continue
        static_row,basis=_canonical_from_static(
            player,
            static_by_name=static_by_name,
            aliases=aliases,
        )
        authority_row=None
        if static_row is not None:
            canonical=str(static_row.get("canonical_name") or "").strip()
            rank=static_row.get("rank")
            points=static_row.get("rank_points")
            ioc=str(static_row.get("ioc") or "")
            source_id=str(static_row.get("canonical_source_id") or "")
            ranking_authority="SEALED_STATIC_CUT_20260921"
        else:
            authority_row,basis=_canonical_from_authority(
                player,
                authority_by_name=authority_by_name,
                aliases=aliases,
            )
            if authority_row is None:
                blockers.append(
                    "PIT_IDENTITY_NOT_RESOLVED:"
                    + str(player.get("provider_player_id") or "")
                )
                continue
            canonical=str(authority_row.get("_dual_canonical_name") or "").strip()
            rank=authority_row.get("provider_rank")
            points=authority_row.get("provider_rank_points")
            ioc=str(
                authority_row.get("provider_ioc_canonical")
                or authority_row.get("provider_ioc_raw")
                or ""
            )
            source_id=str(authority_row.get("_dual_canonical_source_id") or "")
            ranking_authority="IDENTITY_AUTHORITY_PRECUT_20260921"
            generated_aliases.append(
                _authority_alias_record(
                    player=player,
                    authority_row=authority_row,
                    canonical_name=canonical,
                )
            )
        if not canonical or rank is None or points is None:
            blockers.append(
                "PIT_RANKING_INCOMPLETE:"
                + str(player.get("provider_player_id") or "")
            )
            continue
        if not str(rank).isdigit() or not str(points).isdigit():
            blockers.append(
                "PIT_RANKING_INVALID:"
                + str(player.get("provider_player_id") or "")
            )
            continue
        original_ranking=player.get("provider_ranking")
        provider_name=(
            str(original_ranking.get("player") or "").strip()
            if isinstance(original_ranking,Mapping)
            else ""
        )
        player["provider_current_ranking_discarded"]=True
        player["provider_name_evidence"]=provider_name or str(player.get("name") or "")
        player["provider_ranking"]={
            "place":str(rank),
            "points":str(points),
            "player":canonical,
            "country":ioc,
            "snapshot_date":"2026-09-21",
            "authority":ranking_authority,
            "current_provider_rank_used":False,
        }
        player["pit_identity_basis"]=basis
        player["canonical_source_id_hint"]=source_id
        canonical_names.append(canonical)
    if blockers:
        return None,sorted(set(blockers)),generated_aliases
    key=_neutral_key(
        names=canonical_names,
        round_name=copy.get("round"),
        start_utc=copy.get("event_start_utc"),
    )
    if key is None:
        return None,["PROVIDER_NEUTRAL_PHYSICAL_KEY_MISSING"],generated_aliases
    copy["physical_event_key"]=key
    copy["provider_neutral_identity"]={
        "schema":"MATRIX_COR0203_PROVIDER_NEUTRAL_PHYSICAL_ID_V1",
        "canonical_names":sorted(canonical_names),
        "event_date_utc":_date(copy.get("event_start_utc")),
        "round":_round(copy.get("round")),
        "surface":"Hard",
        "ranking_authority":"STATIC_OR_PRECUT_IDENTITY_AUTHORITY_20260921",
        "current_api_tennis_rank_used":False,
    }
    return copy,[],generated_aliases
def _enrich_rapid_candidate(
    candidate: Mapping[str,Any],
) -> tuple[dict[str,Any],str | None]:
    copy=json.loads(json.dumps(candidate))
    names,_=_candidate_names(copy)
    key=_neutral_key(
        names=names,
        round_name=copy.get("round"),
        start_utc=copy.get("event_start_utc"),
    )
    if key:
        copy["physical_event_key"]=key
        copy["provider_neutral_identity"]={
            "schema":"MATRIX_COR0203_PROVIDER_NEUTRAL_PHYSICAL_ID_V1",
            "canonical_names":sorted(names),
            "event_date_utc":_date(copy.get("event_start_utc")),
            "round":_round(copy.get("round")),
            "surface":"Hard",
            "ranking_authority":"RAPIDAPI_RANKING_CUT_20260921",
        }
    return copy,key


def reconcile_dual_discovery(
    *,
    rapidapi: Mapping[str,Any],
    api_tennis: Mapping[str,Any],
    static_cut: Mapping[str,Any],
    runtime_dir: Path,
    certified_aliases: Mapping[str,Any] | None=None,
    identity_authority: Mapping[str,Any] | None=None,
) -> tuple[dict[str,Any],dict[str,Any],dict[str,Any]]:
    if rapidapi.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError("RAPIDAPI_DISCOVERY_NOT_READY")
    if api_tennis.get("status")!="DISCOVERY_COMPLETED":
        raise ValueError("API_TENNIS_DISCOVERY_NOT_READY")

    static_by_name=_static_index(static_cut)
    aliases=_certified_aliases(certified_aliases)
    authority_by_name=_authority_index(identity_authority,aliases)
    existing=_existing_neutral_keys(runtime_dir)

    rapid_out=[]
    rapid_by_key={}
    rapid_no_neutral=[]
    for raw in rapidapi.get("eligible_candidates",[]) or []:
        if not isinstance(raw,Mapping):
            continue
        row,key=_enrich_rapid_candidate(raw)
        if key:
            if key in existing:
                continue
            rapid_by_key.setdefault(key,row)
        else:
            rapid_no_neutral.append(str(row.get("event_id") or ""))
            rapid_out.append(row)
    rapid_out.extend(rapid_by_key.values())

    api_out=[]
    api_blocked=[]
    api_cross_provider_aliases=[]
    api_existing_aliases=[]
    api_seen=set()
    generated_identity_aliases={}
    for raw in api_tennis.get("eligible_candidates",[]) or []:
        if not isinstance(raw,Mapping):
            continue
        row,blockers,new_aliases=_enrich_api_candidate(
            raw,
            static_by_name=static_by_name,
            authority_by_name=authority_by_name,
            aliases=aliases,
        )
        for alias_row in new_aliases:
            pid=str(alias_row.get("provider_player_id") or "")
            if pid:
                generated_identity_aliases[pid]=alias_row
        source_id=str(raw.get("canonical_source_event_id") or raw.get("event_id") or "")
        if row is None:
            api_blocked.append({
                "source_event_id":source_id,
                "players":[
                    str((p.get("provider_ranking") or {}).get("player") or p.get("name") or "")
                    for p in raw.get("players",[]) or []
                    if isinstance(p,Mapping)
                ],
                "blockers":blockers,
            })
            continue
        key=str(row["physical_event_key"])
        if key in rapid_by_key:
            api_cross_provider_aliases.append({
                "api_tennis_source_event_id":source_id,
                "rapidapi_source_event_id":str(
                    rapid_by_key[key].get("canonical_source_event_id")
                    or rapid_by_key[key].get("event_id")
                    or ""
                ),
                "physical_event_key":key,
            })
            continue
        if key in existing:
            api_existing_aliases.append({
                "api_tennis_source_event_id":source_id,
                "physical_event_key":key,
            })
            continue
        if key in api_seen:
            api_existing_aliases.append({
                "api_tennis_source_event_id":source_id,
                "physical_event_key":key,
                "reason":"API_TENNIS_INTRAPROVIDER_DUPLICATE",
            })
            continue
        api_seen.add(key)
        api_out.append(row)

    rapid_payload=dict(rapidapi)
    rapid_payload["eligible_candidates"]=rapid_out
    rapid_payload["eligible_input_events"]=len(rapid_out)
    rapid_payload["dual_reconciled"]=True
    rapid_payload["provider_neutral_physical_identity"]=True

    api_payload=dict(api_tennis)
    api_payload["eligible_candidates"]=api_out
    api_payload["eligible_input_events"]=len(api_out)
    api_payload["dual_reconciled"]=True
    api_payload["provider_neutral_physical_identity"]=True
    api_payload["current_standings_competitive_values_used"]=False

    audit={
        "schema":"MATRIX_COR0203_DUAL_PROVIDER_DISCOVERY_RECONCILIATION_V1",
        "status":"PASS",
        "rapidapi_provider_status":rapidapi.get("status"),
        "api_tennis_provider_status":api_tennis.get("status"),
        "api_tennis_tournaments_seen":int(api_tennis.get("tournaments_seen") or 0),
        "api_tennis_draw_requests":int(api_tennis.get("draw_requests") or 0),
        "api_tennis_draw_request_limit":int(api_tennis.get("draw_request_limit") or 0),
        "api_tennis_unqueried_tournaments":sum(
            int(row.get("unqueried_tournaments") or 0)
            for row in api_tennis.get("provider_rejected",[]) or []
            if isinstance(row,Mapping)
            and "DRAW_REQUEST_LIMIT_REACHED" in (row.get("blockers") or [])
        ),
        "rapidapi_candidates_input":len(rapidapi.get("eligible_candidates",[]) or []),
        "api_tennis_candidates_input":len(api_tennis.get("eligible_candidates",[]) or []),
        "rapidapi_candidates_output":len(rapid_out),
        "api_tennis_unique_candidates_output":len(api_out),
        "cross_provider_alias_count":len(api_cross_provider_aliases),
        "cross_provider_aliases":api_cross_provider_aliases,
        "api_tennis_existing_physical_alias_count":len(api_existing_aliases),
        "api_tennis_existing_physical_aliases":api_existing_aliases,
        "api_tennis_identity_blocked_count":len(api_blocked),
        "api_tennis_identity_blocked":api_blocked,
        "identity_authority_records_input":len(
            identity_authority.get("records",[]) or []
        ) if isinstance(identity_authority,Mapping) else 0,
        "cross_provider_identity_aliases_generated":len(generated_identity_aliases),
        "cross_provider_identity_alias_provider_ids":sorted(generated_identity_aliases),
        "rapidapi_candidates_without_neutral_key":rapid_no_neutral,
        "existing_provider_neutral_keys":len(existing),
        "ranking_cut":"20260921",
        "api_tennis_current_rank_used":False,
        "static_cut_post_cut_data_used":False,
        "silent_imputation":False,
        "odds_to_probability":False,
        "metrics_opened":False,
        "outcomes_read":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    original_alias_records=[
        dict(row)
        for row in (certified_aliases.get("records",[]) if isinstance(certified_aliases,Mapping) else [])
        if isinstance(row,Mapping)
    ]
    alias_by_id={
        str(row.get("provider_player_id") or ""):row
        for row in original_alias_records
        if str(row.get("provider_player_id") or "")
    }
    alias_by_id.update(generated_identity_aliases)
    audit["_identity_alias_payload"]={
        "schema":"MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1",
        "purpose":"Certified cross-provider identity aliases for API-Tennis discovery, joined only to sealed pre-cut authority.",
        "strict_before_period":20260921,
        "records":[alias_by_id[key] for key in sorted(alias_by_id)],
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return rapid_payload,api_payload,audit


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--rapidapi",required=True)
    parser.add_argument("--api-tennis",required=True)
    parser.add_argument("--static-cut",required=True)
    parser.add_argument("--runtime-dir",default="evidence/cor0203/runtime")
    parser.add_argument("--certified-aliases")
    parser.add_argument("--identity-authority")
    parser.add_argument("--identity-alias-out")
    parser.add_argument("--out-rapidapi",required=True)
    parser.add_argument("--out-api-tennis",required=True)
    parser.add_argument("--audit-out",required=True)
    args=parser.parse_args()

    aliases=(
        _load(Path(args.certified_aliases))
        if args.certified_aliases and Path(args.certified_aliases).exists()
        else None
    )
    identity_authority=(
        _load(Path(args.identity_authority))
        if args.identity_authority and Path(args.identity_authority).exists()
        else None
    )
    rapid_out,api_out,audit=reconcile_dual_discovery(
        rapidapi=_load(Path(args.rapidapi)),
        api_tennis=_load(Path(args.api_tennis)),
        static_cut=_load(Path(args.static_cut)),
        runtime_dir=Path(args.runtime_dir),
        certified_aliases=aliases,
        identity_authority=identity_authority,
    )
    alias_payload=audit.pop("_identity_alias_payload")
    _write(Path(args.out_rapidapi),rapid_out)
    _write(Path(args.out_api_tennis),api_out)
    if args.identity_alias_out:
        _write(Path(args.identity_alias_out),alias_payload)
    _write(Path(args.audit_out),audit)
    print(json.dumps({
        "status":audit["status"],
        "rapidapi_candidates_input":audit["rapidapi_candidates_input"],
        "api_tennis_candidates_input":audit["api_tennis_candidates_input"],
        "rapidapi_candidates_output":audit["rapidapi_candidates_output"],
        "api_tennis_unique_candidates_output":audit["api_tennis_unique_candidates_output"],
        "cross_provider_alias_count":audit["cross_provider_alias_count"],
        "api_tennis_identity_blocked_count":audit["api_tennis_identity_blocked_count"],
        "cross_provider_identity_aliases_generated":audit["cross_provider_identity_aliases_generated"],
        "real_money":audit["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
