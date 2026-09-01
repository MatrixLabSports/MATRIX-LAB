from __future__ import annotations
import argparse,json,subprocess,sys,tempfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any,Callable

SCHEMA="MATRIX_ELITE_SCOPE_REGISTRY_BUILD_EVIDENCE_R2"
INPUT_SCHEMA="MATRIX_ELITE_SCOPE_REGISTRY_BUILDER_INPUT_R2"
OUTPUT_SCHEMA="MATRIX_ELITE_CLOSURE_SCOPE_REGISTRY_R3"
INPUT_CONTRACT_SHA256="688b6379aaee061db8894b66f3e8f4e785213792748dfdfee6aa571f276583c9"
EXPECTED_SELECTION_AUDITOR_SHA256="27a6962b3d1ddd6f78d55fe4e2ff7654319dbb53a709dbb0800e166c56d0f425"
EXPECTED_SELECTION_CONTRACT_SHA256="03aba764a943225f39d8c25fb074afd0c239ad5d933b2bc409a99125975b424c"
EXPECTED_SELECTION_STATIC_SHA256="3c6e3ed07e955e7ab8ed228ff9332b47020b697c5ebad6a57a71bf4f36c04729"
EXPECTED_RUBRIC_SHA256="88cb406880575c943ffee466ed774e109de55a39d58e353af3a1c098eaa51d27"
PRED_FIELDS=("candidate_id","scope_id","sport","competition","market","model_version","feature_version","market_semantics_version","settlement_rules_version","data_contract_version","identity_contract_version","rights_profile_version","odds_contract_version","evaluation_protocol_version","sample_requirement_policy_version","risk_class","live_required","live_scope_id")
LIVE_FIELDS=("candidate_id","live_scope_id","sport","market","model_version","feature_version","event_time_contract_version","live_window_policy_version","staleness_policy_version","replay_protocol_version","shadow_live_protocol_version")
FAIL_FIELDS=("candidate_id","failover_scope_id","primary_provider","secondary_provider","environment","schema_compatibility_contract_version","identity_reconciliation_contract_version","primary_rights_profile_version","secondary_rights_profile_version","human_approval_policy_version","rollback_plan_version")

def readj(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding="utf-8-sig"))
 if not isinstance(x,dict):raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
 return x
def fsha(p:Path)->str:return sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->str:return sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def dt(v:Any)->datetime:
 x=datetime.fromisoformat(str(v).replace("Z","+00:00"))
 if x.tzinfo is None or x.utcoffset() is None:raise ValueError("TIME_MUST_BE_TIMEZONE_AWARE")
 return x
def payload_ok(j:dict[str,Any])->bool:
 if "output_payload_sha256" not in j:return False
 h=dict(j);x=h.get("output_payload_sha256");h["output_payload_sha256"]=None;return canon(h)==x
def exact(path_value:Any,sha_value:Any,missing:str,mismatch:str,errors:list[str]):
 try:
  p=Path(path_value).resolve()
  if not p.is_file():errors.append(missing);return None,None
  if fsha(p)!=sha_value:errors.append(mismatch);return p,None
  return p,readj(p)
 except Exception:errors.append(missing);return None,None
def default_runner(auditor:Path,input_path:Path):
 with tempfile.TemporaryDirectory(prefix="matrix_builder_r2_selection_") as td:
  op=Path(td)/"out.json"
  try:p=subprocess.run([sys.executable,str(auditor),"--input",str(input_path),"--output",str(op)],capture_output=True,text=True,timeout=1200,check=False)
  except subprocess.TimeoutExpired:return -1,None,"","TIMEOUT"
  try:j=readj(op) if op.is_file() else None
  except Exception:j=None
  return int(p.returncode),j,p.stdout,p.stderr
def pack_root(c:dict[str,Any],errors:list[str],label:str)->str|None:
 ref=c.get("supportability_pack_evidence")
 if not isinstance(ref,dict):errors.append("SUPPORTABILITY_PACK_REF_MISSING:"+label);return None
 try:
  p=Path(ref["path"]).resolve();h=str(ref["sha256"]).lower()
  if not p.is_file():errors.append("SUPPORTABILITY_PACK_EVIDENCE_MISSING:"+label);return None
  if len(h)!=64 or fsha(p)!=h:errors.append("SUPPORTABILITY_PACK_EVIDENCE_SHA_MISMATCH:"+label);return None
  j=readj(p)
  if j.get("schema")!="MATRIX_ELITE_SCOPE_SUPPORTABILITY_EVIDENCE_PACK_AUDIT_R1" or j.get("result")!="PASS" or j.get("supportability_pack_admitted") is not True:
   errors.append("SUPPORTABILITY_PACK_NOT_PASS:"+label);return None
  return h
 except Exception:errors.append("SUPPORTABILITY_PACK_REF_INVALID:"+label);return None
def support_fp(pred:list[dict],live:list[dict],fail:list[dict])->str:
 roots=[]
 for kind,rows,key in (("PREDICTIVE",pred,"scope_id"),("LIVE",live,"live_scope_id"),("FAILOVER",fail,"failover_scope_id")):
  for x in rows:roots.append({"kind":kind,"id":x[key],"candidate_id":x["candidate_id"],"supportability_pack_evidence_sha256":x["supportability_pack_evidence_sha256"]})
 return canon(sorted(roots,key=lambda x:(x["kind"],x["id"])))

def evaluate(data:dict[str,Any],*,input_path:Path,selection_runner:Callable=default_runner)->tuple[dict[str,Any],dict[str,Any]|None]:
 errors=[]
 if data.get("schema")!=INPUT_SCHEMA:errors.append("INPUT_SCHEMA_MISMATCH")
 auditor=Path(data.get("selection_auditor_path","")).resolve()
 contract=Path(data.get("selection_contract_path","")).resolve()
 staticp=Path(data.get("selection_static_audit_path","")).resolve()
 if not auditor.is_file() or fsha(auditor)!=EXPECTED_SELECTION_AUDITOR_SHA256:errors.append("SELECTION_AUDITOR_NOT_CANONICAL")
 if not contract.is_file() or fsha(contract)!=EXPECTED_SELECTION_CONTRACT_SHA256:errors.append("SELECTION_CONTRACT_NOT_CANONICAL")
 if not staticp.is_file() or fsha(staticp)!=EXPECTED_SELECTION_STATIC_SHA256:errors.append("SELECTION_STATIC_AUDIT_NOT_CANONICAL")
 sep,se=exact(data.get("selection_evidence_path"),data.get("selection_evidence_sha256"),"SELECTION_EVIDENCE_MISSING","SELECTION_EVIDENCE_SHA_MISMATCH",errors)
 invp,inv=exact(data.get("candidate_inventory_path"),data.get("candidate_inventory_sha256"),"CANDIDATE_INVENTORY_MISSING","CANDIDATE_INVENTORY_SHA_MISMATCH",errors)
 if se:
  if se.get("schema")!="MATRIX_ELITE_SCOPE_SELECTION_EVIDENCE_R2" or se.get("result")!="PASS" or se.get("selection_admitted") is not True:errors.append("SELECTION_EVIDENCE_NOT_PASS")
  if se.get("running_auditor_sha256")!=EXPECTED_SELECTION_AUDITOR_SHA256 or se.get("input_contract_sha256")!=EXPECTED_SELECTION_CONTRACT_SHA256 or se.get("eligibility_rubric_sha256")!=EXPECTED_RUBRIC_SHA256:errors.append("SELECTION_EVIDENCE_ROOT_MISMATCH")
  if se.get("support_declared_by_this_audit") is not False or se.get("controlled_live_admissible") is not False or se.get("production_admissible") is not False:errors.append("SELECTION_SAFETY_MISMATCH")
  if not payload_ok(se):errors.append("SELECTION_EVIDENCE_OUTPUT_HASH_MISMATCH")
  if invp and se.get("candidate_inventory_sha256")!=fsha(invp):errors.append("SELECTION_TO_INVENTORY_BINDING_MISMATCH")
  sip,_=exact(se.get("input_path"),se.get("input_sha256"),"SELECTION_INPUT_MISSING","SELECTION_INPUT_SHA_MISMATCH",errors)
  if sip and auditor.is_file():
   code,rj,_,_=selection_runner(auditor,sip)
   if code!=0 or rj is None:errors.append("SELECTION_INDEPENDENT_RERUN_FAILED")
   elif rj!=se:errors.append("SELECTION_INDEPENDENT_RERUN_NOT_IDENTICAL")
 if inv:
  if inv.get("schema")!="MATRIX_ELITE_SCOPE_CANDIDATE_INVENTORY_R2":errors.append("INVENTORY_SCHEMA_MISMATCH")
  if inv.get("status")!="FINAL_PREREGISTRATION_CANDIDATE_INVENTORY":errors.append("INVENTORY_STATUS_NOT_FINAL")
  if inv.get("support_declared_by_this_inventory") is not False:errors.append("INVENTORY_MUST_NOT_DECLARE_SUPPORT")
 try:
  registered=dt(data.get("registered_at"));start=dt(data.get("evidence_population_start_at"))
  if registered>=start:errors.append("REGISTERED_AT_MUST_PRECEDE_EVIDENCE_POPULATION")
  if inv and dt(inv.get("created_at"))>registered:errors.append("INVENTORY_CREATED_AFTER_REGISTERED_AT")
 except Exception as exc:errors.append(str(exc));registered=start=None

 pred=[];live=[];fail=[]
 if inv:
  for c in inv.get("predictive_candidates") or []:
   if c.get("selection_decision")!="INCLUDE":continue
   row={k:c.get(k) for k in PRED_FIELDS}
   row["supportability_pack_evidence_sha256"]=pack_root(c,errors,"PREDICTIVE:"+str(c.get("scope_id")))
   pred.append(row)
  for c in inv.get("live_candidates") or []:
   if c.get("selection_decision")!="INCLUDE":continue
   row={k:c.get(k) for k in LIVE_FIELDS}
   row["supportability_pack_evidence_sha256"]=pack_root(c,errors,"LIVE:"+str(c.get("live_scope_id")))
   live.append(row)
  for c in inv.get("failover_candidates") or []:
   if c.get("selection_decision")!="INCLUDE":continue
   row={k:c.get(k) for k in FAIL_FIELDS}
   row["supportability_pack_evidence_sha256"]=pack_root(c,errors,"FAILOVER:"+str(c.get("failover_scope_id")))
   fail.append(row)
 if se:
  if {str(x["scope_id"]) for x in pred}!=set(se.get("included_predictive_scope_ids") or []):errors.append("BUILDER_PREDICTIVE_SET_MISMATCH")
  if {str(x["live_scope_id"]) for x in live}!=set(se.get("included_live_scope_ids") or []):errors.append("BUILDER_LIVE_SET_MISMATCH")
  if {str(x["failover_scope_id"]) for x in fail}!=set(se.get("included_failover_scope_ids") or []):errors.append("BUILDER_FAILOVER_SET_MISMATCH")
  expected=len(pred)+len(live)+len(fail)
  if se.get("supportability_pack_rerun_summary")!=f"{expected}/{expected}_IDENTICAL_PASS":errors.append("SELECTION_SUPPORTABILITY_RERUN_SUMMARY_MISMATCH")
  if any(v!="IDENTICAL_PASS" for v in (se.get("supportability_pack_rerun_status") or {}).values()):errors.append("SELECTION_SUPPORTABILITY_RERUN_STATUS_MISMATCH")

 registry=None;fp=None
 if not errors:
  pred=sorted(pred,key=lambda x:str(x["scope_id"]));live=sorted(live,key=lambda x:str(x["live_scope_id"]));fail=sorted(fail,key=lambda x:str(x["failover_scope_id"]))
  fp=support_fp(pred,live,fail)
  registry={"schema":OUTPUT_SCHEMA,"status":"FINAL_SCOPE_REGISTRY","eligibility_rubric_sha256":EXPECTED_RUBRIC_SHA256,
   "selection_evidence_sha256":fsha(sep),"candidate_inventory_sha256":fsha(invp),"supportability_roots_fingerprint":fp,
   "registered_at":registered.isoformat(),"evidence_population_start_at":start.isoformat(),"project_sports":["football","tennis"],
   "closure_semantics":"ONLY_REGISTERED_ACTIVE_SUPPORTED_SCOPES_CAN_BE_CLOSED","unregistered_scopes_admissible":False,
   "scope_removal_after_anchor_allowed":False,"predictive_scopes":pred,"live_scopes":live,"provider_failover_scopes":fail,
   "builder_does_not_select_scopes":True,"supportability_pack_roots_preserved":True,"scope_registry_frozen":False,
   "post_hoc_scope_selection_admissible":False,"controlled_live_admissible":False,"production_admissible":False}
 out={"schema":SCHEMA,"result":"PASS" if not errors else "FAIL_CLOSED","running_builder_path":str(Path(__file__).resolve()),"running_builder_sha256":fsha(Path(__file__).resolve()),
  "input_contract_sha256":INPUT_CONTRACT_SHA256,"input_path":str(input_path),"input_sha256":fsha(input_path),
  "selection_evidence_sha256":fsha(sep) if sep else None,"candidate_inventory_sha256":fsha(invp) if invp else None,
  "supportability_roots_fingerprint":fp,"registry_payload_sha256":canon(registry) if registry else None,
  "included_predictive_scope_count":len(pred),"included_live_scope_count":len(live),"included_failover_scope_count":len(fail),
  "selection_independent_rerun":"IDENTICAL_PASS" if not errors else "FAILED_OR_NOT_RUN","supportability_pack_roots_preserved":bool(not errors),
  "builder_made_selection_decisions":False,"scope_registry_frozen":False,"automatic_wagering_authorized":False,
  "controlled_live_admissible":False,"production_admissible":False,"network_calls_performed":False,"blocking_codes":sorted(set(errors)),"output_payload_sha256":None}
 h=dict(out);h["output_payload_sha256"]=None;out["output_payload_sha256"]=canon(h);return out,registry

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--registry-output",required=True);ap.add_argument("--evidence-output",required=True);ns=ap.parse_args()
 ip=Path(ns.input).resolve();rp=Path(ns.registry_output).resolve();ep=Path(ns.evidence_output).resolve();data=readj(ip);out,registry=evaluate(data,input_path=ip)
 if registry is not None:rp.parent.mkdir(parents=True,exist_ok=True);rp.write_text(json.dumps(registry,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 ep.parent.mkdir(parents=True,exist_ok=True);ep.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 ok=out["result"]=="PASS";print("RESULT="+("PASS" if ok else "FAIL_CLOSED"));print("SELECTION_INDEPENDENT_RERUN="+out["selection_independent_rerun"])
 print("SUPPORTABILITY_PACK_ROOTS_PRESERVED="+str(out["supportability_pack_roots_preserved"]).upper());print("BUILDER_MADE_SELECTION_DECISIONS=FALSE")
 print("SCOPE_REGISTRY_FROZEN=FALSE");print("CONTROLLED_LIVE_ADMISSIBLE=FALSE");print("PRODUCTION_ADMISSIBLE=FALSE")
 print("BLOCKING_CODES="+(",".join(out["blocking_codes"]) if out["blocking_codes"] else "<NONE>"))
 if registry is not None:print("REGISTRY="+str(rp));print("REGISTRY_SHA256="+fsha(rp))
 print("EVIDENCE="+str(ep));print("EVIDENCE_SHA256="+fsha(ep));return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
