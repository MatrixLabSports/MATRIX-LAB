from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from statistics import mean, median
from typing import Any

SCHEMA = "MATRIX_ELITE_C02_REAL_PROSPECTIVE_PAPER_TRADING_EVIDENCE_R3"
INPUT_SCHEMA = "MATRIX_ELITE_C02_REAL_PROSPECTIVE_PAPER_TRADING_INPUT_R3"
PLAN_SCHEMA = "MATRIX_ELITE_C02_PROSPECTIVE_PAPER_TRADING_PLAN_R3"
SETTLEMENT_SCHEMA = "MATRIX_ELITE_C02_SETTLEMENT_EVIDENCE_R1"
INPUT_CONTRACT_SHA256="aabdad0f70ec4637af1a5fda1e0465a7cc6d81dbc6d0bdea289b82833075f3ce"
ALLOWED_ANCHOR_TYPES = {
    "RFC3161_TSA",
    "WORM_OBJECT_VERSION",
    "EXTERNAL_AUDIT_LEDGER",
    "SIGNED_TRANSPARENCY_LOG",
}
ALLOWED_POSTMORTEM = {
    "LEGITIMATE_VARIANCE",
    "DATA_ERROR",
    "LEAKAGE_ERROR",
    "IDENTITY_ERROR",
    "MODEL_ERROR",
    "CALIBRATION_ERROR",
    "PRICE_EV_ERROR",
    "EXECUTION_ERROR",
    "LATENCY_ERROR",
    "CONTEXT_ERROR",
    "RISK_ERROR",
    "SETTLEMENT_ERROR",
    "NO_BET_CORRECT",
    "MISSED_OPPORTUNITY",
    "UNKNOWN_REQUIRES_REVIEW",
}

def dt(value: str) -> datetime:
    x = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if x.tzinfo is None or x.utcoffset() is None:
        raise ValueError("TIME_MUST_BE_TIMEZONE_AWARE")
    return x

def readj(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value

def fsha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()

def canonical_hash(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()

def valid_sha(value: Any) -> bool:
    try:
        return isinstance(value, str) and len(value) == 64 and int(value, 16) >= 0
    except Exception:
        return False

def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    p = (len(s) - 1) * q
    lo = int(p)
    hi = min(lo + 1, len(s) - 1)
    frac = p - lo
    return s[lo] * (1 - frac) + s[hi] * frac

def record_digest(record: dict[str, Any]) -> str:
    core = {
        "sequence": record["sequence"],
        "previous_record_sha256": record.get("previous_record_sha256"),
        "recorded_at": record["recorded_at"],
        "payload": record["payload"],
    }
    return canonical_hash(core)

def verify_chain(
    records: list[dict[str, Any]],
    *,
    label: str,
    errors: list[str],
) -> tuple[dict[int, str], dict[str, dict[str, Any]]]:
    seq_to_sha: dict[int, str] = {}
    by_id: dict[str, dict[str, Any]] = {}
    expected_prev = None
    for expected_seq, record in enumerate(records, start=1):
        try:
            seq = int(record["sequence"])
            if seq != expected_seq:
                raise ValueError(f"{label}_SEQUENCE_GAP_OR_REORDER")
            if record.get("previous_record_sha256") != expected_prev:
                raise ValueError(f"{label}_CHAIN_MISMATCH")
            digest = record_digest(record)
            if record.get("record_sha256") != digest:
                raise ValueError(f"{label}_RECORD_HASH_MISMATCH")
            payload = record["payload"]
            record_id = str(payload.get("candidate_id") or payload.get("decision_id") or payload.get("review_id") or "")
            if not record_id:
                raise ValueError(f"{label}_RECORD_ID_REQUIRED")
            if record_id in by_id:
                raise ValueError(f"{label}_DUPLICATE_RECORD_ID")
            seq_to_sha[seq] = digest
            by_id[record_id] = record
            expected_prev = digest
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    return seq_to_sha, by_id

def verify_anchor_evidence(anchor: dict[str, Any], errors: list[str]) -> None:
    try:
        if anchor.get("anchor_type") not in ALLOWED_ANCHOR_TYPES:
            raise ValueError("UNTRUSTED_TIMESTAMP_ANCHOR_TYPE")
        if anchor.get("verification_result") != "PASS":
            raise ValueError("TIMESTAMP_ANCHOR_NOT_VERIFIED")
        evidence_path = Path(anchor["anchor_evidence_path"]).resolve()
        if not evidence_path.is_file():
            raise ValueError("TIMESTAMP_ANCHOR_EVIDENCE_MISSING")
        if fsha(evidence_path) != anchor.get("anchor_evidence_sha256"):
            raise ValueError("TIMESTAMP_ANCHOR_EVIDENCE_SHA_MISMATCH")
        if not valid_sha(anchor.get("root_sha256")):
            raise ValueError("TIMESTAMP_ANCHOR_ROOT_SHA_INVALID")
        anchor_at = dt(anchor["anchored_at"])
        proof = readj(evidence_path)
        if proof.get("schema") != "MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1" or proof.get("result") != "PASS":
            raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_SCHEMA_OR_RESULT_INVALID")
        if proof.get("anchor_type") != anchor.get("anchor_type"):
            raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_TYPE_MISMATCH")
        if proof.get("root_sha256") != anchor.get("root_sha256"):
            raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_ROOT_MISMATCH")
        if dt(proof["anchored_at"]) != anchor_at:
            raise ValueError("TIMESTAMP_ANCHOR_VERIFICATION_TIME_MISMATCH")
        if not str(proof.get("verifier", "")).strip():
            raise ValueError("TIMESTAMP_ANCHOR_VERIFIER_REQUIRED")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))

def find_pre_event_anchor(
    *,
    sequence: int,
    event_start_at: datetime,
    recorded_at: datetime,
    anchors: list[dict[str, Any]],
    seq_to_sha: dict[int, str],
    max_anchor_delay: timedelta,
) -> dict[str, Any] | None:
    candidates = []
    for anchor in anchors:
        try:
            through = int(anchor["through_sequence"])
            if through < sequence:
                continue
            root = seq_to_sha.get(through)
            if root is None or root != anchor.get("root_sha256"):
                continue
            at = dt(anchor["anchored_at"])
            if at < recorded_at or at >= event_start_at:
                continue
            if at - recorded_at > max_anchor_delay:
                continue
            if anchor.get("verification_result") != "PASS" or anchor.get("anchor_type") not in ALLOWED_ANCHOR_TYPES:
                continue
            evidence_path = Path(anchor["anchor_evidence_path"]).resolve()
            if not evidence_path.is_file() or fsha(evidence_path) != anchor.get("anchor_evidence_sha256"):
                continue
            proof = readj(evidence_path)
            if proof.get("schema") != "MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1" or proof.get("result") != "PASS":
                continue
            if proof.get("anchor_type") != anchor.get("anchor_type") or proof.get("root_sha256") != anchor.get("root_sha256"):
                continue
            if dt(proof["anchored_at"]) != at or not str(proof.get("verifier", "")).strip():
                continue
            candidates.append((at, anchor))
        except Exception:
            continue
    return min(candidates, key=lambda x: x[0])[1] if candidates else None

def find_anchor_before_cutoff(
    *,
    sequence: int,
    cutoff_at: datetime,
    recorded_at: datetime,
    anchors: list[dict[str, Any]],
    seq_to_sha: dict[int, str],
    max_anchor_delay: timedelta | None = None,
) -> dict[str, Any] | None:
    candidates = []
    for anchor in anchors:
        try:
            through = int(anchor["through_sequence"])
            if through < sequence:
                continue
            root = seq_to_sha.get(through)
            if root is None or root != anchor.get("root_sha256"):
                continue
            at = dt(anchor["anchored_at"])
            if at < recorded_at or at >= cutoff_at:
                continue
            if max_anchor_delay is not None and at - recorded_at > max_anchor_delay:
                continue
            if anchor.get("verification_result") != "PASS" or anchor.get("anchor_type") not in ALLOWED_ANCHOR_TYPES:
                continue
            evidence_path = Path(anchor["anchor_evidence_path"]).resolve()
            if not evidence_path.is_file() or fsha(evidence_path) != anchor.get("anchor_evidence_sha256"):
                continue
            proof = readj(evidence_path)
            if proof.get("schema") != "MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1" or proof.get("result") != "PASS":
                continue
            if proof.get("anchor_type") != anchor.get("anchor_type") or proof.get("root_sha256") != anchor.get("root_sha256"):
                continue
            if dt(proof["anchored_at"]) != at or not str(proof.get("verifier", "")).strip():
                continue
            candidates.append((at, anchor))
        except Exception:
            continue
    return min(candidates, key=lambda x: x[0])[1] if candidates else None

def verify_plan_registration_anchor(
    *,
    plan_path: Path,
    plan: dict[str, Any],
    anchor: dict[str, Any] | None,
    sample_start: datetime,
    errors: list[str],
) -> bool:
    if not isinstance(anchor, dict):
        errors.append("PLAN_REGISTRATION_INDEPENDENT_ANCHOR_REQUIRED")
        return False
    verify_anchor_evidence(anchor, errors)
    try:
        if anchor.get("root_sha256") != fsha(plan_path):
            raise ValueError("PLAN_REGISTRATION_ANCHOR_ROOT_MISMATCH")
        if int(anchor.get("through_sequence", -1)) != 1:
            raise ValueError("PLAN_REGISTRATION_ANCHOR_SEQUENCE_INVALID")
        registered_at = dt(plan["registered_at"])
        anchored_at = dt(anchor["anchored_at"])
        if anchored_at < registered_at:
            raise ValueError("PLAN_ANCHORED_BEFORE_REGISTERED_AT")
        if anchored_at >= sample_start:
            raise ValueError("PLAN_NOT_INDEPENDENTLY_ANCHORED_BEFORE_SAMPLE_START")
        return True
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
        return False

def load_settlement(review: dict[str, Any], decision: dict[str, Any], errors: list[str]) -> dict[str, Any] | None:
    try:
        path = Path(review["settlement_evidence_path"]).resolve()
        if not path.is_file():
            raise ValueError("SETTLEMENT_EVIDENCE_MISSING")
        if fsha(path) != review.get("settlement_evidence_sha256"):
            raise ValueError("SETTLEMENT_EVIDENCE_SHA_MISMATCH")
        s = readj(path)
        if s.get("schema") != SETTLEMENT_SCHEMA:
            raise ValueError("SETTLEMENT_SCHEMA_MISMATCH")
        for key in ("decision_id", "event_id", "market_id", "selection_id"):
            expected = decision["decision_id"] if key == "decision_id" else decision[key]
            if str(s.get(key)) != str(expected):
                raise ValueError("SETTLEMENT_DECISION_BINDING_MISMATCH")
        if s.get("outcome") not in {"WIN", "LOSS", "PUSH", "VOID"}:
            raise ValueError("SETTLEMENT_OUTCOME_INVALID")
        if dt(s["settled_at"]) <= dt(decision["event_start_at"]):
            raise ValueError("SETTLEMENT_TOO_EARLY")
        return s
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
        return None

def expected_pnl(*, outcome: str, odds: float, stake: float) -> float:
    if outcome == "WIN":
        return stake * (odds - 1.0)
    if outcome == "LOSS":
        return -stake
    return 0.0

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ns = ap.parse_args()
    ip = Path(ns.input).resolve()
    op = Path(ns.output).resolve()
    data = readj(ip)
    errors: list[str] = []

    if data.get("schema") != INPUT_SCHEMA:
        errors.append("INPUT_SCHEMA_MISMATCH")

    # Upstream OOS and prospective market evidence are both exact-SHA-bound.
    try:
        oos_path = Path(data["upstream_oos_evidence_path"]).resolve()
        market_path = Path(data["prospective_market_evidence_path"]).resolve()
        plan_path = Path(data["paper_trading_plan_path"]).resolve()
        oos = readj(oos_path)
        market = readj(market_path)
        plan = readj(plan_path)
        if fsha(oos_path) != data.get("upstream_oos_evidence_sha256"):
            errors.append("UPSTREAM_OOS_EVIDENCE_SHA_MISMATCH")
        if fsha(market_path) != data.get("prospective_market_evidence_sha256"):
            errors.append("PROSPECTIVE_MARKET_EVIDENCE_SHA_MISMATCH")
        if fsha(plan_path) != data.get("paper_trading_plan_sha256"):
            errors.append("PAPER_TRADING_PLAN_SHA_MISMATCH")
        if oos.get("schema") not in {"MATRIX_ELITE_C01_REAL_OOS_EVIDENCE_R2", "MATRIX_ELITE_C01_REAL_OOS_EVIDENCE_R1"} or oos.get("result") != "PASS" or oos.get("oos_edge_evidence_passed") is not True:
            errors.append("UPSTREAM_OOS_EVIDENCE_NOT_PASS")
        if market.get("schema") != "MATRIX_ELITE_C05_REAL_LINE_HISTORY_CLV_EVIDENCE_R1" or market.get("result") != "PASS" or market.get("market_line_history_clv_evidence_passed") is not True:
            errors.append("PROSPECTIVE_MARKET_EVIDENCE_NOT_PASS")
        if plan.get("schema") != PLAN_SCHEMA:
            errors.append("PAPER_TRADING_PLAN_SCHEMA_MISMATCH")
        justification_path = Path(plan["sample_size_justification_path"]).resolve()
        if not justification_path.is_file():
            errors.append("SAMPLE_SIZE_JUSTIFICATION_MISSING")
            justification = {}
        else:
            if fsha(justification_path) != plan.get("sample_size_justification_sha256"):
                errors.append("SAMPLE_SIZE_JUSTIFICATION_SHA_MISMATCH")
            justification = readj(justification_path)
            if justification.get("schema") != "MATRIX_ELITE_C02_SAMPLE_SIZE_JUSTIFICATION_R1" or justification.get("result") != "PASS":
                errors.append("SAMPLE_SIZE_JUSTIFICATION_NOT_PASS")
            if justification.get("method") not in {"POWER_ANALYSIS", "PRECISION_TARGET", "PREREGISTERED_SEQUENTIAL_DESIGN"}:
                errors.append("SAMPLE_SIZE_JUSTIFICATION_METHOD_INVALID")
            if not valid_sha(justification.get("assumptions_sha256")) or not valid_sha(justification.get("calculation_evidence_sha256")):
                errors.append("SAMPLE_SIZE_JUSTIFICATION_EVIDENCE_HASH_REQUIRED")
    except (KeyError, OSError, ValueError) as exc:
        errors.append(str(exc))
        oos, market, plan = {}, {}, {}

    # Pre-registration and immutable process design.
    try:
        registered_at = dt(plan["registered_at"])
        sample_start = dt(plan["sample_start_at"])
        sample_end = dt(plan["sample_end_at"])
        if registered_at >= sample_start:
            errors.append("PLAN_NOT_REGISTERED_BEFORE_SAMPLE_START")
        if sample_end <= sample_start:
            errors.append("PAPER_SAMPLE_WINDOW_INVALID")
        min_total = int(plan["minimum_total_decisions"])
        min_bets = int(plan["minimum_paper_bets"])
        min_no_bets = int(plan["minimum_no_bets"])
        min_days = float(plan["minimum_sample_duration_days"])
        max_seal_lag = timedelta(seconds=int(plan["max_decision_seal_lag_seconds"]))
        max_anchor_delay = timedelta(seconds=int(plan["max_decision_anchor_delay_seconds"]))
        max_quote_age = timedelta(seconds=int(plan["max_quote_age_seconds"]))
        max_combo_fraction = float(plan["maximum_combo_fraction"])
        min_odds = float(plan["default_min_decimal_odds"])
        require_anchor = bool(plan["independent_timestamp_anchor_required"])
        if min_total < 20 or min_bets < 1 or min_no_bets < 1:
            errors.append("PAPER_SAMPLE_MINIMUMS_TOO_WEAK")
        try:
            if min_total < int(justification["recommended_minimum_total_decisions"]):
                errors.append("PLAN_TOTAL_DECISIONS_BELOW_JUSTIFIED_MINIMUM")
            if min_bets < int(justification["recommended_minimum_paper_bets"]):
                errors.append("PLAN_PAPER_BETS_BELOW_JUSTIFIED_MINIMUM")
            if min_no_bets < int(justification["recommended_minimum_no_bets"]):
                errors.append("PLAN_NO_BETS_BELOW_JUSTIFIED_MINIMUM")
            if min_days < float(justification["recommended_minimum_sample_duration_days"]):
                errors.append("PLAN_DURATION_BELOW_JUSTIFIED_MINIMUM")
        except (KeyError, TypeError, ValueError):
            errors.append("SAMPLE_SIZE_JUSTIFICATION_RECOMMENDATIONS_INVALID")
        if min_days < 1 or (sample_end - sample_start).total_seconds() < min_days * 86400:
            errors.append("PAPER_SAMPLE_DURATION_TOO_SHORT")
        if max_seal_lag.total_seconds() <= 0 or max_seal_lag.total_seconds() > 300:
            errors.append("DECISION_SEAL_LAG_POLICY_INVALID")
        if max_anchor_delay.total_seconds() <= 0 or max_anchor_delay.total_seconds() > 1800:
            errors.append("DECISION_ANCHOR_DELAY_POLICY_INVALID")
        if max_quote_age.total_seconds() < 0:
            errors.append("QUOTE_AGE_POLICY_INVALID")
        if max_combo_fraction < 0 or max_combo_fraction > 0.10:
            errors.append("COMBO_FRACTION_POLICY_EXCEEDS_MATRIX_LIMIT")
        if min_odds < 1.70:
            errors.append("DEFAULT_MIN_ODDS_BELOW_MATRIX_POLICY")
        if not require_anchor:
            errors.append("INDEPENDENT_TIMESTAMP_ANCHOR_REQUIRED")
        if plan.get("performance_policy") != "REPORT_ONLY_FOR_C02_PROCESS_GATE":
            errors.append("C02_PERFORMANCE_POLICY_MUST_BE_REPORT_ONLY")
        plan_sport = str(plan["sport"])
        plan_competition = str(plan["competition"])
        plan_market = str(plan["market"])
        plan_model_version = str(plan["model_version"])
        plan_feature_version = str(plan["feature_version"])
        if plan_sport not in {"football", "tennis"}:
            errors.append("PLAN_SPORT_INVALID")
        if not all(x.strip() for x in (plan_competition, plan_market, plan_model_version, plan_feature_version)):
            errors.append("PLAN_SCOPE_METADATA_REQUIRED")
        if (str(oos.get("sport","")), str(oos.get("competition","")), str(oos.get("market",""))) != (plan_sport, plan_competition, plan_market):
            errors.append("OOS_PLAN_SCOPE_MISMATCH")
        if (str(market.get("sport","")), str(market.get("competition","")), str(market.get("market",""))) != (plan_sport, plan_competition, plan_market):
            errors.append("C05_PLAN_SCOPE_MISMATCH")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
        sample_start = sample_end = None
        max_seal_lag = max_anchor_delay = max_quote_age = timedelta(0)
        min_total = min_bets = min_no_bets = 10**9
        max_combo_fraction = 0.10
        min_odds = 1.70
        plan_sport = plan_competition = plan_market = plan_model_version = plan_feature_version = ""

    opportunities = list(data.get("opportunity_records") or [])
    decisions = list(data.get("decision_records") or [])
    reviews = list(data.get("review_records") or [])
    opportunity_anchors = list(data.get("opportunity_timestamp_anchors") or [])
    decision_anchors = list(data.get("decision_timestamp_anchors") or [])
    review_anchors = list(data.get("review_timestamp_anchors") or [])
    plan_anchor = data.get("plan_registration_anchor")

    opp_seq, opp_by_id = verify_chain(opportunities, label="OPPORTUNITY", errors=errors)
    dec_seq, dec_by_id = verify_chain(decisions, label="DECISION", errors=errors)
    rev_seq, rev_by_id = verify_chain(reviews, label="REVIEW", errors=errors)

    for anchor in opportunity_anchors + decision_anchors + review_anchors:
        verify_anchor_evidence(anchor, errors)
    if sample_start is not None:
        verify_plan_registration_anchor(plan_path=plan_path, plan=plan, anchor=plan_anchor, sample_start=sample_start, errors=errors)

    market_by_id = {
        str(x.get("record_id")): x
        for x in (market.get("decision_evidence") or [])
        if isinstance(x, dict) and x.get("record_id") is not None
    }

    opportunity_to_decision: dict[str, dict[str, Any]] = {}
    decision_payloads: dict[str, dict[str, Any]] = {}
    decision_hashes: dict[str, str] = {}
    seal_lags: list[float] = []
    bet_decisions: list[dict[str, Any]] = []
    no_bet_decisions: list[dict[str, Any]] = []

    # Validate opportunity universe.
    for record in opportunities:
        try:
            p = record["payload"]
            generated = dt(p["generated_at"])
            start = dt(p["event_start_at"])
            if p.get("sport") not in {"football", "tennis"}:
                raise ValueError("SPORT_BOUNDARY_VIOLATION")
            if (str(p.get("sport")), str(p.get("competition")), str(p.get("market_id")), str(p.get("model_version")), str(p.get("feature_version"))) != (plan_sport, plan_competition, plan_market, plan_model_version, plan_feature_version):
                raise ValueError("OPPORTUNITY_PLAN_SCOPE_MISMATCH")
            if generated >= start:
                raise ValueError("OPPORTUNITY_NOT_GENERATED_PRE_EVENT")
            if sample_start and (generated < sample_start or generated > sample_end):
                raise ValueError("OPPORTUNITY_OUTSIDE_REGISTERED_SAMPLE")
            for key in ("data_snapshot_sha256", "identity_manifest_sha256", "rights_evidence_sha256", "thesis_sha256"):
                if not valid_sha(p.get(key)):
                    raise ValueError("OPPORTUNITY_REQUIRED_HASH_BINDING_MISSING")
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))

    # Validate every final decision and its exact prospective timestamp anchor.
    for record in decisions:
        try:
            p = record["payload"]
            decision_id = str(p["decision_id"])
            candidate_id = str(p["candidate_id"])
            if candidate_id not in opp_by_id:
                raise ValueError("DECISION_OPPORTUNITY_NOT_FOUND")
            if candidate_id in opportunity_to_decision:
                raise ValueError("MULTIPLE_DECISIONS_FOR_ONE_OPPORTUNITY")
            opp_record = opp_by_id[candidate_id]
            opp = opp_record["payload"]
            if str(p.get("opportunity_record_sha256")) != str(opp_record.get("record_sha256")):
                raise ValueError("DECISION_OPPORTUNITY_RECORD_HASH_MISMATCH")
            for key in ("sport", "competition", "event_id", "market_id", "selection_id", "event_start_at", "model_version", "feature_version",
                        "data_snapshot_sha256", "identity_manifest_sha256", "rights_evidence_sha256", "thesis_sha256"):
                if str(p.get(key)) != str(opp.get(key)):
                    raise ValueError("DECISION_OPPORTUNITY_BINDING_MISMATCH")
            decided_at = dt(p["decided_at"])
            recorded_at = dt(record["recorded_at"])
            event_start = dt(p["event_start_at"])
            generated_at = dt(opp["generated_at"])
            if decided_at < generated_at:
                raise ValueError("DECISION_PRECEDES_OPPORTUNITY")
            opp_anchor = find_anchor_before_cutoff(
                sequence=int(opp_record["sequence"]),
                cutoff_at=decided_at,
                recorded_at=dt(opp_record["recorded_at"]),
                anchors=opportunity_anchors,
                seq_to_sha=opp_seq,
                max_anchor_delay=max_anchor_delay,
            )
            if opp_anchor is None:
                raise ValueError("OPPORTUNITY_UNIVERSE_NOT_INDEPENDENTLY_ANCHORED_BEFORE_DECISION")
            if recorded_at < decided_at:
                raise ValueError("DECISION_RECORDED_BEFORE_DECIDED_AT")
            if recorded_at - decided_at > max_seal_lag:
                raise ValueError("DECISION_SEAL_LAG_EXCEEDED")
            if recorded_at >= event_start:
                raise ValueError("DECISION_NOT_PHYSICALLY_SEALED_PRE_EVENT")
            if sample_start and not (sample_start <= decided_at <= sample_end):
                raise ValueError("DECISION_OUTSIDE_REGISTERED_SAMPLE")
            anchor = find_pre_event_anchor(
                sequence=int(record["sequence"]),
                event_start_at=event_start,
                recorded_at=recorded_at,
                anchors=decision_anchors,
                seq_to_sha=dec_seq,
                max_anchor_delay=max_anchor_delay,
            )
            if anchor is None:
                raise ValueError("DECISION_INDEPENDENT_PRE_EVENT_TIMESTAMP_NOT_PROVEN")
            forbidden_pre_event_fields = {
                "outcome", "result", "pnl_units", "settled_at", "settlement_evidence_sha256",
                "closing_fair_probability", "closing_line_sha256", "probability_clv",
                "postmortem_primary_cause", "postmortem_evidence", "reviewed_at",
            }
            if forbidden_pre_event_fields.intersection(p):
                raise ValueError("POST_EVENT_FIELDS_FORBIDDEN_IN_FROZEN_DECISION")
            action = str(p["action"])
            if action not in {"PAPER_BET", "NO_BET"}:
                raise ValueError("FINAL_PAPER_ACTION_INVALID")
            bet_type = str(p.get("bet_type", "SIMPLE"))
            if bet_type not in {"SIMPLE", "COMBO"}:
                raise ValueError("BET_TYPE_INVALID")
            stake = float(p.get("stake_units", 0.0))
            odds = float(p["decimal_odds"])
            if odds <= 1:
                raise ValueError("DECIMAL_ODDS_INVALID")
            captured = dt(p["quote_captured_at"])
            if captured > decided_at:
                raise ValueError("DECISION_QUOTE_FROM_FUTURE")
            if decided_at - captured > max_quote_age:
                raise ValueError("DECISION_QUOTE_STALE")
            if not valid_sha(p.get("odds_snapshot_sha256")):
                raise ValueError("ODDS_SNAPSHOT_SHA_REQUIRED")
            prob = float(p["matrix_probability"])
            fair = float(p["fair_market_probability"])
            ev = float(p["expected_value"])
            if not 0 <= prob <= 1 or not 0 <= fair <= 1:
                raise ValueError("DECISION_PROBABILITY_INVALID")

            m = market_by_id.get(decision_id)
            if m is None:
                raise ValueError("PROSPECTIVE_DECISION_NOT_IN_C05_MARKET_EVIDENCE")
            for mk in ("event_id", "market_id", "selection_id"):
                if str(m.get(mk)) != str(p.get(mk)):
                    raise ValueError("C05_DECISION_SCOPE_MISMATCH")
            if dt(m["decision_at"]) != decided_at:
                raise ValueError("C05_DECISION_TIME_MISMATCH")
            if abs(float(m["model_probability"]) - prob) > 1e-12:
                raise ValueError("C05_MODEL_PROBABILITY_MISMATCH")
            if str(m["taken_quote_sha256"]) != str(p["odds_snapshot_sha256"]):
                raise ValueError("C05_QUOTE_HASH_MISMATCH")
            if abs(float(m["taken_decimal_odds"]) - odds) > 1e-12:
                raise ValueError("C05_ODDS_MISMATCH")
            if str(m["taken_provider"]) != str(p["price_provider"]):
                raise ValueError("C05_PROVIDER_MISMATCH")

            if action == "PAPER_BET":
                if not all(bool(p.get(k)) for k in ("data_quality_gate_passed", "calibration_gate_passed", "risk_gate_passed")):
                    raise ValueError("PAPER_BET_GATE_FAILURE")
                if ev <= 0:
                    raise ValueError("PAPER_BET_POSITIVE_EV_REQUIRED")
                if stake <= 0:
                    raise ValueError("PAPER_BET_POSITIVE_STAKE_REQUIRED")
                if odds < min_odds:
                    exc = p.get("odds_policy_exception")
                    if not isinstance(exc, dict) or not str(exc.get("exception_id", "")).strip() or not str(exc.get("rationale", "")).strip():
                        raise ValueError("LOW_ODDS_POLICY_EXCEPTION_REQUIRED")
                bet_decisions.append(p)
            else:
                if abs(stake) > 1e-12:
                    raise ValueError("NO_BET_STAKE_MUST_BE_ZERO")
                if str(p.get("no_bet_reason_code", "")).strip() == "":
                    raise ValueError("NO_BET_REASON_REQUIRED")
                no_bet_decisions.append(p)

            opportunity_to_decision[candidate_id] = p
            decision_payloads[decision_id] = p
            decision_hashes[decision_id] = record["record_sha256"]
            seal_lags.append((recorded_at - decided_at).total_seconds())
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))

    if set(opportunity_to_decision) != set(opp_by_id):
        errors.append("OPPORTUNITY_UNIVERSE_NOT_FULLY_DECIDED")

    combo_count = sum(1 for p in bet_decisions if p.get("bet_type") == "COMBO")
    combo_fraction = combo_count / len(bet_decisions) if bet_decisions else 0.0
    if combo_fraction > max_combo_fraction + 1e-12:
        errors.append("COMBO_FRACTION_EXCEEDS_REGISTERED_LIMIT")

    # Post-event reviews are separate immutable records.
    reviewed: set[str] = set()
    risked = 0.0
    pnl = 0.0
    clvs: list[float] = []
    no_bet_counterfactual_pnl = 0.0
    outcomes = Counter()
    causes = Counter()
    for record in reviews:
        try:
            r = record["payload"]
            decision_id = str(r["decision_id"])
            if decision_id not in decision_payloads:
                raise ValueError("REVIEW_DECISION_NOT_FOUND")
            if decision_id in reviewed:
                raise ValueError("DUPLICATE_DECISION_REVIEW")
            d = decision_payloads[decision_id]
            if str(r.get("decision_sha256")) != decision_hashes[decision_id]:
                raise ValueError("REVIEW_DECISION_HASH_MISMATCH")
            reviewed_at = dt(r["reviewed_at"])
            recorded_at = dt(record["recorded_at"])
            event_start = dt(d["event_start_at"])
            if reviewed_at <= event_start:
                raise ValueError("POST_EVENT_REVIEW_TOO_EARLY")
            if recorded_at < reviewed_at:
                raise ValueError("REVIEW_RECORDED_BEFORE_REVIEWED_AT")
            market_record = market_by_id[decision_id]
            closing_prob = float(r["closing_fair_probability"])
            if abs(closing_prob - float(market_record["closing_consensus_fair_probability"])) > 1e-12:
                raise ValueError("REVIEW_C05_CLOSING_PROBABILITY_MISMATCH")
            if str(r.get("closing_line_sha256")) != canonical_hash({
                "record_id": market_record["record_id"],
                "closing_consensus_fair_probability": market_record["closing_consensus_fair_probability"],
                "closing_providers_used": market_record["closing_providers_used"],
                "closing_latest_capture_at": market_record["closing_latest_capture_at"],
            }):
                raise ValueError("REVIEW_CLOSING_LINE_HASH_MISMATCH")

            settlement = load_settlement(r, d, errors)
            if settlement is None:
                raise ValueError("SETTLEMENT_INVALID")
            if reviewed_at < dt(settlement["settled_at"]):
                raise ValueError("REVIEW_PRECEDES_SETTLEMENT")

            cause = str(r["postmortem_primary_cause"])
            evidence = r.get("postmortem_evidence") or []
            if cause not in ALLOWED_POSTMORTEM:
                raise ValueError("POSTMORTEM_CAUSE_INVALID")
            if cause in {"LEGITIMATE_VARIANCE", "UNKNOWN_REQUIRES_REVIEW"} and not evidence:
                raise ValueError("POSTMORTEM_CAUSE_REQUIRES_EVIDENCE")
            causes[cause] += 1

            odds = float(d["decimal_odds"])
            action = d["action"]
            outcome = str(settlement["outcome"])
            outcomes[outcome] += 1
            if action == "PAPER_BET":
                stake = float(d["stake_units"])
                expected = expected_pnl(outcome=outcome, odds=odds, stake=stake)
                rpnl = float(r["pnl_units"])
                if abs(rpnl - expected) > 1e-9:
                    raise ValueError("PAPER_BET_SETTLEMENT_PNL_MISMATCH")
                if r.get("counterfactual_outcome") is not None:
                    raise ValueError("PAPER_BET_COUNTERFACTUAL_FIELDS_FORBIDDEN")
                risked += stake
                pnl += rpnl
            else:
                if abs(float(r["pnl_units"])) > 1e-12:
                    raise ValueError("NO_BET_REALIZED_PNL_MUST_BE_ZERO")
                cf = str(r.get("counterfactual_outcome", ""))
                if cf not in {"WIN", "LOSS", "PUSH", "VOID"}:
                    raise ValueError("NO_BET_COUNTERFACTUAL_OUTCOME_REQUIRED")
                cf_pnl = expected_pnl(outcome=cf, odds=odds, stake=1.0)
                if abs(float(r.get("counterfactual_pnl_units", 999999.0)) - cf_pnl) > 1e-9:
                    raise ValueError("NO_BET_COUNTERFACTUAL_PNL_MISMATCH")
                no_bet_counterfactual_pnl += cf_pnl

            clv = closing_prob - (1.0 / odds)
            if abs(float(r["probability_clv"]) - clv) > 1e-12:
                raise ValueError("REVIEW_CLV_MISMATCH")
            clvs.append(clv)
            reviewed.add(decision_id)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))

    if reviewed != set(decision_payloads):
        errors.append("REVIEW_COMPLETENESS_FAILED")

    # Final review chain must itself be independently anchored, protecting post-event records from later edits.
    review_anchor_ok = False
    if reviews:
        last_seq = len(reviews)
        last_sha = rev_seq.get(last_seq)
        last_recorded = dt(reviews[-1]["recorded_at"])
        for anchor in review_anchors:
            try:
                if int(anchor["through_sequence"]) != last_seq or anchor.get("root_sha256") != last_sha:
                    continue
                if dt(anchor["anchored_at"]) < last_recorded:
                    continue
                if anchor.get("verification_result") != "PASS" or anchor.get("anchor_type") not in ALLOWED_ANCHOR_TYPES:
                    continue
                ep = Path(anchor["anchor_evidence_path"]).resolve()
                if ep.is_file() and fsha(ep) == anchor.get("anchor_evidence_sha256"):
                    proof = readj(ep)
                    if (
                        proof.get("schema") == "MATRIX_ELITE_TIMESTAMP_ANCHOR_VERIFICATION_R1"
                        and proof.get("result") == "PASS"
                        and proof.get("anchor_type") == anchor.get("anchor_type")
                        and proof.get("root_sha256") == anchor.get("root_sha256")
                        and dt(proof["anchored_at"]) == dt(anchor["anchored_at"])
                        and str(proof.get("verifier", "")).strip()
                    ):
                        review_anchor_ok = True
                        break
            except Exception:
                continue
    if not review_anchor_ok:
        errors.append("FINAL_REVIEW_CHAIN_INDEPENDENT_ANCHOR_MISSING")

    total = len(decision_payloads)
    if total < min_total:
        errors.append("MINIMUM_TOTAL_DECISIONS_FAILED")
    if len(bet_decisions) < min_bets:
        errors.append("MINIMUM_PAPER_BETS_FAILED")
    if len(no_bet_decisions) < min_no_bets:
        errors.append("MINIMUM_NO_BETS_FAILED")

    metrics = {
        "decisions_total": total,
        "paper_bets": len(bet_decisions),
        "no_bets": len(no_bet_decisions),
        "combo_bets": combo_count,
        "combo_fraction": combo_fraction,
        "reviews": len(reviewed),
        "review_completion_rate": (len(reviewed) / total) if total else 0.0,
        "risked_units": risked,
        "pnl_units": pnl,
        "paper_yield": (pnl / risked) if risked else 0.0,
        "mean_probability_clv": mean(clvs) if clvs else 0.0,
        "median_probability_clv": median(clvs) if clvs else 0.0,
        "positive_clv_fraction": (sum(x > 0 for x in clvs) / len(clvs)) if clvs else 0.0,
        "no_bet_counterfactual_pnl_at_1u_each": no_bet_counterfactual_pnl,
        "decision_seal_lag_seconds_p50": percentile(seal_lags, 0.50),
        "decision_seal_lag_seconds_p95": percentile(seal_lags, 0.95),
        "outcomes": dict(sorted(outcomes.items())),
        "postmortem_causes": dict(sorted(causes.items())),
    }

    passed = not errors
    out = {
        "schema": SCHEMA,
        "result": "PASS" if passed else "FAIL_CLOSED","running_auditor_path":str(Path(__file__).resolve()),"running_auditor_sha256":sha256(Path(__file__).resolve().read_bytes()).hexdigest(),
        "input_contract_sha256": INPUT_CONTRACT_SHA256,
        "input_path": str(ip),
        "input_sha256": fsha(ip),
        "paper_trading_plan_path": str(Path(data.get("paper_trading_plan_path", "")).resolve()) if data.get("paper_trading_plan_path") else None,
        "paper_trading_plan_sha256": data.get("paper_trading_plan_sha256"),
        "sample_size_justification_path": str(justification_path) if "justification_path" in locals() else None,
        "sample_size_justification_sha256": fsha(justification_path) if "justification_path" in locals() and justification_path.is_file() else None,
        "sample_size_justification_bound": passed,
        "upstream_oos_evidence_path": str(Path(data.get("upstream_oos_evidence_path", "")).resolve()) if data.get("upstream_oos_evidence_path") else None,
        "upstream_oos_evidence_sha256": data.get("upstream_oos_evidence_sha256"),
        "prospective_market_evidence_path": str(Path(data.get("prospective_market_evidence_path", "")).resolve()) if data.get("prospective_market_evidence_path") else None,
        "prospective_market_evidence_sha256": data.get("prospective_market_evidence_sha256"),
        "metrics": metrics,
        "opportunity_chain_root_sha256": opp_seq.get(len(opportunities)) if opportunities else None,
        "decision_chain_root_sha256": dec_seq.get(len(decisions)) if decisions else None,
        "review_chain_root_sha256": rev_seq.get(len(reviews)) if reviews else None,
        "plan_registration_independently_timestamped": passed,
        "opportunity_universe_independently_timestamped": passed,
        "blocking_codes": sorted(set(errors)),
        "paper_process_integrity_passed": passed,
        "independent_prospective_timestamp_proven": passed,
        "paper_trading_evidence_passed": passed,
        "performance_is_report_only_for_c02_gate": True,
        "performance_supports_automatic_model_promotion": False,
        "automatic_wagering_authorized": False,
        "controlled_live_admissible": False,
        "production_admissible": False,
        "network_calls_performed": False,
        "output_payload_sha256": None,
    }
    h = dict(out)
    h["output_payload_sha256"] = None
    out["output_payload_sha256"] = canonical_hash(h)
    op.parent.mkdir(parents=True, exist_ok=True)
    op.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("RESULT=" + ("PASS" if passed else "FAIL_CLOSED"))
    print("C02_REAL_PROSPECTIVE_PAPER_TRADING_EVIDENCE_R3=" + ("PASS" if passed else "FAIL"))
    print("DECISIONS=" + str(total))
    print("PAPER_BETS=" + str(len(bet_decisions)))
    print("NO_BETS=" + str(len(no_bet_decisions)))
    print("INDEPENDENT_PROSPECTIVE_TIMESTAMP_PROVEN=" + str(passed).upper())
    print("BLOCKING_CODES=" + (",".join(sorted(set(errors))) if errors else "<NONE>"))
    print("CONTROLLED_LIVE_ADMISSIBLE=FALSE")
    print("PRODUCTION_ADMISSIBLE=FALSE")
    print("EVIDENCE=" + str(op))
    print("EVIDENCE_SHA256=" + fsha(op))
    return 0 if passed else 2

if __name__ == "__main__":
    raise SystemExit(main())
