"""Strict historical three-way bridge: API-Football canonical enriched -> raw -> free raw.

Maps team IDs solely from verified historical result pairs BEFORE the original
analysis cutoff. It NEVER uses future fixture scores or promotes a p_matrix.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_market_shadow_p_matrix import _inputs_for_target, _load_group, _pool_over25
from tools.matrix_championship_cross_provider_archived_replay import ARCHIVE, CYCLE, audit
from tools.matrix_independent_over25_historical_parity import parse_archive, parse_free, compare
from tools.matrix_football_independent_over25_shadow import historic_rows

def dt(x):
    v=datetime.fromisoformat(str(x).replace("Z","+00:00"))
    if v.utcoffset() is None:raise ValueError("ENRICHED_BRIDGE_NAIVE_TIMESTAMP")
    return v.astimezone(timezone.utc)

def almost(a,b,eps=1e-8):
    return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=eps

def unique_mapping(pairs,orig,indep):
    """Reject ALL ambiguous API->independent team mappings, not just one row."""
    forward,reverse={},{}
    conflicts=set()
    for pair in pairs:
        a=orig.get(pair["archived_api_id"])
        b=indep.get(pair["free_id"])
        if a is None or b is None:continue
        if (a["home_goals"],a["away_goals"])!=(b["home_goals"],b["away_goals"]):
            continue
        for side in ("home","away"):
            x=a[f"{side}_team_id"]
            y=b[f"{side}_team_id"]
            if (x in forward and forward[x]!=y) or (y in reverse and reverse[y]!=x):
                conflicts.add(x)
                conflicts.add(reverse.get(y,x))
            else:
                forward[x]=y
                reverse[y]=x
    for k in conflicts:
        forward.pop(k,None)
    return forward,conflicts

def replay(shadow,*,cycle=CYCLE,archive=ARCHIVE):
    prior=audit(shadow,archive=archive,cycle=cycle)
    if (not prior["historical_raw_group_model_feature_parity_verified"]
        or prior["historical_result_disagreements"]!=0):
        raise ValueError("ENRICHED_BRIDGE_HISTORICAL_RAW_PARITY_NOT_PROVEN")
    root=cycle.parent
    bundle,manifest=load_chunked_canonical_bundle(root/"canonical_analysis")
    if (manifest.get("provider")!="api_football"
        or manifest.get("real_money")!="BLOCKED"
        or manifest.get("status")!="PASS"
        or manifest.get("p_matrix_status")!="NOT_GENERATED"):
        raise ValueError("ENRICHED_BRIDGE_ORIGINAL_CANONICAL_INVALID")
    cutoff=dt(manifest["analysis_as_of_utc"])
    if cutoff>dt(prior["reference_cutoff_utc"]):
        raise ValueError("ENRICHED_BRIDGE_CUTOFF_AFTER_REFERENCE")
    original_raw=archive.read_bytes()
    orig_payload=json.loads(original_raw.decode("utf-8"))
    data=shadow["authenticated_raw_group_replay_evidence"]["2016"]
    raw=base64.b64decode(data["response_base64"],validate=True)
    sha=hashlib.sha256(raw).hexdigest()
    if sha!=prior["source_independent_http_sha256"]:
        raise ValueError("ENRICHED_BRIDGE_SOURCE_SHA_MISMATCH")
    free_payload=json.loads(raw.decode("utf-8"))
    original_matches=parse_archive(orig_payload,cutoff,archived_league_id=40)
    free_matches=parse_free(free_payload,cutoff,source_league_id=2016)
    pairs=compare(original_matches,free_matches)
    if pairs["score_disagreements"] or pairs["ambiguous"]:
        raise ValueError("ENRICHED_BRIDGE_AMBIGUOUS_MATCHED_HISTORY")
    group_path=root/"history"/"raw"/"league_40_season_2026.bin"
    original_group=_load_group(group_path)
    if not original_group:
        raise ValueError("ENRICHED_BRIDGE_ORIGINAL_RAW_GROUP_MISSING")
    original_rows,original_sha=original_group
    if original_sha!=hashlib.sha256(original_raw).hexdigest():
        raise ValueError("ENRICHED_BRIDGE_ORIGINAL_GROUP_ARCHIVE_SHA_MISMATCH")
    original_rows=[r for r in original_rows if r["kickoff_utc"]<cutoff]
    independent_rows=[r for r in historic_rows(free_payload,2016) if r["kickoff_utc"]<cutoff]
    original_by={r["fixture_id"]:r for r in original_rows}
    free_by={r["fixture_id"]:r for r in independent_rows}
    mapping,conflicts=unique_mapping(pairs["matches"],original_by,free_by)
    targets=sorted((r for r in bundle["inputs"] if str(r.get("competition_id"))=="40"),
                   key=lambda x:(x["kickoff_utc"],x["fixture_id"]))
    out=[]
    for t in targets:
        fid=str(t["fixture_id"])
        row={"original_api_fixture_id":fid,"status":"BLOCKED",
             "original_canonical_sha256":t["canonical_sha256"],
             "new_production_probability_authorized":False,
             "telegram_signal_authorized":False}
        out.append(row)
        if dt(t["kickoff_utc"])<=cutoff:
            row["status"]="BLOCKED_ORIGINAL_TARGET_NOT_FUTURE";continue
        home=str(t["home_team_id"])
        away=str(t["away_team_id"])
        if home in conflicts or away in conflicts:
            row["status"]="BLOCKED_CONFLICTING_TEAM_CROSSWALK";continue
        home_free=mapping.get(home)
        away_free=mapping.get(away)
        if not home_free or not away_free or home_free==away_free:
            row["status"]="BLOCKED_HISTORICAL_TEAM_CROSSWALK_MISSING";continue
        enhanced,enhanced_reason=_inputs_for_target(original_rows,t)
        base,base_reason=_inputs_for_target(original_rows,{
            **t,"home_history":[],"away_history":[]})
        alternative,alternative_reason=_inputs_for_target(independent_rows,{
            "kickoff_utc":t["kickoff_utc"],"home_team_id":home_free,
            "away_team_id":away_free,"home_history":[],"away_history":[]})
        if any(v is None for v in (enhanced,base,alternative)):
            row["status"]="BLOCKED_INSUFFICIENT_TEAM_HISTORY"
            row["reason_codes"]=[str(enhanced_reason),str(base_reason),str(alternative_reason)]
            continue
        if (enhanced["home_history_source"]!="CANONICAL_ENRICHED_PIT"
            or enhanced["away_history_source"]!="CANONICAL_ENRICHED_PIT"):
            row["status"]="BLOCKED_ORIGINAL_ENRICHED_INPUT_NOT_USED";continue
        calc=lambda x:_pool_over25(x["poisson"]["over_2_5"],x["baseline"]["over_2_5"])
        p0,p1,p2=calc(enhanced),calc(base),calc(alternative)
        agree=all((
            almost(p0,p1),almost(p0,p2),
            almost(enhanced["poisson"]["over_2_5"],alternative["poisson"]["over_2_5"]),
            almost(enhanced["baseline"]["over_2_5"],alternative["baseline"]["over_2_5"]),
            enhanced["home_history_count"]==alternative["home_history_count"],
            enhanced["away_history_count"]==alternative["away_history_count"],
            enhanced["prior_group_fixture_count"]==alternative["prior_group_fixture_count"]))
        row.update({
            "status":("PASS_HISTORICAL_THREE_WAY_ENRICHED_BRIDGE_ONLY" if agree
                      else "BLOCKED_HISTORICAL_ENRICHED_BRIDGE_DISAGREEMENT"),
            "original_home_team_id":home,"original_away_team_id":away,
            "independent_home_team_id":home_free,"independent_away_team_id":away_free,
            "original_enriched_probability":round(p0,12),
            "original_group_probability":round(p1,12),
            "independent_group_probability":round(p2,12),
            "max_three_way_probability_delta":round(max(abs(p0-p1),abs(p0-p2)),12),
            "source_history_count":alternative["prior_group_fixture_count"],
            "historical_three_way_equal":agree,
        })
    return {
        "schema":"MATRIX_CHAMPIONSHIP_ENRICHED_PROVIDER_HISTORICAL_BRIDGE_V1",
        "original_archive_sha256":original_sha,
        "source_provider_sha256":sha,
        "original_bundle_sha256":manifest["bundle_sha256"],
        "original_analysis_as_of_utc":cutoff.isoformat(),
        "original_canonical_targets":len(out),
        "mapped_historical_team_count":len(mapping),
        "conflicting_historical_team_count":len(conflicts),
        "historical_three_way_parity_count":sum(
            x["status"]=="PASS_HISTORICAL_THREE_WAY_ENRICHED_BRIDGE_ONLY" for x in out),
        "blocked_count":sum(x["status"]!="PASS_HISTORICAL_THREE_WAY_ENRICHED_BRIDGE_ONLY" for x in out),
        "rows":out,
        "historical_enriched_bridge_certified_for_subset":False,
        "prospective_enriched_provider_equivalence_verified":False,
        "future_fixture_original_provider_crosswalk_verified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
        "network_calls":0,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shadow",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if any(x in a.out.parts for x in ("daily_prematch_reports","telegram","tennis_signals")):
        raise SystemExit("HISTORICAL_BRIDGE_CANNOT_WRITE_SIGNAL")
    d=replay(json.loads(a.shadow.read_text(encoding="utf-8")))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(d,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:d[k] for k in (
        "original_canonical_targets","historical_three_way_parity_count",
        "blocked_count","prospective_enriched_provider_equivalence_verified",
        "production_p_matrix_authorized")},sort_keys=True))

if __name__=="__main__":main()
