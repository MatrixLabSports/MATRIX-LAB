"""Deterministic original API-Football fixture-ID lineage recovery, fail-closed.

Maps historic shadow probability fixture IDs to *previously captured* original
API-Football fixture registries. Captures are immutable source proof only;
the audit never creates original or alternative predictions, and NEVER promotes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_six_league_existing_evidence_recovery import ROOT, relative_paths
from tools.matrix_six_league_prospective_preflight import REGISTRY
from tools.matrix_over25_noncanonical_probability_recovery import (
    MAX_BYTES, numeric_probability, rows_from_document, tracked_report_path
)

OUTPUT=Path("evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json")
REGISTRY_SUFFIX="/fixtures/future_fixture_registry.json"
MAX_SOURCE_BYTES=12*1024*1024

def utc(raw):
    if not isinstance(raw,str) or not raw.strip():
        raise ValueError("SOURCE_TIME_MISSING")
    out=datetime.fromisoformat(raw.replace("Z","+00:00"))
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError("SOURCE_TIME_NOT_TZ_AWARE")
    return out.astimezone(timezone.utc)

def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_index(root:Path, paths:list[str]):
    """Index ID->unique source identity. Multiple snapshots must agree."""
    registries=sorted({p.replace("\\","/") for p in paths
        if p.startswith("evidence/api_football/prospective_daily/")
        and p.replace("\\","/").endswith(REGISTRY_SUFFIX)})
    index=defaultdict(list)
    errors=[]
    admitted=0
    for name in registries:
        path=root/name
        try:
            if not path.is_file() or path.stat().st_size>MAX_SOURCE_BYTES:
                raise ValueError("ORIGINAL_REGISTRY_UNAVAILABLE_OR_OVERSIZED")
            data=json.loads(path.read_text(encoding="utf-8-sig"))
            if (not isinstance(data,dict) or data.get("provider")!="api_football"
                or not isinstance(data.get("events"),list)
                or data.get("future_only") is not True):
                raise ValueError("NOT_AUTHENTIC_ORIGINAL_FUTURE_REGISTRY")
            capture=utc(data["captured_at_utc"])
            manifest=path.parent/"capture_manifest.json"
            if not manifest.is_file():
                raise ValueError("SOURCE_CAPTURE_MANIFEST_MISSING")
            meta=json.loads(manifest.read_text(encoding="utf-8-sig"))
            if (meta.get("provider")!="api_football" or
                meta.get("status")!="PASS" or
                meta.get("verified_successful_provider_response") is not True or
                utc(meta.get("captured_at_utc"))!=capture):
                raise ValueError("SOURCE_CAPTURE_MANIFEST_NOT_ATTESTED")
            digest=file_sha(path)
            for event in data["events"]:
                if not isinstance(event,dict):continue
                fid=str(event.get("provider_fixture_id") or "").strip()
                lid=str(event.get("provider_league_id") or "").strip()
                home=str(event.get("provider_home_team_id") or "").strip()
                away=str(event.get("provider_away_team_id") or "").strip()
                try:
                    kickoff=utc(event.get("event_start_utc"))
                except (TypeError,ValueError):
                    continue
                if (not fid.isdecimal() or not lid.isdecimal() or
                    not home.isdecimal() or not away.isdecimal() or
                    home==away or not capture<kickoff):
                    continue
                index[fid].append({
                    "league_id":lid,"home_team_id":home,"away_team_id":away,
                    "kickoff_utc":kickoff.isoformat(),
                    "captured_at_utc":capture.isoformat(),
                    "original_registry_path":name,"original_registry_sha256":digest,
                    "capture_manifest_sha256":file_sha(manifest),
                })
            admitted+=1
        except (OSError,TypeError,ValueError,KeyError,json.JSONDecodeError) as exc:
            errors.append({"path":name,"reason":str(exc)[:125]})
    return index,registries,admitted,errors

def examine(root:Path,paths:list[str])->dict:
    registry=json.loads((root/REGISTRY).read_text(encoding="utf-8"))
    selected=registry.get("original_six_league_ids")
    if (registry.get("schema")!="MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
        or registry.get("scope_approved") is not True
        or not isinstance(selected,list) or len(selected)!=6
        or len(set(selected))!=6):
        raise ValueError("SOURCE_SIX_LEAGUE_SCOPE_NOT_APPROVED")
    ids,srcfiles,src_ok,src_errors=source_index(root,paths)
    originals=defaultdict(list)
    ignored=Counter()
    report_sources={}
    for name in sorted(set(p for p in paths if tracked_report_path(p))):
        path=root/name
        try:
            if not path.is_file() or path.stat().st_size>MAX_BYTES:
                raise ValueError("SOURCE_PROBABILITY_REPORT_UNAVAILABLE")
            doc=json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(doc,dict):raise ValueError("SOURCE_PROBABILITY_NOT_OBJECT")
            created=utc(doc.get("generated_at_utc"))
            report_sources[name]=file_sha(path)
            for row in rows_from_document(doc):
                if not isinstance(row,dict):continue
                if not (numeric_probability(row.get("p_over_2_5")) or
                        numeric_probability(row.get("p_matrix"))):
                    continue
                fid=str(row.get("fixture_id") or "").strip()
                if not fid.isdecimal():
                    ignored["probability_missing_original_fixture_id"]+=1
                    continue
                try:
                    kickoff=utc(row.get("kickoff_utc"))
                except (TypeError,ValueError):
                    ignored["probability_missing_kickoff"]+=1
                    continue
                if not created<kickoff:
                    ignored["probability_generated_at_or_after_kickoff"]+=1
                    continue
                indicated=row.get("league_id") or row.get("competition_id")
                originals[fid].append({
                    "league_claim":str(indicated) if indicated is not None else "",
                    "kickoff_utc":kickoff.isoformat(),
                    "generated_at_utc":created.isoformat(),
                    "probability_report":name,
                    "probability_report_sha256":report_sources[name]
                })
        except (OSError,TypeError,ValueError,json.JSONDecodeError) as exc:
            ignored["unreadable_probability_report"]+=1
    out=[]
    statuses=Counter()
    per_league={i:Counter() for i in selected}
    for fid,probs in sorted(originals.items(),key=lambda t:int(t[0])):
        originals_frozen=ids.get(fid,[])
        identities={(x["league_id"],x["home_team_id"],
                     x["away_team_id"],x["kickoff_utc"]) for x in originals_frozen}
        claimed={x["league_claim"] for x in probs if x["league_claim"]}
        times={p["kickoff_utc"] for p in probs}
        status="NO_ORIGINAL_FIXTURE_REGISTRY_MATCH"
        picked=None
        if len(identities)>1 or len(times)>1 or len(claimed)>1:
            status="CONFLICTING_ORIGINAL_IDENTITY"
        elif len(identities)==1:
            matches=[v for v in originals_frozen if v["kickoff_utc"] in times]
            if not matches:
                status="ORIGINAL_FIXTURE_KICKOFF_CONFLICT"
            else:
                first=matches[0]
                if claimed and claimed!={first["league_id"]}:
                    status="ORIGINAL_LEAGUE_ID_CONFLICT"
                elif not all(utc(v["captured_at_utc"])<utc(p["kickoff_utc"]) for v in matches for p in probs):
                    status="ORIGINAL_REGISTRY_NOT_CAPTURED_PRE_KICKOFF"
                else:
                    status="ORIGINAL_FIXTURE_IDENTITY_RECOVERED"
                    picked=first
        statuses[status]+=1
        if picked and picked["league_id"] in per_league:
            per_league[picked["league_id"]]["recovered_unique_fixture_ids"]+=1
        if claimed and status!="ORIGINAL_FIXTURE_IDENTITY_RECOVERED":
            for lid in claimed:
                if lid in per_league: per_league[lid]["originally_labeled_unresolved_fixture_ids"]+=1
        out.append({
            "fixture_id":fid,"status":status,
            "claimed_league_ids":sorted(claimed),
            "league_id":picked["league_id"] if picked else None,
            "home_team_id":picked["home_team_id"] if picked else None,
            "away_team_id":picked["away_team_id"] if picked else None,
            "original_kickoff_utc":picked["kickoff_utc"] if picked else None,
            "evidence_registry":picked["original_registry_path"] if picked else None,
            "evidence_registry_sha256":picked["original_registry_sha256"] if picked else None,
            "probability_source_count":len(probs),
            "probability_source_paths":sorted({p["probability_report"] for p in probs})[:6],
            "historical_probability_not_source_triplet_certified":True,
            "production_p_matrix_authorized":False,
        })
    # Keep all matched and conflicting identities in a compact SHA-keyed
    # index that GitHub can return through the contents API (<1MB).
    catalog={x["evidence_registry_sha256"]:x["evidence_registry"]
             for x in out if x["evidence_registry_sha256"]}
    compact_rows=[{
        "fixture_id":x["fixture_id"],"status":x["status"],
        "claimed_league_ids":x["claimed_league_ids"],"league_id":x["league_id"],
        "home_team_id":x["home_team_id"],"away_team_id":x["away_team_id"],
        "original_kickoff_utc":x["original_kickoff_utc"],
        "source_sha256":x["evidence_registry_sha256"],
        "probability_source_count":x["probability_source_count"]
    } for x in out]
    return {
        "schema":"MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_V1",
        "status":"RESEARCH_IDENTITY_RECOVERY_ONLY",
        "original_fixture_registries_found":len(srcfiles),
        "original_fixture_registries_accepted":src_ok,
        "original_fixture_registry_failures":src_errors[:50],
        "original_fixture_registry_failures_count":len(src_errors),
        "probability_report_source_sha256":report_sources,
        "original_probability_distinct_fixture_ids_with_known_prematch_report_time":len(originals),
        "probability_rows_excluded_from_identity_recovery":dict(ignored),
        "identity_status_counts":dict(statuses),
        "selected_six_league_ids":selected,
        "selected_league_identity_counts":{k:dict(per_league[k]) for k in selected},
        "source_registry_catalog_by_sha256":catalog,
        "identity_rows":compact_rows,
        "source_registry_capture_before_kickoff_required":True,
        "source_identity_conflict_fails_closed":True,
        "matches_without_source_are_never_assigned_a_league":True,
        "historical_original_probability_not_prospectively_paired":True,
        "strict_original_alternative_result_triplets_certified":0,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    parser.add_argument("--out",type=Path,default=OUTPUT)
    args=parser.parse_args()
    if any(v in args.out.parts for v in ("daily_prematch_reports","telegram","tennis_signals","governance")):
        raise SystemExit("CROSSWALK_RESEARCH_ONLY_NOT_PRODUCTION")
    value=examine(args.root,relative_paths(args.root))
    target=args.out if args.out.is_absolute() else args.root/args.out
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({
        "status":value["status"],
        "original_fixture_registries_accepted":value["original_fixture_registries_accepted"],
        "identity_status_counts":value["identity_status_counts"],
        "selected_league_identity_counts":value["selected_league_identity_counts"],
        "strict_original_alternative_result_triplets_certified":0,
    },sort_keys=True))

if __name__=="__main__":main()
