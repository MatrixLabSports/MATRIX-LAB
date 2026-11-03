"""Independent historical scoreboard concordance against archived API-Football.

Only Serie A 2026 is examined because the exact paid-era physical group is
present in the repository. A good scoreboard match is NOT model calibration
parity and NEVER promotes signals or touches frozen parameters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from tools.api_football_market_shadow_p_matrix import _fixture, _inputs_for_target, _pool_over25
from tools.matrix_football_independent_over25_shadow import historic_rows

ARCHIVE=Path("evidence/api_football/prospective_daily/2026-10-28/20261028T054128Z/history/raw/league_135_season_2026.bin")
CYCLE=Path("evidence/api_football/prospective_daily/2026-10-28/20261028T054128Z/cycle_summary.json")
ENDPOINT="https://api.football-data.org/v4/competitions/SA/matches"
SOURCE_LEAGUE_ID=2019
ARCHIVED_API_LEAGUE_ID=135
MAX_BYTES=3_000_000

def utc(value):
    stamp=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if stamp.utcoffset() is None:raise ValueError("UNAWARE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)

def norm(value):
    s=unicodedata.normalize("NFKD",str(value or ""))
    s="".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+"," ",s).strip()

def sim(a,b):
    a,b=norm(a),norm(b)
    if not a or not b:return 0.
    ta,tb=set(a.split()),set(b.split())
    return max(1. if ta<=tb or tb<=ta else 0.,
               len(ta&tb)/max(1,len(ta|tb)),
               SequenceMatcher(None,a,b).ratio())

def parse_archive(raw,cutoff,*,archived_league_id=ARCHIVED_API_LEAGUE_ID,season=2026):
    arr=raw.get("response")
    if not isinstance(arr,list):raise ValueError("ARCHIVED_RAW_GROUP_INVALID")
    rows=[]
    for a in arr:
        if not isinstance(a,dict):continue
        league=a.get("league") or {}
        if league.get("id")!=archived_league_id or league.get("season")!=season:
            raise ValueError("ARCHIVED_LEAGUE_SCOPE_MISMATCH")
        fixture=a.get("fixture") or {}
        if (fixture.get("status") or {}).get("short")!="FT":continue
        teams=a.get("teams") or {}; goals=a.get("goals") or {}
        h,a_goals=goals.get("home"),goals.get("away")
        if isinstance(h,bool) or isinstance(a_goals,bool) or not isinstance(h,int) or not isinstance(a_goals,int):
            continue
        try:
            kickoff=utc(fixture["date"])
            if kickoff>=cutoff:continue
            home=(teams["home"] or {})["name"];away=(teams["away"] or {})["name"]
        except (KeyError,ValueError,TypeError):
            continue
        rows.append({"id":str(fixture["id"]),"kickoff":kickoff,"home":home,"away":away,"home_goals":h,"away_goals":a_goals})
    return rows

def parse_free(raw,cutoff,*,source_league_id=SOURCE_LEAGUE_ID):
    arr=raw.get("matches")
    if not isinstance(arr,list):raise ValueError("FREE_HISTORY_MATCHES_INVALID")
    rows=[]
    for x in arr:
        if not isinstance(x,dict) or x.get("status")!="FINISHED":continue
        comp=x.get("competition") or raw.get("competition") or {}
        if comp.get("id")!=source_league_id:
            raise ValueError("FREE_HISTORICAL_COMPETITION_ID_MISMATCH")
        score=((x.get("score") or {}).get("fullTime") or {})
        h,a=score.get("home"),score.get("away")
        if isinstance(h,bool) or isinstance(a,bool) or not isinstance(h,int) or not isinstance(a,int):continue
        try:
            kickoff=utc(x["utcDate"])
            if kickoff>=cutoff:continue
            home=x["homeTeam"]["name"];away=x["awayTeam"]["name"]
        except (TypeError,KeyError,ValueError):continue
        rows.append({"id":str(x["id"]),"kickoff":kickoff,"home":home,"away":away,"home_goals":h,"away_goals":a})
    return rows

def compare(api_rows,free_rows):
    out={"matches":[],"score_disagreements":[],"unmatched_free":[],"ambiguous":[]}
    used=set()
    for f in free_rows:
        candidates=[]
        for a in api_rows:
            seconds=abs((a["kickoff"]-f["kickoff"]).total_seconds())
            if seconds>600:continue
            home=sim(a["home"],f["home"]);away=sim(a["away"],f["away"])
            swapped=(sim(a["home"],f["away"])+sim(a["away"],f["home"]))/2
            score=(home+away)/2
            if home>=0.70 and away>=0.70 and score>swapped+0.10:
                candidates.append((score,a))
        candidates.sort(key=lambda x:x[0],reverse=True)
        if not candidates:
            out["unmatched_free"].append(f["id"]);continue
        if len(candidates)>1 and candidates[0][0]-candidates[1][0]<0.10:
            out["ambiguous"].append(f["id"]);continue
        a=candidates[0][1]
        if a["id"] in used:
            out["ambiguous"].append(f["id"]);continue
        used.add(a["id"])
        meta={"free_id":f["id"],"archived_api_id":a["id"],"kickoff_utc":f["kickoff"].isoformat(),
              "name_agreement":round(candidates[0][0],4)}
        if (f["home_goals"],f["away_goals"])!=(a["home_goals"],a["away_goals"]):
            out["score_disagreements"].append({**meta,
                "free_goals":[f["home_goals"],f["away_goals"]],
                "archived_api_goals":[a["home_goals"],a["away_goals"]]})
        else:
            out["matches"].append(meta)
    return out

def compare_raw_features(archived_payload, free_payload, matched_pairs, cutoff,
                         *, source_league_id=SOURCE_LEAGUE_ID,
                         archived_api_league_id=ARCHIVED_API_LEAGUE_ID):
    """Side-by-side PIT features from real archived and independent score groups.

    Research only.  These raw-group features do NOT certify the original
    CANONICAL_ENRICHED_PIT inputs, which are absent from this comparison.
    No output from this function may become an executable betting candidate.
    """
    archive_rows = sorted(
        (z for raw in archived_payload["response"] if (z := _fixture(raw)) is not None
         and z["kickoff_utc"] < cutoff),
        key=lambda row: (row["kickoff_utc"], row["fixture_id"]),
    )
    free_rows = [r for r in historic_rows(free_payload, source_league_id)
                 if r["kickoff_utc"] < cutoff]
    original = {r["fixture_id"]: r for r in archive_rows}
    independent = {r["fixture_id"]: r for r in free_rows}
    results = {
        "schema": "MATRIX_SERIE_A_RAW_GROUP_PIT_FEATURE_REPLAY_V1",
        "source_league": source_league_id,
        "reference_league": archived_api_league_id,
        "pairs_with_matching_full_time_score": len(matched_pairs),
        "pairs_with_valid_raw_provider_ids": 0,
        "scoreable_both": 0,
        "same_raw_group_feature_and_probability_count": 0,
        "different_raw_group_feature_or_probability_count": 0,
        "blocked_both": 0,
        "blocked_one_side": 0,
        "not_found_in_raw_group": 0,
        "max_absolute_model_probability_difference": 0.0,
        "feature_differences": [],
        "blocked_examples": [],
        "source_data_is_historical_outcomes_for_parity_audit_only": True,
        "future_target_outcomes_used": False,
        "original_p_matrix_calibration_refit": False,
        "canonical_enriched_pit_parity_verified": False,
        "all_six_leagues_equivalence_verified": False,
        "signal_generation_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    for pair in matched_pairs:
        arch = original.get(pair["archived_api_id"])
        free = independent.get(pair["free_id"])
        if not arch or not free:
            results["not_found_in_raw_group"] += 1
            continue
        results["pairs_with_valid_raw_provider_ids"] += 1
        af, ar = _inputs_for_target(archive_rows, arch)
        ff, fr = _inputs_for_target(free_rows, free)
        if af is None or ff is None:
            key = "blocked_both" if af is None and ff is None else "blocked_one_side"
            results[key] += 1
            if len(results["blocked_examples"]) < 12:
                results["blocked_examples"].append({
                    "archived_api_id": pair["archived_api_id"],
                    "free_id": pair["free_id"],
                    "archived_reason": ar,
                    "free_reason": fr,
                })
            continue
        results["scoreable_both"] += 1
        keys = ("prior_group_fixture_count", "home_history_count",
                "away_history_count", "home_history_source",
                "away_history_source", "expected_home_goals",
                "expected_away_goals")
        num_keys = ("expected_home_goals", "expected_away_goals")
        count_equal = all(
            (abs(af[key] - ff[key]) <= 1e-8 if key in num_keys else af[key] == ff[key])
            for key in keys
        )
        poisson_equal = abs(
            af["poisson"]["over_2_5"] - ff["poisson"]["over_2_5"]
        ) <= 1e-8
        baseline_equal = abs(
            af["baseline"]["over_2_5"] - ff["baseline"]["over_2_5"]
        ) <= 1e-8
        pa = _pool_over25(af["poisson"]["over_2_5"], af["baseline"]["over_2_5"])
        pf = _pool_over25(ff["poisson"]["over_2_5"], ff["baseline"]["over_2_5"])
        difference = abs(pa - pf)
        results["max_absolute_model_probability_difference"] = max(
            results["max_absolute_model_probability_difference"], difference
        )
        if count_equal and poisson_equal and baseline_equal and difference <= 1e-8:
            results["same_raw_group_feature_and_probability_count"] += 1
        else:
            results["different_raw_group_feature_or_probability_count"] += 1
            if len(results["feature_differences"]) < 12:
                results["feature_differences"].append({
                    "archived_api_id": pair["archived_api_id"],
                    "free_id": pair["free_id"],
                    "archived_feature_counts": {
                        k: af[k] for k in keys[:3]
                    },
                    "independent_feature_counts": {
                        k: ff[k] for k in keys[:3]
                    },
                    "archived_expected_goals": [
                        af["expected_home_goals"], af["expected_away_goals"]
                    ],
                    "independent_expected_goals": [
                        ff["expected_home_goals"], ff["expected_away_goals"]
                    ],
                    "probability_difference": round(difference, 10),
                })
    return results



def inspect(token,*,archive=ARCHIVE,cycle=CYCLE,opener=urlopen):
    result={"schema":"MATRIX_INDEPENDENT_OVER25_SERIE_A_SOURCE_PARITY_V1",
            "source":"FOOTBALL_DATA_ORG","reference_source":"ARCHIVED_API_FOOTBALL",
            "source_league_id":SOURCE_LEAGUE_ID,"reference_league_id":ARCHIVED_API_LEAGUE_ID,
            "scope":"SERIE_A_2026_FINISHED_BEFORE_ARCHIVED_CYCLE",
            "status":"BLOCKED_PARITY_UNVERIFIED","network_calls":0,
            "history_result_concordance_verified":False,
            "equivalence_across_all_six_leagues_verified":False,
            "calibrated_model_feature_equivalence_verified":False,
            "odds_quote_verified":False,"signal_generation_authorized":False,
            "real_money":"BLOCKED","automatic_wagering":False}
    try:
        raw=archive.read_bytes()
        cycle_summary=json.loads(cycle.read_text(encoding="utf-8"))
        assert cycle_summary["status"]=="PASS"
        cutoff=utc(cycle_summary["finished_at_utc"])
        api=parse_archive(json.loads(raw.decode("utf-8")),cutoff)
        result["reference_raw_sha256"]=hashlib.sha256(raw).hexdigest()
        result["reference_raw_path"]=str(archive)
        result["reference_fixture_count"]=len(api)
        result["reference_cycle_cutoff_utc"]=cutoff.isoformat()
        if not token.strip():
            result["status"]="BLOCKED_MISSING_FREE_PROVIDER_KEY"
            return result
        request=Request(ENDPOINT,headers={"X-Auth-Token":token.strip(),"Accept":"application/json"})
        result["network_calls"]=1
        with opener(request,timeout=25) as response:
            status=int(response.status);body=response.read(MAX_BYTES+1)
        result["free_provider_http_status"]=status
        result["free_response_sha256"]=hashlib.sha256(body).hexdigest()
        if status!=200 or len(body)>MAX_BYTES:
            result["status"]="BLOCKED_FREE_PROVIDER_HTTP_OR_SIZE"
            return result
        free=parse_free(json.loads(body.decode("utf-8")),cutoff)
        result["free_fixture_count"]=len(free)
        pairs=compare(api,free)
        result["raw_group_feature_parity"] = compare_raw_features(
            json.loads(raw.decode("utf-8")),
            json.loads(body.decode("utf-8")),
            pairs["matches"], cutoff,
        )
        result["matched_exact_result_count"]=len(pairs["matches"])
        result["score_disagreement_count"]=len(pairs["score_disagreements"])
        result["ambiguous_count"]=len(pairs["ambiguous"])
        result["unmatched_free_count"]=len(pairs["unmatched_free"])
        result["source_fixture_matching_rate"]=round(len(pairs["matches"])/len(free),4) if free else None
        result["score_disagreements"]=pairs["score_disagreements"][:10]
        result["examples"]=pairs["matches"][:12]
        passed=(len(pairs["matches"])>=20 and not pairs["score_disagreements"] and
                len(pairs["matches"])/max(1,len(free))>=0.7)
        result["history_result_concordance_verified"]=passed
        result["status"]="PASS_SERIE_A_HISTORICAL_SCORE_CONCORDANCE_ONLY" if passed else "BLOCKED_SOURCE_SCORE_PARITY_INCOMPLETE"
    except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError,TypeError,AssertionError,UnicodeError) as exc:
        result["status"]="BLOCKED_PARITY_PROBE_ERROR"
        result["error_type"]=type(exc).__name__
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    r=inspect(os.environ.get("FOOTBALL_DATA_ORG_TOKEN",""))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(r,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:r.get(k) for k in ("status","network_calls","matched_exact_result_count",
                                            "score_disagreement_count","history_result_concordance_verified",
                                            "calibrated_model_feature_equivalence_verified")},sort_keys=True))
if __name__=="__main__":
    main()
