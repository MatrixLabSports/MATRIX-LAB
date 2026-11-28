"""Real Colombian research-only odds intake adapter with strict pre-kickoff 120m.

Reuses existing audited odds-api.net quote verification; NEVER promotes research
predictions into canonical P_MATRIX or Telegram. No new sportsbook integrations.
"""
from __future__ import annotations
import argparse,json,os
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_independent_over25_quote_audit import audit as quote_audit

def adapt(observations,three_way,shadow):
    if (observations.get("schema")!="MATRIX_COLOMBIA_239_LIVE_BROWSER_THREE_SOURCE_OBSERVATION_V1"
        or three_way.get("schema")!="MATRIX_COLOMBIA_239_THREE_SOURCE_RESEARCH_TO_TELEGRAM_GUARD_V1"
        or shadow.get("schema")!="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"
        or three_way.get("three_calendar_matches",0)<1
        or three_way.get("production_p_matrix_authorized") is not False
        or three_way.get("telegram_signal_authorized") is not False
        or shadow.get("original_parameters")!={"a":0.6,"b":0,"c":0.4}
        or any(j.get("real_money")!="BLOCKED" for j in (observations,three_way,shadow))):
        raise ValueError("UNTRUSTED_BROWSER_OR_RESEARCH_PRODUCTION_INPUT")
    linked={str(x["espn_event_id"]):x for x in three_way["three_source_matches"]}
    scores={str(x["espn_event_id"]):x for x in shadow["research_scores"]}
    seen=set();fixtures=[];scored=[]
    for item in observations["fixtures"]:
        fid=str(item["espn_event_id"])
        if fid in seen:raise ValueError("DUPLICATE_ESPN_NATIVE_FIXTURE_ID")
        seen.add(fid)
        if fid not in linked or fid not in scores:raise ValueError("MISSING_VERIFIED_SOURCE_IDENTITY_OR_RESEARCH_SCORE")
        link=linked[fid];score=scores[fid]
        if (link.get("source_fixture_identity_on_three_calendars_verified") is not True
            or link.get("canonical_probability_authorized") is not False
            or score.get("production_p_matrix_authorized") is not False
            or item["kickoff_utc"]!=link["kickoff_utc"]
            or item["kickoff_utc"]!=score["kickoff_utc"]):
            raise ValueError("CROSS_SOURCE_RESEARCH_SCORE_CONTRADICTION")
        fixtures.append({"source_fixture_id":fid,"kickoff_utc":item["kickoff_utc"],
            "home":item["home"],"away":item["away"],
            "source_competition_id":239,"source_competition_code":"COL_PRIMERA_A",
            "source_provider":"ESPN_RESEARCH_NATIVE_ID"})
        scored.append({"source_fixture_id":fid,"kickoff_utc":item["kickoff_utc"],
            "p_over25_research":score["p_over25_research_only"],
            "source_feature_equivalence_verified":False,
            "production_p_matrix_authorized":False})
    day=observations["target_date_bogota"]
    intake={"schema":"MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
         "target_date_bogota":day,"source":"ESPN_COL_1_RESEARCH_QUOTES_ONLY",
         "fixtures":fixtures,"signal_generation_authorized":False,
         "automatic_wagering":False,"real_money":"BLOCKED"}
    synthetic_shadow={"schema":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
         "target_date_bogota":day,"source":"UNCHANGED_ORIGINAL_MATH_ESPN_RESEARCH",
         "scored":scored,"market_signal_authorized":False,"automatic_wagering":False,
         "real_money":"BLOCKED"}
    return intake,synthetic_shadow

def check(obs,verified,shadow,key="",*,session=None,now=None,previous=None,global_quota_guard=None):
    intake,scored=adapt(obs,verified,shadow)
    result=quote_audit(intake,scored,key,session=session,now=now,max_matches=1,
        previous=previous,global_quota_guard=global_quota_guard)
    if (result["signal_generation_authorized"] is not False
        or result["telegram_messages_sent"]!=0
        or result["real_money"]!="BLOCKED"
        or result["automatic_wagering"] is not False):
        raise ValueError("RESEARCH_QUOTE_GOVERNANCE_BREACH")
    result["colombia_research_quote_adapter_schema"]="MATRIX_COL_239_ESPN_THREE_BROWSER_QUOTE_RESEARCH_ADAPTER_V1"
    result["three_source_browser_crosswalk_verified_for_research"]=True
    result["official_original_model_enriched_feature_parity_verified"]=False
    result["production_p_matrix_authorized"]=False
    result["full_quality_gate_authorized"]=False
    return result

def main():
    p=argparse.ArgumentParser()
    for key in ("observations","three-source","shadow","out"):
        p.add_argument("--"+key,required=True,type=Path)
    p.add_argument("--previous",type=Path)
    p.add_argument("--global-quota-guard",type=Path)
    a=p.parse_args()
    if set(a.out.parts)&{"telegram","governance","notifications","daily_prematch_reports"}:
        raise SystemExit("READ_ONLY_QUOTE_RESEARCH_ONLY")
    get=lambda path:json.loads(path.read_bytes())
    previous=get(a.previous) if a.previous and a.previous.is_file() else None
    guard=(get(a.global_quota_guard) if a.global_quota_guard and a.global_quota_guard.is_file() else None)
    if a.global_quota_guard and guard is None:guard={"schema":"BLOCKED_MISSING_GLOBAL_QUOTA_GUARD"}
    result=check(get(a.observations),get(getattr(a,"three_source")),get(a.shadow),
                 os.environ.get("ODDS_API_NET_KEY",""),previous=previous,global_quota_guard=guard)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"network_calls":result["network_calls"],
      "bookmaker_quotes":result["bookmaker_quote_verified_count"],
      "sharp_fresh":result["sharp_120s_verified_count"],"telegram":False},sort_keys=True))

if __name__=="__main__":main()
