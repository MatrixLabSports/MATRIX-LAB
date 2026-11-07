"""MATRIX six-league stepwise certification: immutable evidence, never fake a forecast.

Stage 1: source-attested original fixture identities and original probability reports.
Stage 2: locate independently frozen alternative forecasts, do not backfill history.
Stage 3: only a three-source SHA-bound manifest can enter scientific evaluation.
Stage 4: run existing six-league scientific OOS test unmodified.
Stage 5: inspect independent quote readiness; never authorize Telegram here.

This is a research certificate, not a producer or a wager executor.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_six_league_existing_evidence_recovery import ROOT, relative_paths
from tools.matrix_six_league_prospective_preflight import REGISTRY, PROSPECTIVE
from tools.matrix_over25_noncanonical_probability_recovery import (
    MAX_BYTES, numeric_probability, rows_from_document, tracked_report_path
)
from tools.matrix_original_fixture_id_lineage_crosswalk import utc

LINEAGE=Path("evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json")
OUTPUT=Path("evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_STEPWISE_CERTIFICATION_LAST.json")
MIN_PER_LEAGUE=30
ALTERNATIVE_RAW=Path("evidence/football_cohort_recovery/FOOTBALL_DATA_ORG_RAW_LAST.json")
GOVERNED_INTAKE=Path("evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json")

def independent_raw_profile(root:Path)->dict:
    """Never count FINISHED postmatch rows as frozen alternative forecasts."""
    source=root/ALTERNATIVE_RAW
    if not source.is_file():
        return {"status":"NO_AUTHENTIC_ALTERNATIVE_RAW_ARCHIVE_AT_EXPECTED_PATH"}
    if source.stat().st_size>MAX_BYTES:
        raise ValueError("ALTERNATIVE_RAW_TOO_LARGE")
    doc=json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(doc,dict) or not isinstance(doc.get("matches"),list):
        raise ValueError("ALTERNATIVE_ARCHIVE_INVALID")
    completed=sum(x.get("status")=="FINISHED" for x in doc["matches"]
                  if isinstance(x,dict))
    # This file is only an API response snapshot, not a per-fixture
    # original-vs-alternative pair frozen before kickoff.
    return {"status":"HISTORICAL_RAW_RESULTS_NOT_A_PROSPECTIVE_FORECAST",
        "path":str(ALTERNATIVE_RAW),"sha256":digest(source),
        "match_rows":len(doc["matches"]),"completed_match_rows":completed,
        "prospective_frozen_forecasts_certified":0}

def governed_intake_profile(root:Path)->dict:
    path=root/GOVERNED_INTAKE
    if not path.is_file():return {"status":"GOVERNED_INTAKE_EVIDENCE_MISSING"}
    doc=json.loads(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(doc,dict)
        or doc.get("schema")!="MATRIX_BROWSER_GOVERNED_INTAKE_SYNC_V1"
        or doc.get("real_money")!="BLOCKED"):
        raise ValueError("GOVERNED_INTAKE_UNTRUSTED")
    return {"status":doc.get("status"),"path":str(GOVERNED_INTAKE),
        "sha256":digest(path),"governed_candidate_count":doc.get("candidate_count"),
        "telegram_signal_authorized":False}


def digest(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def original_reports(root:Path,files:list[str],selected:set[str]):
    """Return only recorded original numbers whose report preceded kickoff.

    A reported number is NOT an original model certificate or a matching
    independent freeze. File path and SHA remain attached for traceability.
    """
    index=defaultdict(list);errors=Counter()
    for name in sorted(set(x for x in files if tracked_report_path(x))):
        path=root/name
        try:
            if not path.is_file() or path.stat().st_size>MAX_BYTES:
                raise ValueError("ORIGINAL_REPORT_MISSING_OR_OVERSIZED")
            raw=json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw,dict):raise ValueError("ORIGINAL_REPORT_NOT_OBJECT")
            moment=utc(raw["generated_at_utc"])
            sha=digest(path)
            for row in rows_from_document(raw):
                if not isinstance(row,dict):continue
                value=row.get("p_over_2_5")
                if not numeric_probability(value):
                    value=row.get("p_matrix")
                if not numeric_probability(value):continue
                fid=str(row.get("fixture_id") or "").strip()
                if not fid.isdecimal():continue
                try: kickoff=utc(row["kickoff_utc"])
                except (KeyError,TypeError,ValueError):continue
                if moment>=kickoff:continue
                league=str(row.get("league_id") or row.get("competition_id") or "")
                # Preserve claims, even missing league IDs; the canonical
                # fixture crosswalk, not the report, decides the true scope.
                index[fid].append({
                    "source_path":name,"source_sha256":sha,
                    "report_generated_at_utc":moment.isoformat(),
                    "kickoff_utc":kickoff.isoformat(),
                    "league_claim":league,"p":value,
                    "field":"p_over_2_5" if numeric_probability(row.get("p_over_2_5")) else "p_matrix",
                    "status":str(raw.get("probability_status") or ""),
                })
        except (OSError,TypeError,ValueError,KeyError,json.JSONDecodeError) as exc:
            errors[type(exc).__name__+":"+str(exc)[:80]]+=1
    return index,dict(errors)

def alternative_refs(root:Path,paths:list[str]):
    """Discover genuine candidate paths, never infer their contents/capture."""
    result=[]
    for p in paths:
        v=p.replace("\\","/").lower()
        if not v.startswith("evidence/") or not v.endswith(".json"):
            continue
        if any(k in v for k in (
          "football-data", "football_data", "alternative_producer",
          "independent_provider", "independent_over25", "prospective_evidence"
        )):
            result.append(p)
    return sorted(set(result))

def assess(root:Path,paths:list[str],*,lineage_path:Path=LINEAGE,
           prospective_path:Path=PROSPECTIVE)->dict:
    reg=json.loads((root/REGISTRY).read_text(encoding="utf-8"))
    scope=reg.get("original_six_league_ids")
    if (reg.get("schema")!="MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1"
        or reg.get("scope_approved") is not True or reg.get("real_money")!="BLOCKED"
        or reg.get("telegram_signal_authorized") is not False
        or not isinstance(scope,list) or len(scope)!=6 or len(set(scope))!=6):
        raise ValueError("SIX_LEAGUE_APPROVED_SCOPE_REQUIRED")
    original=root/lineage_path
    document=json.loads(original.read_text(encoding="utf-8"))
    if (document.get("schema")!="MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_V1"
        or document.get("production_p_matrix_authorized") is not False
        or document.get("telegram_signal_authorized") is not False):
        raise ValueError("ORIGINAL_LINEAGE_NOT_ATTESTED")
    provenance=document.get("source_registry_catalog_by_sha256",{})
    for h,p in provenance.items():
        if len(h)!=64 or not (root/p).is_file() or digest(root/p)!=h:
            raise ValueError("ORIGINAL_FIXTURE_REGISTRY_SHA_MISMATCH")
    original_index,source_errors=original_reports(root,paths,set(scope))
    candidates=alternative_refs(root,paths)
    rows=[r for r in document["identity_rows"] if
          r["status"]=="ORIGINAL_FIXTURE_IDENTITY_RECOVERED" and
          r["league_id"] in scope]
    per={l:{"original_identity_valid":0,"original_number_reported_pre_kickoff":0,
             "original_number_independently_frozen_and_attested":0,
             "alternative_genuine_prematch_pair":0,
             "three_independent_source_pairs_verified":0,
             "minimum_contractual_prospective_rows":MIN_PER_LEAGUE,
             "validated_prospective_rows":0,
             "missing_valid_prospective_rows":MIN_PER_LEAGUE} for l in scope}
    decisions=[];found=set()
    for row in sorted(rows,key=lambda r:(scope.index(r["league_id"]),int(r["fixture_id"]))):
        fixture=row["fixture_id"];league=row["league_id"]
        if (league,fixture) in found:raise ValueError("SIX_LEAGUE_DUPLICATE_IDENTITY")
        found.add((league,fixture))
        per[league]["original_identity_valid"]+=1
        proofs=[x for x in original_index.get(fixture,[]) if
                x["kickoff_utc"]==row["original_kickoff_utc"] and
                (not x["league_claim"] or x["league_claim"]==league)]
        # Never silently decide between conflicting p values or sources.
        distinct_values={round(float(p["p"]),12) for p in proofs}
        stage="ORIGINAL_PREMATCH_PROBABILITY_NOT_VERIFIED"
        source=None
        if len(distinct_values)>1:
            stage="CONFLICTING_ORIGINAL_PROBABILITIES"
        elif proofs:
            stage="ORIGINAL_NUMBER_FOUND_NOT_INDEPENDENTLY_FROZEN"
            per[league]["original_number_reported_pre_kickoff"]+=1
            proof=min(proofs,key=lambda p:(p["report_generated_at_utc"],p["source_path"]))
            source={"path":proof["source_path"],"sha256":proof["source_sha256"],
                    "reported_at_utc":proof["report_generated_at_utc"],
                    "field":proof["field"],"value_not_certified_as_frozen":True}
        decisions.append({"fixture_id":fixture,"league_id":league,
            "status":stage,"original_probability_source":source,
            "alternative_freeze_attested":False,
            "independent_result_attested":False,"prospective_oos_eligible":False})
    # An OOS document cannot be synthesized from isolated historical rows.
    # When an authentic existing manifest is present, run the production
    # scientific contract, and do not let this inventory bypass it.
    oos_path=root/prospective_path
    check=None
    if oos_path.is_file():
        from tools.matrix_six_league_enriched_oos_audit import audit
        scientific=audit(oos_path)
        if [str(x["league"]) for x in scientific["leagues"]]!=scope:
            raise ValueError("OOS_MANIFEST_SCOPE_CONFLICT")
        check={"sha256":digest(oos_path),
               "status":scientific["status"],
               "scientific_pass":scientific["six_league_scientific_validation_passed"]}
        for l in scientific["leagues"]:
            p=per[str(l["league"])]
            p["validated_prospective_rows"]=l["validated_prospective_rows"]
            p["original_number_independently_frozen_and_attested"]=l["validated_prospective_rows"]
            p["alternative_genuine_prematch_pair"]=l["validated_prospective_rows"]
            p["three_independent_source_pairs_verified"]=l["validated_prospective_rows"]
            p["missing_valid_prospective_rows"]=max(0,MIN_PER_LEAGUE-l["validated_prospective_rows"])
    blockers=[]
    if any(v["original_number_reported_pre_kickoff"]==0 for v in per.values()):
        blockers.append("ORIGINAL_NUMERIC_REPORTS_INCOMPLETE")
    if not oos_path.is_file():
        blockers.append("ORIGINAL_ALTERNATIVE_RESULT_SHA_BOUND_MANIFEST_MISSING")
    elif not check["scientific_pass"]:
        blockers.append("SIX_LEAGUE_SCIENTIFIC_OOS_NOT_PASSED")
    passed=bool(check and check["scientific_pass"])
    return {
        "schema":"MATRIX_SIX_LEAGUE_STEPWISE_CERTIFICATION_V1",
        "status":"SCIENTIFIC_EVIDENCE_PASS_ONLY_NO_TELEGRAM_PROMOTION" if passed
                 else "BLOCKED_MISSING_AUTHENTIC_PROSPECTIVE_PAIRS",
        "identity_source_sha256":digest(original),
        "six_league_scope_sha256":digest(root/REGISTRY),
        "six_league_ids":scope,
        "steps":{
            "step_1_original": "REPORTED_NUMBERS_RESEARCH_ONLY",
            "step_2_alternative": "NOT_CERTIFIED_WITHOUT_SOURCE_SNAPSHOT",
            "step_3_manifest": "SHA_BOUND_MANIFEST_VERIFIED" if check else "MISSING",
            "step_4_oos": "SCIENTIFIC_PASS_ONLY" if passed else "BLOCKED",
            "step_5_telegram": "BLOCKED_SEPARATE_SHARP_ODDS_AND_GOVERNANCE"
        },
        "counts":per,
        "original_source_errors":source_errors,
        "alternative_named_source_file_count":len(candidates),
        "alternative_named_source_path_examples":candidates[:30],
        "alternative_filename_not_proof_of_pre_kickoff_forecast":True,
        "alternative_raw_provenance_profile":independent_raw_profile(root),
        "telegram_governed_intake_profile":governed_intake_profile(root),
        "existing_strict_manifest":check,
        "blocking_requirements":blockers,
        "fixture_decisions":decisions,
        "counts_may_be_repeated_across_old_reports_but_fixture_rows_are_unique":True,
        "scientific_six_league_validation_passed":passed,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=ROOT)
    p.add_argument("--out",type=Path,default=OUTPUT)
    a=p.parse_args()
    if any(x in a.out.parts for x in ("telegram","governance","tennis_signals","daily_prematch_reports")):
        raise SystemExit("RESEARCH_CERTIFICATE_CANNOT_WRITE_PRODUCTION")
    output=assess(a.root,relative_paths(a.root))
    dest=a.out if a.out.is_absolute() else a.root/a.out
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n",encoding="utf-8")
    print(json.dumps({"status":output["status"],"counts":output["counts"],
        "blocking_requirements":output["blocking_requirements"],
        "scientific_six_league_validation_passed":output["scientific_six_league_validation_passed"],
        "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":main()
