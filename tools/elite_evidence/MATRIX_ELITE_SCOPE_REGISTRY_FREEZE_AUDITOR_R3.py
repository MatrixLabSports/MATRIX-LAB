from __future__ import annotations
import argparse,json,subprocess,sys,tempfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any,Callable

SCHEMA="MATRIX_ELITE_SCOPE_REGISTRY_FREEZE_EVIDENCE_R3"
INPUT_SCHEMA="MATRIX_ELITE_SCOPE_REGISTRY_FREEZE_INPUT_R3"
INPUT_CONTRACT_SHA256="5a189b5838dc335600de6528e2a889cace0a8fe758ab16b07662b42a040159e1"
EXPECTED_BUILDER_SHA256="c94939601fe495f623781ceb1ed95861e3fbf751c8d3bdb8af662759a9031f34"
EXPECTED_BUILDER_CONTRACT_SHA256="688b6379aaee061db8894b66f3e8f4e785213792748dfdfee6aa571f276583c9"
EXPECTED_BUILDER_STATIC_SHA256="011ac3c7b9799ff146558ef59f8ea2e8a3472483cbba8c722c9f184f4318de6c"
EXPECTED_REGISTRY_AUDITOR_SHA256="6869b989d06adca4867a1109507b1a216fc3e51f280c04cb4b7bbb6bab8467a6"
EXPECTED_REGISTRY_CONTRACT_SHA256="c8c5beab640339fbb48775568ac77b255e2b492b4ccd60855b43ad8e82fd7648"
EXPECTED_REGISTRY_STATIC_SHA256="1975e8dc099b9a8a7387a8ab1a704416e5e0419ef23c7e6638363a1e2998bf97"
EXPECTED_RUBRIC_SHA256="88cb406880575c943ffee466ed774e109de55a39d58e353af3a1c098eaa51d27"
ANCHOR_SCHEMA="MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1"
ALLOWED_ANCHORS={"RFC3161_TSA","WORM_OBJECT_VERSION","EXTERNAL_AUDIT_LEDGER","SIGNED_TRANSPARENCY_LOG"}

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
def default_builder_runner(builder:Path,input_path:Path):
 with tempfile.TemporaryDirectory(prefix="matrix_freeze_r3_builder_") as td:
  rp=Path(td)/"registry.json";ep=Path(td)/"evidence.json"
  try:p=subprocess.run([sys.executable,str(builder),"--input",str(input_path),"--registry-output",str(rp),"--evidence-output",str(ep)],capture_output=True,text=True,timeout=1200,check=False)
  except subprocess.TimeoutExpired:return -1,None,None,"","TIMEOUT"
  try:be=readj(ep) if ep.is_file() else None;reg=readj(rp) if rp.is_file() else None
  except Exception:be=reg=None
  return int(p.returncode),be,reg,p.stdout,p.stderr
def default_registry_runner(auditor:Path,input_path:Path):
 with tempfile.TemporaryDirectory(prefix="matrix_freeze_r3_registry_") as td:
  op=Path(td)/"out.json"
  try:p=subprocess.run([sys.executable,str(auditor),"--input",str(input_path),"--output",str(op)],capture_output=True,text=True,timeout=1200,check=False)
  except subprocess.TimeoutExpired:return -1,None,"","TIMEOUT"
  try:j=readj(op) if op.is_file() else None
  except Exception:j=None
  return int(p.returncode),j,p.stdout,p.stderr
def verify_anchor(root_path:Path,root_sha:str,anchor:dict[str,Any],registered:datetime,start:datetime,errors:list[str],prefix:str):
 try:
  if anchor.get("anchor_type") not in ALLOWED_ANCHORS:raise ValueError(prefix+"_ANCHOR_TYPE_INVALID")
  if anchor.get("verification_result")!="PASS":raise ValueError(prefix+"_ANCHOR_NOT_VERIFIED")
  if anchor.get("root_sha256")!=root_sha or fsha(root_path)!=root_sha:raise ValueError(prefix+"_ANCHOR_ROOT_MISMATCH")
  at=dt(anchor["anchored_at"])
  if at<registered:raise ValueError(prefix+"_ANCHOR_BEFORE_REGISTERED_AT")
  if at>=start:raise ValueError(prefix+"_ANCHOR_NOT_BEFORE_EVIDENCE_POPULATION")
  ep=Path(anchor["anchor_evidence_path"]).resolve()
  if not ep.is_file() or fsha(ep)!=anchor.get("anchor_evidence_sha256"):raise ValueError(prefix+"_ANCHOR_EVIDENCE_INVALID")
  proof=readj(ep)
  if proof.get("schema")!=ANCHOR_SCHEMA or proof.get("result")!="PASS" or proof.get("root_sha256")!=root_sha or proof.get("anchor_type")!=anchor.get("anchor_type"):raise ValueError(prefix+"_ANCHOR_PROOF_INVALID")
  if dt(proof.get("anchored_at"))!=at or not str(proof.get("verifier","")).strip():raise ValueError(prefix+"_ANCHOR_PROOF_TIME_OR_VERIFIER_INVALID")
  return at
 except Exception as exc:errors.append(str(exc));return None

def evaluate(data:dict[str,Any],*,input_path:Path,builder_runner:Callable=default_builder_runner,registry_runner:Callable=default_registry_runner)->dict[str,Any]:
 errors=[];builder_rerun="NOT_RUN";registry_rerun="NOT_RUN"
 if data.get("schema")!=INPUT_SCHEMA:errors.append("INPUT_SCHEMA_MISMATCH")
 bp=Path(data.get("builder_path","")).resolve();ra=Path(data.get("registry_auditor_path","")).resolve()
 if not bp.is_file() or fsha(bp)!=EXPECTED_BUILDER_SHA256:errors.append("BUILDER_NOT_CANONICAL")
 if not ra.is_file() or fsha(ra)!=EXPECTED_REGISTRY_AUDITOR_SHA256:errors.append("REGISTRY_AUDITOR_NOT_CANONICAL")
 bep,be=exact(data.get("build_evidence_path"),data.get("build_evidence_sha256"),"BUILD_EVIDENCE_MISSING","BUILD_EVIDENCE_SHA_MISMATCH",errors)
 bip=None
 if be:
  if be.get("schema")!="MATRIX_ELITE_SCOPE_REGISTRY_BUILD_EVIDENCE_R2" or be.get("result")!="PASS" or be.get("running_builder_sha256")!=EXPECTED_BUILDER_SHA256 or be.get("input_contract_sha256")!=EXPECTED_BUILDER_CONTRACT_SHA256:errors.append("BUILD_EVIDENCE_INVALID")
  if be.get("selection_independent_rerun")!="IDENTICAL_PASS" or be.get("supportability_pack_roots_preserved") is not True or be.get("builder_made_selection_decisions") is not False:errors.append("BUILD_EVIDENCE_GOVERNANCE_INVALID")
  if not payload_ok(be):errors.append("BUILD_EVIDENCE_OUTPUT_HASH_MISMATCH")
  bip,_=exact(be.get("input_path"),be.get("input_sha256"),"BUILD_INPUT_MISSING","BUILD_INPUT_SHA_MISMATCH",errors)
 rep,re=exact(data.get("scope_registry_evidence_path"),data.get("scope_registry_evidence_sha256"),"REGISTRY_EVIDENCE_MISSING","REGISTRY_EVIDENCE_SHA_MISMATCH",errors)
 rip=None;registry_path=None;registry=None;registered=start=None
 if re:
  if re.get("schema")!="MATRIX_ELITE_CLOSURE_SCOPE_REGISTRY_EVIDENCE_R3" or re.get("result")!="PASS" or re.get("scope_registry_admitted") is not True:errors.append("REGISTRY_EVIDENCE_INVALID")
  if re.get("running_auditor_sha256")!=EXPECTED_REGISTRY_AUDITOR_SHA256 or re.get("input_contract_sha256")!=EXPECTED_REGISTRY_CONTRACT_SHA256:errors.append("REGISTRY_EVIDENCE_PRODUCER_CONTRACT_MISMATCH")
  if re.get("support_contract_versions_preserved") is not True or re.get("supportability_pack_roots_preserved") is not True or re.get("manual_registry_edit_admissible") is not False:errors.append("REGISTRY_EVIDENCE_GOVERNANCE_INVALID")
  if not payload_ok(re):errors.append("REGISTRY_EVIDENCE_OUTPUT_HASH_MISMATCH")
  rip,_=exact(re.get("input_path"),re.get("input_sha256"),"REGISTRY_AUDIT_INPUT_MISSING","REGISTRY_AUDIT_INPUT_SHA_MISMATCH",errors)
  try:
   registry_path=Path(re["scope_registry_path"]).resolve();registry=readj(registry_path)
   if fsha(registry_path)!=re.get("scope_registry_sha256"):raise ValueError("REGISTRY_FILE_SHA_MISMATCH")
   registered=dt(re["registered_at"]);start=dt(re["evidence_population_start_at"])
  except Exception as exc:errors.append(str(exc))
 if be and re and registry:
  if be.get("registry_payload_sha256")!=canon(registry):errors.append("BUILD_TO_REGISTRY_PAYLOAD_MISMATCH")
  if be.get("selection_evidence_sha256")!=re.get("selection_evidence_sha256") or be.get("candidate_inventory_sha256")!=re.get("candidate_inventory_sha256"):errors.append("BUILD_REGISTRY_SELECTION_LINEAGE_MISMATCH")
  if be.get("supportability_roots_fingerprint")!=re.get("supportability_roots_fingerprint"):errors.append("BUILD_REGISTRY_SUPPORTABILITY_FINGERPRINT_MISMATCH")
 if bip and bp.is_file() and registry:
  code,be2,reg2,_,_=builder_runner(bp,bip)
  if code!=0 or be2 is None or reg2 is None:errors.append("BUILDER_INDEPENDENT_RERUN_FAILED");builder_rerun="FAILED"
  elif be2!=be:errors.append("BUILDER_INDEPENDENT_RERUN_EVIDENCE_NOT_IDENTICAL");builder_rerun="NON_IDENTICAL"
  elif reg2!=registry:errors.append("BUILDER_INDEPENDENT_RERUN_REGISTRY_NOT_IDENTICAL");builder_rerun="NON_IDENTICAL"
  else:builder_rerun="IDENTICAL_PASS"
 if rip and ra.is_file():
  code,re2,_,_=registry_runner(ra,rip)
  if code!=0 or re2 is None:errors.append("REGISTRY_AUDITOR_INDEPENDENT_RERUN_FAILED");registry_rerun="FAILED"
  elif re2!=re:errors.append("REGISTRY_AUDITOR_INDEPENDENT_RERUN_NOT_IDENTICAL");registry_rerun="NON_IDENTICAL"
  else:registry_rerun="IDENTICAL_PASS"
 reviewp,review=exact(data.get("freeze_review_path"),data.get("freeze_review_sha256"),"FREEZE_REVIEW_MISSING","FREEZE_REVIEW_SHA_MISMATCH",errors)
 review_at=review_anchor_at=None
 if review and registry_path and re and be and registered and start:
  if review.get("schema")!="MATRIX_ELITE_SCOPE_REGISTRY_FREEZE_REVIEW_R3" or review.get("status")!="FINAL_REVIEW_EVIDENCE" or review.get("review_result")!="APPROVED":errors.append("FREEZE_REVIEW_INVALID")
  binds={"reviewed_registry_sha256":fsha(registry_path),"reviewed_registry_payload_sha256":canon(registry),
   "reviewed_scope_registry_evidence_sha256":fsha(rep),"reviewed_build_evidence_sha256":fsha(bep),
   "reviewed_selection_evidence_sha256":re.get("selection_evidence_sha256"),"reviewed_candidate_inventory_sha256":re.get("candidate_inventory_sha256"),
   "reviewed_supportability_roots_fingerprint":re.get("supportability_roots_fingerprint"),"eligibility_rubric_sha256":EXPECTED_RUBRIC_SHA256}
  for k,v in binds.items():
   if review.get(k)!=v:errors.append("FREEZE_REVIEW_BINDING_MISMATCH:"+k)
  controls={"reviewer_independent_of_real_evidence_production":True,"selection_basis":"NON_PERFORMANCE_PREREGISTRATION",
   "no_real_evidence_campaign_results_used_for_scope_selection":True,"real_evidence_campaign_results_available_to_reviewer":False,
   "performance_metrics_used_to_add_or_remove_scopes":False,"support_contract_versions_reviewed":True,"supportability_pack_roots_reviewed":True}
  for k,v in controls.items():
   if review.get(k)!=v:errors.append("FREEZE_REVIEW_CONTROL_MISMATCH:"+k)
  policy=review.get("scope_change_policy") or {}
  req={"adding_scope_requires_new_registry_generation":True,"retiring_scope_requires_new_registry_generation":True,
   "retirement_requires_documented_non_performance_reason":True,"silent_scope_removal_allowed":False,
   "historical_failed_or_adverse_evidence_may_be_deleted":False,"expanded_support_invalidates_prior_global_13_of_13_for_expanded_scope":True}
  for k,v in req.items():
   if policy.get(k)!=v:errors.append("FREEZE_REVIEW_CHANGE_POLICY_MISMATCH:"+k)
  try:
   review_at=dt(review["reviewed_at"])
   if review_at<registered:errors.append("FREEZE_REVIEW_BEFORE_REGISTRY_REGISTERED")
   if review_at>=start:errors.append("FREEZE_REVIEW_NOT_BEFORE_EVIDENCE_POPULATION")
  except Exception as exc:errors.append(str(exc))
  review_anchor_at=verify_anchor(reviewp,fsha(reviewp),data.get("review_anchor") or {},registered,start,errors,"FREEZE_REVIEW")
  if review_anchor_at and review_at and review_anchor_at<review_at:errors.append("FREEZE_REVIEW_ANCHORED_BEFORE_REVIEWED_AT")
 if registry_path and any(x in registry_path.read_text(encoding="utf-8-sig") for x in ("<todo>","<exact","<future","<stable")):errors.append("REGISTRY_PLACEHOLDER_TEXT_DETECTED")
 if reviewp and any(x in reviewp.read_text(encoding="utf-8-sig") for x in ("<todo>","<exact","<independent","<timezone")):errors.append("REVIEW_PLACEHOLDER_TEXT_DETECTED")
 passed=not errors
 out={"schema":SCHEMA,"result":"PASS" if passed else "FAIL_CLOSED","running_auditor_path":str(Path(__file__).resolve()),"running_auditor_sha256":fsha(Path(__file__).resolve()),
  "input_contract_sha256":INPUT_CONTRACT_SHA256,"input_path":str(input_path),"input_sha256":fsha(input_path),"build_evidence_sha256":fsha(bep) if bep else None,
  "scope_registry_evidence_sha256":fsha(rep) if rep else None,"frozen_registry_path":str(registry_path) if registry_path else None,
  "frozen_registry_sha256":fsha(registry_path) if registry_path else None,"frozen_registry_payload_sha256":canon(registry) if registry else None,
  "selection_evidence_sha256":re.get("selection_evidence_sha256") if re else None,"candidate_inventory_sha256":re.get("candidate_inventory_sha256") if re else None,
  "supportability_roots_fingerprint":re.get("supportability_roots_fingerprint") if re else None,"freeze_review_path":str(reviewp) if reviewp else None,
  "freeze_review_sha256":fsha(reviewp) if reviewp else None,"registered_at":registered.isoformat() if registered else None,
  "reviewed_at":review_at.isoformat() if review_at else None,"review_anchor_at":review_anchor_at.isoformat() if review_anchor_at else None,
  "evidence_population_start_at":start.isoformat() if start else None,"predictive_scope_count":int(re.get("predictive_scope_count",0)) if re else 0,
  "live_scope_count":int(re.get("live_scope_count",0)) if re else 0,"failover_scope_count":int(re.get("provider_failover_scope_count",0)) if re else 0,
  "builder_independent_rerun":builder_rerun,"registry_auditor_independent_rerun":registry_rerun,"scope_registry_frozen":passed,
  "support_contract_versions_preserved":passed,"supportability_pack_roots_preserved":passed,"post_hoc_scope_selection_admissible":False,
  "manual_registry_edit_admissible":False,"scope_removal_after_freeze_allowed":False,"expanded_support_requires_new_registry_generation":True,
  "historical_adverse_evidence_deletion_allowed":False,"automatic_wagering_authorized":False,"controlled_live_admissible":False,
  "production_admissible":False,"network_calls_performed":False,"blocking_codes":sorted(set(errors)),"output_payload_sha256":None}
 h=dict(out);h["output_payload_sha256"]=None;out["output_payload_sha256"]=canon(h);return out

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip)
 out=evaluate(data,input_path=ip);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 ok=out["result"]=="PASS";print("RESULT="+("PASS" if ok else "FAIL_CLOSED"));print("SCOPE_REGISTRY_FROZEN="+str(bool(out["scope_registry_frozen"])).upper())
 print("BUILDER_INDEPENDENT_RERUN="+out["builder_independent_rerun"]);print("REGISTRY_AUDITOR_INDEPENDENT_RERUN="+out["registry_auditor_independent_rerun"])
 print("SUPPORTABILITY_PACK_ROOTS_PRESERVED="+str(out["supportability_pack_roots_preserved"]).upper());print("MANUAL_REGISTRY_EDIT_ADMISSIBLE=FALSE")
 print("POST_HOC_SCOPE_SELECTION_ADMISSIBLE=FALSE");print("CONTROLLED_LIVE_ADMISSIBLE=FALSE");print("PRODUCTION_ADMISSIBLE=FALSE")
 print("BLOCKING_CODES="+(",".join(out["blocking_codes"]) if out["blocking_codes"] else "<NONE>"));print("EVIDENCE="+str(op));print("EVIDENCE_SHA256="+fsha(op));return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
