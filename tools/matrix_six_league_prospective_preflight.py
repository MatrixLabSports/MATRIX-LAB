"""Six-league original-vs-alternative prospective evidence preflight.

Read-only research gate. A broad original archive cannot select a six-league
cohort; a historical 11/11 bridge cannot replace genuinely frozen paired
prospective predictions. No production probability or Telegram authorization.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
DISCOVERY=Path("evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY.json")
REGISTRY=Path("evidence/api_football/governance/alternative_producer_original_six_league_registry.json")
PROSPECTIVE=Path("evidence/football_world_inventory/2026-11-04/MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE.json")
OUTPUT=Path("evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_PROSPECTIVE_PREFLIGHT_LAST.json")

def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path:Path)->dict[str,Any]:
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):raise ValueError("SIX_LEAGUE_SOURCE_NOT_OBJECT")
    return obj

def assess(root:Path,*,discovery_path:Path=DISCOVERY,registry_path:Path=REGISTRY,
           prospective_path:Path=PROSPECTIVE)->dict[str,Any]:
    discovery_file=root/discovery_path
    registry_file=root/registry_path
    prospective_file=root/prospective_path
    archive={}
    archive_map={}
    if discovery_file.is_file():
        archive=load(discovery_file)
        if archive.get("schema")!="MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY_V1":
            raise ValueError("ORIGINAL_ARCHIVE_DISCOVERY_SCHEMA_INVALID")
        for r in archive.get("reference_groups",[]):
            if not isinstance(r,dict) or not isinstance(r.get("archive_files"),list):
                raise ValueError("ORIGINAL_ARCHIVE_GROUP_INVALID")
            league=str(r.get("original_league_id") or "")
            season=r.get("season")
            if not league or isinstance(season,bool) or not isinstance(season,int):
                raise ValueError("ORIGINAL_ARCHIVE_GROUP_ID_INVALID")
            key=(league,season)
            if key in archive_map:raise ValueError("ORIGINAL_ARCHIVE_DUPLICATE_GROUP")
            archive_map[key]=len(r["archive_files"])
        if archive.get("archived_reference_group_count")!=len(archive_map):
            raise ValueError("ORIGINAL_ARCHIVE_GROUP_COUNT_MISMATCH")
    registry=None
    ids=[]
    if registry_file.is_file():
        registry=load(registry_file)
        candidates=registry.get("original_six_league_ids")
        if (registry.get("schema")=="MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
            and registry.get("scope_approved") is True
            and registry.get("source")=="ORIGINAL_FROZEN_MODEL"
            and registry.get("real_money")=="BLOCKED"
            and registry.get("telegram_signal_authorized") is False
            and isinstance(candidates,list) and len(candidates)==6
            and all(isinstance(x,str) and x.isdecimal() for x in candidates)
            and len(set(candidates))==6):
            ids=candidates
    archive_league_ids={k[0] for k in archive_map}
    scoped=bool(ids) and set(ids).issubset(archive_league_ids)
    prospective=None
    prospective_metrics=None
    if scoped and prospective_file.is_file():
        from tools.matrix_six_league_enriched_oos_audit import audit
        prospective_metrics=audit(prospective_file)
        # audit() itself verifies SHA-bound source snapshots, six real archive
        # scopes, no holdout overlap, feature equivalence and freeze timestamps.
        if [str(x["league"]) for x in prospective_metrics["leagues"]]!=ids:
            raise ValueError("OOS_SCOPE_DIFFERENT_FROM_APPROVED_REGISTRY")
    details=[]
    for ident in ids:
        counts=[{"season":season,"archived_file_count":n} for (league,season),n
                in sorted(archive_map.items()) if league==ident]
        prospective_row=next((x for x in (prospective_metrics or {}).get("leagues",[])
                              if str(x["league"])==ident),None)
        details.append({
            "league_id":ident,
            "original_archived_group_seasons":counts,
            "valid_prospective_rows":prospective_row["validated_prospective_rows"] if prospective_row else 0,
            "minimum_prospective_rows":30,
            "prospective_evidence_present":prospective_row is not None,
            "prospective_holdout_certified":bool(prospective_row and
                                                 prospective_row["prospective_holdout_certified"]),
            "unverified_must_not_be_interpreted_as_absent":prospective_row is None
        })
    blockers=[]
    if not discovery_file.is_file():blockers.append("ORIGINAL_ARCHIVE_DISCOVERY_MISSING")
    if not ids:blockers.append("ORIGINAL_SIX_LEAGUE_COHORT_NOT_APPROVED")
    elif not scoped:blockers.append("SELECTED_SIX_LEAGUES_NOT_ALL_IN_ORIGINAL_ARCHIVE")
    if not prospective_file.is_file():blockers.append("PROSPECTIVE_SOURCE_SNAPSHOT_MANIFEST_MISSING")
    elif not scoped:blockers.append("PROSPECTIVE_EVIDENCE_NOT_EVALUATED_WITHOUT_APPROVED_SCOPE")
    if scoped and prospective_metrics and not prospective_metrics["six_league_scientific_validation_passed"]:
        blockers.append("ENRICHED_PROSPECTIVE_OOS_NOT_CERTIFIED")
    certified=bool(scoped and prospective_metrics and
                    prospective_metrics["six_league_scientific_validation_passed"])
    return {
        "schema":"MATRIX_SIX_LEAGUE_PROSPECTIVE_PREFLIGHT_V1",
        "status":"SCIENTIFIC_SIX_LEAGUE_EVIDENCE_PASS_ONLY" if certified else
                 "BLOCKED_PROSPECTIVE_SIX_LEAGUE_EVIDENCE_INCOMPLETE",
        "original_archive_group_count":len(archive_map),
        "original_archived_unique_league_count":len(archive_league_ids),
        "six_league_registry_approved":bool(ids),
        "selected_six_leagues_present_in_original_archive":scoped,
        "six_league_ids":ids,
        "leagues":details,
        "missing_evidence":blockers,
        "scientific_oos_validation_passed":certified,
        "source_sha256":{
            "original_archive_inventory":sha(discovery_file) if discovery_file.is_file() else None,
            "approved_cohort_registry":sha(registry_file) if registry_file.is_file() else None,
            "prospective_source_manifest":sha(prospective_file) if prospective_file.is_file() else None,
        },
        "historical_championship_eleven_of_eleven_not_prospective":True,
        "physical_snapshot_verification_required":True,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=OUTPUT)
    a=p.parse_args()
    if any(part in a.out.parts for part in ("daily_prematch_reports","telegram","tennis_signals","governance")):
        raise SystemExit("SIX_LEAGUE_AUDIT_CANNOT_WRITE_PRODUCTION")
    report=assess(a.root)
    target=a.out if a.out.is_absolute() else a.root/a.out
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in (
      "status","original_archive_group_count","original_archived_unique_league_count",
      "six_league_registry_approved","scientific_oos_validation_passed",
      "missing_evidence","telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":main()
