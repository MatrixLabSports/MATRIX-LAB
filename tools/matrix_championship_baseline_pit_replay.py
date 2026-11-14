"""Independently replay the frozen Over 2.5 group baseline from provider HTTP bytes.

Read-only, historical input validation; NOT alternative-provider calibration
equivalence, not an API-Football crosswalk, not production p_matrix/Telegram.
"""
from __future__ import annotations
import argparse
import base64
import binascii
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_market_shadow_p_matrix import _inputs_for_target, _pool_over25
from tools.matrix_championship_prospective_pit_attestation import source_digest
from tools.matrix_football_independent_over25_shadow import historic_rows

def utc(value):
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("BASELINE_PIT_NAIVE_TIME")
    return t.astimezone(timezone.utc)

def keyed(rows,key):
    if not isinstance(rows,list):raise ValueError("BASELINE_ROWS_INVALID")
    mapped={}
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("BASELINE_ROW_INVALID")
        ident=str(row.get(key) or "")
        if not ident or ident in mapped:
            raise ValueError("BASELINE_DUPLICATE_OR_INVALID_ID")
        mapped[ident]=row
    return mapped

def close(a,b):
    try:
        a,b=float(a),float(b)
        return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-9
    except (ValueError,TypeError,OverflowError):
        return False

def replay(intake,shadow,attestation,sofa,flash,*,now):
    clock=utc(now.isoformat())
    day=intake.get("target_date_bogota")
    for doc in (intake,shadow,attestation,sofa,flash):
        if doc.get("real_money")!="BLOCKED" or doc.get("target_date_bogota")!=day:
            raise ValueError("BASELINE_GOVERNANCE_OR_DATE_INVALID")
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or intake.get("provider_status")!="AUTHENTICATED_FIXTURE_CAPTURE"
        or intake.get("source")!="FOOTBALL_DATA_ORG"
        or shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        or shadow.get("source")!="FOOTBALL_DATA_ORG"
        or attestation.get("schema")!="MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION_V1"
        or attestation.get("source_binding_schema")!="MATRIX_PROSPECTIVE_PIT_EXACT_FOUR_SOURCE_BINDING_V1"
        or attestation.get("source_intake_sha256")!=source_digest(intake)
        or attestation.get("source_shadow_sha256")!=source_digest(shadow)
        or attestation.get("source_sofa_sha256")!=source_digest(sofa)
        or attestation.get("source_flash_sha256")!=source_digest(flash)
        or shadow.get("frozen_parameters")!={"a":0.6,"b":0.0,"c":0.4}
        or shadow.get("parameter_refit") is not False
        or intake.get("signal_generation_authorized") is not False
        or shadow.get("market_signal_authorized") is not False
        or attestation.get("telegram_signal_authorized") is not False
        or attestation.get("production_p_matrix_authorized_count")!=0):
        raise ValueError("BASELINE_BOUND_SOURCE_OR_FROZEN_MODEL_INVALID")
    source_at=utc(intake["generated_at_utc"])
    completed_at=utc(shadow["completed_at_utc"])
    attested_at=utc(attestation["observed_at_utc"])
    if not (source_at<=completed_at<=attested_at<=clock
            and 0<=(clock-source_at).total_seconds()<=86400):
        raise ValueError("BASELINE_CAPTURE_TIME_STALE_OR_INCONSISTENT")
    fixtures=keyed(intake.get("fixtures"),"source_fixture_id")
    scored=keyed(shadow.get("scored"),"source_fixture_id")
    attest=keyed(attestation.get("rows"),"source_fixture_id")
    raw_groups=shadow.get("authenticated_raw_group_replay_evidence") or {}
    group_meta=shadow.get("group_status") or {}
    if not isinstance(raw_groups,dict) or not isinstance(group_meta,dict):
        raise ValueError("BASELINE_GROUP_PROVENANCE_INVALID")
    output=[]
    decoded={}
    for fid,a in sorted(attest.items()):
        if a.get("status")!="PASS_PROSPECTIVE_RESEARCH_HISTORY_ONLY":
            continue
        f=fixtures.get(fid)
        s=scored.get(fid)
        row={"source_fixture_id":fid,"status":"BLOCKED",
             "home":a.get("home"),"away":a.get("away"),
             "baseline_verified_research_only":False,
             "original_provider_feature_equivalence_verified":False,
             "production_p_matrix_authorized":False,
             "telegram_signal_authorized":False}
        output.append(row)
        if f is None or s is None:
            row["status"]="BLOCKED_MISSING_BOUND_FIXTURE_SCORE";continue
        cid=str(f.get("source_competition_id") or "")
        if (cid!="2016" or f.get("source_competition_code")!="ELC"
            or s.get("kickoff_utc")!=f.get("kickoff_utc")
            or a.get("kickoff_utc")!=f.get("kickoff_utc")
            or s.get("signal_generation_authorized") is not False):
            row["status"]="BLOCKED_TARGET_CONTRACT";continue
        kickoff=utc(f["kickoff_utc"])
        if not (attested_at<kickoff and clock<kickoff):
            row["status"]="BLOCKED_NOT_PREMATCH";continue
        evidence=raw_groups.get(cid)
        meta=group_meta.get(cid)
        if not isinstance(evidence,dict) or not isinstance(meta,dict):
            row["status"]="BLOCKED_AUTHENTIC_HTTP_RESPONSE_NOT_PERSISTED";continue
        if cid not in decoded:
            try:
                b64=evidence.get("response_base64")
                if not isinstance(b64,str) or len(b64)>4_200_000:
                    raise ValueError("RAW_HTTP_TOO_LARGE")
                raw=base64.b64decode(b64,validate=True)
                if not raw or len(raw)>3_000_000:
                    raise ValueError("RAW_HTTP_INVALID_SIZE")
                sha=hashlib.sha256(raw).hexdigest()
                if (sha!=evidence.get("source_payload_sha256")
                    or sha!=meta.get("sha256")):
                    raise ValueError("RAW_HTTP_SHA_MISMATCH")
                observed=utc(evidence["observed_at_utc"])
                if (observed!=utc(meta["observed_at_utc"])
                    or not source_at<=observed<=completed_at
                    or observed>=kickoff):
                    raise ValueError("RAW_HTTP_CAPTURE_TIME_INVALID")
                if str(evidence.get("competition_id"))!=cid:
                    raise ValueError("RAW_HTTP_COMPETITION_MISMATCH")
                payload=json.loads(raw.decode("utf-8"))
                rows=historic_rows(payload,int(cid))
                if len(rows)!=meta.get("history_count"):
                    raise ValueError("RAW_HTTP_HISTORY_COUNT_MISMATCH")
                if any(x["kickoff_utc"]>=observed for x in rows):
                    raise ValueError("RAW_HTTP_FINISHED_AFTER_CAPTURE")
                decoded[cid]=(rows,sha,observed)
            except (ValueError,TypeError,KeyError,UnicodeDecodeError,binascii.Error,json.JSONDecodeError) as exc:
                decoded[cid]=("BLOCKED",type(exc).__name__,None)
        group=decoded[cid]
        if group[0]=="BLOCKED":
            row["status"]="BLOCKED_GROUP_HTTP_VERIFICATION_"+str(group[1])
            continue
        rows,sha,observed=group
        if (sha!=s.get("history_sha256")
            or observed!=utc(a["research_as_of_utc"])
            or sha!=a.get("research_source_history_sha256")):
            row["status"]="BLOCKED_PIT_SOURCE_BINDING_MISMATCH";continue
        features,reason=_inputs_for_target(rows,{
            "kickoff_utc":f["kickoff_utc"],
            "home_team_id":str(f["home_source_team_id"]),
            "away_team_id":str(f["away_source_team_id"]),
        })
        if features is None:
            row["status"]="BLOCKED_RAW_GROUP_FEATURES_"+str(reason);continue
        expected_baseline=float(features["baseline"]["over_2_5"])
        expected_poisson=float(features["poisson"]["over_2_5"])
        expected_pool=_pool_over25(expected_poisson,expected_baseline)
        counts=s.get("feature_counts") or {}
        if (not close(expected_baseline,s.get("baseline_over25_research_component"))
            or not close(expected_poisson,s.get("poisson_over25_research_component"))
            or not close(expected_pool,s.get("p_over25_research"))
            or not close(expected_pool,a.get("research_model_probability_over25"))
            or counts.get("prior_group_fixture_count")!=features["prior_group_fixture_count"]
            or counts.get("home_history_count")!=features["home_history_count"]
            or counts.get("away_history_count")!=features["away_history_count"]):
            row["status"]="BLOCKED_FROZEN_GROUP_FEATURE_OR_PROBABILITY_MISMATCH";continue
        row.update({
            "status":"PASS_AUTHENTIC_RAW_HTTP_BASELINE_AND_POISSON_REPLAY_ONLY",
            "baseline_verified_research_only":True,
            "baseline_over25_recomputed":round(expected_baseline,12),
            "poisson_over25_recomputed":round(expected_poisson,12),
            "research_probability_recomputed":round(expected_pool,10),
            "original_group_fixture_count":features["prior_group_fixture_count"],
            "source_response_sha256":sha,
            "source_observed_at_utc":observed.isoformat(),
        })
    return {"schema":"MATRIX_CHAMPIONSHIP_ORIGINAL_FROZEN_BASELINE_REPLAY_V1",
        "target_date_bogota":day,"verified_at_utc":clock.isoformat(),
        "verified_research_baseline_count":sum(x["baseline_verified_research_only"] for x in output),
        "evaluated_count":len(output),"rows":output,
        "source":"FOOTBALL_DATA_ORG_AUTHENTICATED_RAW_RESPONSE",
        "original_frozen_function_reused":True,
        "original_provider_feature_equivalence_verified":False,
        "calibrated_model_equivalence_verified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if any(part in a.out.parts for part in ("daily_prematch_reports","telegram","tennis_signals")):
        raise SystemExit("BASELINE_REPLAY_OUTPUT_NOT_AUTHORIZED_FOR_SIGNAL")
    folder=a.root/"evidence"/"football_world_inventory"/a.date
    get=lambda name:json.loads((folder/name).read_text(encoding="utf-8"))
    intake=get("MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json")
    shadow=get("MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json")
    sofa=get("MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json")
    flash=get("MATRIX_FLASH_FOOTBALL_CROSSCHECK.json")
    snapshots={
        "source_intake_sha256":source_digest(intake),
        "source_shadow_sha256":source_digest(shadow),
        "source_sofa_sha256":source_digest(sofa),
        "source_flash_sha256":source_digest(flash),
    }
    files=[
        folder/"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json",
        *sorted(folder.glob("MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_*.json")),
    ]
    matching=[]
    for path in files:
        if not path.is_file():
            continue
        try:
            candidate=json.loads(path.read_text(encoding="utf-8"))
            if (candidate.get("source_binding_schema")=="MATRIX_PROSPECTIVE_PIT_EXACT_FOUR_SOURCE_BINDING_V1"
                and candidate.get("target_date_bogota")==a.date
                and all(candidate.get(key)==sha for key,sha in snapshots.items())):
                matching.append((utc(candidate["observed_at_utc"]),path,candidate))
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
            continue
    if not matching:
        raise SystemExit("BASELINE_FAIL_CLOSED_NO_EXACT_FOUR_SOURCE_ATTESTATION")
    latest=max(matching,key=lambda x:(x[0],x[1].name))
    result=replay(intake,shadow,latest[2],sofa,flash,now=datetime.now(timezone.utc))
    result["exact_source_attestation_file"]=latest[1].name
    result["exact_source_attestation_sha256"]=source_digest(latest[2])
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("verified_research_baseline_count","evaluated_count",
        "calibrated_model_equivalence_verified","telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
