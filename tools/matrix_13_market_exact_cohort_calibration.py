"""Strict prospective 13-market final-only calibration measurement, no model fit/promotion.

Only matches the 42-lane pre-kickoff frozen predictions with the authenticated,
hash-chain-checked API-Football standard FT settlement ledger. No network calls.
Period score fields are ABSENT from that ledger: never infer halftime from fulltime.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.api_football_prospective_api_settlement import _load_ledger as verified_settlements
from tools.matrix_13_cohort_independent_settlement import validated_ledger as verified_independent_settlements

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json"
PORTFOLIO = ROOT / "evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl"
SETTLEMENT = ROOT / "evidence/api_football/prospective_market_freeze/settlement_ledger.jsonl"
INDEPENDENT = ROOT / "evidence/football_cohort_recovery/MATRIX_INDEPENDENT_VERIFIED_FT_LEDGER.jsonl"
OUT = ROOT / "evidence/governance/MATRIX_13_MARKET_EXACT_COHORT_CALIBRATION_LAST.json"
RAW = ROOT / "evidence/api_football/prospective_market_freeze/settlement_raw"

PERIOD_LANES = {
    "FIRST_HALF_TEAM_TOTAL_GOALS_AWAY", "FIRST_HALF_TEAM_TOTAL_GOALS_HOME",
    "FIRST_HALF_TOTAL_GOALS_OVER_UNDER", "SECOND_HALF_TEAM_TOTAL_GOALS_AWAY",
    "SECOND_HALF_TEAM_TOTAL_GOALS_HOME", "SECOND_HALF_TOTAL_GOALS_OVER_UNDER",
}
TEAM_LANES = {"TEAM_TOTAL_GOALS_HOME", "TEAM_TOTAL_GOALS_AWAY"}
CORE_LANES = {
    "MATCH_RESULT_1X2", "DOUBLE_CHANCE_1X", "DOUBLE_CHANCE_X2",
    "DOUBLE_CHANCE_12", "TOTAL_GOALS_OVER_UNDER",
}
EPS = 1e-15


def utc(v: Any) -> datetime:
    d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if d.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def digest(v: Any) -> str:
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",",":"), allow_nan=False).encode()).hexdigest()


def probability(v: Any) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("NOT_NUMERIC_PROBABILITY")
    p = float(v)
    if not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise ValueError("PROBABILITY_OUTSIDE_0_1")
    return p


def statistics(probs: list[Any], outcomes: list[Any], *, multiclass: bool = False) -> dict:
    if len(probs) != len(outcomes) or not probs:
        raise ValueError("INVALID_METRIC_SAMPLE")
    if multiclass:
        loss = []
        brier = []
        accuracy = []
        conf = []
        correct = []
        for prediction, outcome in zip(probs, outcomes):
            if outcome not in {"H", "D", "A"} or set(prediction) != {"H", "D", "A"}:
                raise ValueError("INVALID_1X2")
            pp = {k: probability(prediction[k]) for k in ("H", "D", "A")}
            if abs(sum(pp.values()) - 1.0) > 1e-6:
                raise ValueError("NOT_NORMALIZED")
            loss.append(-math.log(max(pp[outcome], EPS)))
            brier.append(sum((p - int(k == outcome)) ** 2 for k, p in pp.items()))
            choice = max(("H", "D", "A"), key=lambda k: pp[k])
            accuracy.append(int(choice == outcome))
            conf.append(pp[choice])
            correct.append(int(choice == outcome))
        ece = sum(
            len(ix) * abs(sum(conf[i] for i in ix) / len(ix) - sum(correct[i] for i in ix) / len(ix))
            for b in range(10)
            if (ix := [i for i, p in enumerate(conf) if b/10 <= p < (b+1)/10 or (b == 9 and p == 1)])
        ) / len(probs)
        return {"n": len(probs), "brier": sum(brier)/len(probs), "log_loss": sum(loss)/len(probs), "ece": ece, "accuracy": sum(accuracy)/len(probs)}
    numbers = [probability(p) for p in probs]
    if any(type(y) not in (bool, int) or y not in (0, 1) for y in outcomes):
        raise ValueError("INVALID_BINARY_TARGET")
    ys = [int(y) for y in outcomes]
    brier = sum((p-y)**2 for p, y in zip(numbers,ys)) / len(numbers)
    ll = sum(-(y*math.log(max(p,EPS))+(1-y)*math.log(max(1-p,EPS))) for p,y in zip(numbers,ys)) / len(numbers)
    ece = sum(
        len(ix) * abs(sum(numbers[i] for i in ix)/len(ix) - sum(ys[i] for i in ix)/len(ix))
        for b in range(10)
        if (ix := [i for i,p in enumerate(numbers) if b/10 <= p < (b+1)/10 or (b==9 and p==1)])
    ) / len(numbers)
    return {"n":len(numbers),"brier":brier,"log_loss":ll,"ece":ece,"observed_positive_rate":sum(ys)/len(ys)}



def verified_half_time(fid: str, settlement: dict, raw_dir: Path) -> tuple[int,int]:
    """Verify original full match response checksum, identity, status and scores.

    No API request and no inference of halftime from final score. The second
    half is arithmetically derived only after a genuine halftime is validated.
    """
    path = raw_dir / f"fixture_{fid}.bin"
    if not path.is_file():
        raise ValueError("MISSING_ORIGINAL_MATCH_RECEIPT")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != settlement.get("result_payload_sha256"):
        raise ValueError("ORIGINAL_MATCH_RECEIPT_SHA256_MISMATCH")
    payload = json.loads(body)
    if payload.get("errors") not in ([], {}, None) or payload.get("results") != 1:
        raise ValueError("PROVIDER_ERRORS_OR_AMBIGUOUS_RESULT")
    rows = payload.get("response")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ValueError("EXPECTED_ONE_PROVIDER_FIXTURE")
    match = rows[0]
    fixture = match.get("fixture") or {}
    if str(fixture.get("id")) != fid or (fixture.get("status") or {}).get("short") != "FT":
        raise ValueError("ORIGINAL_FIXTURE_ID_OR_STATUS_MISMATCH")
    if utc(fixture.get("date")) != utc(settlement["kickoff_utc"]):
        raise ValueError("ORIGINAL_FIXTURE_DATE_MISMATCH")
    score = match.get("score") or {}
    full = score.get("fulltime") or {}
    half = score.get("halftime") or {}
    hg, ag = full.get("home"), full.get("away")
    hh, ah = half.get("home"), half.get("away")
    values = (hg,ag,hh,ah)
    if any(type(x) is not int or x < 0 for x in values):
        raise ValueError("INVALID_RAW_HALF_OR_FINAL_SCORE")
    if (hg,ag) != (settlement["fulltime_home_goals"],settlement["fulltime_away_goals"]):
        raise ValueError("ORIGINAL_FINAL_RESULT_MISMATCH")
    if hh > hg or ah > ag:
        raise ValueError("HALFTIME_EXCEEDS_FINAL_SCORE")
    goals = match.get("goals") or {}
    if goals.get("home") != hg or goals.get("away") != ag:
        raise ValueError("RAW_FINAL_GOALS_NOT_CONSISTENT")
    return hh,ah


def _prediction_and_targets(lane: str, row: dict, result: dict, halftime: tuple[int,int] | None = None) -> dict[str, tuple[float | dict, int | str]]:
    pred = row["prediction"]
    home, away = result["fulltime_home_goals"], result["fulltime_away_goals"]
    if lane == "MATCH_RESULT_1X2":
        return {"1x2": (pred, "H" if home > away else "D" if home == away else "A")}
    if lane in {"DOUBLE_CHANCE_1X", "DOUBLE_CHANCE_X2", "DOUBLE_CHANCE_12"}:
        key = {"DOUBLE_CHANCE_1X":"1X","DOUBLE_CHANCE_X2":"X2","DOUBLE_CHANCE_12":"12"}[lane]
        return {key:(pred[key], int((home >= away) if key == "1X" else (away >= home) if key == "X2" else (home != away)))}
    if lane == "TOTAL_GOALS_OVER_UNDER":
        return {"over_2_5":(pred["over_2_5"], int(home + away >= 3))}
    if lane in TEAM_LANES:
        goals = home if lane.endswith("HOME") else away
        return {key: (pred[key], int(goals >= 1+int(key.split("_")[1]))) for key in ("over_0_5","over_1_5","over_2_5")}
    if lane in PERIOD_LANES:
        if halftime is None:
            raise ValueError("VERIFIED_HALFTIME_REQUIRED")
        first_h,first_a = halftime
        second_h,second_a = home - first_h, away - first_a
        is_first = lane.startswith("FIRST_HALF_")
        ph,pa = (first_h,first_a) if is_first else (second_h,second_a)
        if "_TEAM_TOTAL_GOALS_HOME" in lane:
            goals = ph
        elif "_TEAM_TOTAL_GOALS_AWAY" in lane:
            goals = pa
        else:
            goals = ph+pa
        thresholds = ("over_0_5","over_1_5") if "_TEAM_TOTAL_GOALS_" not in lane else ("over_0_5",)
        return {key:(pred[key],int(goals >= 1+int(key.split("_")[1]))) for key in thresholds}
    raise ValueError("UNKNOWN_MARKET_LANE")


def build(registry: dict, portfolio: list[dict], settlements: list[dict], *, raw_dir: Path = RAW, secondary_settlements: list[dict] | None = None) -> dict:
    if registry.get("status") != "PASS" or registry.get("total_lanes") != 42:
        raise ValueError("CANONICAL_REGISTRY_REQUIRED")
    guards = registry.get("protections") or {}
    if guards.get("real_money") != "BLOCKED" or guards.get("automatic_wagering") is not False:
        raise ValueError("REGISTRY_SAFETY_INVALID")
    lane_count = {key:v["prospective_unique_count"] for key,v in registry["lanes"].items()}
    targeted = {key for key,count in lane_count.items() if count >= 600}
    if len(targeted) != 13 or targeted != CORE_LANES | TEAM_LANES | PERIOD_LANES:
        raise ValueError("EXPECTED_EXACTLY_13_APPROVED_RESEARCH_LANES")
    if any(row.get("real_money") != "BLOCKED" or row.get("terminal_status") != "FT" for row in settlements):
        raise ValueError("UNVERIFIED_SETTLEMENT_SOURCE")
    by_fixture = {}
    for item in settlements:
        fid = str(item.get("fixture_id") or "")
        if not fid or fid in by_fixture:
            raise ValueError("DUPLICATE_SETTLEMENT_ID")
        by_fixture[fid] = item
    independent = secondary_settlements or []
    for record in independent:
        fid=str(record.get("fixture_id") or "")
        if (not fid or fid in by_fixture or record.get("terminal_status")!="FT"
            or record.get("real_money")!="BLOCKED"
            or record.get("automatic_wagering") is not False
            or record.get("source_provider") not in {"ESPN_MLS","ESPN_CUP"}
            or not record.get("source_raw_sha256")):
            raise ValueError("INDEPENDENT_SOURCE_DUPLICATE_OR_NOT_VERIFIED")
        by_fixture[fid] = record

    admitted: dict[str, dict[str, list[dict]]] = {lane: {} for lane in targeted}
    rejections = Counter()
    lane_portfolio_count = Counter()
    for row in portfolio:
        lane = row.get("market_lane")
        if lane not in targeted:
            continue
        lane_portfolio_count[lane] += 1
        try:
            if (row.get("record_type") != "PROSPECTIVE_PREMATCH_FREEZE" or
                row.get("prospective_admitted") is not True or
                row.get("real_money") != "BLOCKED" or row.get("automatic_wagering") is not False or
                row.get("odds_used_to_generate_probability") is not False or
                row.get("target_outcome") is not None or row.get("settlement") is not None):
                raise ValueError("UNTRUSTED_FREEZE")
            if not row.get("prediction_snapshot_sha256") or not isinstance(row.get("prediction"),dict):
                raise ValueError("MISSING_FROZEN_PREDICTION")
            fid = str(row.get("fixture_id") or row.get("event_id") or "")
            if not fid:
                raise ValueError("NO_EVENT_ID")
            freeze, kickoff = utc(row["freeze_timestamp_utc"]), utc(row["event_start_utc"])
            if freeze >= kickoff:
                raise ValueError("LATE_FREEZE")
            admitted[lane].setdefault(fid, []).append(row)
        except (ValueError, KeyError, TypeError):
            rejections["INVALID_PROSPECTIVE_FREEZE"] += 1
    rows_out = []
    for lane in sorted(targeted):
        sampled: dict[str, list[tuple[float | dict,int | str]]] = {}
        good_ids = []
        issues = Counter()
        source_records = admitted[lane]
        for fid, bucket in source_records.items():
            if len(bucket) != 1:
                issues["DUPLICATE_FIXTURE_FREEZE"] += len(bucket)
                continue
            record = by_fixture.get(fid)
            if record is None:
                issues["NO_EXACT_STANDARD_FT_SETTLEMENT"] += 1
                continue
            row = bucket[0]
            try:
                if (utc(record["kickoff_utc"]) != utc(row["event_start_utc"]) or
                    utc(record["freeze_at_utc"]) != utc(row["freeze_timestamp_utc"])):
                    raise ValueError("EVENT_OR_FREEZE_MISMATCH")
                if utc(record["settled_at_utc"]) < utc(record["kickoff_utc"]):
                    raise ValueError("RESULT_BEFORE_KICKOFF")
                original_api = record.get("result_source_provider") == "api_football"
                if original_api:
                    if not record.get("result_payload_sha256"):
                        raise ValueError("API_FINAL_RECEIPT_MISSING")
                elif (record.get("source_provider") not in {"ESPN_MLS","ESPN_CUP"}
                      or not record.get("source_raw_sha256")
                      or record.get("halftime_verified") is not False):
                    raise ValueError("UNVERIFIED_INDEPENDENT_PROVIDER_FINAL")
                home, away = record["fulltime_home_goals"], record["fulltime_away_goals"]
                if type(home) is not int or type(away) is not int or home < 0 or away < 0:
                    raise ValueError("RESULT_GOALS_INVALID")
                if lane in PERIOD_LANES and not original_api:
                    issues["INDEPENDENT_FULL_TIME_ONLY_HALFTIME_NOT_VERIFIED"] += 1
                    continue
                half = verified_half_time(fid, record, raw_dir) if lane in PERIOD_LANES else None
                vals = _prediction_and_targets(lane, row, record, halftime=half)
                for k, (p, outcome) in vals.items():
                    if isinstance(p,dict):
                        if set(p) != {"H","D","A"} or abs(sum(probability(z) for z in p.values())-1)>1e-6:
                            raise ValueError("1X2_PREDICTION_INVALID")
                    else:
                        probability(p)
                    if type(outcome) not in (int,str):
                        raise ValueError("BAD_OUTCOME")
                    sampled.setdefault(k, []).append((p,outcome))
                good_ids.append(fid)
            except (ValueError,TypeError,KeyError) as exc:
                reason = str(exc)
                if lane in PERIOD_LANES and reason in {
                    "MISSING_ORIGINAL_MATCH_RECEIPT",
                    "ORIGINAL_MATCH_RECEIPT_SHA256_MISMATCH",
                    "INVALID_RAW_HALF_OR_FINAL_SCORE",
                    "HALFTIME_EXCEEDS_FINAL_SCORE",
                    "ORIGINAL_FINAL_RESULT_MISMATCH",
                }:
                    issues[reason] += 1
                else:
                    issues["RESULT_OR_PREDICTION_IDENTITY_REJECTED"] += 1
        metrics = {name:statistics([v[0] for v in values],[v[1] for v in values],multiclass=(name=="1x2"))
                   for name,values in sampled.items()}
        n = len(good_ids)
        decision = "RESEARCH_ONLY_NO_PROMOTION"
        if lane in PERIOD_LANES and n == 0:
            decision = "HOLD_NO_VALIDATED_HALF_TIME_RECEIPTS"
        elif lane in PERIOD_LANES and n < 600:
            decision = "HOLD_HALF_TIME_COHORT_BELOW_600"
        elif lane in PERIOD_LANES:
            decision = "REQUIRES_FORMAL_PERIOD_MODEL_CALIBRATION_AND_PRICE_MAPPING"
        elif lane == "DOUBLE_CHANCE_12":
            decision = "NO_GO_DIAGNOSTIC_CURRENT_CHALLENGER"
        elif n < 600:
            decision = "HOLD_FT_COHORT_BELOW_600"
        else:
            decision = "REQUIRES_FORMAL_PREDECLARED_HOLDOUT_AND_MODEL_COMPARISON"
        rows_out.append({
            "market_key":lane,
            "prospective_valid_freezes":lane_count[lane],
            "portfolio_rows_seen":lane_portfolio_count[lane],
            "unique_fixture_freezes_reviewed":len(source_records),
            "exact_cohort_final_verified":n,
            "matched_fixture_ids_sha256":digest(sorted(good_ids)),
            "outcome_source":"MATRIX_FOOTBALL_PROSPECTIVE_SETTLEMENT_RECORD_V1_STANDARD_FT_HASHCHAIN",
            "calibration_metrics_unpromoted":metrics,
            "blockers":dict(sorted(issues.items())),
            "decision":decision,
            "parameters_refitted":False,
            "telegram_authorized_by_audit":False,
        })
    return {
        "schema":"MATRIX_13_MARKET_EXACT_COHORT_CALIBRATION_V1",
        "status":"RESEARCH_AUDIT_NO_PROMOTION",
        "source_hashes":{
            "registry_canonical_json_sha256":digest(registry),
            "portfolio_ledger_records_sha256":digest(portfolio),
            "verified_settlement_ledger_records_sha256":digest(settlements),
            "independent_verified_settlement_records_sha256":digest(independent),
        },
        "summary":{
            "markets_targeted":len(rows_out),
            "market_count_with_any_exact_final":sum(x["exact_cohort_final_verified"]>0 for x in rows_out),
            "markets_with_600_exact_final":sum(x["exact_cohort_final_verified"]>=600 for x in rows_out),
            "settlement_source_rows":len(settlements),
            "independent_ledger_final_rows":len(independent),
            "combined_distinct_verified_final_rows":len(by_fixture),
            "portfolio_rows":len(portfolio),
            "invalid_freezes":dict(rejections),
        },
        "lanes":rows_out,
        "safety":{
            "no_paid_api_queries":True,"no_outcome_imputation":True,
            "no_half_time_inference_from_fulltime":True,
            "halftime_raw_receipt_sha256_and_final_score_match_required":True,
            "no_promotion_from_600_freezes":True,
            "no_parameter_refit":True,"automatic_wagering":False,
            "real_money":"BLOCKED","telegram_messages_sent":0,
        },
    }


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    portfolio = [json.loads(line) for line in PORTFOLIO.read_text(encoding="utf-8").splitlines() if line.strip()]
    settlement = verified_settlements(SETTLEMENT)
    secondary = verified_independent_settlements(INDEPENDENT)
    report = build(registry,portfolio,settlement,secondary_settlements=secondary)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"summary":report["summary"],
                      "lanes":[{"lane":x["market_key"],"final":x["exact_cohort_final_verified"],"decision":x["decision"]} for x in report["lanes"]]},sort_keys=True))


if __name__ == "__main__":
    main()
