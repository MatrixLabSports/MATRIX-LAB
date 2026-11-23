"""Independent physical Colombia three-source fixture verification and PAPER gate.

Research probabilities never become official just because calendar identities match.
All inputs are fixed SHA-traceable evidence; no source data is invented or scraped.
"""
from __future__ import annotations
import argparse,json,re,unicodedata
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from zoneinfo import ZoneInfo

BOGOTA=ZoneInfo("America/Bogota")
ALIASES={"atl bucaramanga":"atletico bucaramanga"}
def norm(s):
    v=unicodedata.normalize("NFKD",str(s or "").casefold())
    return re.sub(r"[^a-z0-9]+"," ","".join(c for c in v if not unicodedata.combining(c))).strip()
def canon(s):return ALIASES.get(norm(s),norm(s))
def utc(s):
    d=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:raise ValueError("TIMEZONE_REQUIRED")
    return d.astimezone(timezone.utc)
def audit(obs,shadow,bridge,parity,quotes):
    if (obs.get("schema")!="MATRIX_COLOMBIA_239_LIVE_BROWSER_THREE_SOURCE_OBSERVATION_V1"
        or shadow.get("schema")!="MATRIX_COLOMBIA_239_ORIGINAL_ENGINE_FREE_SOURCE_PIT_SHADOW_V1"
        or bridge.get("schema")!="MATRIX_COLOMBIA_239_PROSPECTIVE_ESPN_HISTORIC_TEAM_BRIDGE_V1"
        or parity.get("schema")!="MATRIX_COLOMBIA_239_COMPLETE_SEASON_FT_GOALS_AND_FUTURE_IDENTITY_AUDIT_V1"
        or quotes.get("schema")!="MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT_V1"):
        raise ValueError("THREE_SOURCE_SCHEMA_INVALID")
    if any(d.get("real_money")!="BLOCKED" for d in (obs,shadow,bridge,parity,quotes)):
        raise ValueError("REAL_MONEY_GUARD_VIOLATION")
    if shadow.get("original_parameters")!={"a":0.6,"b":0.0,"c":0.4}:
        raise ValueError("ORIGINAL_CALIBRATION_MUTATED")
    if (shadow.get("production_p_matrix_authorized") is not False
        or shadow.get("telegram_signal_authorized") is not False
        or parity.get("original_enriched_feature_equivalence_certified") is not False
        or obs.get("signal_generation_authorized") is not False
        or quotes.get("signal_generation_authorized") is not False):
        raise ValueError("UNTRUSTED_SOURCE_PROMOTION")
    when=utc(obs["observed_at_utc"])
    researched={str(x["espn_event_id"]):x for x in shadow["research_scores"]}
    prereg={str(x["espn_current_fixture_id"]):x for x in bridge["historically_joined_research_only_fixtures"]}
    parity_reg={str(x["espn_current_fixture_id"]):x for x in parity["future_native_team_identity_bridged_rows"]}
    if len(researched)!=shadow["research_scores_count"]:
        raise ValueError("DUPLICATE_RESEARCH_EVENT_ID")
    matched=[];blocked=[];seen=set();sofa_seen=set();flash_seen=set()
    for row in obs["fixtures"]:
        event_id=str(row["espn_event_id"])
        if event_id in seen:raise ValueError("DUPLICATE_ESPN_EVENT")
        seen.add(event_id)
        sofa=row["sofascore"];flash=row["flashscore"]
        sid=str(sofa["event_id"]);mid=str(flash["mid"])
        if sid in sofa_seen or mid in flash_seen:raise ValueError("DUPLICATE_BROWSER_PROVIDER_ID")
        sofa_seen.add(sid);flash_seen.add(mid)
        if not sid.isdecimal() or not re.fullmatch("[a-zA-Z0-9]{8}",mid):
            raise ValueError("INVALID_PROVIDER_NATIVE_EVENT_ID")
        sp=urlparse(sofa["url"]);fp=urlparse(flash["url"])
        if (sp.scheme!="https" or sp.netloc!="www.sofascore.com"
            or not sp.path.startswith("/es/football/match/") or sp.fragment!="id:"+sid
            or fp.scheme!="https" or fp.netloc!="www.flashscore.co"
            or not fp.path.startswith("/partido/futbol/") or parse_qs(fp.query).get("mid")!=[mid]):
            raise ValueError("PROVIDER_EVENT_LINK_NOT_AUTHENTICATED")
        if row["espn_event_id"] not in researched or event_id not in prereg or event_id not in parity_reg:
            raise ValueError("MISSING_PRIOR_SHA_BOUND_RESEARCH_SOURCE")
        research=researched[event_id];historic=prereg[event_id];source=parity_reg[event_id]
        kickoff=utc(row["kickoff_utc"])
        if (kickoff<=when or kickoff!=utc(research["kickoff_utc"])
            or kickoff!=utc(historic["kickoff_utc"])
            or kickoff!=utc(source["kickoff_utc"])):
            raise ValueError("MULTI_SOURCE_KICKOFF_OR_LOOKAHEAD")
        dt=kickoff.astimezone(BOGOTA)
        expected_sofa=dt.strftime("%d/%m/%y %H:%M")
        expected_flash=dt.strftime("%d.%m. %H:%M")
        if sofa["calendar_display"]!=expected_sofa or flash["calendar_display"]!=expected_flash:
            raise ValueError("BROWSER_DATE_AND_TIME_MISMATCH")
        if any(canon(row[side])!=canon(sofa[side]) or canon(row[side])!=canon(flash[side])
               for side in ("home","away")):
            raise ValueError("BROWSER_TEAM_ORIENTATION_MISMATCH")
        if (research.get("scored_at_utc") is None
            or utc(research["scored_at_utc"])>=kickoff
            or research.get("source_feature_equivalence_certified") is not False
            or research.get("telegram_signal_authorized") is not False):
            raise ValueError("RESEARCH_RESULT_NOT_PREMATCH_GOVERNED")
        if (historic["home"]["espn_team_id"]!=source["home"]["espn_team_id"]
            or historic["away"]["espn_team_id"]!=source["away"]["espn_team_id"]):
            raise ValueError("ESPN_TEAM_ID_CONTRADICTION")
        matched.append({"espn_event_id":event_id,"sofascore_event_id":sid,
            "flashscore_mid":mid,"kickoff_utc":kickoff.isoformat(),
            "home":row["home"],"away":row["away"],
            "source_fixture_identity_on_three_calendars_verified":True,
            "research_p_over25":research["p_over25_research_only"],
            "canonical_probability_authorized":False,
            "bookmaker_price_verified":False,"telegram_authorized":False})
    if (obs["target_date_bogota"]!="2026-11-24"
        or quotes.get("target_date_bogota")!="2026-11-24"):
        raise ValueError("CROSS_SOURCE_LOCAL_DAY_MISMATCH")
    result={"schema":"MATRIX_COLOMBIA_239_THREE_SOURCE_RESEARCH_TO_TELEGRAM_GUARD_V1",
      "status":"THREE_SOURCE_CALENDAR_VERIFIED_RESEARCH_ONLY_QUOTE_AND_PARITY_BLOCKED",
      "source_order":["SOFASCORE","FLASHSCORE","ESPN"],
      "browser_observed_at_utc":when.isoformat(),
      "three_calendar_matches":len(matched),
      "three_source_matches":matched,
      "discrepancy_count":parity["original_results_unmatched_count"],
      "strict_historical_goals_matches":parity["exact_original_goals_time_and_team_parity_count"],
      "all_original_enriched_features_certified":False,
      "scientific_oos_certified":False,
      "last_quote_audit_status":quotes["status"],
      "last_quote_audit_bookmaker_verified":quotes["bookmaker_quote_verified_count"],
      "last_quote_audit_sharp_verified":quotes["sharp_120s_verified_count"],
      "true_official_p_matrix_candidates":0,"telegram_green_signals_authorized":0,
      "production_p_matrix_authorized":False,"telegram_signal_authorized":False,
      "automatic_wagering":False,"real_money":"BLOCKED"}
    if result["last_quote_audit_bookmaker_verified"] or result["last_quote_audit_sharp_verified"]:
        result["status"]="THREE_SOURCE_CALENDAR_VERIFIED_QUOTE_GATE_REQUIRES_SEPARATE_AUTHENTICATION"
    return result

def main():
    p=argparse.ArgumentParser()
    for x in ("observations","shadow","bridge","parity","quotes","out"):
        p.add_argument("--"+x,required=True,type=Path)
    a=p.parse_args()
    path=a.out
    if any(x in path.parts for x in ("telegram","notifications","governance","daily_prematch_reports")):
        raise SystemExit("NO_WRITES_TO_PRODUCTION")
    load=lambda x:json.loads(x.read_bytes())
    j=audit(load(a.observations),load(a.shadow),load(a.bridge),load(a.parity),load(a.quotes))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(j,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"verified_calendar_matches":j["three_calendar_matches"],
        "official_candidates":0,"quotes":j["last_quote_audit_bookmaker_verified"],
        "telegram":False}))
if __name__=="__main__":main()
