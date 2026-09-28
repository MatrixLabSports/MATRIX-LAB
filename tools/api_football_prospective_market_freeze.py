from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path
from typing import Any, Mapping

from app.research.football.experimental_evaluator import evaluate_transparent_poisson_baseline
from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_freeze_experimental_shadow import _rehydrate_input

EPS=1e-12
MIN_GROUP_HISTORY=20
FINAL_STATUSES={"FT","AET","PEN"}


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _utc(value:Any)->datetime:
    dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return dt.astimezone(timezone.utc)


def _clip(p:float)->float:
    return min(max(float(p),EPS),1-EPS)


def _logit(p:float)->float:
    p=_clip(p)
    return log(p/(1-p))


def _sigmoid(x:float)->float:
    if x>=0:
        z=exp(-x)
        return 1/(1+z)
    z=exp(x)
    return z/(1+z)


def _sha(payload:Any)->str:
    return sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def _historical_group_baseline(raw_path:Path, freeze_at:datetime)->dict[str,float]|None:
    if not raw_path.exists():
        return None
    payload=_load(raw_path)
    response=payload.get("response")
    if not isinstance(response,list):
        return None
    finals=[]
    for row in response:
        if not isinstance(row,Mapping):
            continue
        fixture=row.get("fixture"); goals=row.get("goals")
        if not isinstance(fixture,Mapping) or not isinstance(goals,Mapping):
            continue
        status=fixture.get("status")
        if not isinstance(status,Mapping) or str(status.get("short") or "").upper() not in FINAL_STATUSES:
            continue
        try:
            kickoff=_utc(fixture.get("date"))
        except Exception:
            continue
        if kickoff>=freeze_at:
            continue
        hg=goals.get("home"); ag=goals.get("away")
        if isinstance(hg,bool) or isinstance(ag,bool) or not isinstance(hg,int) or not isinstance(ag,int):
            continue
        finals.append((kickoff,hg,ag))
    finals.sort()
    if len(finals)<MIN_GROUP_HISTORY:
        return None
    n=len(finals)
    return {
        "H":sum(hg>ag for _,hg,ag in finals)/n,
        "D":sum(hg==ag for _,hg,ag in finals)/n,
        "A":sum(hg<ag for _,hg,ag in finals)/n,
        "over_2_5":sum(hg+ag>=3 for _,hg,ag in finals)/n,
        "btts":sum(hg>0 and ag>0 for _,hg,ag in finals)/n,
        "sample_size":n,
    }


def _mc_pool(poisson:Mapping[str,float], baseline:Mapping[str,float], a:float,c:float)->dict[str,float]:
    scores={}
    for k,pkey in (("H","home_win"),("D","draw"),("A","away_win")):
        pp=max(float(poisson[pkey]),EPS); bp=max(float(baseline[k]),EPS)
        scores[k]=exp(a*log(pp)+c*log(bp))
    total=sum(scores.values())
    return {k:v/total for k,v in scores.items()}


def _bin_pool(poisson_p:float, baseline_p:float, a:float,c:float,b:float)->float:
    return _sigmoid(a*_logit(poisson_p)+c*_logit(baseline_p)+b)


def _btts_v2_probability(*,poisson_p:float,baseline_p:float,ehg:float,eag:float,home_count:int,away_count:int,weights:list[float])->float:
    x=[
        1.0,
        _logit(poisson_p),
        _logit(baseline_p),
        float(ehg),
        float(eag),
        abs(float(ehg)-float(eag)),
        min(float(ehg),float(eag)),
        float(home_count)/20.0,
        float(away_count)/20.0,
    ]
    if len(weights)!=len(x):
        raise ValueError("BTTS_V2_WEIGHT_DIMENSION_MISMATCH")
    return _sigmoid(sum(w*v for w,v in zip(weights,x)))


def build_freeze(root:Path, freeze_at:datetime)->dict[str,Any]:
    freeze=freeze_at.astimezone(timezone.utc).replace(microsecond=0)
    canonical,manifest=load_chunked_canonical_bundle(root/"evidence/api_football/canonical_analysis")
    gov=_load(root/"evidence/api_football/market_governance/market_governance.json")
    btts=_load(root/"evidence/api_football/btts_challenger_v2/manifest.json")
    retrospective=_load(root/"evidence/api_football/model_validation/retrospective_predictions.json")
    excluded_original=_load(root/"evidence/api_football/btts_challenger_v2/exclusion_registry.json")

    if set(gov["approved_markets"])!={"1x2","over_2_5"}:
        raise ValueError("MARKET_GOVERNANCE_NOT_EXPECTED")
    if btts["candidate_status"]!="FROZEN_BTTS_V2_AWAITING_NEW_PROSPECTIVE_HOLDOUT":
        raise ValueError("BTTS_V2_NOT_FROZEN")
    if btts["forbidden_final_holdout_outcomes_read"] is not False:
        raise ValueError("ORIGINAL_HOLDOUT_CONTAMINATED")

    historical_seen={str(r["fixture_id"]) for r in retrospective.get("rows",[]) if isinstance(r,Mapping)}
    forbidden={str(x) for x in excluded_original.get("forbidden_fixture_ids",[])}
    if len(forbidden)!=357:
        raise ValueError("FORBIDDEN_REGISTRY_COUNT_CHANGED")

    gov_by_market={r["market"]:r for r in gov["markets"]}
    p1=gov_by_market["1x2"]["frozen_parameters"]
    po=gov_by_market["over_2_5"]["frozen_parameters"]
    weights=list(btts["selected"]["weights"])

    frozen=[]
    exclusions=[]
    for raw in canonical.get("inputs",[]):
        value=_rehydrate_input(raw)
        kickoff=_utc(value.kickoff_utc)
        fid=str(value.fixture_id)
        if freeze>=kickoff:
            exclusions.append({"fixture_id":fid,"target_key":value.target_key,"reason":"NOT_FUTURE_AT_FREEZE"})
            continue
        if fid in historical_seen or fid in forbidden:
            exclusions.append({"fixture_id":fid,"target_key":value.target_key,"reason":"NOT_UNSEEN_EVENT"})
            continue

        raw_path=root/f"evidence/api_football/history/raw/league_{value.competition_id}_season_{value.season}.bin"
        baseline=_historical_group_baseline(raw_path,freeze)
        if baseline is None:
            exclusions.append({
                "fixture_id":fid,
                "target_key":value.target_key,
                "reason":"FEATURE_NOT_REPRODUCIBLE",
                "required_source":raw_path.as_posix(),
            })
            continue

        ev=evaluate_transparent_poisson_baseline(value)
        if ev.probabilities is None or ev.expected_home_goals is None or ev.expected_away_goals is None:
            exclusions.append({"fixture_id":fid,"target_key":value.target_key,"reason":"POISSON_INPUT_NOT_EXECUTABLE"})
            continue
        home_count=ev.readiness.home_history_count
        away_count=ev.readiness.away_history_count

        p_1x2=_mc_pool(ev.probabilities,baseline,float(p1["a"]),float(p1["c"]))
        p_over=_bin_pool(float(ev.probabilities["over_2_5"]),float(baseline["over_2_5"]),float(po["a"]),float(po["c"]),float(po["b"]))
        p_btts=_btts_v2_probability(
            poisson_p=float(ev.probabilities["btts"]),
            baseline_p=float(baseline["btts"]),
            ehg=float(ev.expected_home_goals),
            eag=float(ev.expected_away_goals),
            home_count=home_count,
            away_count=away_count,
            weights=weights,
        )
        frozen.append({
            "fixture_id":fid,
            "target_key":value.target_key,
            "competition_id":value.competition_id,
            "competition_name":value.competition_name,
            "season":value.season,
            "kickoff_utc":value.kickoff_utc,
            "freeze_at_utc":freeze.isoformat(),
            "input_sha256":value.canonical_sha256(),
            "historical_baseline_source":raw_path.as_posix(),
            "historical_baseline_sample_size":baseline["sample_size"],
            "poisson_reference":{
                "1x2":{"H":ev.probabilities["home_win"],"D":ev.probabilities["draw"],"A":ev.probabilities["away_win"]},
                "over_2_5":ev.probabilities["over_2_5"],
                "btts":ev.probabilities["btts"],
            },
            "frozen_research_probabilities":{
                "1x2":p_1x2,
                "over_2_5":p_over,
                "btts_v2":p_btts,
            },
            "market_status":{
                "1x2":"APPROVED_CHALLENGER_PROSPECTIVE_SHADOW",
                "over_2_5":"APPROVED_CHALLENGER_PROSPECTIVE_SHADOW",
                "btts_v2":"NEW_PROSPECTIVE_HOLDOUT",
            },
            "outcome":None,
            "settlement_status":"PENDING_FINAL",
            "odds_used_to_generate_probability":False,
            "p_matrix":None,
        })

    frozen.sort(key=lambda r:(r["kickoff_utc"],int(r["fixture_id"])))
    exclusions.sort(key=lambda r:int(r["fixture_id"]))
    return {
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_MARKET_FREEZE_V1",
        "created_at_utc":freeze.isoformat(),
        "source_canonical_bundle_sha256":manifest["bundle_sha256"],
        "source_market_governance_holdout_sha256":gov["holdout_seal_sha256"],
        "source_btts_v2_exclusion_registry_sha256":btts["exclusion_registry_sha256"],
        "historical_seen_fixture_count":len(historical_seen),
        "permanently_forbidden_original_holdout_count":len(forbidden),
        "frozen_event_count":len(frozen),
        "excluded_event_count":len(exclusions),
        "rows":frozen,
        "exclusions":exclusions,
        "protections":{
            "future_only":True,
            "unseen_events_only":True,
            "freeze_strictly_before_kickoff":True,
            "original_357_holdout_excluded":True,
            "missing_feature_imputation":False,
            "outcomes_read_at_freeze":False,
            "settlement_final_only":True,
            "odds_used_to_generate_probability":False,
            "p_matrix_generated":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def main()->None:
    root=Path(".")
    out=root/"evidence/api_football/prospective_market_freeze"
    out.mkdir(parents=True,exist_ok=True)
    existing=out/"freeze.json"
    if existing.exists():
        old=_load(existing)
        if old.get("rows"):
            raise ValueError("PROSPECTIVE_FREEZE_ALREADY_EXISTS_REFUSE_OVERWRITE")
    data=build_freeze(root,datetime.now(timezone.utc))
    if data["frozen_event_count"]<=0:
        raise ValueError("NO_ELIGIBLE_FUTURE_EVENTS_FOR_PROSPECTIVE_FREEZE")
    existing.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest={k:v for k,v in data.items() if k not in {"rows","exclusions"}}
    manifest["freeze_sha256"]=_sha(data)
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "created_at_utc":data["created_at_utc"],
        "frozen_event_count":data["frozen_event_count"],
        "excluded_event_count":data["excluded_event_count"],
        "first_kickoff":data["rows"][0]["kickoff_utc"] if data["rows"] else None,
        "last_kickoff":data["rows"][-1]["kickoff_utc"] if data["rows"] else None,
        "protections":data["protections"],
    },sort_keys=True))


if __name__=="__main__":
    main()
