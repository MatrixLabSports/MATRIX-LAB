from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient

SCHEMA="MATRIX_TENNIS_CLAY_PROFILE_IDENTITY_RECOVERY_V1"
LANE_ID="ATP_CHALLENGER_MEN_SINGLES_CLAY"
CUT_TOKEN="20260921"
COUNTRY_ALIASES={"POR":"PRT"}
DETERMINISTIC_CACHEABLE_REASONS={
    "PROFILE_HAND_INVALID_FOR_NEW_PLAYER",
    "PROFILE_DOB_INVALID",
    "HISTORICAL_HAND_NOT_UNIQUE",
}
CACHE_MAX_AGE_SECONDS=6*60*60


def _norm(value: object) -> str:
    text=unicodedata.normalize("NFKD",str(value or ""))
    text="".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _ioc(value: object) -> str:
    token=str(value or "").strip().upper()
    return COUNTRY_ALIASES.get(token,token)


def _dob(value: object) -> date | None:
    token=str(value or "").strip()[:10]
    try:
        return date.fromisoformat(token)
    except ValueError:
        return None


def _hand(value: object) -> str | None:
    token=str(value or "").strip().casefold()
    if token.startswith("right"): return "R"
    if token.startswith("left"): return "L"
    return None


def _profile(payload: Mapping[str,Any]) -> dict[str,Any]:
    data=payload.get("data") if isinstance(payload.get("data"),Mapping) else payload
    info=data.get("information") if isinstance(data.get("information"),Mapping) else {}
    return {
        "id":str(data.get("id") or "").strip(),
        "name":str(data.get("name") or "").strip(),
        "ioc":_ioc(data.get("countryAcr")),
        "dob":_dob(data.get("birthday")),
        "hand":_hand(info.get("plays") or info.get("hand")),
        "competitive_fields":[k for k in ("currentRank","points","progress","careerMoney") if k in data],
    }


def _historical_index(rows: list[Mapping[str,Any]]) -> dict[str,list[dict[str,Any]]]:
    out=defaultdict(list)
    for row in rows:
        d=str(row.get("tourney_date") or "").strip()
        for side in ("a","b"):
            name=str(row.get(f"player_{side}_name") or "").strip()
            cid=str(row.get(f"player_{side}_id") or "").strip()
            if not name or not cid: continue
            try: age=float(row.get(f"player_{side}_age"))
            except (TypeError,ValueError): age=None
            hand=str(row.get(f"player_{side}_hand") or "").strip().upper()
            out[_norm(name)].append({
                "canonical_source_id":cid,
                "canonical_name":name,
                "hand":hand if hand in {"R","L"} else None,
                "age":age,
                "tourney_date":d,
            })
    return out


def _age_on(dob: date, ymd: str) -> float | None:
    if len(ymd)!=8 or not ymd.isdigit(): return None
    try: d=date(int(ymd[:4]),int(ymd[4:6]),int(ymd[6:8]))
    except ValueError: return None
    return (d-dob).days/365.25


def recover(
    *,
    catchup: Mapping[str,Any],
    historical_rows: list[Mapping[str,Any]],
    model: Mapping[str,Any],
    profile_fetcher: Callable[[str],Mapping[str,Any]],
    max_targets: int,
    cached_blocks: Mapping[str,Mapping[str,Any]] | None = None,
) -> dict[str,Any]:
    if model.get("candidate_identity")!="ATP_CHALLENGER_CLAY_ELO_V1":
        raise ValueError("CLAY_PROFILE_RECOVERY_MODEL_IDENTITY_INVALID")
    if float(model.get("rating_initial"))!=1500.0:
        raise ValueError("CLAY_PROFILE_RECOVERY_INITIAL_RATING_INVALID")
    if model.get("same_day_update_policy")!="BATCH_AFTER_ALL_MATCHES_ON_TOURNEY_DATE":
        raise ValueError("CLAY_PROFILE_RECOVERY_UPDATE_POLICY_INVALID")
    if catchup.get("silent_imputation") is not False:
        raise ValueError("CLAY_PROFILE_RECOVERY_CATCHUP_IMPUTATION_FLAG_INVALID")

    hist=_historical_index(historical_rows)
    cached_blocks=cached_blocks or {}
    mappings=[]; events=[]; blocked=[]; requests=0; cached_blocked=0
    backlog=[
        row for row in catchup.get("unmapped_identity_backlog",[]) or []
        if isinstance(row,Mapping)
    ]
    backlog.sort(
        key=lambda row: (
            -int(row.get("target_component_hits") or 0),
            -int(row.get("catchup_matches") or 0),
            str(row.get("provider_player_id") or ""),
        )
    )
    backlog=backlog[:max(0,int(max_targets))]

    for raw in backlog:
        pid=str(raw.get("provider_player_id") or "")
        numeric=str(raw.get("numeric_player_id") or "")
        names=[str(x).strip() for x in raw.get("observed_names",[]) or [] if str(x).strip()]
        iocs=[_ioc(x) for x in raw.get("observed_iocs",[]) or [] if str(x).strip()]
        if (
            raw.get("identity_observation_status")!="CONSISTENT"
            or len(names)!=1 or len(iocs)!=1
            or pid!="rapidapi-tennis:player:"+numeric
            or not numeric.isdigit()
        ):
            blocked.append({"provider_player_id":pid,"reason":"CATCHUP_IDENTITY_NOT_UNIQUE"})
            continue

        cached=cached_blocks.get(pid)
        if cached and str(cached.get("reason") or "") in DETERMINISTIC_CACHEABLE_REASONS:
            row=dict(cached)
            row["provider_player_id"]=pid
            row["cached_deterministic_block"]=True
            blocked.append(row)
            cached_blocked+=1
            continue

        payload=profile_fetcher(numeric); requests+=1
        p=_profile(payload)
        if p["id"] not in {"",numeric}:
            blocked.append({"provider_player_id":pid,"reason":"PROFILE_ID_MISMATCH"}); continue
        if _norm(p["name"])!=_norm(names[0]):
            blocked.append({"provider_player_id":pid,"reason":"PROFILE_NAME_MISMATCH"}); continue
        if p["ioc"]!=iocs[0]:
            blocked.append({"provider_player_id":pid,"reason":"PROFILE_IOC_MISMATCH"}); continue
        if p["dob"] is None:
            blocked.append({"provider_player_id":pid,"reason":"PROFILE_DOB_INVALID"}); continue

        hist_rows=hist.get(_norm(names[0]),[])
        hist_ids=sorted({x["canonical_source_id"] for x in hist_rows})
        if len(hist_ids)>1:
            blocked.append({"provider_player_id":pid,"reason":"HISTORICAL_CANONICAL_ID_AMBIGUOUS","ids":hist_ids}); continue

        if len(hist_ids)==1:
            hands=sorted({x["hand"] for x in hist_rows if x["hand"]})
            if len(hands)!=1:
                blocked.append({"provider_player_id":pid,"reason":"HISTORICAL_HAND_NOT_UNIQUE"}); continue
            if p["hand"] in {"R","L"} and hands[0]!=p["hand"]:
                blocked.append({"provider_player_id":pid,"reason":"PROFILE_HISTORICAL_HAND_CONFLICT"}); continue
            resolved_hand=hands[0]
            hand_source=(
                "RAPIDAPI_PROFILE_CONFIRMED_BY_UNIQUE_CLAY_HISTORY"
                if p["hand"] in {"R","L"}
                else "UNIQUE_PRE_CUT_CLAY_HISTORY"
            )
            diffs=[]
            for x in hist_rows:
                expected=_age_on(p["dob"],x["tourney_date"])
                if expected is not None and x["age"] is not None:
                    diffs.append(abs(expected-float(x["age"])))
            if not diffs or max(diffs)>0.06:
                blocked.append({
                    "provider_player_id":pid,
                    "reason":"PROFILE_HISTORICAL_DOB_AGE_CONFLICT",
                    "max_age_delta":max(diffs) if diffs else None,
                }); continue
            cid=hist_ids[0]
            basis="EXACT_PROVIDER_ID_NAME_IOC_PROFILE_DOB_PLUS_UNIQUE_CLAY_HISTORICAL_ID_HAND_AGE"
            new_player=False
        else:
            if p["hand"] not in {"R","L"}:
                blocked.append({"provider_player_id":pid,"reason":"PROFILE_HAND_INVALID_FOR_NEW_PLAYER"}); continue
            resolved_hand=p["hand"]
            hand_source="RAPIDAPI_PROFILE"
            cid="RAPIDAPI_CLAY_NEW_"+numeric
            basis="EXACT_PROVIDER_ID_NAME_IOC_PROFILE_DOB_HAND_PLUS_FROZEN_ELO_NEW_PLAYER_PRIOR"
            new_player=True

        profile_sha=hashlib.sha256(
            json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
        ).hexdigest()
        mapping={
            "provider":"rapidapi_tennis",
            "provider_player_id":pid,
            "provider_display_name":names[0],
            "canonical_source_id":cid,
            "canonical_name":names[0],
            "canonical_ioc":iocs[0],
            "canonical_dob":p["dob"].isoformat(),
            "canonical_hand":resolved_hand,
            "hand_source":hand_source,
            "match_basis":basis,
            "identity_evidence_role":"CLAY_CATCHUP_IDENTITY_ONLY",
            "new_to_clay_historical_dataset":new_player,
            "frozen_initial_rating":1500.0 if new_player else None,
            "profile_competitive_fields_discarded":p["competitive_fields"],
            "provider_profile_sha256":profile_sha,
            "ranking_cut":CUT_TOKEN,
            "status":"PASS",
        }
        mappings.append(mapping)
        events.append({
            "event_id":"CLAY-PROFILE-IDENTITY-"+numeric,
            "provider_player_ids":[pid],
            "status":"PASS",
            "blockers":[],
        })

    return {
        "schema":SCHEMA,
        "lane_id":LANE_ID,
        "revision":"CLAY_PROFILE_IDENTITY_RECOVERY",
        "status":"PASS_WITH_BLOCKERS" if blocked else "PASS",
        "ranking_cut":CUT_TOKEN,
        "join_by_name_only":False,
        "passed_events":len(events),
        "blocked_events":len(blocked),
        "events":events,
        "mappings":mappings,
        "blocked":blocked,
        "profile_requests":requests,
        "cached_deterministic_blocks":cached_blocked,
        "model_identity":model.get("candidate_identity"),
        "model_rating_initial":1500.0,
        "same_day_update_policy":model.get("same_day_update_policy"),
        "identity_only":True,
        "model_admission_forbidden":True,
        "historical_backfill_into_prospective_holdout":False,
        "post_cut_competitive_data_used_for_identity":False,
        "outcomes_used_for_identity":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--catchup",required=True)
    p.add_argument("--historical-dataset",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--out",required=True)
    p.add_argument("--max-targets",type=int,default=30)
    a=p.parse_args()
    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key: raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    client=RapidApiTennisClient(key)
    rows=list(csv.DictReader(Path(a.historical_dataset).read_text(encoding="utf-8-sig").splitlines()))
    model=json.loads(Path(a.model).read_text(encoding="utf-8"))
    catchup=json.loads(Path(a.catchup).read_text(encoding="utf-8"))
    path=Path(a.out)
    cached_blocks={}
    cache_source_generated_at_utc=None
    if path.exists():
        try:
            prior=json.loads(path.read_text(encoding="utf-8"))
            stamp=str(prior.get("generated_at_utc") or "")
            parsed=datetime.fromisoformat(stamp.replace("Z","+00:00")) if stamp else None
            now=datetime.now(timezone.utc)
            if parsed is not None and parsed.tzinfo is not None and 0 <= (now-parsed).total_seconds() <= CACHE_MAX_AGE_SECONDS:
                cached_blocks={
                    str(x.get("provider_player_id") or ""):x
                    for x in prior.get("blocked",[]) or []
                    if str(x.get("reason") or "") in DETERMINISTIC_CACHEABLE_REASONS
                    and str(x.get("provider_player_id") or "")
                }
                cache_source_generated_at_utc=stamp
        except (ValueError,TypeError,json.JSONDecodeError):
            cached_blocks={}
    out=recover(
        catchup=catchup,
        historical_rows=rows,
        model=model,
        profile_fetcher=lambda numeric: client.player_profile(player_id=numeric),
        max_targets=a.max_targets,
        cached_blocks=cached_blocks,
    )
    out["provider_network_calls"]=client.request_count
    out["generated_at_utc"]=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out["cache_source_generated_at_utc"]=cache_source_generated_at_utc
    out["cache_policy"]="DETERMINISTIC_BLOCKS_ONLY_6H"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "passed_events":out["passed_events"],
        "blocked_events":out["blocked_events"],
        "profile_requests":out["profile_requests"],
        "cached_deterministic_blocks":out["cached_deterministic_blocks"],
        "provider_network_calls":out["provider_network_calls"],
        "new_player_priors":sum(1 for x in out["mappings"] if x["new_to_clay_historical_dataset"]),
        "historical_links":sum(1 for x in out["mappings"] if not x["new_to_clay_historical_dataset"]),
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
