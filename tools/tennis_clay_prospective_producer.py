from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

LANE_ID="ATP_CHALLENGER_MEN_SINGLES_CLAY"
HOLDOUT_ID="ATP_CHALLENGER_CLAY_PROSPECTIVE_V1"
MODEL_ID="ATP_CHALLENGER_CLAY_ELO_V1"


def _load(path: Path) -> dict[str,Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc(value: object) -> datetime:
    d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return d.astimezone(timezone.utc)


def _sha(payload: Mapping[str,Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(payload),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()


def _p(ra: float, rb: float, scale: float) -> float:
    return 1.0/(1.0+10.0**((rb-ra)/scale))


def _window(index: int) -> int:
    return 1 if index<=200 else 2 if index<=400 else 3


def existing_observations(path: Path) -> list[dict[str,Any]]:
    if not path.exists():
        return []
    out=[]
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            row=json.loads(raw)
            if isinstance(row,dict):
                out.append(row)
    return out


def produce(
    *,
    prefeature: Mapping[str,Any],
    crosswalk: Mapping[str,Any],
    catchup: Mapping[str,Any],
    reconciliation: Mapping[str,Any],
    state: Mapping[str,Any],
    model: Mapping[str,Any],
    prior: list[dict[str,Any]],
    freeze_at_utc: str,
) -> tuple[list[dict[str,Any]],dict[str,Any],dict[str,Any]]:
    now=_utc(freeze_at_utc)
    if state.get("metrics_opened") is not False or int(state.get("outcomes_read") or 0)!=0:
        raise ValueError("CLAY_STATE_PROTECTION_INVALID")
    if state.get("real_money")!="BLOCKED":
        raise ValueError("CLAY_REAL_MONEY_NOT_BLOCKED")
    if str(state.get("frozen_model_identity") or "")!=MODEL_ID:
        raise ValueError("CLAY_MODEL_ID_MISMATCH")
    if str(catchup.get("model_identity") or "")!=MODEL_ID:
        raise ValueError("CLAY_CATCHUP_MODEL_ID_MISMATCH")
    if float(catchup.get("chosen_k") or -1)!=32.0:
        raise ValueError("CLAY_K_NOT_FROZEN_32")
    if catchup.get("silent_imputation") is not False:
        raise ValueError("CLAY_CATCHUP_IMPUTATION_FLAG_INVALID")
    if int(catchup.get("outcomes_used_for_model_parameter_tuning") or 0)!=0:
        raise ValueError("CLAY_CATCHUP_TUNING_LEAKAGE")
    chosen=float((model.get("parameter_selection") or {}).get("chosen_k") or -1)
    if chosen!=32.0:
        raise ValueError("CLAY_MODEL_FILE_K_NOT_32")
    scale=float(model.get("probability_scale") or 400.0)
    if not math.isclose(scale,400.0):
        raise ValueError("CLAY_MODEL_SCALE_CHANGED")

    event_by_source={
        str(e.get("canonical_source_event_id") or ""):e
        for e in prefeature.get("events",[]) or []
        if isinstance(e,Mapping)
    }
    cross_events={
        str(e.get("event_id") or ""):e
        for e in crosswalk.get("events",[]) or []
        if isinstance(e,Mapping)
    }
    mapping_by_pid={
        str(m.get("provider_player_id") or ""):m
        for m in crosswalk.get("mappings",[]) or []
        if isinstance(m,Mapping) and m.get("status")=="PASS"
    }
    target_by_pid={
        str(t.get("provider_player_id") or ""):t
        for t in catchup.get("targets",[]) or []
        if isinstance(t,Mapping)
    }
    seen_keys={str(x.get("physical_event_key") or "") for x in prior}
    seen_sources={str(x.get("rapidapi_source_event_id") or "") for x in prior}
    start_count=len(prior)
    admitted=[]; blocked=[]

    for bind in reconciliation.get("bindings",[]) or []:
        if not isinstance(bind,Mapping) or bind.get("surface_family")!="CLAY":
            continue
        rapid_id=str(bind.get("rapid_source_event_id") or "")
        source_event=event_by_source.get(rapid_id)
        if source_event is None:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"CURRENT_PREFEATURE_EVENT_MISSING"})
            continue
        if rapid_id in seen_sources or str(bind.get("rapid_physical_event_key") or "") in seen_keys:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"DUPLICATE_PHYSICAL_EVENT"})
            continue
        blockers=[
            str(x) for x in bind.get("blockers",[]) or []
            if str(x)!="PIT_HISTORY_NOT_CAUGHT_UP_TO_EVENT"
        ]
        if blockers:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"RECONCILIATION_BLOCKED","blockers":blockers})
            continue
        start=_utc(source_event.get("event_start_utc"))
        if start<=now:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"POST_START_FREEZE_FORBIDDEN"})
            continue
        if str(source_event.get("surface") or "").casefold()!="clay":
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"SURFACE_MISMATCH"})
            continue
        xevent=cross_events.get(str(source_event.get("event_id") or ""))
        if not isinstance(xevent,Mapping) or xevent.get("status")!="PASS":
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"IDENTITY_CROSSWALK_NOT_PASS"})
            continue

        identities=list(source_event.get("player_identities") or [])
        if len(identities)!=2:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"PROVIDER_IDENTITIES_REQUIRED"})
            continue
        players=[]
        failed=[]
        for identity in identities:
            pid=str(identity.get("provider_player_id") or "")
            mapping=mapping_by_pid.get(pid)
            target=target_by_pid.get(pid)
            if not isinstance(mapping,Mapping):
                failed.append("CROSSWALK_MAPPING_MISSING:"+pid); continue
            if not isinstance(target,Mapping) or target.get("ready") is not True:
                failed.append("PIT_CATCHUP_NOT_READY:"+pid); continue
            if str(target.get("canonical_source_id") or "")!=str(mapping.get("canonical_source_id") or ""):
                failed.append("CATCHUP_CROSSWALK_CANONICAL_ID_MISMATCH:"+pid); continue
            rating=target.get("rating_after_catchup")
            if rating is None:
                failed.append("CATCHUP_RATING_MISSING:"+pid); continue
            players.append({
                "provider_player_id":pid,
                "canonical_source_id":str(mapping.get("canonical_source_id")),
                "canonical_name":str(mapping.get("canonical_name")),
                "elo_rating":float(rating),
            })
        if failed or len(players)!=2:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"PIT_OR_IDENTITY_BLOCKED","blockers":failed})
            continue
        players.sort(key=lambda x:x["canonical_source_id"])
        if players[0]["canonical_source_id"]==players[1]["canonical_source_id"]:
            blocked.append({"rapid_source_event_id":rapid_id,"reason":"CANONICAL_PLAYER_COLLISION"})
            continue
        p_a=_p(players[0]["elo_rating"],players[1]["elo_rating"],scale)
        index=start_count+len(admitted)+1
        obs={
            "schema":"MATRIX_TENNIS_CLAY_PROSPECTIVE_OBSERVATION_V1",
            "lane_id":LANE_ID,
            "holdout_id":HOLDOUT_ID,
            "observation_index":index,
            "window":_window(index),
            "event_id":str(source_event.get("event_id") or ""),
            "rapidapi_source_event_id":rapid_id,
            "api_tennis_source_event_id":str(bind.get("api_tennis_source_event_id") or ""),
            "physical_event_key":str(bind.get("rapid_physical_event_key") or source_event.get("physical_event_key") or ""),
            "competition":source_event.get("competition"),
            "round":source_event.get("round"),
            "surface":"Clay",
            "event_start_utc":start.isoformat(),
            "freeze_at_utc":now.isoformat(),
            "player_a":players[0],
            "player_b":players[1],
            "model":{
                "identity":MODEL_ID,
                "k":32.0,
                "probability_scale":scale,
                "same_day_update_policy":"BATCH_AFTER_ALL_MATCHES_ON_TOURNEY_DATE",
                "p_player_a":p_a,
            },
            "identity":{
                "crosswalk_status":"PASS",
                "dual_paid_provider_binding":"PASS",
                "binding_basis":bind.get("identity_binding_basis"),
                "surface_binding":bind.get("surface_binding"),
            },
            "pit":{
                "catchup_source_stop":catchup.get("catchup_source_stop"),
                "historical_dataset_max_tourney_date":catchup.get("historical_dataset_max_tourney_date"),
                "all_connected_identities_mapped":True,
            },
            "outcome":None,
            "metrics_opened":False,
            "odds_used":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
        obs["observation_sha256"]=_sha(obs)
        admitted.append(obs)
        seen_keys.add(obs["physical_event_key"]); seen_sources.add(rapid_id)

    all_rows=prior+admitted
    new_state=dict(state)
    new_state["observation_count"]=len(all_rows)
    new_state["unique_physical_event_count"]=len({str(x.get("physical_event_key") or "") for x in all_rows})
    new_state["status"]="ACTIVE_PROSPECTIVE" if all_rows else "ACTIVE_WAITING_FUTURE_ELIGIBLE_EVENTS"
    new_state["metrics_opened"]=False
    new_state["outcomes_read"]=0
    new_state["real_money"]="BLOCKED"
    audit={
        "schema":"MATRIX_TENNIS_CLAY_PROSPECTIVE_PRODUCER_AUDIT_V1",
        "freeze_at_utc":now.isoformat(),
        "starting_observation_count":start_count,
        "new_observations":len(admitted),
        "ending_observation_count":len(all_rows),
        "admitted_event_ids":[x["event_id"] for x in admitted],
        "blocked":blocked,
        "metrics_opened":False,
        "outcomes_read":0,
        "historical_backfill":False,
        "silent_imputation":False,
        "odds_to_probability":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return admitted,new_state,audit


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--prefeature",required=True)
    p.add_argument("--crosswalk",required=True)
    p.add_argument("--catchup",required=True)
    p.add_argument("--reconciliation",required=True)
    p.add_argument("--state",required=True)
    p.add_argument("--model",required=True)
    p.add_argument("--observations",required=True)
    p.add_argument("--audit-out",required=True)
    a=p.parse_args()
    state_path=Path(a.state); model_path=Path(a.model); obs_path=Path(a.observations)
    state=_load(state_path); model=_load(model_path)
    frozen=str(state.get("frozen_model_sha256") or "")
    actual=hashlib.sha256(model_path.read_bytes()).hexdigest()
    if frozen!=actual:
        raise SystemExit("CLAY_FROZEN_MODEL_SHA_MISMATCH")
    prior=existing_observations(obs_path)
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    admitted,new_state,audit=produce(
        prefeature=_load(Path(a.prefeature)),
        crosswalk=_load(Path(a.crosswalk)),
        catchup=_load(Path(a.catchup)),
        reconciliation=_load(Path(a.reconciliation)),
        state=state,
        model=model,
        prior=prior,
        freeze_at_utc=now,
    )
    if admitted:
        obs_path.parent.mkdir(parents=True,exist_ok=True)
        with obs_path.open("a",encoding="utf-8") as fh:
            for row in admitted:
                fh.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    state_path.write_text(json.dumps(new_state,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    out=Path(a.audit_out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "new_observations":audit["new_observations"],
        "ending_observation_count":audit["ending_observation_count"],
        "blocked":len(audit["blocked"]),
        "metrics_opened":False,
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
