"""Immutable paid-era replay: quantify CANONICAL_ENRICHED_PIT vs RAW_GROUP_PIT.

This is not a current fixture producer, source substitution authorization,
or signal pipeline. It never generates a p_matrix production export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_market_shadow_p_matrix import (
    _load_group, _inputs_for_target, _pool_over25,
)

DEFAULT_CYCLE=Path(
    "evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z"
)

def _dt(value):
    t=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("PIT_UNAWARE_TIMESTAMP")
    return t.astimezone(timezone.utc)

def compare_cycle(cycle:Path=DEFAULT_CYCLE, league_id:str="40")->dict:
    bundle,manifest=load_chunked_canonical_bundle(cycle/"canonical_analysis")
    if (manifest.get("provider")!="api_football"
        or manifest.get("status")!="PASS"
        or manifest.get("real_money")!="BLOCKED"
        or manifest.get("p_matrix_status")!="NOT_GENERATED"):
        raise ValueError("PIT_ARCHIVE_GOVERNANCE_INVALID")
    as_of=_dt(manifest["analysis_as_of_utc"])
    rows=[r for r in bundle["inputs"] if str(r.get("competition_id"))==str(league_id)]
    rows.sort(key=lambda r:(r["kickoff_utc"],r["fixture_id"]))
    groups={}
    output=[]
    for target in rows:
        kickoff=_dt(target["kickoff_utc"])
        if kickoff<=as_of:
            raise ValueError("PIT_ARCHIVE_TARGET_AFTER_KICKOFF")
        season=target.get("season")
        if not isinstance(season,int) or isinstance(season,bool):
            raise ValueError("PIT_SEASON_INVALID")
        group_key=(str(league_id),season)
        if group_key not in groups:
            f=cycle/"history"/"raw"/f"league_{league_id}_season_{season}.bin"
            groups[group_key]=_load_group(f) if f.is_file() else None
        group=groups[group_key]
        data={
          "fixture_id":str(target["fixture_id"]),
          "kickoff_utc":target["kickoff_utc"],
          "target_canonical_sha256":target["canonical_sha256"],
          "reference_status":"NOT_REPLAYABLE",
          "same_probability_with_group_only":False,
        }
        if group is None:
            data["blocker"]="ORIGINAL_RAW_GROUP_MISSING"
            output.append(data)
            continue
        group_rows,sha=group
        if any(row["kickoff_utc"]>=as_of for row in group_rows):
            # Only finished historical results available BEFORE this frozen cycle.
            group_rows=[row for row in group_rows if row["kickoff_utc"]<as_of]
        actual,err1=_inputs_for_target(group_rows,target)
        raw_target={**target,"home_history":[],"away_history":[]}
        baseline,err2=_inputs_for_target(group_rows,raw_target)
        data["source_group_sha256"]=sha
        data["enriched_history_source"]={
          "home":actual.get("home_history_source") if actual else None,
          "away":actual.get("away_history_source") if actual else None
        }
        if actual is None or baseline is None:
            data["blocker"]="REPLAY_BLOCKED:"+str(err1 or err2)
            output.append(data)
            continue
        a=_pool_over25(actual["poisson"]["over_2_5"],actual["baseline"]["over_2_5"])
        b=_pool_over25(baseline["poisson"]["over_2_5"],baseline["baseline"]["over_2_5"])
        delta=abs(a-b)
        data.update({
            "reference_status":"PAIRED_ARCHIVED_REPLAY_ONLY",
            "original_enriched_probability":round(a,12),
            "replacement_raw_group_probability":round(b,12),
            "absolute_probability_delta":round(delta,12),
            "same_probability_with_group_only":delta<1e-10,
            "original_home_history_count":actual["home_history_count"],
            "original_away_history_count":actual["away_history_count"],
            "raw_home_history_count":baseline["home_history_count"],
            "raw_away_history_count":baseline["away_history_count"],
        })
        output.append(data)
    paired=[row for row in output if row["reference_status"]=="PAIRED_ARCHIVED_REPLAY_ONLY"]
    different=[row for row in paired if not row["same_probability_with_group_only"]]
    return {
        "schema":"MATRIX_OVER25_ENRICHED_VS_RAW_GROUP_PIT_REPLAY_V1",
        "reference_cycle":str(cycle),
        "reference_canonical_bundle_sha256":manifest["bundle_sha256"],
        "reference_cutoff_utc":as_of.isoformat(),
        "league_id":str(league_id),
        "canonical_targets":len(rows),
        "paired_targets":len(paired),
        "probability_identical_targets":len(paired)-len(different),
        "probability_changed_targets":len(different),
        "blocked_targets":len(rows)-len(paired),
        "maximum_probability_difference":max((row["absolute_probability_delta"] for row in paired),default=None),
        "rows":output,
        "raw_group_replacement_equivalence_certified":False,
        "future_model_probability_authorized":False,
        "canonical_inputs_generated":False,
        "original_model_parameters_unchanged":True,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--cycle",type=Path,default=DEFAULT_CYCLE)
    p.add_argument("--league-id",default="40")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if "daily_prematch_reports" in a.out.parts or "tennis_signals" in a.out.parts:
        raise SystemExit("PIT_REPLAY_CANNOT_WRITE_SIGNAL_CANDIDATES")
    result=compare_cycle(a.cycle,a.league_id)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "canonical_targets","paired_targets","probability_identical_targets",
        "probability_changed_targets","blocked_targets",
        "maximum_probability_difference","telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
