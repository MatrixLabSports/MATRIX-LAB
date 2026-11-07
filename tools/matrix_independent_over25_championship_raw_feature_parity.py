"""Championship 2026 archived API-Football vs authenticated football-data.org.

Uses the same physical PIT replay as the previously validated Brazil/Italy
research audits. Never changes calibrated source, p_matrix, Telegram or wagers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.matrix_independent_over25_historical_parity import (
    utc, parse_archive, parse_free, compare, compare_raw_features,
)

ARCHIVE=Path("evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z/history/raw/league_40_season_2026.bin")
CYCLE=Path("evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z/cycle_summary.json")
ENDPOINT="https://api.football-data.org/v4/competitions/ELC/matches"
SOURCE_LEAGUE=2016
ARCHIVED_LEAGUE=40
MAX_BYTES=3_000_000

def inspect(token: str, *, archive:Path=ARCHIVE, cycle:Path=CYCLE, opener=urlopen)->dict:
    result={
       "schema":"MATRIX_CHAMPIONSHIP_RAW_GROUP_PIT_REPLAY_V1",
       "source":"FOOTBALL_DATA_ORG","reference_source":"ARCHIVED_API_FOOTBALL",
       "source_league_id":SOURCE_LEAGUE,"reference_league_id":ARCHIVED_LEAGUE,
       "scope":"HISTORICAL_2026_PRIOR_TO_ARCHIVED_CYCLE_ONLY",
       "status":"BLOCKED_PARITY_UNVERIFIED","network_calls":0,
       "historical_score_concordance_verified":False,
       "original_calibrated_feature_equivalence_verified":False,
       "canonical_enriched_pit_parity_verified":False,
       "all_six_leagues_equivalence_verified":False,
       "model_parameters_mutated":False,
       "signal_generation_authorized":False,
       "automatic_wagering":False,"real_money":"BLOCKED"
    }
    try:
        raw=archive.read_bytes()
        cycle_json=json.loads(cycle.read_text(encoding="utf-8"))
        if cycle_json.get("status")!="PASS":
            raise ValueError("ARCHIVED_REFERENCE_NOT_PASS")
        cutoff=utc(cycle_json["finished_at_utc"])
        archived_payload=json.loads(raw.decode("utf-8"))
        archived=parse_archive(archived_payload,cutoff,archived_league_id=ARCHIVED_LEAGUE)
        result.update({
          "reference_archive_sha256":hashlib.sha256(raw).hexdigest(),
          "reference_archive_path":str(archive),
          "reference_cycle_cutoff_utc":cutoff.isoformat(),
          "reference_fixture_count":len(archived)
        })
        if not str(token).strip():
            result["status"]="BLOCKED_MISSING_FREE_PROVIDER_KEY"
            return result
        request=Request(ENDPOINT,headers={"X-Auth-Token":token.strip(),"Accept":"application/json"})
        result["network_calls"]=1
        with opener(request,timeout=25) as response:
            status=int(response.status)
            body=response.read(MAX_BYTES+1)
        result.update({"free_provider_http_status":status,"free_response_sha256":hashlib.sha256(body).hexdigest()})
        if status!=200 or len(body)>MAX_BYTES:
            result["status"]="BLOCKED_FREE_PROVIDER_HTTP_OR_SIZE"
            return result
        free_payload=json.loads(body.decode("utf-8"))
        free=parse_free(free_payload,cutoff,source_league_id=SOURCE_LEAGUE)
        pairs=compare(archived,free)
        result.update({
          "free_fixture_count":len(free),
          "matched_score_count":len(pairs["matches"]),
          "score_disagreements":len(pairs["score_disagreements"]),
          "ambiguous":len(pairs["ambiguous"]),
          "unmatched_free":len(pairs["unmatched_free"]),
          "score_pairs":pairs["matches"][:12],
        })
        result["raw_group_feature_parity"]=compare_raw_features(
          archived_payload,free_payload,pairs["matches"],cutoff,
          source_league_id=SOURCE_LEAGUE,archived_api_league_id=ARCHIVED_LEAGUE
        )
        passed=(len(pairs["matches"])>=20 and
                len(pairs["score_disagreements"])==0 and
                len(pairs["ambiguous"])==0 and
                len(pairs["matches"])/max(1,len(free))>=0.7)
        result["historical_score_concordance_verified"]=passed
        result["status"]=(
           "PASS_CHAMPIONSHIP_HISTORICAL_SCORE_CONCORDANCE_ONLY" if passed
           else "BLOCKED_CHAMPIONSHIP_SCORE_PARITY_INCOMPLETE"
        )
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError,TypeError,AssertionError,UnicodeError) as exc:
        result["status"]="BLOCKED_CHAMPIONSHIP_PARITY_PROBE_ERROR"
        result["error_type"]=type(exc).__name__
    return result

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    if "daily_prematch_reports" in a.out.parts or "tennis_signals" in a.out.parts:
        raise SystemExit("HISTORICAL_PARITY_CANNOT_WRITE_CANONICAL_SIGNALS")
    result=inspect(os.environ.get("FOOTBALL_DATA_ORG_TOKEN",""))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result.get(k) for k in ("status","network_calls","matched_score_count","historical_score_concordance_verified","original_calibrated_feature_equivalence_verified","signal_generation_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
