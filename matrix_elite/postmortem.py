from __future__ import annotations

ALLOWED_CAUSES={
    "LEGITIMATE_VARIANCE","DATA_ERROR","LEAKAGE","IDENTITY_ERROR","MODEL_ERROR",
    "CALIBRATION_ERROR","PRICE_EV_ERROR","EXECUTION_ERROR","LATENCY_ERROR",
    "CONTEXT_ERROR","RISK_ERROR","SETTLEMENT_ERROR","UNKNOWN_REQUIRES_REVIEW"
}

def classify_outcome(*, primary_cause: str, evidence: tuple[str,...]) -> dict:
    if primary_cause not in ALLOWED_CAUSES: raise ValueError("POSTMORTEM_CAUSE_INVALID")
    if primary_cause == "LEGITIMATE_VARIANCE" and not evidence:
        raise ValueError("VARIANCE_REQUIRES_EVIDENCE")
    return {"primary_cause":primary_cause,"evidence":list(evidence),"review_required":primary_cause=="UNKNOWN_REQUIRES_REVIEW"}
