"""Explain exact 8/11 historic Championship bridge gaps without future-score leakage.

Eight of eleven are MATCHES (not model feature dimensions). Input bytes
come from archived, cross-checked bridge replay. This never promotes p_matrix.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
from tools.matrix_championship_enriched_provider_bridge import replay, dt
from tools.matrix_championship_cross_provider_archived_replay import CYCLE
from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.matrix_independent_over25_historical_parity import sim

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"

def diagnose(shadow:dict, *, cycle:Path=CYCLE)->dict:
    bridge=replay(shadow,cycle=cycle)
    if bridge.get("original_canonical_targets")!=11:
        raise ValueError("HISTORIC_11_TARGET_SCOPE_CHANGED")
    bundle,manifest=load_chunked_canonical_bundle(cycle.parent/"canonical_analysis")
    if manifest.get("bundle_sha256")!=bridge["original_bundle_sha256"]:
        raise ValueError("ORIGINAL_BUNDLE_HASH_MISMATCH")
    src=shadow["authenticated_raw_group_replay_evidence"]["2016"]
    raw=base64.b64decode(src["response_base64"],validate=True)
    if hashlib.sha256(raw).hexdigest()!=bridge["source_provider_sha256"]:
        raise ValueError("FREE_HISTORY_SHA_MISMATCH")
    source=json.loads(raw)
    original={str(x["fixture_id"]):x for x in bundle["inputs"]
              if str(x.get("competition_id"))=="40"}
    blocked=[]
    for row in bridge["rows"]:
        if row["status"]=="PASS_HISTORICAL_THREE_WAY_ENRICHED_BRIDGE_ONLY":
            continue
        ident=row["original_api_fixture_id"]
        target=original[ident]
        kickoff=dt(target["kickoff_utc"])
        choices=[]
        for m in source["matches"]:
            try:
                when=dt(m["utcDate"])
                if abs((kickoff-when).total_seconds())>600:
                    continue
                competition=m.get("competition") or source.get("competition") or {}
                if str(competition.get("id"))!="2016":continue
                h=m["homeTeam"];a=m["awayTeam"]
                home_sim=sim(target["home_team_name"],h["name"])
                away_sim=sim(target["away_team_name"],a["name"])
                swapped=(sim(target["home_team_name"],a["name"])+
                          sim(target["away_team_name"],h["name"]))/2
                choices.append({
                    "free_fixture_id":str(m["id"]),
                    "free_home_team_id":str(h["id"]), "free_away_team_id":str(a["id"]),
                    "free_home_name":str(h["name"]),"free_away_name":str(a["name"]),
                    "home_name_similarity":round(home_sim,5),
                    "away_name_similarity":round(away_sim,5),
                    "swap_similarity":round(swapped,5),
                    "matches_strict_historical_name_gate":(
                        home_sim>=0.83 and away_sim>=0.83 and
                        (home_sim+away_sim)/2 >= swapped+0.12),
                })
            except (KeyError,TypeError,ValueError,AttributeError):
                continue
        choices.sort(key=lambda z:(-(z["home_name_similarity"]+z["away_name_similarity"]),
                                   z["free_fixture_id"]))
        blocked.append({
            "original_api_fixture_id":ident,
            "original_home_name":target["home_team_name"],
            "original_away_name":target["away_team_name"],
            "original_home_team_id":str(target["home_team_id"]),
            "original_away_team_id":str(target["away_team_id"]),
            "kickoff_utc":target["kickoff_utc"],
            "original_status":row["status"],
            "calendar_candidates_same_kickoff":choices[:10],
            "strict_name_gate_matches":sum(bool(z["matches_strict_historical_name_gate"]) for z in choices),
            "historical_crosswalk_recovered":False,
            "prospective_crosswalk_verified":False,
        })
    return {
        "schema":"MATRIX_CHAMPIONSHIP_EIGHT_OF_ELEVEN_IDENTITY_GAP_DIAGNOSTIC_V1",
        "interpretation":"EIGHT_OF_ELEVEN_HISTORICAL_FIXTURES_NOT_FEATURE_DIMENSIONS",
        "historical_fixture_count":bridge["original_canonical_targets"],
        "historical_paired_count":bridge["historical_three_way_parity_count"],
        "historical_blocked_count":len(blocked),
        "blocked_ids":[x["original_api_fixture_id"] for x in blocked],
        "blocked":blocked,
        "original_archive_sha256":bridge["original_archive_sha256"],
        "source_provider_sha256":bridge["source_provider_sha256"],
        "original_bundle_sha256":bridge["original_bundle_sha256"],
        "cutoff_utc":bridge["original_analysis_as_of_utc"],
        "source_calendar_observed_after_cutoff_not_prospective":True,
        "source_game_outcomes_used_for_identity_candidates":False,
        "unmatched_three_repaired":False,
        "calibration_parameters_modified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",type=Path,default=SOURCE)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if any(x in a.out.parts for x in ("daily_prematch_reports","telegram","tennis_signals","governance")):
        raise SystemExit("RESEARCH_DIAGNOSTIC_CANNOT_WRITE_PRODUCTION")
    value=diagnose(json.loads(a.source.read_text(encoding="utf-8")))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":"HISTORICAL_IDENTITY_GAPS_PHYSICALLY_DIAGNOSED",
      "historical_paired_count":value["historical_paired_count"],
      "blocked_ids":value["blocked_ids"],
      "production_p_matrix_authorized":False
    },sort_keys=True))

if __name__=="__main__":main()
