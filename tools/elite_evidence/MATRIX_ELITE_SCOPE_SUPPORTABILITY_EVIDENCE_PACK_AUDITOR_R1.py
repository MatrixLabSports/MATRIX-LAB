from __future__ import annotations
import argparse,json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

SCHEMA="MATRIX_ELITE_SCOPE_SUPPORTABILITY_EVIDENCE_PACK_AUDIT_R1"
INPUT_SCHEMA="MATRIX_ELITE_SCOPE_SUPPORTABILITY_EVIDENCE_PACK_AUDIT_INPUT_R1"
PACK_SCHEMA="MATRIX_ELITE_SCOPE_SUPPORTABILITY_EVIDENCE_PACK_R1"
INPUT_CONTRACT_SHA256="dc4b94a9bfa72bcc37d360778fa7669afc359a6168a959d0e6ceec53d6a0d153"
EXPECTED_RUBRIC_SHA256="88cb406880575c943ffee466ed774e109de55a39d58e353af3a1c098eaa51d27"
REQ_PRED={'pit_data_contract', 'settlement_rules', 'canonical_market_definition', 'identity_contract', 'baseline_definition', 'evaluation_protocol', 'sample_requirement_policy', 'rights_profile', 'risk_policy', 'odds_binding_contract'}
REQ_LIVE={'staleness_policy', 'event_time_contract', 'replay_protocol', 'shadow_live_protocol', 'live_window_policy'}
REQ_FAIL={'identity_reconciliation_contract', 'schema_compatibility_contract', 'secondary_rights_profile', 'rollback_plan', 'human_approval_policy', 'primary_rights_profile'}
ID_PRED=('scope_id', 'sport', 'competition', 'market', 'model_version', 'feature_version', 'market_semantics_version', 'settlement_rules_version', 'data_contract_version', 'identity_contract_version', 'rights_profile_version', 'odds_contract_version', 'evaluation_protocol_version', 'sample_requirement_policy_version', 'risk_class')
ID_LIVE=('live_scope_id', 'sport', 'market', 'model_version', 'feature_version', 'event_time_contract_version', 'live_window_policy_version', 'staleness_policy_version', 'replay_protocol_version', 'shadow_live_protocol_version')
ID_FAIL=('failover_scope_id', 'primary_provider', 'secondary_provider', 'environment', 'schema_compatibility_contract_version', 'identity_reconciliation_contract_version', 'primary_rights_profile_version', 'secondary_rights_profile_version', 'human_approval_policy_version', 'rollback_plan_version')
FORBIDDEN_KEYS={'logloss', 'model_edge', 'losses', 'profitability', 'win_rate', 'brier', 'campaign_result', 'net_return', 'pnl', 'wins', 'campaign_results', 'roi', 'profit', 'ece', 'clv', 'calibration_error', 'realized_ev', 'hit_rate'}
FORBIDDEN_TOKENS=('roi', 'win rate', 'hit rate', 'clv', 'brier', 'logloss', 'profit', 'profitable', 'losing', 'winning', 'recent results', 'campaign performance', 'realized ev')

def readj(p:Path)->dict[str,Any]:
 x=json.loads(p.read_text(encoding="utf-8-sig"))
 if not isinstance(x,dict):raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
 return x
def fsha(p:Path)->str:return sha256(p.read_bytes()).hexdigest()
def canon(x:Any)->str:return sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
def dt(v:Any)->datetime:
 x=datetime.fromisoformat(str(v).replace("Z","+00:00"))
 if x.tzinfo is None or x.utcoffset() is None:raise ValueError("REVIEWED_AT_MUST_BE_TIMEZONE_AWARE")
 return x
def nonempty(v:Any,code:str)->str:
 s=str(v or "").strip()
 if not s:raise ValueError(code)
 if "<" in s or ">" in s:raise ValueError("PLACEHOLDER_TEXT_DETECTED")
 return s
def scan_keys(x:Any,path:str,errors:list[str]):
 if isinstance(x,dict):
  for k,v in x.items():
   kk=str(k).strip().lower()
   if kk in FORBIDDEN_KEYS:errors.append("FORBIDDEN_PERFORMANCE_KEY:"+path+"/"+kk)
   scan_keys(v,path+"/"+kk,errors)
 elif isinstance(x,list):
  for i,v in enumerate(x):scan_keys(v,path+"/"+str(i),errors)
def has_perf_text(v:Any)->bool:
 s=" ".join(str(v or "").lower().split())
 return any(tok in s for tok in FORBIDDEN_TOKENS)
def exact_ref(ref:Any,errors:list[str],prefix:str):
 if not isinstance(ref,dict):errors.append(prefix+"_REF_MUST_BE_OBJECT");return
 try:
  p=Path(ref["path"]).resolve();expected=str(ref["sha256"])
  if not p.is_file():errors.append(prefix+"_FILE_MISSING");return
  if len(expected)!=64 or fsha(p)!=expected:errors.append(prefix+"_SHA_MISMATCH")
 except Exception:errors.append(prefix+"_REF_INVALID")

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--input",required=True);ap.add_argument("--output",required=True);ns=ap.parse_args()
 ip=Path(ns.input).resolve();op=Path(ns.output).resolve();data=readj(ip);errors=[]
 if data.get("schema")!=INPUT_SCHEMA:errors.append("INPUT_SCHEMA_MISMATCH")
 rub=Path(data.get("eligibility_rubric_path","")).resolve()
 if not rub.is_file() or fsha(rub)!=EXPECTED_RUBRIC_SHA256:errors.append("ELIGIBILITY_RUBRIC_NOT_CANONICAL")
 pp=Path(data.get("evidence_pack_path","")).resolve();pack={}
 if not pp.is_file():errors.append("EVIDENCE_PACK_MISSING")
 elif fsha(pp)!=data.get("evidence_pack_sha256"):errors.append("EVIDENCE_PACK_SHA_MISMATCH")
 else:
  try:pack=readj(pp)
  except Exception:errors.append("EVIDENCE_PACK_INVALID")
 ptype=None;required=set();ids=[];identity_fields=()
 if pack:
  if pack.get("schema")!=PACK_SCHEMA:errors.append("EVIDENCE_PACK_SCHEMA_MISMATCH")
  if pack.get("status") in (None,"TEMPLATE_NOT_VALID_EVIDENCE"):errors.append("EVIDENCE_PACK_NOT_FINAL")
  if pack.get("support_declared_by_this_pack") is not False:errors.append("PACK_MUST_NOT_DECLARE_SUPPORT")
  if pack.get("performance_information_available_to_reviewer") is not False:errors.append("PERFORMANCE_INFORMATION_MUST_NOT_BE_AVAILABLE")
  if pack.get("performance_information_used_for_verdicts") is not False:errors.append("PERFORMANCE_INFORMATION_MUST_NOT_BE_USED")
  scan_keys(pack,"pack",errors)
  try:nonempty(pack.get("candidate_id"),"CANDIDATE_ID_REQUIRED")
  except ValueError as exc:errors.append(str(exc))
  try:nonempty(pack.get("reviewer"),"REVIEWER_REQUIRED")
  except ValueError as exc:errors.append(str(exc))
  try:dt(pack.get("reviewed_at"))
  except Exception as exc:errors.append(str(exc))
  ptype=str(pack.get("pack_type","")).strip()
  if ptype=="PREDICTIVE":
   required=REQ_PRED;identity_fields=ID_PRED
   if pack.get("sport") not in ("football","tennis"):errors.append("PREDICTIVE_SPORT_INVALID")
  elif ptype=="LIVE":
   required=REQ_LIVE;identity_fields=ID_LIVE
   if pack.get("sport") not in ("football","tennis"):errors.append("LIVE_SPORT_INVALID")
  elif ptype=="FAILOVER":
   required=REQ_FAIL;identity_fields=ID_FAIL
  else:errors.append("PACK_TYPE_INVALID")
  for field in identity_fields:
   try:nonempty(pack.get(field),ptype+"_"+field.upper()+"_REQUIRED")
   except ValueError as exc:errors.append(str(exc))
  if ptype=="FAILOVER":
   if str(pack.get("primary_provider"))==str(pack.get("secondary_provider")):errors.append("FAILOVER_PROVIDERS_MUST_DIFFER")
   if pack.get("environment") not in ("STAGING","SHADOW"):errors.append("FAILOVER_ENVIRONMENT_INVALID")
  controls=list(pack.get("controls") or [])
  if not controls:errors.append("CONTROLS_REQUIRED")
  for i,ctl in enumerate(controls):
   pref="CONTROL_"+str(i)
   try:
    cid=nonempty(ctl.get("control_id"),pref+"_ID_REQUIRED");ids.append(cid)
    if ctl.get("verdict")!="PASS":errors.append(pref+"_VERDICT_NOT_PASS")
    rationale=nonempty(ctl.get("rationale"),pref+"_RATIONALE_REQUIRED")
    if has_perf_text(rationale):errors.append(pref+"_PERFORMANCE_RATIONALE_FORBIDDEN")
    refs=list(ctl.get("evidence_refs") or [])
    if not refs:errors.append(pref+"_EVIDENCE_REFS_REQUIRED")
    for j,ref in enumerate(refs):exact_ref(ref,errors,pref+"_REF_"+str(j))
   except ValueError as exc:errors.append(str(exc))
  if len(ids)!=len(set(ids)):errors.append("DUPLICATE_CONTROL_ID")
  if set(ids)!=required:errors.append("CONTROL_SET_MISMATCH")
 passed=not errors
 identity={k:pack.get(k) for k in identity_fields} if pack else {}
 out={"schema":SCHEMA,"result":"PASS" if passed else "FAIL_CLOSED","running_auditor_path":str(Path(__file__).resolve()),"running_auditor_sha256":fsha(Path(__file__).resolve()),
  "input_contract_sha256":INPUT_CONTRACT_SHA256,"input_path":str(ip),"input_sha256":fsha(ip),"eligibility_rubric_sha256":EXPECTED_RUBRIC_SHA256,
  "evidence_pack_path":str(pp) if pp else None,"evidence_pack_sha256":fsha(pp) if pp.is_file() else None,"pack_type":ptype,"candidate_id":pack.get("candidate_id") if pack else None,
  "identity":identity,"control_count":len(ids),"required_control_count":len(required),"supportability_pack_admitted":passed,"support_declared_by_this_audit":False,
  "performance_based_supportability_detected":any("PERFORMANCE" in x or x.startswith("FORBIDDEN_PERFORMANCE") for x in errors),
  "automatic_model_promotion":False,"automatic_provider_switch":False,"automatic_wagering_authorized":False,"controlled_live_admissible":False,"production_admissible":False,"network_calls_performed":False,
  "blocking_codes":sorted(set(errors)),"output_payload_sha256":None}
 h=dict(out);h["output_payload_sha256"]=None;out["output_payload_sha256"]=canon(h)
 op.parent.mkdir(parents=True,exist_ok=True);op.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
 print("RESULT="+("PASS" if passed else "FAIL_CLOSED"));print("SUPPORTABILITY_PACK_ADMITTED="+str(passed).upper());print("PACK_TYPE="+str(ptype));print("CONTROLS="+str(len(ids))+"/"+str(len(required)))
 print("SUPPORT_DECLARED_BY_THIS_AUDIT=FALSE");print("CONTROLLED_LIVE_ADMISSIBLE=FALSE");print("PRODUCTION_ADMISSIBLE=FALSE")
 print("BLOCKING_CODES="+(",".join(out["blocking_codes"]) if out["blocking_codes"] else "<NONE>"));print("EVIDENCE="+str(op));print("EVIDENCE_SHA256="+fsha(op));return 0 if passed else 2
if __name__=="__main__":raise SystemExit(main())
