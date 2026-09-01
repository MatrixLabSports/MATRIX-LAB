from __future__ import annotations
import argparse,json,subprocess,sys,tempfile
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any,Callable

SCHEMA="MATRIX_ELITE_CLOSURE_SCOPE_REGISTRY_EVIDENCE_R3"
INPUT_SCHEMA="MATRIX_ELITE_CLOSURE_SCOPE_REGISTRY_AUDIT_INPUT_R3"
REGISTRY_SCHEMA="MATRIX_ELITE_CLOSURE_SCOPE_REGISTRY_R3"
INPUT_CONTRACT_SHA256="c8c5beab640339fbb48775568ac77b255e2b492b4ccd60855b43ad8e82fd7648"
EXPECTED_SELECTION_AUDITOR_SHA256="27a6962b3d1ddd6f78d55fe4e2ff7654319dbb53a709dbb0800e166c56d0f425"
EXPECTED_SELECTION_CONTRACT_SHA256="03aba764a943225f39d8c25fb074afd0c239ad5d933b2bc409a99125975b424c"
EXPECTED_BUILDER_SHA256="c94939601fe495f623781ceb1ed95861e3fbf751c8d3bdb8af662759a9031f34"
EXPECTED_BUILDER_CONTRACT_SHA256="688b6379aaee061db8894b66f3e8f4e785213792748dfdfee6aa571f276583c9"
EXPECTED_BUILDER_STATIC_SHA256="011ac3c7b9799ff146558ef59f8ea2e8a3472483cbba8c722c9f184f4318de6c"
EXPECTED_RUBRIC_SHA256="88cb406880575c943ffee466ed774e109de55a39d58e353af3a1c098eaa51d27"
ANCHOR_SCHEMA="MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1"
ALLOWED_ANCHORS={"RFC3161_TSA","WORM_OBJECT_VERSION","EXTERNAL_AUDIT_LEDGER","SIGNED_TRANSPARENCY_LOG"}
PRED_FIELDS=("candidate_id","scope_id","sport","competition","market","model_version","feature_version","market_semantics_version","settlement_rules_version","data_contract_version","identity_contract_version","rights_profile_version","odds_contract_version","evaluation_protocol_version","sample_requirement_policy_version","risk_class","live_required","live_scope_id","supportability_pack_evidence_sha256")
LIVE_FIELDS=("candidate_id","live_scope_id","sport","market","model_version","feature_version","event_time_contract_version","live_window_policy_version","staleness_policy_version","replay_protocol_version","shadow_live_protocol_version","supportability_pack_evidence_sha256")
FAIL_FIELDS=("candidate_id","failover_scope_id","primary_provider","secondary_provider","environment","schema_compatibility_contract_version","identity_reconciliation_contract_version","primary_rights_profile_version","secondary_rights_profile_version","human_approval_policy_version","rollback_plan_version","supportability_pack_evidence_sha256")

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
 with tempfile.TemporaryDirectory(prefix="matrix_registry_r3_builder_") as td:
  rp=Path(td)/"registry.json";ep=Path(td)/"evidence.json"
  try:p=subprocess.run([sys.executable,str(builder),"--input",str(input_path),"--registry-output",str(rp),"--evidence-output",str(ep)],capture_output=True,text=True,timeout=1200,check=False)
  except subprocess.TimeoutExpired:return -1,None,None,"","TIMEOUT"
  try:ej=readj(ep) if ep.is_file() else None; rj=readj(rp) if rp.is_file() else None
  except Exception:ej=rj=None
  return int(p.returncode),ej,rj,p.stdout,p.stderr
def verify_anchor(root_path:Path,root_sha:str,anchor:dict[str,Any],registered:datetime,start:datetime,errors:list[str]):
 try:
  if anchor.get("anchor_type") not in ALLOWED_ANCHORS:raise ValueError("REGISTRY_ANCHOR_TYPE_INVALID")
  if anchor.get("verification_result")!="PASS":raise ValueError("REGISTRY_ANCHOR_NOT_VERIFIED")
  if anchor.get("root_sha256")!=root_sha or fsha(root_path)!=root_sha:raise ValueError("REGISTRY_ANCHOR_ROOT_MISMATCH")
  at=dt(anchor["anchored_at"])
  if at<registered:raise ValueError("REGISTRY_ANCHOR_BEFORE_REGISTERED_AT")
  if at>=start:raise ValueError("REGISTRY_ANCHOR_NOT_BEFORE_EVIDENCE_POPULATION")
  ep=Path(anchor["anchor_evidence_path"]).resolve()
  if not ep.is_file() or fsha(ep)!=anchor.get("anchor_evidence_sha256"):raise ValueError("REGISTRY_ANCHOR_EVIDENCE_INVALID")
  proof=readj(ep)
  if proof.get("schema")!=ANCHOR_SCHEMA or proof.get("result")!="PASS" or proof.get("root_sha256")!=root_sha or proof.get("anchor_type")!=anchor.get("anchor_type"):raise ValueError("REGISTRY_ANCHOR_PROOF_INVALID")
  if dt(proof.get("anchored_at"))!=at or not str(proof.get("verifier","")).strip():raise ValueError("REGISTRY_ANCHOR_PROOF_TIME_OR_VERIFIER_INVALID")
  return at
 except Exception as exc:errors.append(str(exc));return None
def expected_projection(inv:dict[str,Any],errors:list[str]):
 pred=[];live=[];fail=[]
 for c in inv.get("predictive_candidates") or []:
  if c.get("selection_decision")!="INCLUDE":continue
  row={k:c.get(k) for k in PRED_FIELDS if k!="supportability_pack_evidence_sha256"}
  ref=c.get("supportability_pack_evidence") or {};row["supportability_pack_evidence_sha256"]=str(ref.get("sha256","")).lower();pred.append(row)
 for c in inv.get("live_candidates") or []:
  if c.get("selection_decision")!="INCLUDE":continue
  row={k:c.get(k) for k in LIVE_FIELDS if k!="supportability_pack_evidence_sha256"}
  ref=c.get("supportability_pack_evidence") or {};row["supportability_pack_evidence_sha256"]=str(ref.get("sha256","")).lower();live.append(row)
 for c in inv.get("failover_candidates") or []:
  if c.get("selection_decision")!="INCLUDE":continue
  row={k:c.get(k) for k in FAIL_FIELDS if k!="supportability_pack_evidence_sha256"}
  ref=c.get("supportability_pack_evidence") or {};row["supportability_pack_evidence_sha256"]=str(ref.get("sha256","")).lower();fail.append(row)
 return sorted(pred,key=lambda x:str(x["scope_id"])),sorted(live,key=lambda x:str(x["live_scope_id"])),sorted(fail,key=lambda x:str(x["failover_scope_id"]))
def support_fp(pred,live,fail):
 roots=[]
 for kind,rows,key in (("PREDICTIVE",pred,"scope_id"),("LIVE",live,"live_scope_id"),("FAILOVER",fail,"failover_scope_id")):
  for x in rows:roots.append({"kind":kind,"id":x[key],"candidate_id":x["candidate_id"],"supportability_pack_evidence_sha256":x["supportability_pack_evidence_sha256"]})
 return canon(sorted(roots,key=lambda x:(x["kind"],x["id"])))

def evaluate(data:dict[str,Any],*,input_path:Path,builder_runner:Callable=default_builder_runner)->dict[str,Any]:
 errors=[];builder_rerun="NOT_RUN"
 if data.get("schema")!=INPUT_SCHEMA:errors.append("INPUT_SCHEMA_MISMATCH")
 bp=Path(data.get("builder_path","")).resolve();bc=Path(data.get("builder_contract_path","")).resolve();bs=Path(data.get("builder_static_audit_path","")).resolve()
 if not bp.is_file() or fsha(bp)!=EXPECTED_BUILDER_SHA256:errors.append("BUILDER_NOT_CANONICAL")
 if not bc.is_file() or fsha(bc)!=EXPECTED_BUILDER_CONTRACT_SHA256:errors.append("BUILDER_CONTRACT_NOT_CANONICAL")
 if not bs.is_file() or fsha(bs)!=EXPECTED_BUILDER_STATIC_SHA256:errors.append("BUILDER_STATIC_AUDIT_NOT_CANONICAL")
 sep,se=exact(data.get("selection_evidence_path"),data.get("selection_evidence_sha256"),"SELECTION_EVIDENCE_MISSING","SELECTION_EVIDENCE_SHA_MISMATCH",errors)
 invp,inv=(None,None)
 if se:
  if se.get("schema")!="MATRIX_ELITE_SCOPE_SELECTION_EVIDENCE_R2" or se.get("result")!="PASS" or se.get("selection_admitted") is not True:errors.append("SELECTION_EVIDENCE_NOT_PASS")
  if se.get("running_auditor_sha256")!=EXPECTED_SELECTION_AUDITOR_SHA256 or se.get("input_contract_sha256")!=EXPECTED_SELECTION_CONTRACT_SHA256:errors.append("SELECTION_EVIDENCE_PRODUCER_CONTRACT_MISMATCH")
  if not payload_ok(se):errors.append("SELECTION_EVIDENCE_OUTPUT_HASH_MISMATCH")
  invp,inv=exact(se.get("candidate_inventory_path"),se.get("candidate_inventory_sha256"),"SELECTION_INVENTORY_MISSING","SELECTION_INVENTORY_SHA_MISMATCH",errors)
 bep,be=exact(data.get("build_evidence_path"),data.get("build_evidence_sha256"),"BUILD_EVIDENCE_MISSING","BUILD_EVIDENCE_SHA_MISMATCH",errors)
 bip=None
 if be:
  if be.get("schema")!="MATRIX_ELITE_SCOPE_REGISTRY_BUILD_EVIDENCE_R2" or be.get("result")!="PASS" or be.get("running_builder_sha256")!=EXPECTED_BUILDER_SHA256 or be.get("input_contract_sha256")!=EXPECTED_BUILDER_CONTRACT_SHA256:errors.append("BUILD_EVIDENCE_INVALID")
  if be.get("selection_independent_rerun")!="IDENTICAL_PASS" or be.get("supportability_pack_roots_preserved") is not True or be.get("builder_made_selection_decisions") is not False:errors.append("BUILD_EVIDENCE_GOVERNANCE_INVALID")
  if not payload_ok(be):errors.append("BUILD_EVIDENCE_OUTPUT_HASH_MISMATCH")
  bip,_=exact(be.get("input_path"),be.get("input_sha256"),"BUILD_INPUT_MISSING","BUILD_INPUT_SHA_MISMATCH",errors)
  if sep and be.get("selection_evidence_sha256")!=fsha(sep):errors.append("BUILD_SELECTION_BINDING_MISMATCH")
  if invp and be.get("candidate_inventory_sha256")!=fsha(invp):errors.append("BUILD_INVENTORY_BINDING_MISMATCH")
 rp,reg=exact(data.get("scope_registry_path"),data.get("scope_registry_sha256"),"SCOPE_REGISTRY_MISSING","SCOPE_REGISTRY_SHA_MISMATCH",errors)
 registered=start=None;pred=[];live=[];fail=[];fp=None
 if reg:
  if reg.get("schema")!=REGISTRY_SCHEMA or reg.get("status")!="FINAL_SCOPE_REGISTRY":errors.append("REGISTRY_SCHEMA_OR_STATUS_MISMATCH")
  if reg.get("eligibility_rubric_sha256")!=EXPECTED_RUBRIC_SHA256:errors.append("REGISTRY_RUBRIC_MISMATCH")
  if sep and reg.get("selection_evidence_sha256")!=fsha(sep):errors.append("REGISTRY_SELECTION_BINDING_MISMATCH")
  if invp and reg.get("candidate_inventory_sha256")!=fsha(invp):errors.append("REGISTRY_INVENTORY_BINDING_MISMATCH")
  if reg.get("builder_does_not_select_scopes") is not True or reg.get("supportability_pack_roots_preserved") is not True or reg.get("scope_registry_frozen") is not False:errors.append("REGISTRY_GOVERNANCE_FLAGS_INVALID")
  try:
   registered=dt(reg.get("registered_at"));start=dt(reg.get("evidence_population_start_at"))
   if registered>=start:errors.append("REGISTERED_AT_MUST_PRECEDE_EVIDENCE_POPULATION")
   if inv and dt(inv.get("created_at"))>registered:errors.append("INVENTORY_CREATED_AFTER_REGISTERED_AT")
  except Exception as exc:errors.append(str(exc))
  pred=list(reg.get("predictive_scopes") or []);live=list(reg.get("live_scopes") or []);fail=list(reg.get("provider_failover_scopes") or [])
  if inv:
   ep,el,ef=expected_projection(inv,errors)
   if pred!=ep:errors.append("REGISTRY_PREDICTIVE_PROJECTION_MISMATCH")
   if live!=el:errors.append("REGISTRY_LIVE_PROJECTION_MISMATCH")
   if fail!=ef:errors.append("REGISTRY_FAILOVER_PROJECTION_MISMATCH")
   fp=support_fp(ep,el,ef)
   if reg.get("supportability_roots_fingerprint")!=fp:errors.append("REGISTRY_SUPPORTABILITY_FINGERPRINT_MISMATCH")
  pids=[str(x.get("scope_id")) for x in pred];lids=[str(x.get("live_scope_id")) for x in live];fids=[str(x.get("failover_scope_id")) for x in fail]
  if len(pids)!=len(set(pids)):errors.append("DUPLICATE_PREDICTIVE_SCOPE_ID")
  if len(lids)!=len(set(lids)):errors.append("DUPLICATE_LIVE_SCOPE_ID")
  if len(fids)!=len(set(fids)):errors.append("DUPLICATE_FAILOVER_SCOPE_ID")
  if len({(str(x.get("sport")),str(x.get("competition")),str(x.get("market"))) for x in pred})!=len(pred):errors.append("DUPLICATE_PREDICTIVE_SPORT_COMPETITION_MARKET")
  if len({(str(x.get("sport")),str(x.get("market"))) for x in live})!=len(live):errors.append("DUPLICATE_LIVE_SPORT_MARKET")
  if len({(str(x.get("primary_provider")),str(x.get("secondary_provider"))) for x in fail})!=len(fail):errors.append("DUPLICATE_FAILOVER_PROVIDER_PAIR")
 if be and reg:
  if be.get("registry_payload_sha256")!=canon(reg):errors.append("BUILD_TO_REGISTRY_PAYLOAD_MISMATCH")
  if be.get("supportability_roots_fingerprint")!=reg.get("supportability_roots_fingerprint"):errors.append("BUILD_TO_REGISTRY_SUPPORTABILITY_FINGERPRINT_MISMATCH")
 if bip and bp.is_file() and reg:
  code,be2,reg2,_,_=builder_runner(bp,bip)
  if code!=0 or be2 is None or reg2 is None:errors.append("BUILDER_INDEPENDENT_RERUN_FAILED");builder_rerun="FAILED"
  elif be2!=be:errors.append("BUILDER_INDEPENDENT_RERUN_EVIDENCE_NOT_IDENTICAL");builder_rerun="NON_IDENTICAL"
  elif reg2!=reg:errors.append("BUILDER_INDEPENDENT_RERUN_REGISTRY_NOT_IDENTICAL");builder_rerun="NON_IDENTICAL"
  else:builder_rerun="IDENTICAL_PASS"
 anchor_at=None
 if rp and reg and registered and start:
  anchor_at=verify_anchor(rp,fsha(rp),data.get("registration_anchor") or {},registered,start,errors)
 if rp and any(x in rp.read_text(encoding="utf-8-sig") for x in ("<todo>","<exact","<future","<stable")):errors.append("REGISTRY_PLACEHOLDER_TEXT_DETECTED")
 passed=not errors
 out={"schema":SCHEMA,"result":"PASS" if passed else "FAIL_CLOSED","running_auditor_path":str(Path(__file__).resolve()),"running_auditor_sha256":fsha(Path(__file__).resolve()),
  "input_contract_sha256":INPUT_CONTRACT_SHA256,"input_path":str(input_path),"input_sha256":fsha(input_path),
  "selection_evidence_sha256":fsha(sep) if sep else None,"candidate_inventory_sha256":fsha(invp) if invp else None,"build_evidence_sha256":fsha(bep) if bep else None,
  "scope_registry_path":str(rp) if rp else None,"scope_registry_sha256":fsha(rp) if rp else None,"registry_payload_sha256":canon(reg) if reg else None,
  "supportability_roots_fingerprint":fp,"registered_at":registered.isoformat() if registered else None,"registration_anchor_at":anchor_at.isoformat() if anchor_at else None,
  "evidence_population_start_at":start.isoformat() if start else None,"predictive_scopes":pred,"live_scopes":live,"provider_failover_scopes":fail,
  "predictive_scope_count":len(pred),"live_scope_count":len(live),"provider_failover_scope_count":len(fail),
  "builder_independent_rerun":builder_rerun,"scope_registry_admitted":passed,"support_contract_versions_preserved":passed,
  "supportability_pack_roots_preserved":passed,"manual_registry_edit_admissible":False,"unregistered_scopes_admissible":False,
  "scope_removal_after_anchor_allowed":False,"automatic_wagering_authorized":False,"controlled_live_admissible":False,"production_admissible":False,
  "network_calls_performed":False,"blocking_codes":sorted(set(errors)),"output_payload_sha256":None}
 h=dict(out);h["output_payload_sha256"]=None;out["output_payload_sha256"]=canon(h);return out

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True);ns=ap.parse_args();ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip)
 out=evaluate(data,input_path=ip);op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 ok=out["result"]=="PASS";print("RESULT="+("PASS" if ok else "FAIL_CLOSED"));print("SCOPE_REGISTRY_ADMITTED="+str(bool(out["scope_registry_admitted"])).upper())
 print("BUILDER_INDEPENDENT_RERUN="+out["builder_independent_rerun"]);print("SUPPORTABILITY_PACK_ROOTS_PRESERVED="+str(out["supportability_pack_roots_preserved"]).upper())
 print("MANUAL_REGISTRY_EDIT_ADMISSIBLE=FALSE");print("CONTROLLED_LIVE_ADMISSIBLE=FALSE");print("PRODUCTION_ADMISSIBLE=FALSE")
 print("BLOCKING_CODES="+(",".join(out["blocking_codes"]) if out["blocking_codes"] else "<NONE>"));print("EVIDENCE="+str(op));print("EVIDENCE_SHA256="+fsha(op));return 0 if ok else 2
if __name__=="__main__":raise SystemExit(main())
