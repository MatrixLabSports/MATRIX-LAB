"""Strict research-only scoreboard for the *original* six league cohort.

Do not count Brazil/Championship/Eredivisie as one of the original leagues.
No original/alternative fixture identity is inferred from provider native IDs.
Cryptographic, chronological, and provider-native evidence is checked before
any immutable prospective research freeze increments a per-league counter.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = Path("evidence/football_research_freezes")
REGISTRY = Path("evidence/api_football/governance/alternative_producer_original_six_league_registry.json")
OUT = Path("evidence/football_world_inventory/MATRIX_OVER25_ORIGINAL_SCOPE_RESEARCH_PROGRESS_LAST.json")
# Source-native competition ids; these are COMPETITION crosswalks, NOT
# authenticated matches or provider fixture-id crosswalks.
SOURCE_TO_ORIGINAL = {"2021":"39","2015":"61","2002":"78","2019":"135","2014":"140"}
FIXTURE_NAME = re.compile(r"^[0-9]+_[0-9a-f]{20}\.json$")
HEX = re.compile(r"^[0-9a-f]{64}$")

def stamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("REQUIRES_AWARE_UTC_TIMESTAMP")
    return parsed.astimezone(timezone.utc)

def sha(value:bytes)->str:
    return hashlib.sha256(value).hexdigest()

def read_document(path:Path,limit:int=24_000_000):
    if not path.is_file() or path.stat().st_size>limit:
        raise ValueError("SOURCE_FILE_MISSING_OR_OVERSIZED")
    raw=path.read_bytes()
    obj=json.loads(raw)
    if not isinstance(obj,dict):
        raise ValueError("SOURCE_NOT_JSON_OBJECT")
    return obj,raw

def source(root:Path,relative:str,expected_sha:str,cache:dict):
    if not isinstance(relative,str) or not relative.startswith(FROZEN.as_posix()+"/"):
        raise ValueError("RESEARCH_SOURCE_PATH_OUTSIDE_APPROVED_DIRECTORY")
    if not HEX.fullmatch(str(expected_sha)):
        raise ValueError("RESEARCH_SOURCE_SHA_INVALID")
    rel=Path(relative)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix!=".json" or rel.stem!=expected_sha:
        raise ValueError("RESEARCH_SOURCE_PATH_INVALID")
    if relative not in cache:
        doc,raw=read_document(root/rel)
        if sha(raw)!=expected_sha:
            raise ValueError("RESEARCH_SOURCE_HASH_MISMATCH")
        cache[relative]=doc
    return cache[relative]

def attest(root:Path,path:Path,cache:dict)->dict:
    row,raw=read_document(path,limit=100_000)
    if (row.get("schema")!="MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1"
        or row.get("provider")!="FOOTBALL_DATA_ORG"
        or row.get("real_money")!="BLOCKED"
        or row.get("telegram_signal_authorized") is not False
        or row.get("production_p_matrix_authorized") is not False
        or row.get("original_vs_alternative_equivalence_certified") is not False
        or row.get("scientific_holdout_certified") is not False
        or row.get("frozen_calibrated_model_parameters_mutated") is not False
        or row.get("automatic_wagering") is not False):
        raise ValueError("RESEARCH_SNAPSHOT_GOVERNANCE_MISMATCH")
    cid=str(row["provider_competition_id"])
    fid=str(row["provider_fixture_id"])
    if not cid.isdecimal() or not fid.isdecimal() or not path.name.startswith(fid+"_"):
        raise ValueError("RESEARCH_PROVIDER_NATIVE_IDENTITY_INVALID")
    if not path.stem.endswith(str(row["source_shadow_file_sha256"])[:20]):
        raise ValueError("RESEARCH_FREEZE_NAME_SHADOW_SHA_MISMATCH")
    times=[stamp(row[k]) for k in (
        "intake_captured_at_utc","history_captured_at_utc",
        "model_calculated_at_utc","sealed_at_utc","kickoff_utc")]
    if times!=sorted(times) or times[3]>=times[4]:
        raise ValueError("RESEARCH_PREMATCH_CHRONOLOGY_INVALID")
    if int(row["source_history_home_count"])<5 or int(row["source_history_away_count"])<5:
        raise ValueError("RESEARCH_HISTORY_BELOW_MINIMUM")
    p=row.get("research_probability_over25")
    if isinstance(p,bool) or not isinstance(p,(int,float)) or not 0<p<1:
        raise ValueError("RESEARCH_PROBABILITY_INVALID")
    intake=source(root,row["source_intake_file_path"],
                  row["source_intake_file_sha256"],cache)
    shadow=source(root,row["source_shadow_file_path"],
                  row["source_shadow_file_sha256"],cache)
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        or intake.get("source")!="FOOTBALL_DATA_ORG"
        or shadow.get("source")!="FOOTBALL_DATA_ORG"
        or intake.get("signal_generation_authorized") is not False
        or shadow.get("market_signal_authorized") is not False
        or shadow.get("parameter_refit") is not False):
        raise ValueError("RESEARCH_SOURCE_GOVERNANCE_INVALID")
    fixtures=[x for x in intake.get("fixtures",[]) if isinstance(x,dict)
        and str(x.get("source_fixture_id"))==fid
        and str(x.get("source_competition_id"))==cid]
    if (len(fixtures)!=1
        or fixtures[0].get("source_status") not in ("TIMED","SCHEDULED")
        or stamp(fixtures[0]["kickoff_utc"])!=times[4]):
        raise ValueError("RESEARCH_INTAKE_IDENTITY_OR_KICKOFF_MISMATCH")
    scored=[x for x in shadow.get("scored",[]) if isinstance(x,dict)
        and str(x.get("source_fixture_id"))==fid
        and str(x.get("competition_id"))==cid]
    if (len(scored)!=1 or stamp(scored[0]["kickoff_utc"])!=times[4]
        or abs(float(scored[0]["p_over25_research"])-p)>1e-9):
        raise ValueError("RESEARCH_SHADOW_IDENTITY_OR_PROBABILITY_MISMATCH")
    g=(shadow.get("authenticated_raw_group_replay_evidence") or {}).get(cid)
    if not isinstance(g,dict) or stamp(g["observed_at_utc"])!=times[1]:
        raise ValueError("RESEARCH_PROVIDER_RAW_HISTORY_CAPTURE_MISSING")
    original_bytes=base64.b64decode(g["response_base64"],validate=True)
    if (len(original_bytes)>3_000_000
        or sha(original_bytes)!=row.get("source_snapshot_sha256")
        or sha(original_bytes)!=g.get("source_payload_sha256")):
        raise ValueError("RESEARCH_RAW_PROVIDER_HISTORY_HASH_MISMATCH")
    return {"fixture_id":fid,"competition_id":cid,
        "original_league_id":SOURCE_TO_ORIGINAL.get(cid),
        "kickoff_utc":times[4].isoformat(),
        "sealed_at_utc":times[3].isoformat(),
        "freeze_path":path.relative_to(root).as_posix(),
        "freeze_sha256":sha(raw)}

def assess(root:Path)->dict:
    registry,_=read_document(root/REGISTRY,limit=40_000)
    ids=registry.get("original_six_league_ids")
    if (registry.get("schema")!="MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
        or registry.get("scope_approved") is not True
        or ids!=["39","61","78","135","140","239"]
        or registry.get("real_money")!="BLOCKED"):
        raise ValueError("ORIGINAL_SIX_LEAGUE_SCOPE_CHANGED")
    leagues={r["id"]:{"original_league_id":r["id"],"name":r["name"],
        "minimum_eligible_research_freezes_for_screening":30,
        "eligible_prematch_research_fixture_count":0,
        "remaining_to_research_screening_30":30,
        "independent_original_provider_same_fixture_PIT_pairs":0,
        "original_equivalence_certified":False,
        "provider_coverage_route":("ALTERNATIVE_FREE_FOOTBALL_DATA_ORG"
                                   if r["id"]!="239" else
                                   "COLOMBIA_FREE_PROVIDER_NOT_VERIFIED")} for r in registry["leagues"]}
    found={};excluded=Counter();cache={}
    directory=root/FROZEN
    for path in sorted(directory.glob("20??-??-??/*.json")) if directory.exists() else []:
        if not FIXTURE_NAME.fullmatch(path.name):
            continue
        try:
            row=attest(root,path,cache)
        except (ValueError,KeyError,TypeError,OverflowError,OSError,
                UnicodeError,json.JSONDecodeError,base64.binascii.Error):
            excluded["INVALID_SHA_OR_PREMATCH_EVIDENCE"]+=1
            continue
        key=(row["competition_id"],row["fixture_id"])
        if key not in found or row["sealed_at_utc"]<found[key]["sealed_at_utc"]:
            found[key]=row
    accepted=[]
    for item in sorted(found.values(),key=lambda r:(r["kickoff_utc"],r["fixture_id"])):
        original=item["original_league_id"]
        if original is None:
            excluded["OTHER_COMPETITION_NOT_PART_OF_ORIGINAL_SIX"]+=1
            continue
        if original not in leagues:
            raise ValueError("SOURCE_TO_ORIGINAL_SCOPE_UNEXPECTED")
        accepted.append(item)
        leagues[original]["eligible_prematch_research_fixture_count"]+=1
    for league in leagues.values():
        count=league["eligible_prematch_research_fixture_count"]
        league["remaining_to_research_screening_30"]=max(0,30-count)
    return {"schema":"MATRIX_OVER25_ORIGINAL_SCOPE_RESEARCH_PROGRESS_V1",
        "status":"RESEARCH_ONLY_ORIGINAL_SIX_LEAGUE_COHORT_TRACKED",
        "original_six_league_ids":ids,
        "provider_competition_map_source_to_original":SOURCE_TO_ORIGINAL,
        "source_ids_are_competition_not_fixture_identity_crosswalks":True,
        "unique_sha_attested_research_freezes_in_original_scope":len(accepted),
        "out_of_scope_or_invalid_counts":dict(excluded),
        "per_league":[leagues[ident] for ident in ids],
        "attested_fixtures":accepted,
        "minimum_30_is_research_screening_not_scientific_certification":True,
        "same_fixture_cross_provider_pit_pairs":0,
        "original_vs_alternative_equivalence_certified":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    output=assess(ROOT)
    path=ROOT/OUT
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,ensure_ascii=False,sort_keys=True,
                               indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":output["status"],
        "total":output["unique_sha_attested_research_freezes_in_original_scope"],
        "per_league":[{"original_league_id":r["original_league_id"],
                        "eligible":r["eligible_prematch_research_fixture_count"]}
                      for r in output["per_league"]],
        "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":
    main()
