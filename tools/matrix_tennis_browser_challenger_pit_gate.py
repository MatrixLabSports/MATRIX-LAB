"""Source-evidenced, model-isolated Challenger Hard/Clay prematch readiness.

Works from actual previously captured Opera match pages and earlier archived
SofaScore/Flashscore crossmatch. Never fabricates surface, kickoff, ranking,
identity or historical player features; never writes governed holdouts.
"""
from __future__ import annotations
import argparse,hashlib,json,unicodedata,re
from datetime import datetime,timezone,date
from zoneinfo import ZoneInfo
from pathlib import Path
from tools.matrix_tennis_exact_browser_crossmatch import fingerprint
from tools.matrix_tennis_browser_first_free_intake import ROOT as CAPTURE_ROOT

DETAIL="sofascore_verified_match_details.json"
CROSS="MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json"
COUNTRY_IOC={"USA":"USA","Switzerland":"SUI","Peru":"PER","Brazil":"BRA","Argentina":"ARG"}
AUTHORITIES={"Hard":"evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json",
"Clay":"evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/identity/MATRIX_CLAY_IDENTITY_AUTHORITY_LAST.json"}
OUT=Path("evidence/tennis_calendar_reconciliation")

def sha(b):return hashlib.sha256(b).hexdigest()
def timestamp(x):
    z=datetime.fromisoformat(str(x).replace("Z","+00:00"))
    if z.tzinfo is None or z.utcoffset() is None:raise ValueError("TIMESTAMP_WITHOUT_TZ")
    return z.astimezone(timezone.utc)
def read(root,p):
    q=root/p
    if not q.is_file():raise ValueError("REQUIRED_ORIGINAL_EVIDENCE_MISSING:"+str(p))
    if q.stat().st_size>7_000_000:raise ValueError("ORIGINAL_EVIDENCE_TOO_LARGE:"+str(p))
    raw=q.read_bytes()
    return json.loads(raw),sha(raw)
def normal(x):
    return " ".join(fingerprint(str(x)))

BOGOTA=ZoneInfo("America/Bogota")

def kickoff_in_bogota_calendar_day(kickoff:datetime,day:str)->bool:
    """The source is a Bogotá-local calendar; UTC dates may be next day."""
    if kickoff.tzinfo is None or kickoff.utcoffset() is None:
        raise ValueError("KICKOFF_TIMEZONE_REQUIRED")
    return kickoff.astimezone(BOGOTA).date()==date.fromisoformat(day)

def evaluate(root:Path,day:str,now:datetime):
    date.fromisoformat(day);now=now.astimezone(timezone.utc)
    details,detailsha=read(root,CAPTURE_ROOT/day/DETAIL)
    cross,crosssha=read(root,OUT/day/CROSS)
    if (details.get("schema")!="MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or cross.get("schema")!="MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1"
        or details.get("target_date_bogota")!=day
        or cross.get("target_date_bogota")!=day
        or details.get("real_money")!="BLOCKED" or cross.get("real_money")!="BLOCKED"
        or details.get("telegram_signal_authorized") is not False
        or cross.get("source_event_equivalence_certified") is not False):
        raise ValueError("UNTRUSTED_OBSERVATION_GOVERNANCE")
    # New browser captures must bind exactly to the cross-source snapshot.
    # Archived 2026-11-04 manually observed pages predate this optional field.
    declared_cross_sha = details.get("source_crossmatch_sha256")
    if declared_cross_sha is not None and declared_cross_sha != crosssha:
        raise ValueError("TENNIS_DETAIL_CROSSMATCH_SHA256_MISMATCH")
    # Research-only birthday and independently observed Flashscore clocks.
    # If a snapshot exists it MUST bind to precisely the source bytes frozen
    # for this match day; stale research must never silently certify a clock.
    research_path=OUT/day/"MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST.json"
    research_by_id={}
    if (root/research_path).is_file():
        research,_=read(root,research_path)
        digests=research.get("source_sha256") or {}
        if (research.get("schema")!="MATRIX_TENNIS_RESEARCH_BIOGRAPHY_CROSSWALK_LAST_V1"
            or research.get("target_date_bogota")!=day
            or digests.get("prematch_details")!=detailsha
            or digests.get("source_crossmatch")!=crosssha
            or research.get("real_money")!="BLOCKED"
            or research.get("provider_id_equivalence_approved_for_model") is not False
            or research.get("new_hard_holdout_admissions")!=0
            or research.get("new_clay_holdout_admissions")!=0):
            raise ValueError("TENNIS_BIOGRAPHY_CLOCK_RESEARCH_SOURCE_DRIFT")
        research_by_id={str(x["sofascore_id"]):x for x in research.get("events") or []}
        if len(research_by_id)!=len(research.get("events") or []):
            raise ValueError("DUPLICATE_RESEARCH_EVENT_ID")
    observed=timestamp(details["observed_at_utc"])
    if observed>now:raise ValueError("DETAIL_CAPTURE_TIMESTAMP_IN_FUTURE")
    crossrows={str(x["sofascore_id"]):x for x in cross.get("matches") or []}
    # Original identity histories are from the separate pre-cut-off authority,
    # NOT from postmatch scores or a new unnamed player provider.
    authority={}
    a_shas={}
    for surface,p in AUTHORITIES.items():
        a,h=read(root,Path(p));a_shas[surface]=h
        if (a.get("outcomes_used") is not False or
            a.get("post_cut_competitive_data_used") is not False or
            a.get("silent_imputation") is not False or a.get("real_money")!="BLOCKED"):
            raise ValueError("HISTORIC_IDENTITY_AUTHORITY_NOT_PRE_CUT")
        by_name={}
        for row in a.get("records",[]):
            if isinstance(row,dict):
                key=normal(row.get("provider_display_name") or "")
                if key:by_name.setdefault(key,[]).append(row)
        authority[surface]=by_name
    seen=set();rows=[]
    for x in details.get("events") or []:
        sid=str(x.get("sofascore_event_id") or "")
        if sid in seen:raise ValueError("DUPLICATE_SOFA_EVENT")
        seen.add(sid)
        status=[];valid=True
        rec=research_by_id.get(sid)
        event_clock_display_consistent=None
        bio_research_triplet_verified=False
        if rec:
            clock=rec.get("independent_match_page_clock") or {}
            event_clock_display_consistent=clock.get("displayed_clock_agrees")
            bio_research_triplet_verified=(rec.get("biographical_triplet_matches")==2)
            if event_clock_display_consistent is not True and event_clock_display_consistent is not False:
                raise ValueError("UNVERIFIED_INDEPENDENT_CLOCK_RESEARCH")
        if event_clock_display_consistent is False:
            status.append("TWO_PROVIDER_FIXTURE_START_DISPLAY_CONFLICT");valid=False
        s=x.get("surface")
        if s not in ("Hard","Clay"):status.append("SURFACE_NOT_CANONICAL");valid=False
        # Exact source-readable court labels only: both indoor and outdoor
        # hard are Hard; "outdoor" alone is not a hard-surface certificate.
        expected_court={"Hard":{"Dura indoor","Dura outdoor"},
                        "Clay":{"Tierra batida"}}
        if s not in expected_court or x.get("court_label") not in expected_court[s]:
            status.append("COURT_NOT_EXACT_MATCH");valid=False
        link=crossrows.get(sid)
        if not link or x.get("sofascore_url")!=link.get("sofascore_url") or x.get("flashscore_url")!=link.get("flashscore_url") or x.get("flashscore_mid")!=link.get("flashscore_mid"):
            status.append("TWO_SOURCE_REFERENCE_MISSING_OR_MISMATCH");valid=False
        players=x.get("players")
        if not isinstance(players,list) or len(players)!=2 or any(
           not isinstance(p,dict) or not p.get("sofascore_player_id") or
           not str(p.get("profile_url") or "").endswith("/"+str(p.get("sofascore_player_id"))) or
           not p.get("name") for p in players):
            status.append("EXACT_SOFA_PLAYER_LINKS_MISSING");valid=False
            players=[]
        else:
            tokens=fingerprint("-".join(p["name"] for p in players))
            if not link or tokens!=tuple(link["source_name_token_key"].split()):
                status.append("PLAYER_NAME_CONFLICT_ACROSS_SOURCES");valid=False
        try:
            kickoff=timestamp(x["kickoff_utc"])
            expected=datetime.strptime(x["calendar_date_token"],"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if kickoff!=expected or not kickoff_in_bogota_calendar_day(kickoff,day):
                status.append("EXACT_UTC_CALENDAR_IDENTITY_MISMATCH");valid=False
            source = x.get("kickoff_clock_source")
            if source is not None:
                if source == "VISIBLE_MATCH_DESCRIPTION_EXPLICIT_UTC":
                    quote = x.get("explicit_visible_utc_match_quote")
                    expected_quote = x.get("source_visible_match_fields",{}).get(
                        "explicit_utc_match_description_quote")
                    # Must be the same explicit UTC quote bound at capture.
                    if not quote or quote != expected_quote or "UTC" not in quote:
                        status.append("EXPLICIT_UTC_SOURCE_PROVENANCE_MISSING");valid=False
                elif source != "GOOGLE_CALENDAR_EXACT_UTC":
                    status.append("UNAPPROVED_KICKOFF_CLOCK_SOURCE");valid=False
            if observed>=kickoff:
                status.append("MATCH_PAGE_CAPTURE_AFTER_KICKOFF");valid=False
            if now>=kickoff:
                status.append("PROSPECTIVE_SCORE_WINDOW_CLOSED");valid=False
        except (TypeError,ValueError,KeyError):
            status.append("KICKOFF_CALENDAR_INCONSISTENT");valid=False
            kickoff=None
        tournament_url = x.get("tournament_url")
        source_category_proved = (
            "Challenger" in str(x.get("competition_label") or "")
            or x.get("challenger_category_evidenced_by_tournament_url") is True
        )
        if (not isinstance(tournament_url,str)
            or not tournament_url.startswith("https://www.sofascore.com/es/tennis/tournament/challenger/")
            or not x.get("round") or not source_category_proved):
            status.append("ATP_CHALLENGER_TOURNAMENT_NOT_VERIFIED");valid=False
        hist=[]
        if s in authority:
            for player in players:
                match=authority[s].get(normal(player["name"]),[])
                if len(match)!=1:
                    hist.append({"player":player["name"],"status":"PRE_CUT_IDENTITY_ABSENT_OR_AMBIGUOUS"});continue
                p=match[0];h=p.get("pre_cut_history") or {}
                rows_n=h.get("rows")
                iocs=h.get("canonical_iocs") or []
                history_ids=h.get("canonical_source_ids") or []
                good=(iocs==[COUNTRY_IOC.get(player.get("country"))] and type(rows_n)==int and rows_n>=5 and len(iocs)==1 and
                      len(history_ids)==1 and type(h.get("latest_row_date"))==int
                      and h["latest_row_date"]<int(day.replace("-","")))
                hist.append({"player":player["name"],"status":"HISTORICAL_PRE_CUT_MATCH_ONLY_NOT_PROVIDER_ID_EQUIVALENCE" if good else "HISTORY_INSUFFICIENT_OR_AMBIGUOUS",
                   "pre_cut_rows":rows_n,
                   "original_canonical_source_id":history_ids[0] if good else None,
                   "pre_cut_latest_row_date":h.get("latest_row_date"),
                   "historical_provider_id":p.get("provider_player_id") if good else None,
                   "native_sofascore_player_id":player["sofascore_player_id"]})
        historical_count=sum(z["status"]=="HISTORICAL_PRE_CUT_MATCH_ONLY_NOT_PROVIDER_ID_EQUIVALENCE" for z in hist)
        readiness="SOURCE_METADATA_VERIFIED_MODEL_PIT_NOT_YET_ADMISSIBLE" if valid else "SOURCE_METADATA_BLOCKED"
        rows.append({"sofascore_id":sid,"surface":s,
          "source_detail_url":x.get("sofascore_url"),"flashscore_url":x.get("flashscore_url"),
          "kickoff_utc":kickoff.isoformat() if kickoff else None,
          "competition":x.get("competition_label"),
          "source_metadata_verified_before_kickoff":valid,
          "source_name_crossmatch_only":True,
          "source_profile_biographical_triplet_research_verified":bio_research_triplet_verified,
          "source_two_provider_fixture_clock_display_agrees":event_clock_display_consistent,
          "provider_clock_timezone_attested":False,
          "source_detail_capture_sha256":detailsha,
          "original_historical_authority_sha256":a_shas.get(s),
          "historical_players_found":historical_count,
          "historical_players_required":2,
          "historical_player_evidence":hist,
          "historical_provider_identity_equivalence_certified":False,
          "latest_pre_game_pit_features_certified":False,
          "current_rank_and_rank_points_certified":False,
          "model_probability_computed":False,
          "official_holdout_admitted":False,
          "blocked":status+["REQUIRES_VERIFIED_PROVIDER_PLAYER_CROSSWALK_AND_CURRENT_PIT_FEATURES"] if valid else status,
          "status":readiness})
    return {"schema":"MATRIX_TENNIS_BROWSER_CHALLENGER_PIT_GATE_V1",
      "target_date_bogota":day,
      "match_detail_sha256":detailsha,"name_crossmatch_sha256":crosssha,
      "original_authorities_sha256":a_shas,
      "source_metadata_verified_before_kickoff":sum(x["source_metadata_verified_before_kickoff"] for x in rows),
      "hard_source_metadata_ready":sum(x["surface"]=="Hard" and x["source_metadata_verified_before_kickoff"] for x in rows),
      "cross_provider_fixture_start_display_conflict_count":sum(x["source_two_provider_fixture_clock_display_agrees"] is False for x in rows),
      "clay_source_metadata_ready":sum(x["surface"]=="Clay" and x["source_metadata_verified_before_kickoff"] for x in rows),
      "new_hard_holdout_observations":0,"new_clay_holdout_observations":0,
      "original_model_weights_modified":False,"parties_approved_for_telegram":0,
      "automatic_wagering":False,"real_money":"BLOCKED","events":rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--date",required=True)
    a=p.parse_args()
    result=evaluate(a.root,a.date,datetime.now(timezone.utc))
    target=a.root/OUT/a.date/"MATRIX_TENNIS_BROWSER_CHALLENGER_PIT_GATE_LAST.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k in ("source_metadata_verified_before_kickoff","hard_source_metadata_ready","clay_source_metadata_ready","new_hard_holdout_observations","new_clay_holdout_observations")},sort_keys=True))
if __name__=="__main__":main()
