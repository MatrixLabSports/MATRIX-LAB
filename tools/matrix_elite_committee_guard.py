from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"config"/"MATRIX_ELITE_COMMITTEE_REGISTRY.json"

REQUIRED_ROLES={
"PRODUCT_DIRECTOR","QUANT_DIRECTOR","CALIBRATION_MODELING_LEAD","TEMPORAL_INTEGRITY_ENGINEER",
"SPORTS_MARKET_SPECIALIST","MARKET_PRICE_MAPPING_ENGINEER","PRINCIPAL_REALTIME_RELIABILITY_ODDS_ENGINEER",
"MARKET_DATA_INTEGRATION_ENGINEER","OBSERVABILITY_INCIDENT_ENGINEER","TELEGRAM_DELIVERY_ENGINEER",
"CLV_RISK_ENGINEER","CORRELATED_RISK_ENGINEER","CHIEF_RISK_OFFICER","QA_REGRESSION_LEAD",
"EVIDENCE_AUDIT_LEAD","DATA_GOVERNANCE_AUDITOR","FINANCE_LEAD","PRICING_STRATEGIST",
"SUBSCRIPTION_PRODUCT_MANAGER","CRM_RETENTION_LEAD","CUSTOMER_EXPERIENCE_LEAD","ANTI_FRAUD_LEAD",
"PRIVACY_SECURITY_LEAD","CONSUMER_COMPLIANCE_LEAD","RESPONSIBLE_GAMBLING_LEAD","TAX_ACCOUNTING_ADVISOR",
"BRAND_STRATEGIST","NAMING_SPECIALIST","BRAND_IDENTITY_DESIGNER","ART_DIRECTOR","COLOR_STRATEGIST",
"SPORTS_MARKETING_DIRECTOR","GROWTH_LEAD","PAID_MEDIA_STRATEGIST","SPONSORSHIP_RESEARCH_ANALYST",
"BRAND_PARTNERSHIPS_MANAGER"
}

def load():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))

def validate(data):
    roles=data.get("roles") or []
    ids=[r.get("id") for r in roles]
    if len(ids)!=len(set(ids)):
        raise RuntimeError("DUPLICATE_COMMITTEE_ROLE_ID")
    missing=sorted(REQUIRED_ROLES-set(ids))
    if missing:
        raise RuntimeError(f"MISSING_REQUIRED_ROLES {missing}")
    if data.get("role_count")!=len(roles):
        raise RuntimeError("ROLE_COUNT_MISMATCH")
    esc=data.get("escalation") or {}
    if esc.get("pipeline_signal_loss_owner")!="PRINCIPAL_REALTIME_RELIABILITY_ODDS_ENGINEER":
        raise RuntimeError("PIPELINE_SIGNAL_LOSS_OWNER_INVALID")
    realtime=next(r for r in roles if r["id"]=="PRINCIPAL_REALTIME_RELIABILITY_ODDS_ENGINEER")
    if "candidate_to_telegram_pipeline" not in realtime.get("owner_of",[]):
        raise RuntimeError("REALTIME_OWNER_SCOPE_INCOMPLETE")
    if "eligible_candidates_lost_to_infrastructure_before_kickoff=0" not in realtime.get("kpis",[]):
        raise RuntimeError("REALTIME_KPI_MISSING")
    return {"status":"PASS","role_count":len(roles),"domains":sorted({r["domain"] for r in roles})}

def main():
    print(json.dumps(validate(load()),sort_keys=True))

if __name__=="__main__":
    main()
