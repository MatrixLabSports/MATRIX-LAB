from __future__ import annotations
import argparse,json,subprocess,sys,tempfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any,Callable

SCHEMA="MATRIX_ELITE_SCOPE_SELECTION_EVIDENCE_R2"
INPUT_SCHEMA="MATRIX_ELITE_SCOPE_SELECTION_AUDIT_INPUT_R2"
INVENTORY_SCHEMA="MATRIX_ELITE_SCOPE_CANDIDATE_INVENTORY_R2"
INPUT_CONTRACT_SHA256="03aba764a943225f39d8c25fb074afd0c239ad5d933b2bc409a99125975b424c"
EXPECTED_RUBRIC_SHA256="88cb406880575c943ffee466ed774e109de55a39d58e353af3a1c098eaa51d27"
EXPECTED_PACK_AUDITOR_SHA256="3095f957f80383f47778ad7b433f0cd0267112a7baff39c432beea81c86a17ab"
EXPECTED_PACK_CONTRACT_SHA256="dc4b94a9bfa72bcc37d360778fa7669afc359a6168a959d0e6ceec53d6a0d153"
EXPECTED_PACK_STATIC_SHA256="2c7cb66a71155d616e67e0f801addb90878883f1bb5f21301ec6997695abb908"
INCLUDE_REASON='ELIGIBLE_SUPPORTABILITY_PACK_PASS'
EXCLUDE_REASONS={'DATA_CONTRACT_NOT_READY', 'RISK_CLASS_NOT_DEFINED', 'ODDS_HISTORY_OR_BINDING_NOT_SUPPORTABLE', 'LIVE_LATENCY_BUDGET_NOT_DEFINED', 'EVALUATION_PROTOCOL_NOT_DEFINED', 'BASELINE_NOT_DEFINED', 'SAMPLE_REQUIREMENT_POLICY_NOT_DEFINED', 'SETTLEMENT_RULES_NOT_CANONICAL', 'MARKET_SEMANTICS_NOT_CANONICAL', 'RIGHTS_NOT_ADMISSIBLE', 'OUT_OF_PROJECT_SPORT_BOUNDARY', 'DEFERRED_BY_CAPACITY_WITHOUT_PERFORMANCE_INFORMATION', 'FAILOVER_RIGHTS_OR_SCHEMA_NOT_SUPPORTABLE', 'LIVE_OBSERVABILITY_NOT_SUPPORTABLE', 'IDENTITY_CONTRACT_NOT_READY', 'PIT_AVAILABILITY_NOT_SUPPORTABLE', 'FAILOVER_SECONDARY_NOT_SUPPORTABLE'}
FORBIDDEN_KEYS={"roi","pnl","profit","profitability","win_rate","hit_rate","clv","brier","logloss","ece","calibration_error","model_edge","realized_ev","campaign_result","campaign_results","wins","losses","net_return"}
FORBIDDEN_TOKENS=("roi","win rate","hit rate","clv","brier","logloss","profit","profitable","losing","winning","recent results","campaign performance","realized ev")
PRED_FIELDS=("scope_id","sport","competition","market","model_version","feature_version","market_semantics_version","settlement_rules_version","data_contract_version","identity_contract_version","rights_profile_version","odds_contract_version","evaluation_protocol_version","sample_requirement_policy_version","risk_class")
LIVE_FIELDS=("live_scope_id","sport","market","model_version","feature_version","event_time_contract_version","live_window_policy_version","staleness_policy_version","replay_protocol_version","shadow_live_protocol_version")
FAIL_FIELDS=("failover_scope_id","primary_provider","secondary_provider","environment","schema_compatibility_contract_version","identity_reconciliation_contract_version","primary_rights_profile_version","secondary_rights_profile_version","human_approval_policy_version","rollback_plan_version")

def readj(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding="utf-8-sig"))
 if not isinstance(x,dict):raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
 return x
def fsha(p:Path)->str:return sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->str:return sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def aware(v:Any)->datetime:
 x=datetime.fromisoformat(str(v).replace("Z","+00:00"))
 if x.tzinfo is None or x.utcoffset() is None:raise ValueError("CREATED_AT_MUST_BE_TIMEZONE_AWARE")
 return x
def nonempty(v:Any,code:str)->str:
 s=str(v or "").strip()
 if not s:raise ValueError(code)
 if "<" in s or ">" in s:raise ValueError("PLACEHOLDER_TEXT_DETECTED")
 return s
def payload_ok(j:dict[str,Any])->bool:
 if "output_payload_sha256" not in j:return False
 h=dict(j);x=h.get("output_payload_sha256");h["output_payload_sha256"]=None
 return canon(h)==x
def scan(x:Any,path:str,errors:list[str]):
 if isinstance(x,dict):
  for k,v in x.items():
   kk=str(k).strip().lower()
   if kk in FORBIDDEN_KEYS:errors.append("FORBIDDEN_PERFORMANCE_KEY:"+path+"/"+kk)
   scan(v,path+"/"+kk,errors)
 elif isinstance(x,list):
  for i,v in enumerate(x):scan(v,path+"/"+str(i),errors)
def perf_text(v:Any)->bool:
 s=" ".join(str(v or "").lower().split());return any(tok in s for tok in FORBIDDEN_TOKENS)
def exact(path_value:Any,sha_value:Any,missing:str,mismatch:str,errors:list[str]):
 try:
  p=Path(path_value).resolve()
  if not p.is_file():errors.append(missing);return None,None
  if fsha(p)!=sha_value:errors.append(mismatch);return p,None
  return p,readj(p)
 except Exception:errors.append(missing);return None,None
def default_runner(auditor:Path,input_path:Path):
 with tempfile.TemporaryDirectory(prefix="matrix_selection_r2_") as td:
  op=Path(td)/"out.json"
  try:p=subprocess.run([sys.executable,str(auditor),"--input",str(input_path),"--output",str(op)],capture_output=True,text=True,timeout=300,check=False)
  except subprocess.TimeoutExpired:return -1,None,"","TIMEOUT"
  try:j=readj(op) if op.is_file() else None
  except Exception:j=None
  return int(p.returncode),j,p.stdout,p.stderr

def evaluate(data:dict[str,Any],*,input_path:Path,pack_runner:Callable=default_runner)->dict[str,Any]:
 errors=[];reruns={};cache={}
 if data.get("schema")!=INPUT_SCHEMA:errors.append("INPUT_SCHEMA_MISMATCH")
 rub=Path(data.get("eligibility_rubric_path","")).resolve()
 if not rub.is_file() or fsha(rub)!=EXPECTED_RUBRIC_SHA256:errors.append("ELIGIBILITY_RUBRIC_NOT_CANONICAL")
 pa=Path(data.get("supportability_pack_auditor_path","")).resolve()
 pc=Path(data.get("supportability_pack_contract_path","")).resolve()
 ps=Path(data.get("supportability_pack_static_audit_path","")).resolve()
 if not pa.is_file() or fsha(pa)!=EXPECTED_PACK_AUDITOR_SHA256:errors.append("PACK_AUDITOR_NOT_CANONICAL")
 if not pc.is_file() or fsha(pc)!=EXPECTED_PACK_CONTRACT_SHA256:errors.append("PACK_CONTRACT_NOT_CANONICAL")
 if not ps.is_file() or fsha(ps)!=EXPECTED_PACK_STATIC_SHA256:errors.append("PACK_STATIC_AUDIT_NOT_CANONICAL")
 invp=Path(data.get("candidate_inventory_path","")).resolve();inv={}
 if not invp.is_file():errors.append("CANDIDATE_INVENTORY_MISSING")
 elif fsha(invp)!=data.get("candidate_inventory_sha256"):errors.append("CANDIDATE_INVENTORY_SHA_MISMATCH")
 else:
  try:inv=readj(invp)
  except Exception:errors.append("CANDIDATE_INVENTORY_INVALID")
 if inv:
  if inv.get("schema")!=INVENTORY_SCHEMA:errors.append("CANDIDATE_INVENTORY_SCHEMA_MISMATCH")
  if inv.get("status") in (None,"TEMPLATE_NOT_VALID_PREREGISTRATION"):errors.append("CANDIDATE_INVENTORY_NOT_FINAL")
  if inv.get("support_declared_by_this_inventory") is not False:errors.append("INVENTORY_MUST_NOT_DECLARE_SUPPORT")
  if inv.get("performance_results_available_to_selector") is not False:errors.append("PERFORMANCE_RESULTS_MUST_NOT_BE_AVAILABLE_TO_SELECTOR")
  if inv.get("performance_results_used_for_selection") is not False:errors.append("PERFORMANCE_RESULTS_MUST_NOT_BE_USED_FOR_SELECTION")
  try:aware(inv.get("created_at"))
  except Exception as exc:errors.append(str(exc))
  try:nonempty(inv.get("campaign_id"),"CAMPAIGN_ID_REQUIRED")
  except ValueError as exc:errors.append(str(exc))
  scan(inv,"inventory",errors)

 def verify_pack(candidate:dict[str,Any],ptype:str,label:str):
  ref=candidate.get("supportability_pack_evidence")
  if not isinstance(ref,dict):errors.append("SUPPORTABILITY_PACK_REF_REQUIRED:"+label);return None
  ep,ej=exact(ref.get("path"),ref.get("sha256"),"SUPPORTABILITY_PACK_EVIDENCE_MISSING:"+label,"SUPPORTABILITY_PACK_EVIDENCE_SHA_MISMATCH:"+label,errors)
  if not ej:return None
  if ej.get("schema")!="MATRIX_ELITE_SCOPE_SUPPORTABILITY_EVIDENCE_PACK_AUDIT_R1" or ej.get("result")!="PASS" or ej.get("supportability_pack_admitted") is not True:errors.append("SUPPORTABILITY_PACK_NOT_PASS:"+label)
  if ej.get("running_auditor_sha256")!=EXPECTED_PACK_AUDITOR_SHA256 or ej.get("input_contract_sha256")!=EXPECTED_PACK_CONTRACT_SHA256:errors.append("SUPPORTABILITY_PACK_PRODUCER_OR_CONTRACT_MISMATCH:"+label)
  if ej.get("support_declared_by_this_audit") is not False or ej.get("automatic_wagering_authorized") is not False or ej.get("controlled_live_admissible") is not False or ej.get("production_admissible") is not False:errors.append("SUPPORTABILITY_PACK_SAFETY_MISMATCH:"+label)
  if ej.get("pack_type")!=ptype or ej.get("candidate_id")!=candidate.get("candidate_id"):errors.append("SUPPORTABILITY_PACK_IDENTITY_MISMATCH:"+label)
  if not payload_ok(ej):errors.append("SUPPORTABILITY_PACK_PAYLOAD_HASH_MISMATCH:"+label)
  pp,pj=exact(ej.get("evidence_pack_path"),ej.get("evidence_pack_sha256"),"SUPPORTABILITY_SOURCE_PACK_MISSING:"+label,"SUPPORTABILITY_SOURCE_PACK_SHA_MISMATCH:"+label,errors)
  fields=PRED_FIELDS if ptype=="PREDICTIVE" else LIVE_FIELDS if ptype=="LIVE" else FAIL_FIELDS
  if pj:
   for k in fields:
    if str(pj.get(k))!=str(candidate.get(k)):errors.append("SUPPORTABILITY_SOURCE_IDENTITY_MISMATCH:"+label+":"+k)
  inp,_=exact(ej.get("input_path"),ej.get("input_sha256"),"SUPPORTABILITY_PACK_INPUT_MISSING:"+label,"SUPPORTABILITY_PACK_INPUT_SHA_MISMATCH:"+label,errors)
  key=fsha(ep) if ep else None
  if key and key in cache:reruns[label]=cache[key]
  elif inp and pa.is_file():
   code,rj,_,_=pack_runner(pa,inp)
   if code!=0 or rj is None:st="FAILED";errors.append("SUPPORTABILITY_PACK_RERUN_FAILED:"+label)
   elif rj!=ej:st="NON_IDENTICAL";errors.append("SUPPORTABILITY_PACK_RERUN_NOT_IDENTICAL:"+label)
   else:st="IDENTICAL_PASS"
   if key:cache[key]=st
   reruns[label]=st
  else:reruns[label]="NOT_RUN"
  return ej

 predictive=list(inv.get("predictive_candidates") or []) if inv else []
 live=list(inv.get("live_candidates") or []) if inv else []
 failover=list(inv.get("failover_candidates") or []) if inv else []
 if not predictive:errors.append("PREDICTIVE_CANDIDATES_REQUIRED")
 global_candidate_ids=[];pids=[];ptuples=[];included_pred={};excluded_pred=[]
 for i,c in enumerate(predictive):
  label="PREDICTIVE_"+str(i)
  try:
   cid=nonempty(c.get("candidate_id"),label+"_CANDIDATE_ID_REQUIRED");global_candidate_ids.append(cid)
   for f in PRED_FIELDS:nonempty(c.get(f),label+"_"+f.upper()+"_REQUIRED")
   if c.get("sport") not in ("football","tennis"):raise ValueError(label+"_SPORT_INVALID")
   sid=str(c["scope_id"]);pids.append(sid);ptuples.append(tuple(str(c.get(f)) for f in ("sport","competition","market","model_version","feature_version")))
   lr=c.get("live_required")
   if not isinstance(lr,bool):raise ValueError(label+"_LIVE_REQUIRED_MUST_BE_BOOLEAN")
   lid=c.get("live_scope_id")
   if lr and not str(lid or "").strip():raise ValueError(label+"_LIVE_SCOPE_ID_REQUIRED")
   if not lr and lid is not None:raise ValueError(label+"_NONLIVE_SCOPE_ID_MUST_BE_NULL")
   decision=nonempty(c.get("selection_decision"),label+"_DECISION_REQUIRED");reason=nonempty(c.get("selection_reason_code"),label+"_REASON_REQUIRED");txt=nonempty(c.get("selection_reason_text"),label+"_REASON_TEXT_REQUIRED")
   if perf_text(txt):raise ValueError(label+"_PERFORMANCE_REASON_FORBIDDEN")
   if decision=="INCLUDE":
    if reason!=INCLUDE_REASON:raise ValueError(label+"_INCLUDE_REASON_INVALID")
    verify_pack(c,"PREDICTIVE",label)
    included_pred[sid]=c
   elif decision=="EXCLUDE":
    if reason not in EXCLUDE_REASONS:raise ValueError(label+"_EXCLUDE_REASON_INVALID")
    if reason=="DEFERRED_BY_CAPACITY_WITHOUT_PERFORMANCE_INFORMATION":
     exact((c.get("capacity_policy_ref") or {}).get("path"),(c.get("capacity_policy_ref") or {}).get("sha256"),label+"_CAPACITY_POLICY_MISSING",label+"_CAPACITY_POLICY_SHA_MISMATCH",errors)
     rank=c.get("selection_rank")
     if not isinstance(rank,int) or isinstance(rank,bool) or rank<1:raise ValueError(label+"_CAPACITY_RANK_INVALID")
    excluded_pred.append(sid)
   else:raise ValueError(label+"_DECISION_INVALID")
  except (KeyError,ValueError) as exc:errors.append(str(exc))
 if len(pids)!=len(set(pids)):errors.append("DUPLICATE_PREDICTIVE_SCOPE_ID")
 if len(ptuples)!=len(set(ptuples)):errors.append("DUPLICATE_PREDICTIVE_SCOPE_TUPLE")
 if {str(c.get("sport")) for c in included_pred.values()}!={"football","tennis"}:errors.append("INCLUDED_PREDICTIVE_SCOPES_MUST_COVER_BOTH_SPORTS")

 included_live={};lids=[];ltuples=[]
 for i,c in enumerate(live):
  label="LIVE_"+str(i)
  try:
   cid=nonempty(c.get("candidate_id"),label+"_CANDIDATE_ID_REQUIRED");global_candidate_ids.append(cid)
   for f in LIVE_FIELDS:nonempty(c.get(f),label+"_"+f.upper()+"_REQUIRED")
   if c.get("sport") not in ("football","tennis"):raise ValueError(label+"_SPORT_INVALID")
   lid=str(c["live_scope_id"]);lids.append(lid);ltuples.append(tuple(str(c.get(f)) for f in ("sport","market","model_version","feature_version")))
   decision=nonempty(c.get("selection_decision"),label+"_DECISION_REQUIRED");reason=nonempty(c.get("selection_reason_code"),label+"_REASON_REQUIRED");txt=nonempty(c.get("selection_reason_text"),label+"_REASON_TEXT_REQUIRED")
   if perf_text(txt):raise ValueError(label+"_PERFORMANCE_REASON_FORBIDDEN")
   if decision=="INCLUDE":
    if reason!=INCLUDE_REASON:raise ValueError(label+"_INCLUDE_REASON_INVALID")
    verify_pack(c,"LIVE",label);included_live[lid]=c
   elif decision=="EXCLUDE":
    if reason not in EXCLUDE_REASONS:raise ValueError(label+"_EXCLUDE_REASON_INVALID")
   else:raise ValueError(label+"_DECISION_INVALID")
  except (KeyError,ValueError) as exc:errors.append(str(exc))
 if len(lids)!=len(set(lids)):errors.append("DUPLICATE_LIVE_SCOPE_ID")
 if len(ltuples)!=len(set(ltuples)):errors.append("DUPLICATE_LIVE_SCOPE_TUPLE")
 referenced=set()
 for sid,c in included_pred.items():
  if c.get("live_required"):
   lid=str(c.get("live_scope_id"));referenced.add(lid);x=included_live.get(lid)
   if not x:errors.append("INCLUDED_PREDICTIVE_LIVE_SCOPE_NOT_INCLUDED:"+sid)
   elif tuple(str(x.get(f)) for f in ("sport","market","model_version","feature_version"))!=tuple(str(c.get(f)) for f in ("sport","market","model_version","feature_version")):errors.append("PREDICTIVE_TO_LIVE_SCOPE_MISMATCH:"+sid)
 if set(included_live)!=referenced:errors.append("UNREFERENCED_INCLUDED_LIVE_SCOPE")

 included_fail={};fids=[];fpairs=[]
 for i,c in enumerate(failover):
  label="FAILOVER_"+str(i)
  try:
   cid=nonempty(c.get("candidate_id"),label+"_CANDIDATE_ID_REQUIRED");global_candidate_ids.append(cid)
   for f in FAIL_FIELDS:nonempty(c.get(f),label+"_"+f.upper()+"_REQUIRED")
   if str(c.get("primary_provider"))==str(c.get("secondary_provider")):raise ValueError(label+"_PROVIDERS_MUST_DIFFER")
   if c.get("environment") not in ("STAGING","SHADOW"):raise ValueError(label+"_ENVIRONMENT_INVALID")
   fid=str(c["failover_scope_id"]);fids.append(fid);fpairs.append((str(c["primary_provider"]),str(c["secondary_provider"])))
   decision=nonempty(c.get("selection_decision"),label+"_DECISION_REQUIRED");reason=nonempty(c.get("selection_reason_code"),label+"_REASON_REQUIRED");txt=nonempty(c.get("selection_reason_text"),label+"_REASON_TEXT_REQUIRED")
   if perf_text(txt):raise ValueError(label+"_PERFORMANCE_REASON_FORBIDDEN")
   if decision=="INCLUDE":
    if reason!=INCLUDE_REASON:raise ValueError(label+"_INCLUDE_REASON_INVALID")
    verify_pack(c,"FAILOVER",label);included_fail[fid]=c
   elif decision=="EXCLUDE":
    if reason not in EXCLUDE_REASONS:raise ValueError(label+"_EXCLUDE_REASON_INVALID")
   else:raise ValueError(label+"_DECISION_INVALID")
  except (KeyError,ValueError) as exc:errors.append(str(exc))
 if len(fids)!=len(set(fids)):errors.append("DUPLICATE_FAILOVER_SCOPE_ID")
 if len(fpairs)!=len(set(fpairs)):errors.append("DUPLICATE_FAILOVER_PROVIDER_PAIR")
 if not included_fail:errors.append("AT_LEAST_ONE_INCLUDED_FAILOVER_SCOPE_REQUIRED")
 if len(global_candidate_ids)!=len(set(global_candidate_ids)):errors.append("DUPLICATE_GLOBAL_CANDIDATE_ID")

 expected_reruns={"PREDICTIVE_"+str(i) for i,c in enumerate(predictive) if c.get("selection_decision")=="INCLUDE"}
 expected_reruns|={"LIVE_"+str(i) for i,c in enumerate(live) if c.get("selection_decision")=="INCLUDE"}
 expected_reruns|={"FAILOVER_"+str(i) for i,c in enumerate(failover) if c.get("selection_decision")=="INCLUDE"}
 if set(reruns)!=expected_reruns or any(v!="IDENTICAL_PASS" for v in reruns.values()):errors.append("ALL_INCLUDED_SUPPORTABILITY_RERUNS_NOT_IDENTICAL")

 passed=not errors
 out={"schema":SCHEMA,"result":"PASS" if passed else "FAIL_CLOSED","running_auditor_path":str(Path(__file__).resolve()),"running_auditor_sha256":fsha(Path(__file__).resolve()),
  "input_contract_sha256":INPUT_CONTRACT_SHA256,"input_path":str(input_path),"input_sha256":fsha(input_path),"eligibility_rubric_sha256":EXPECTED_RUBRIC_SHA256,
  "candidate_inventory_path":str(invp) if invp else None,"candidate_inventory_sha256":fsha(invp) if invp.is_file() else None,
  "included_predictive_scope_ids":sorted(included_pred),"excluded_predictive_scope_ids":sorted(excluded_pred),"included_live_scope_ids":sorted(included_live),"included_failover_scope_ids":sorted(included_fail),
  "supportability_pack_rerun_status":dict(sorted(reruns.items())),"supportability_pack_rerun_summary":str(len(reruns))+"/"+str(len(reruns))+"_IDENTICAL_PASS" if passed else "FAIL_CLOSED",
  "selection_admitted":passed,"support_declared_by_this_audit":False,"performance_based_selection_detected":any("PERFORMANCE" in x or x.startswith("FORBIDDEN_PERFORMANCE") for x in errors),
  "automatic_model_promotion":False,"automatic_provider_switch":False,"automatic_wagering_authorized":False,"controlled_live_admissible":False,"production_admissible":False,"network_calls_performed":False,
  "blocking_codes":sorted(set(errors)),"output_payload_sha256":None}
 h=dict(out);h["output_payload_sha256"]=None;out["output_payload_sha256"]=canon(h);return out

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);out=evaluate(data,input_path=ip)
 op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 ok=out["result"]=="PASS";print("RESULT="+("PASS" if ok else "FAIL_CLOSED"));print("SELECTION_ADMITTED="+str(bool(out["selection_admitted"])).upper());print("SUPPORTABILITY_RERUN="+out["supportability_pack_rerun_summary"]);print("SUPPORT_DECLARED_BY_THIS_AUDIT=FALSE");print("CONTROLLED_LIVE_ADMISSIBLE=FALSE");print("PRODUCTION_ADMISSIBLE=FALSE");print("BLOCKING_CODES="+(",".join(out["blocking_codes"]) if out["blocking_codes"] else "<NONE>"));print("EVIDENCE="+str(op));print("EVIDENCE_SHA256="+fsha(op));return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
