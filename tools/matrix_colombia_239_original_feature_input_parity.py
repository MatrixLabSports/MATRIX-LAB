"""Independent, point-in-time comparison of original 239 vs ESPN on EXACT 356 pairs.

Compares only *common* time-verified historical fixtures; the two mismatches
remain quarantined. This proves goal-level feature reproducibility, NOT
source availability equivalence, enriched parity or prospective OOS approval.
"""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_colombia_239_original_espn_historic_crosswalk import original_rows,espn_rows,utc
from tools.api_football_market_shadow_p_matrix import _inputs_for_target,_pool_over25,PARAMS_OVER25

FIELDS=("prior_group_fixture_count","home_history_count","away_history_count",
    "expected_home_goals","expected_away_goals")
def verify(original_raw:bytes,espn_raw:bytes,parity:dict,crosswalk:dict,shadow:dict):
    if (parity.get("schema")!="MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1"
        or crosswalk.get("schema")!="MATRIX_COLOMBIA_239_API_ESPN_HISTORIC_IDENTITY_CROSSWALK_V1"
        or shadow.get("schema")!="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"
        or shadow.get("original_parameters")!=PARAMS_OVER25
        or parity.get("exact_original_goals_time_and_team_parity_count")!=356
        or parity.get("original_results_unmatched_count")!=2
        or parity.get("original_enriched_feature_equivalence_certified") is not False
        or any(x.get("real_money")!="BLOCKED" for x in (parity,crosswalk,shadow))):
        raise ValueError("UNTRUSTED_PARITY_CONTRACT")
    if (hashlib.sha256(original_raw).hexdigest()!=parity["original_archive_sha256"]
        or hashlib.sha256(espn_raw).hexdigest()!=parity["espn_fullseason_raw_sha256"]):
        raise ValueError("SOURCE_CONTENT_SHA_MISMATCH")
    original={x["id"]:x for x in original_rows(original_raw)}
    external={x["id"]:x for x in espn_rows(espn_raw)}
    cross={};reverse={}
    for m in crosswalk["historical_matches"]:
        if m.get("kickoff_score_orientation_and_name_verified") is not True:
            raise ValueError("CROSSWALK_TEAM_IDENTITY_UNVERIFIED")
        for side in ("home","away"):
            aid=str(m[f"api_{side}_id"]);eid=str(m[f"espn_{side}_id"])
            if (eid in cross and cross[eid]!=aid or
                aid in reverse and reverse[aid]!=eid):
                raise ValueError("CROSSWALK_TEAM_ID_CONTRADICTION")
            cross[eid]=aid;reverse[aid]=eid
    if len(cross)!=20:raise ValueError("NOT_ALL_ORIGINAL_TEAMS_VERIFIED")
    src_a=[];src_b=[];used_a=set();used_b=set()
    for link in parity["historical_matched_fixture_ids"]:
        aid=str(link["original_fixture_id"]);eid=str(link["espn_event_id"])
        a=original.get(aid);b=external.get(eid)
        if a is None or b is None or aid in used_a or eid in used_b:
            raise ValueError("PAIRED_FIXTURE_NOT_UNIQUE_OR_NOT_FOUND")
        if (a["kickoff"]!=b["kickoff"] or
            a["home_id"]!=cross.get(b["home_id"]) or
            a["away_id"]!=cross.get(b["away_id"]) or
            a["home_goals"]!=b["home_goals"] or
            a["away_goals"]!=b["away_goals"]):
            raise ValueError("PAIRED_FIXTURE_ID_TIME_GOAL_CONTRADICTION")
        used_a.add(aid);used_b.add(eid)
        src_a.append({"fixture_id":aid,"kickoff_utc":a["kickoff"],
            "home_team_id":a["home_id"],"away_team_id":a["away_id"],
            "home_goals":a["home_goals"],"away_goals":a["away_goals"]})
        src_b.append({"fixture_id":eid,"kickoff_utc":b["kickoff"],
            "home_team_id":cross[b["home_id"]],"away_team_id":cross[b["away_id"]],
            "home_goals":b["home_goals"],"away_goals":b["away_goals"]})
    if len(src_a)!=356 or len(src_b)!=356:
        raise ValueError("COMMON_HISTORY_ROW_COUNT_MISMATCH")
    full=[{"fixture_id":x["id"],"kickoff_utc":x["kickoff"],
       "home_team_id":x["home_id"],"away_team_id":x["away_id"],
       "home_goals":x["home_goals"],"away_goals":x["away_goals"]}
       for x in original.values()]
    rows=[]
    for target in shadow["research_scores"]:
        native=str(target["espn_event_id"])
        fixture=next((f for f in parity["future_native_team_identity_bridged_rows"]
                      if str(f["espn_current_fixture_id"])==native),None)
        if fixture is None:raise ValueError("TARGET_NOT_FROM_PIT_FROZEN_SOURCE")
        kickoff=utc(fixture["kickoff_utc"])
        if (kickoff!=utc(target["kickoff_utc"]) or
            utc(target["scored_at_utc"])>=kickoff or
            target.get("production_p_matrix_authorized") is not False):
            raise ValueError("FUTURE_TARGET_TIMESTAMP_OR_PRODUCTION_INVALID")
        t={"kickoff_utc":kickoff.isoformat(),
           "home_team_id":str(fixture["home"]["original_api_football_team_id_from_history"]),
           "away_team_id":str(fixture["away"]["original_api_football_team_id_from_history"])}
        left,reason_a=_inputs_for_target(src_a,t)
        right,reason_b=_inputs_for_target(src_b,t)
        full_orig,reason_full=_inputs_for_target(full,t)
        if left is None or right is None or full_orig is None:
            raise ValueError("INSUFFICIENT_AUDIT_HISTORY:"+str((reason_a,reason_b,reason_full)))
        fields={f:{"original_exact356":left[f],"espn_exact356":right[f],
                   "equal":left[f]==right[f]} for f in FIELDS}
        for key in ("poisson","baseline"):
            fields[key+"_over25"]={"original_exact356":left[key]["over_2.5"],
              "espn_exact356":right[key]["over_2.5"],
              "equal":math.isclose(left[key]["over_2.5"],right[key]["over_2.5"],abs_tol=1e-12)}
        p_a=_pool_over25(left["poisson"]["over_2.5"],left["baseline"]["over_2_5"])
        p_b=_pool_over25(right["poisson"]["over_2_5"],right["baseline"]["over_2_5"])
        p_full=_pool_over25(full_orig["poisson"]["over_2_5"],full_orig["baseline"]["over_2_5"])
        if not all(v["equal"] for v in fields.values()) or not math.isclose(p_a,p_b,abs_tol=1e-12):
            raise ValueError("EXACT_356_INPUTS_NOT_EQUIVALENT")
        rows.append({"espn_event_id":native,"kickoff_utc":kickoff.isoformat(),
          "input_comparisons":fields,
          "original_356_matched_p_research_only":round(p_a,10),
          "espn_356_matched_p_research_only":round(p_b,10),
          "original_full_358_p_research_only":round(p_full,10),
          "full_358_minus_exact_356_probability":round(p_full-p_a,10),
          "comparison_research_only":True,"official_p_matrix_authorized":False,
          "telegram_authorized":False})
    return {"schema":"MATRIX_COL_239_356_PAIR_ORIGINAL_FEATURE_MATH_PARITY_V1",
      "status":"EXACT_356_GOAL_INPUT_PARITY_VERIFIED_PARTIAL_SOURCE_EQUIVALENCE_ONLY",
      "original_source_sha256":hashlib.sha256(original_raw).hexdigest(),
      "espn_fullseason_source_sha256":hashlib.sha256(espn_raw).hexdigest(),
      "verified_exact_common_finished_fixtures":len(src_a),
      "quarantined_kickoff_discrepancies":2,
      "identically_mapped_original_team_ids":len(cross),
      "target_count":len(rows),"targets":rows,
      "original_parameters_unmodified":dict(PARAMS_OVER25),
      "raw_goals_input_parity_within_exact_common_subset":True,
      "all_358_historical_matches_identical":False,
      "all_enriched_source_features_certified":False,
      "real_time_source_availability_equivalent":False,
      "prospective_out_of_sample_certified":False,
      "research_scores_are_not_official":True,
      "production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,"real_money":"BLOCKED"}
def main():
    p=argparse.ArgumentParser()
    for name in ("original","espn-gz","parity","crosswalk","shadow","out"):
        p.add_argument("--"+name,required=True,type=Path)
    args=p.parse_args()
    get=lambda path:json.loads(path.read_bytes())
    out=verify(args.original.read_bytes(),gzip.decompress(args.espn_gz.read_bytes()),
        get(args.parity),get(args.crosswalk),get(args.shadow))
    if any(t in args.out.parts for t in ("telegram","notifications","governance")):
        raise SystemExit("RESEARCH_CANNOT_WRITE_TO_PRODUCTION")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"compared_historical":out["verified_exact_common_finished_fixtures"],
        "targets":out["target_count"],"only_common_goal_feature_parity":True,
        "official_p_matrix":False,"telegram":False}))
if __name__=="__main__":main()
