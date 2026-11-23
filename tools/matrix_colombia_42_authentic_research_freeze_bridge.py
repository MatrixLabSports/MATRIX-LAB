"""Restore authentic *research-only* prospectively frozen football market-lane intake.

Only two triple-confirmed Colombian 24-Nov events, strictly before kickoff,
using frozen Over2.5 and equal actual 356-match original/ESPN goal features.
Never promotes original official P_MATRIX, sends Telegram, bets, or extrapolates
missing halves/shots/tennis data. Stable event/lane idempotency prevents inflation.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_42_lane_prospective_registry import validate_freeze

TRIPLE=Path("evidence/football_world_inventory/2026-11-24/MATRIX_COLOMBIA_THREE_SOURCE_READINESS_RUN_45090559298.json")
SHADOW=Path("evidence/football_world_inventory/2026-11-22/MATRIX_COLOMBIA_239_ORIGINAL_FORMULA_SHADOW_RUN_45089678156.json")
PARITY=Path("evidence/football_world_inventory/2026-11-22/MATRIX_COL_239_ORIGINAL_356_INPUT_PARITY_RUN_45092565897.json")
CANON=Path("evidence/football_world_inventory/2026-11-24/MATRIX_COL_239_EXPERIMENTAL_CANONICAL_INPUT_RUN_45092696407.json")
INBOX=Path("evidence/market_portfolio/MATRIX_42_LANE_FREEZE_INBOX.jsonl")
LEDGER=Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_LEDGER.jsonl")
AUDIT=Path("evidence/market_portfolio/MATRIX_COLOMBIA_AUTHENTIC_GOALS_PROSPECTIVE_INTAKE_LAST.json")
MODEL="MATRIX_COL239_ESPN_AUTHENTIC_RESEARCH_ONLY_GOALS_V1"
LANES=("TOTAL_GOALS_OVER_UNDER","TEAM_TOTAL_GOALS_HOME","TEAM_TOTAL_GOALS_AWAY")
def aware(value):
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.utcoffset() is None:raise ValueError("TIMESTAMP_NOT_TIMEZONE_AWARE")
    return t.astimezone(timezone.utc)
def raw_sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical_sha(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def poisson_over(lam,threshold):
    if not math.isfinite(lam) or lam<=0:raise ValueError("EXPECTED_GOAL_RATE_INVALID")
    cut=math.floor(threshold)
    term=math.exp(-lam);cdf=term
    for k in range(1,cut+1):
        term*=lam/k;cdf+=term
    return max(0.0,min(1.0,1-cdf))
def _as_dict(p):
    obj=json.loads(p.read_bytes())
    if not isinstance(obj,dict):raise ValueError("NOT_JSON_OBJECT")
    return obj
def make_rows(triple,shadow,parity,canon,*,now,source_shas,existing_events):
    now=now.astimezone(timezone.utc).replace(microsecond=0)
    if (triple.get("schema")!="MATRIX_COLOMBIA_239_THREE_SOURCE_RESEARCH_TO_TELEGRAM_GUARD_V1"
      or shadow.get("schema")!="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"
      or parity.get("schema")!="MATRIX_COL_239_356_PAIR_ORIGINAL_FEATURE_MATH_PARITY_V1"
      or canon.get("schema")!="MATRIX_COL_239_ESPN_AUTHENTIC_CANONICAL_EXPERIMENTAL_INPUT_V1"
      or shadow.get("original_parameters")!={"a":0.6,"b":0.0,"c":0.4}
      or triple.get("three_calendar_matches")!=2
      or canon.get("input_count")!=2
      or parity.get("verified_exact_common_finished_fixtures")!=356
      or parity.get("raw_goals_input_parity_within_exact_common_subset") is not True
      or parity.get("quarantined_kickoff_discrepancies")!=2
      or any(x.get("real_money")!="BLOCKED" for x in (triple,shadow,parity,canon))
      or any(x.get("production_p_matrix_authorized") is not False for x in (triple,shadow,parity,canon))
      or any(x.get("telegram_signal_authorized") is not False for x in (triple,shadow,parity,canon))):
        raise ValueError("PIT_RESEARCH_SOURCE_NOT_INDEPENDENTLY_VERIFIED")
    scores={str(x["espn_event_id"]):x for x in shadow["research_scores"]}
    parity_map={str(x["espn_event_id"]):x for x in parity["targets"]}
    can_map={str(x["espn_fixture_id"]):x for x in canon["inputs"]}
    rows=[];blocked=[]
    for f in triple["three_source_matches"]:
        fid=str(f["espn_event_id"])
        p=scores.get(fid);q=parity_map.get(fid);c=can_map.get(fid)
        if not p or not q or not c:raise ValueError("MATCH_NOT_FOUND_IN_THREE_INDEPENDENT_CERTIFICATES")
        kickoff=aware(f["kickoff_utc"])
        if (kickoff!=aware(p["kickoff_utc"]) or kickoff!=aware(q["kickoff_utc"])
          or f["source_fixture_identity_on_three_calendars_verified"] is not True
          or c.get("structural_readiness")!="READY_FOR_EXPERIMENTAL_EVALUATION"
          or c.get("source_native_competition_id")!="col.1"
          or c.get("original_api_football_fixture_id") is not None
          or c.get("home_history_count")!=20 or c.get("away_history_count")!=20
          or p.get("production_p_matrix_authorized") is not False
          or p.get("telegram_signal_authorized") is not False):
            raise ValueError("TARGET_IDENTITY_OR_HISTORY_NOT_VALID")
        if (aware(p["scored_at_utc"])>=now or
            aware(triple["browser_observed_at_utc"])>=now):
            raise ValueError("SOURCE_PIT_RECEIPT_AFTER_FREEZE")
        if now>=kickoff:
            blocked.append({"espn_fixture_id":fid,"reason":"TARGET_KICKOFF_PASSED_NO_RETROACTIVE_FREEZE"});continue
        for key in ("expected_home_goals","expected_away_goals","home_history_count","away_history_count"):
            cmp=q["input_comparisons"].get(key)
            if not isinstance(cmp,dict) or cmp.get("equal") is not True or cmp.get("original_exact356")!=cmp.get("espn_exact356"):
                raise ValueError("STRICT_356_SOURCE_FEATURE_NOT_EQUAL:"+key)
        eh=float(q["input_comparisons"]["expected_home_goals"]["espn_exact356"])
        ea=float(q["input_comparisons"]["expected_away_goals"]["espn_exact356"])
        prob=float(p["p_over25_research_only"])
        if not 0<prob<1:raise ValueError("NON_FINITE_OR_INVALID_ORIGINAL_FROZEN_SCORE")
        predictions={
          "TOTAL_GOALS_OVER_UNDER":{"over_2_5":prob,"under_2_5":1-prob},
          "TEAM_TOTAL_GOALS_HOME":{"over_0_5":poisson_over(eh,0.5),"under_0_5":1-poisson_over(eh,0.5),
              "over_1_5":poisson_over(eh,1.5),"under_1_5":1-poisson_over(eh,1.5)},
          "TEAM_TOTAL_GOALS_AWAY":{"over_0_5":poisson_over(ea,0.5),"under_0_5":1-poisson_over(ea,0.5),
              "over_1_5":poisson_over(ea,1.5),"under_1_5":1-poisson_over(ea,1.5)}
        }
        for lane in LANES:
            key="football|"+lane+"|source:ESPN_COL_1|fixture:"+fid+"|research:v1"
            event_id="ESPN_COL_1:"+fid
            if (lane,event_id) in existing_events:continue
            prediction=predictions[lane]
            capsule={"fixture":fid,"event":event_id,"lane":lane,"prediction":prediction,
               "sha_sources":source_shas,"p_original_freeze_utc":p["scored_at_utc"],
               "research_model":MODEL,"goal_features_strict_pair_count":356}
            row={"observation_key":key,"record_type":"PROSPECTIVE_PREMATCH_FREEZE",
              "sport":"football","market_lane":lane,"fixture_id":event_id,"event_id":event_id,
              "event_start_utc":kickoff.isoformat(),"freeze_timestamp_utc":now.isoformat(),
              "source_schema":MODEL,"source_snapshot_sha256":canonical_sha(source_shas),
              "prediction_snapshot_sha256":canonical_sha(capsule),
              "feature_snapshot_sha256":c["canonical_analysis_input_sha256"],
              "prediction":prediction,"model_basis":MODEL,
              "source_kind":"ESPN_COL_1_RESEARCH_FROZEN_THREE_SOURCE_VERIFIED",
              "source_original_model_params":dict(shadow["original_parameters"]),
              "source_provider_native_event_id":fid,"source_competition_id":"col.1",
              "sofascore_event_id":str(f["sofascore_event_id"]),"flashscore_mid":f["flashscore_mid"],
              "source_goal_histories_strictly_matched":356,
              "history_kickoff_conflicts_quarantined":2,
              "experimental_only":True,"model_enriched_feature_equivalence_certified":False,
              "official_p_matrix_authorized":False,"telegram_signal_authorized":False,
              "source_provenance_sha256":source_shas,
              "target_outcome":None,"settlement":None,
              "prospective_admitted":True,"counts_toward_100_300_600":True,
              "odds_used_to_generate_probability":False,
              "missing_not_zero":True,"silent_imputation":False,
              "automatic_wagering":False,"real_money":"BLOCKED"}
            valid,errs=validate_freeze(row)
            if not valid:raise ValueError("CONTRACT_FREEZE_VALIDATION_FAILED:"+repr(errs))
            rows.append(row)
    return rows,blocked
def _rows(path):
    if not path.is_file():return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
def main():
    a=argparse.ArgumentParser()
    a.add_argument("--root",type=Path,default=Path("."))
    a.add_argument("--inbox",type=Path,default=INBOX)
    a.add_argument("--ledger",type=Path,default=LEDGER)
    a.add_argument("--audit-out",type=Path,default=AUDIT)
    args=a.parse_args()
    root=args.root
    ps={"triple":TRIPLE,"shadow":SHADOW,"parity":PARITY,"canonical":CANON}
    docs={k:_as_dict(root/p) for k,p in ps.items()}
    shas={k:raw_sha(root/p) for k,p in ps.items()}
    seen={(str(row.get("market_lane")),str(row.get("event_id"))) for row in (_rows(args.inbox)+_rows(args.ledger))}
    now=datetime.now(timezone.utc)
    admitted,blocked=make_rows(docs["triple"],docs["shadow"],docs["parity"],docs["canonical"],
        now=now,source_shas=shas,existing_events=seen)
    args.inbox.parent.mkdir(parents=True,exist_ok=True)
    if admitted:
        with args.inbox.open("a",encoding="utf-8") as fp:
            for row in admitted:fp.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    out={"schema":"MATRIX_COL239_AUTHENTIC_42_LANE_RESEARCH_FREEZE_BRIDGE_V1",
      "generated_at_utc":now.astimezone(timezone.utc).isoformat(),
      "status":"AUTHENTIC_RESEARCH_PREMATCH_PROSPECTIVE_INTAKE_NOT_PRODUCTION",
      "source_files_sha256":shas,
      "market_lanes":list(LANES),
      "incoming_research_freezes":len(admitted),
      "incoming_research_fixture_count":len({x["event_id"] for x in admitted}),
      "blocked":blocked,
      "duplicate_suppression_by_event_and_lane":True,
      "no_source_backfill":True,"no_tennis_or_specialty_features_imputed":True,
      "model_enriched_feature_equivalence_certified":False,
      "production_p_matrix_authorized":False,"telegram_signal_authorized":False,
      "real_money":"BLOCKED","automatic_wagering":False}
    args.audit_out.parent.mkdir(parents=True,exist_ok=True)
    args.audit_out.write_text(json.dumps(out,sort_keys=True,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"prospective_research_rows_inbox":len(admitted),"eligible_markets":list(LANES),
      "telegram":False,"real_money":"BLOCKED"},sort_keys=True))
if __name__=="__main__":main()
