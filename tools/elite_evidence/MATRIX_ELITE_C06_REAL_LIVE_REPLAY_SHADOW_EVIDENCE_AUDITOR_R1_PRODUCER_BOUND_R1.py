from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA="MATRIX_ELITE_C06_REAL_LIVE_REPLAY_SHADOW_EVIDENCE_R1"
INPUT_SCHEMA="MATRIX_ELITE_C06_REAL_LIVE_REPLAY_SHADOW_INPUT_R1"
INPUT_CONTRACT_SHA256="91f1679e7e1308f2790298d6d0d21a5033b5c1ce915d02a99f9571d8bfb6c602"
PLAN_SCHEMA="MATRIX_ELITE_C06_LIVE_EVALUATION_PLAN_R1"
RUN_SCHEMA="MATRIX_ELITE_C06_LIVE_RUN_MANIFEST_R1"
TRACE_SCHEMA="MATRIX_ELITE_C06_LIVE_TIMING_TRACE_R1"
ORACLE_SCHEMA="MATRIX_ELITE_C06_LIVE_ORACLE_EVIDENCE_R1"
CLOCK_SCHEMA="MATRIX_ELITE_C06_CLOCK_SYNC_EVIDENCE_R1"
RAW_TRACE_MANIFEST_SCHEMA="MATRIX_ELITE_C06_RAW_TRACE_MANIFEST_R1"
ANCHOR_SCHEMA="MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1"
ALLOWED_ANCHORS={"RFC3161_TSA","WORM_OBJECT_VERSION","EXTERNAL_AUDIT_LEDGER","SIGNED_TRANSPARENCY_LOG"}
LIVE_STATES={"DISCARD","WATCH","PRE_SIGNAL","ENTRY","WINDOW_CLOSED"}
STAGE_NAMES=(
    "event_to_provider_ms","provider_to_ingest_ms","ingest_to_normalize_ms",
    "normalize_to_feature_ms","feature_to_inference_ms","inference_to_market_ms",
    "market_to_signal_ms","signal_to_visible_ms",
)

def dt(v:str)->datetime:
    x=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if x.tzinfo is None or x.utcoffset() is None: raise ValueError("TIME_MUST_BE_TIMEZONE_AWARE")
    return x

def readj(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8-sig"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return x

def fsha(p:Path)->str:return sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->str:return sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def valid_sha(v:Any)->bool:
    try:return isinstance(v,str) and len(v)==64 and int(v,16)>=0
    except Exception:return False

def pct(values:list[float],q:float)->float:
    if not values: raise ValueError("EMPTY_METRIC_SERIES")
    s=sorted(values);p=(len(s)-1)*q;lo=int(p);hi=min(lo+1,len(s)-1);f=p-lo
    return s[lo]*(1-f)+s[hi]*f

def record_sha(r:dict[str,Any])->str:
    return canon({"sequence":r["sequence"],"previous_record_sha256":r.get("previous_record_sha256"),"recorded_at":r["recorded_at"],"payload":r["payload"]})

def verify_chain(records:list[dict[str,Any]],errors:list[str])->dict[int,str]:
    out={};prev=None
    for i,r in enumerate(records,1):
        try:
            if int(r["sequence"])!=i:raise ValueError("SHADOW_SEQUENCE_GAP_OR_REORDER")
            if r.get("previous_record_sha256")!=prev:raise ValueError("SHADOW_CHAIN_MISMATCH")
            h=record_sha(r)
            if r.get("record_sha256")!=h:raise ValueError("SHADOW_RECORD_HASH_MISMATCH")
            out[i]=h;prev=h
        except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))
    return out

def verify_anchor(anchor:dict[str,Any],errors:list[str])->bool:
    try:
        if anchor.get("anchor_type") not in ALLOWED_ANCHORS:raise ValueError("UNTRUSTED_TIMESTAMP_ANCHOR_TYPE")
        if anchor.get("verification_result")!="PASS":raise ValueError("TIMESTAMP_ANCHOR_NOT_VERIFIED")
        ep=Path(anchor["anchor_evidence_path"]).resolve()
        if not ep.is_file():raise ValueError("TIMESTAMP_ANCHOR_EVIDENCE_MISSING")
        if fsha(ep)!=anchor.get("anchor_evidence_sha256"):raise ValueError("TIMESTAMP_ANCHOR_EVIDENCE_SHA_MISMATCH")
        proof=readj(ep)
        if proof.get("schema")!=ANCHOR_SCHEMA or proof.get("result")!="PASS":raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_INVALID")
        if proof.get("anchor_type")!=anchor.get("anchor_type") or proof.get("root_sha256")!=anchor.get("root_sha256"):raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_BINDING_MISMATCH")
        if dt(proof["anchored_at"])!=dt(anchor["anchored_at"]):raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_TIME_MISMATCH")
        if not str(proof.get("verifier","")).strip():raise ValueError("TIMESTAMP_ANCHOR_VERIFIER_REQUIRED")
        return True
    except (KeyError,TypeError,ValueError) as exc:
        errors.append(str(exc));return False

def root_anchor_before(*,sequence:int,cutoff:datetime,recorded_at:datetime,anchors:list[dict[str,Any]],seq_sha:dict[int,str],errors:list[str])->bool:
    for a in anchors:
        try:
            through=int(a["through_sequence"])
            if through<sequence or seq_sha.get(through)!=a.get("root_sha256"):continue
            at=dt(a["anchored_at"])
            if at<recorded_at or at>=cutoff:continue
            local=[]
            if verify_anchor(a,local):return True
        except Exception:continue
    errors.append("SHADOW_SIGNAL_INDEPENDENT_PRE_WINDOW_TIMESTAMP_NOT_PROVEN")
    return False

def verify_exact_file(path_value:Any,sha_value:Any,missing_code:str,sha_code:str)->tuple[Path|None,dict[str,Any]|None,str|None]:
    try:
        p=Path(path_value).resolve()
        if not p.is_file():return None,None,missing_code
        h=fsha(p)
        if h!=sha_value:return p,None,sha_code
        return p,readj(p),None
    except Exception:
        return None,None,missing_code

def trace_metrics(trace:dict[str,Any],mode:str,plan:dict[str,Any],errors:list[str])->dict[str,float]|None:
    try:
        if trace.get("schema")!=TRACE_SCHEMA or trace.get("mode")!=mode:raise ValueError("TRACE_SCHEMA_OR_MODE_MISMATCH")
        if mode=="REPLAY":
            if trace.get("timing_claim")!="REPLAY_RECONSTRUCTED_NOT_RUNTIME_SLO":raise ValueError("REPLAY_TIMING_CLAIM_INVALID")
        else:
            if trace.get("timing_claim")!="SHADOW_LIVE_OBSERVED_RUNTIME_SLO_ELIGIBLE":raise ValueError("SHADOW_TIMING_CLAIM_INVALID")
        names=("source_event_at","provider_observed_at","ingest_received_at","normalize_completed_at","feature_completed_at","inference_completed_at","market_snapshot_at","signal_created_at","signal_visible_at","entry_window_closed_at")
        ts={n:dt(trace[n]) for n in names}
        ordered=[ts[n] for n in names[:-1]]
        if any(b<a for a,b in zip(ordered,ordered[1:])):raise ValueError("LIVE_TRACE_TIMESTAMP_ORDER_INVALID")
        if mode=="SHADOW_LIVE":
            cp,c,err=verify_exact_file(trace.get("clock_sync_evidence_path"),trace.get("clock_sync_evidence_sha256"),"CLOCK_SYNC_EVIDENCE_MISSING","CLOCK_SYNC_EVIDENCE_SHA_MISMATCH")
            if err:raise ValueError(err)
            if c.get("schema")!=CLOCK_SCHEMA or c.get("result")!="PASS":raise ValueError("CLOCK_SYNC_EVIDENCE_NOT_PASS")
            if float(c["max_abs_offset_ms"])>float(plan["maximum_clock_offset_ms"]):raise ValueError("CLOCK_OFFSET_SLO_BREACH")
            if float(c["max_jitter_ms"])>float(plan["maximum_clock_jitter_ms"]):raise ValueError("CLOCK_JITTER_SLO_BREACH")
            if abs((dt(c["measured_at"])-ts["ingest_received_at"]).total_seconds())>float(plan["maximum_clock_evidence_age_seconds"]):raise ValueError("CLOCK_SYNC_EVIDENCE_STALE")
        stage_pairs=(
            ("source_event_at","provider_observed_at"),("provider_observed_at","ingest_received_at"),
            ("ingest_received_at","normalize_completed_at"),("normalize_completed_at","feature_completed_at"),
            ("feature_completed_at","inference_completed_at"),("inference_completed_at","market_snapshot_at"),
            ("market_snapshot_at","signal_created_at"),("signal_created_at","signal_visible_at"),
        )
        vals=[(ts[b]-ts[a]).total_seconds()*1000 for a,b in stage_pairs]
        if any(v<0 for v in vals):raise ValueError("NEGATIVE_STAGE_LATENCY")
        e2e=sum(vals)
        window_at_ingest=(ts["entry_window_closed_at"]-ts["ingest_received_at"]).total_seconds()*1000
        window_at_visible=(ts["entry_window_closed_at"]-ts["signal_visible_at"]).total_seconds()*1000
        return {**dict(zip(STAGE_NAMES,vals)),"end_to_end_ms":e2e,"window_at_ingest_ms":window_at_ingest,"window_at_visible_ms":window_at_visible}
    except (KeyError,TypeError,ValueError) as exc:
        errors.append(str(exc));return None

def report(samples:list[dict[str,Any]],plan:dict[str,Any],mode:str,errors:list[str])->dict[str,Any]:
    if not samples:return {}
    e2e=[s["timing"]["end_to_end_ms"] for s in samples]
    stage_p95={n:pct([s["timing"][n] for s in samples],.95) for n in STAGE_NAMES}
    stage_p99={n:pct([s["timing"][n] for s in samples],.99) for n in STAGE_NAMES}
    closed=sum(s["timing"]["window_at_ingest_ms"]<=0 for s in samples)
    processing=sum(s["timing"]["window_at_ingest_ms"]>0 and s["timing"]["window_at_visible_ms"]<=0 for s in samples)
    late=sum(s["timing"]["window_at_visible_ms"]<=0 for s in samples)
    stale=sum(s["timing"]["end_to_end_ms"]>float(plan["stale_threshold_ms"]) for s in samples)
    pred=[s["predicted_state"]=="ENTRY" for s in samples];oracle=[bool(s["oracle"]) for s in samples]
    fp=sum(p and not y for p,y in zip(pred,oracle));fn=sum((not p) and y for p,y in zip(pred,oracle))
    predicted=sum(pred);actual=sum(oracle)
    return {
      "mode":mode,"n":len(samples),"p50_ms":pct(e2e,.50),"p95_ms":pct(e2e,.95),"p99_ms":pct(e2e,.99),
      "stage_p95_ms":stage_p95,"stage_p99_ms":stage_p99,
      "window_closed_on_arrival_rate":closed/len(samples),"processing_missed_window_rate":processing/len(samples),
      "missed_window_rate":late/len(samples),"stale_signal_rate":stale/len(samples),"decision_too_late_rate":late/len(samples),
      "false_positive_count":fp,"false_negative_count":fn,
      "false_positive_rate":fp/predicted if predicted else 0.0,
      "false_negative_rate":fn/actual if actual else 0.0,
      "runtime_latency_claimable":mode=="SHADOW_LIVE",
    }

def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True);ns=ap.parse_args()
    ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);errors=[]
    if data.get("schema")!=INPUT_SCHEMA:errors.append("INPUT_SCHEMA_MISMATCH")

    pp,plan,e=verify_exact_file(data.get("live_evaluation_plan_path"),data.get("live_evaluation_plan_sha256"),"LIVE_PLAN_MISSING","LIVE_PLAN_SHA_MISMATCH")
    if e:errors.append(e);plan={}
    elif plan.get("schema")!=PLAN_SCHEMA:errors.append("LIVE_PLAN_SCHEMA_MISMATCH")

    try:
        registered=dt(plan["registered_at"]);start=dt(plan["sample_start_at"]);end=dt(plan["sample_end_at"])
        if registered>=start:errors.append("LIVE_PLAN_NOT_REGISTERED_BEFORE_SAMPLE")
        if end<=start:errors.append("LIVE_SAMPLE_WINDOW_INVALID")
        if plan.get("sport") not in {"football","tennis"} or not str(plan.get("market","")).strip():errors.append("LIVE_PLAN_SCOPE_INVALID")
        jp,j,e=verify_exact_file(plan.get("sample_size_justification_path"),plan.get("sample_size_justification_sha256"),"LIVE_SAMPLE_SIZE_JUSTIFICATION_MISSING","LIVE_SAMPLE_SIZE_JUSTIFICATION_SHA_MISMATCH")
        if e:errors.append(e);j={}
        elif j.get("schema")!="MATRIX_ELITE_C06_SAMPLE_SIZE_JUSTIFICATION_R1" or j.get("result")!="PASS":errors.append("LIVE_SAMPLE_SIZE_JUSTIFICATION_NOT_PASS")
        min_replay=int(plan["minimum_replay_samples"]);min_shadow=int(plan["minimum_shadow_samples"])
        if min_replay<20 or min_shadow<20:errors.append("LIVE_SAMPLE_MINIMUMS_TOO_WEAK")
        if min_replay<int(j.get("recommended_minimum_replay_samples",10**9)):errors.append("REPLAY_SAMPLE_BELOW_JUSTIFIED_MINIMUM")
        if min_shadow<int(j.get("recommended_minimum_shadow_samples",10**9)):errors.append("SHADOW_SAMPLE_BELOW_JUSTIFIED_MINIMUM")
        if float(plan["minimum_shadow_duration_hours"])<float(j.get("recommended_minimum_shadow_duration_hours",10**9)):errors.append("SHADOW_DURATION_BELOW_JUSTIFIED_MINIMUM")
        for k in ("maximum_missed_window_rate","maximum_stale_signal_rate","maximum_decision_too_late_rate","maximum_false_positive_rate","maximum_false_negative_rate"):
            if not 0<=float(plan[k])<=1:errors.append("LIVE_RATE_POLICY_INVALID")
        if float(plan["maximum_shadow_p99_ms"])<float(plan["maximum_shadow_p95_ms"]):errors.append("LIVE_LATENCY_POLICY_INVALID")
        if plan.get("sampling_policy")!="ALL_ELIGIBLE_SIGNAL_EVALUATIONS":errors.append("LIVE_SAMPLING_POLICY_MUST_CAPTURE_ALL_ELIGIBLE")
        # Plan exact-file SHA is independently anchored before sample start.
        anchor=data.get("plan_registration_anchor")
        if not isinstance(anchor,dict):errors.append("LIVE_PLAN_INDEPENDENT_ANCHOR_REQUIRED")
        else:
            verify_anchor(anchor,errors)
            if anchor.get("root_sha256")!=fsha(pp):errors.append("LIVE_PLAN_ANCHOR_ROOT_MISMATCH")
            if dt(anchor["anchored_at"])>=start:errors.append("LIVE_PLAN_NOT_INDEPENDENTLY_ANCHORED_BEFORE_SAMPLE")
    except (KeyError,TypeError,ValueError) as exc:
        errors.append(str(exc));start=end=None;min_replay=min_shadow=10**9

    # Exact run manifests; neither may submit orders.
    run_manifests={}
    for mode,key in (("REPLAY","replay_run_manifest"),("SHADOW_LIVE","shadow_run_manifest")):
        p,j,e=verify_exact_file(data.get(key+"_path"),data.get(key+"_sha256"),"LIVE_RUN_MANIFEST_MISSING","LIVE_RUN_MANIFEST_SHA_MISMATCH")
        if e:errors.append(mode+"_"+e);continue
        if j.get("schema")!=RUN_SCHEMA or j.get("mode")!=mode:errors.append(mode+"_RUN_MANIFEST_SCHEMA_OR_MODE_MISMATCH")
        if (j.get("sport"),j.get("market"),j.get("model_version"),j.get("feature_version"))!=(plan.get("sport"),plan.get("market"),plan.get("model_version"),plan.get("feature_version")):errors.append(mode+"_RUN_SCOPE_MISMATCH")
        if int(j.get("orders_submitted",-1))!=0 or int(j.get("wagers_executed",-1))!=0:errors.append(mode+"_WAGERING_ACTIVITY_FORBIDDEN")
        if int(j.get("dropped_evaluations",-1))!=0 or int(j.get("sequence_gaps",-1))!=0:errors.append(mode+"_RUN_GAPS_OR_DROPS_PRESENT")
        if int(j.get("eligible_evaluations",-1))!=int(j.get("observed_samples",-2)):errors.append(mode+"_RUN_NOT_ALL_ELIGIBLE_CAPTURED")
        try:
            rs=dt(j["started_at"]);re=dt(j["ended_at"])
            if re<=rs:errors.append(mode+"_RUN_WINDOW_INVALID")
            if start is not None and (rs<start or re>end):errors.append(mode+"_RUN_OUTSIDE_REGISTERED_SAMPLE")
        except Exception:errors.append(mode+"_RUN_TIME_INVALID")
        rmp,rm,e2=verify_exact_file(j.get("raw_trace_manifest_path"),j.get("raw_trace_manifest_sha256"),"RAW_TRACE_MANIFEST_MISSING","RAW_TRACE_MANIFEST_SHA_MISMATCH")
        if e2:errors.append(mode+"_"+e2)
        elif rm.get("schema")!=RAW_TRACE_MANIFEST_SCHEMA or rm.get("mode")!=mode:errors.append(mode+"_RAW_TRACE_MANIFEST_SCHEMA_OR_MODE_MISMATCH")
        else:
            ids=[str(x) for x in (rm.get("sample_ids") or [])]
            if len(ids)!=len(set(ids)) or len(ids)!=int(j.get("observed_samples",-1)):errors.append(mode+"_RAW_TRACE_MANIFEST_SAMPLE_COUNT_MISMATCH")
            j["_raw_trace_sample_ids"]=ids
        run_manifests[mode]=j

    replay_raw=list(data.get("replay_samples") or [])
    shadow_records=list(data.get("shadow_signal_records") or [])
    shadow_anchors=list(data.get("shadow_timestamp_anchors") or [])
    seq_sha=verify_chain(shadow_records,errors)
    for a in shadow_anchors:verify_anchor(a,errors)

    processed={"REPLAY":[],"SHADOW_LIVE":[]}
    seen=set()

    # Replay is functional evidence only; reconstructed timing can never satisfy runtime latency.
    for sample in replay_raw:
        try:
            sid=str(sample["sample_id"])
            if sid in seen:raise ValueError("DUPLICATE_LIVE_SAMPLE_ID")
            seen.add(sid)
            if sample.get("mode")!="REPLAY":raise ValueError("REPLAY_SAMPLE_MODE_INVALID")
            if (sample.get("sport"),sample.get("market"),sample.get("model_version"),sample.get("feature_version"))!=(plan.get("sport"),plan.get("market"),plan.get("model_version"),plan.get("feature_version")):raise ValueError("REPLAY_SAMPLE_SCOPE_MISMATCH")
            tp,tr,e=verify_exact_file(sample.get("trace_evidence_path"),sample.get("trace_evidence_sha256"),"TRACE_EVIDENCE_MISSING","TRACE_EVIDENCE_SHA_MISMATCH")
            if e:raise ValueError(e)
            if tr.get("sample_id")!=sid:raise ValueError("TRACE_SAMPLE_BINDING_MISMATCH")
            timing=trace_metrics(tr,"REPLAY",plan,errors)
            if "REPLAY" in run_manifests:
                rs=dt(run_manifests["REPLAY"]["started_at"]);re=dt(run_manifests["REPLAY"]["ended_at"])
                if dt(tr["source_event_at"])<rs or dt(tr["signal_visible_at"])>re:raise ValueError("REPLAY_TRACE_OUTSIDE_RUN_WINDOW")
            oracle_path,oracle,e=verify_exact_file(sample.get("oracle_evidence_path"),sample.get("oracle_evidence_sha256"),"ORACLE_EVIDENCE_MISSING","ORACLE_EVIDENCE_SHA_MISMATCH")
            if e:raise ValueError(e)
            if oracle.get("schema")!=ORACLE_SCHEMA or oracle.get("sample_id")!=sid:raise ValueError("ORACLE_SCHEMA_OR_SAMPLE_MISMATCH")
            if dt(oracle["oracle_generated_at"])<=dt(tr["entry_window_closed_at"]):raise ValueError("ORACLE_GENERATED_BEFORE_WINDOW_CLOSE")
            state=str(sample["predicted_state"])
            if state not in LIVE_STATES:raise ValueError("LIVE_STATE_INVALID")
            if bool(sample.get("order_submitted")) or float(sample.get("stake_units",0))!=0:raise ValueError("REPLAY_WAGERING_ACTIVITY_FORBIDDEN")
            if timing:processed["REPLAY"].append({"sample_id":sid,"timing":timing,"predicted_state":state,"oracle":bool(oracle["oracle_entry_eligible"])})
        except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

    # Shadow records are immutable and independently anchored before their entry window closes.
    for rec in shadow_records:
        try:
            p=rec["payload"];sid=str(p["sample_id"])
            if sid in seen:raise ValueError("DUPLICATE_LIVE_SAMPLE_ID")
            seen.add(sid)
            if p.get("mode")!="SHADOW_LIVE":raise ValueError("SHADOW_SAMPLE_MODE_INVALID")
            if (p.get("sport"),p.get("market"),p.get("model_version"),p.get("feature_version"))!=(plan.get("sport"),plan.get("market"),plan.get("model_version"),plan.get("feature_version")):raise ValueError("SHADOW_SAMPLE_SCOPE_MISMATCH")
            tp,tr,e=verify_exact_file(p.get("trace_evidence_path"),p.get("trace_evidence_sha256"),"TRACE_EVIDENCE_MISSING","TRACE_EVIDENCE_SHA_MISMATCH")
            if e:raise ValueError(e)
            if tr.get("sample_id")!=sid:raise ValueError("TRACE_SAMPLE_BINDING_MISMATCH")
            timing=trace_metrics(tr,"SHADOW_LIVE",plan,errors)
            if "SHADOW_LIVE" in run_manifests:
                rs=dt(run_manifests["SHADOW_LIVE"]["started_at"]);re=dt(run_manifests["SHADOW_LIVE"]["ended_at"])
                if dt(tr["source_event_at"])<rs or dt(tr["signal_visible_at"])>re:raise ValueError("SHADOW_TRACE_OUTSIDE_RUN_WINDOW")
            visible=dt(tr["signal_visible_at"]);close=dt(tr["entry_window_closed_at"])
            if dt(rec["recorded_at"])<visible:raise ValueError("SHADOW_RECORD_PRECEDES_SIGNAL_VISIBILITY")
            root_anchor_before(sequence=int(rec["sequence"]),cutoff=close,recorded_at=dt(rec["recorded_at"]),anchors=shadow_anchors,seq_sha=seq_sha,errors=errors)
            oracle_path,oracle,e=verify_exact_file(p.get("oracle_evidence_path"),p.get("oracle_evidence_sha256"),"ORACLE_EVIDENCE_MISSING","ORACLE_EVIDENCE_SHA_MISMATCH")
            if e:raise ValueError(e)
            if oracle.get("schema")!=ORACLE_SCHEMA or oracle.get("sample_id")!=sid:raise ValueError("ORACLE_SCHEMA_OR_SAMPLE_MISMATCH")
            if dt(oracle["oracle_generated_at"])<=close:raise ValueError("ORACLE_GENERATED_BEFORE_WINDOW_CLOSE")
            state=str(p["predicted_state"])
            if state not in LIVE_STATES:raise ValueError("LIVE_STATE_INVALID")
            if bool(p.get("order_submitted")) or float(p.get("stake_units",0))!=0:raise ValueError("SHADOW_WAGERING_ACTIVITY_FORBIDDEN")
            if timing:processed["SHADOW_LIVE"].append({"sample_id":sid,"timing":timing,"predicted_state":state,"oracle":bool(oracle["oracle_entry_eligible"])})
        except (KeyError,TypeError,ValueError) as exc:errors.append(str(exc))

    # Manifest counts must match exact supplied records.
    if "REPLAY" in run_manifests and int(run_manifests["REPLAY"].get("observed_samples",-1))!=len(replay_raw):errors.append("REPLAY_MANIFEST_SAMPLE_COUNT_MISMATCH")
    if "SHADOW_LIVE" in run_manifests and int(run_manifests["SHADOW_LIVE"].get("observed_samples",-1))!=len(shadow_records):errors.append("SHADOW_MANIFEST_SAMPLE_COUNT_MISMATCH")
    if "REPLAY" in run_manifests:
        supplied=sorted(str(x.get("sample_id")) for x in replay_raw)
        if supplied!=sorted(run_manifests["REPLAY"].get("_raw_trace_sample_ids",[])):errors.append("REPLAY_RAW_TRACE_SAMPLE_SET_MISMATCH")
    if "SHADOW_LIVE" in run_manifests:
        supplied=sorted(str(x.get("payload",{}).get("sample_id")) for x in shadow_records)
        if supplied!=sorted(run_manifests["SHADOW_LIVE"].get("_raw_trace_sample_ids",[])):errors.append("SHADOW_RAW_TRACE_SAMPLE_SET_MISMATCH")

    replay_report=report(processed["REPLAY"],plan,"REPLAY",errors) if processed["REPLAY"] else {}
    shadow_report=report(processed["SHADOW_LIVE"],plan,"SHADOW_LIVE",errors) if processed["SHADOW_LIVE"] else {}

    if len(processed["REPLAY"])<min_replay:errors.append("MINIMUM_REPLAY_SAMPLES_FAILED")
    if len(processed["SHADOW_LIVE"])<min_shadow:errors.append("MINIMUM_SHADOW_SAMPLES_FAILED")

    # Replay gates only functional classification/window behavior, never runtime latency SLO.
    if replay_report:
        if replay_report["false_positive_rate"]>float(plan["maximum_false_positive_rate"]):errors.append("REPLAY_FALSE_POSITIVE_RATE_BREACH")
        if replay_report["false_negative_rate"]>float(plan["maximum_false_negative_rate"]):errors.append("REPLAY_FALSE_NEGATIVE_RATE_BREACH")
    # Shadow gates real observed runtime SLO + decision quality.
    if shadow_report:
        if shadow_report["p95_ms"]>float(plan["maximum_shadow_p95_ms"]):errors.append("SHADOW_P95_LATENCY_BREACH")
        if shadow_report["p99_ms"]>float(plan["maximum_shadow_p99_ms"]):errors.append("SHADOW_P99_LATENCY_BREACH")
        stage_limits=plan.get("maximum_stage_p95_ms") or {}
        for stage in STAGE_NAMES:
            if stage not in stage_limits:errors.append("STAGE_P95_POLICY_MISSING");break
            if shadow_report["stage_p95_ms"][stage]>float(stage_limits[stage]):errors.append("SHADOW_STAGE_P95_BREACH_"+stage.upper())
        for field,code in (
            ("missed_window_rate","SHADOW_MISSED_WINDOW_RATE_BREACH"),
            ("stale_signal_rate","SHADOW_STALE_SIGNAL_RATE_BREACH"),
            ("decision_too_late_rate","SHADOW_DECISION_TOO_LATE_RATE_BREACH"),
            ("false_positive_rate","SHADOW_FALSE_POSITIVE_RATE_BREACH"),
            ("false_negative_rate","SHADOW_FALSE_NEGATIVE_RATE_BREACH"),
        ):
            max_field="maximum_"+field
            if shadow_report[field]>float(plan[max_field]):errors.append(code)

    # Shadow duration is real run-manifest duration, not reconstructed sample range.
    if "SHADOW_LIVE" in run_manifests:
        dur=(dt(run_manifests["SHADOW_LIVE"]["ended_at"])-dt(run_manifests["SHADOW_LIVE"]["started_at"])).total_seconds()/3600
        if dur<float(plan["minimum_shadow_duration_hours"]):errors.append("MINIMUM_SHADOW_DURATION_FAILED")

    passed=not errors
    out={
      "schema":SCHEMA,"result":"PASS" if passed else "FAIL_CLOSED","running_auditor_path":str(Path(__file__).resolve()),"running_auditor_sha256":sha256(Path(__file__).resolve().read_bytes()).hexdigest(),'input_contract_sha256':INPUT_CONTRACT_SHA256,
      "input_path":str(ip),"input_sha256":fsha(ip),
      "sport":plan.get("sport"),"market":plan.get("market"),
      "replay_report":replay_report,"shadow_live_report":shadow_report,
      "blocking_codes":sorted(set(errors)),
      "replay_functional_evidence_passed":passed,
      "shadow_live_runtime_slo_evidence_passed":passed,
      "replay_runtime_latency_claimable":False,
      "shadow_runtime_latency_claimable":bool(passed),
      "c06_live_evidence_passed":passed,
      "orders_submitted":0,"wagers_executed":0,
      "automatic_wagering_authorized":False,
      "controlled_live_admissible":False,"production_admissible":False,
      "output_payload_sha256":None,
    }
    h=dict(out);h["output_payload_sha256"]=None;out["output_payload_sha256"]=canon(h)
    op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("RESULT="+("PASS" if passed else "FAIL_CLOSED"))
    print("C06_REAL_REPLAY_SHADOW_EVIDENCE="+("PASS" if passed else "FAIL"))
    print("REPLAY_RUNTIME_LATENCY_CLAIMABLE=FALSE")
    print("SHADOW_RUNTIME_LATENCY_CLAIMABLE="+str(bool(passed)).upper())
    print("ORDERS_SUBMITTED=0");print("WAGERS_EXECUTED=0")
    print("BLOCKING_CODES="+(",".join(sorted(set(errors))) if errors else "<NONE>"))
    print("CONTROLLED_LIVE_ADMISSIBLE=FALSE");print("PRODUCTION_ADMISSIBLE=FALSE")
    print("EVIDENCE="+str(op));print("EVIDENCE_SHA256="+fsha(op))
    return 0 if passed else 2

if __name__=="__main__":raise SystemExit(main())
