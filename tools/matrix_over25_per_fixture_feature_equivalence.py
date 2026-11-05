"""SHA-proven per-fixture, per-variable Over2.5 cross-provider research comparison.

Never infer fixture identity from date, team name or a shared league name.
A missing original prematch feature is UNKNOWN, not a numeric disagreement.
No reconstructed or historical report is certified as an original PIT freeze.
The current original-engine alternative replay is kept separate from
actual API-Football-to-alternative feature comparisons.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from tools.matrix_original_over25_alternative_native_adapter import (
    PROMOTION, ROOT as FREEZES, evaluate as verify_original_engine,
    verify as verify_native, MAX_BYTES,
)
from tools.matrix_independent_over25_prematch_freeze import canonical, stamp
from tools.matrix_over25_noncanonical_probability_recovery import (
    rows_from_document, numeric_probability,
)

ORIGINAL_REGISTRY = Path("evidence/api_football/governance/alternative_producer_original_six_league_registry.json")
ORIGINAL_LINEAGE = Path("evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json")
ORIGINAL_STAGES = Path("evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_STEPWISE_CERTIFICATION_LAST.json")
PAIR_MANIFEST = Path("evidence/football_world_inventory/MATRIX_OVER25_SHA_BOUND_FEATURE_PAIR_MANIFEST.json")
OUT = Path("evidence/football_world_inventory/MATRIX_OVER25_PER_FIXTURE_FEATURE_EQUIVALENCE_LAST.json")
FEATURES = (
    "prior_group_fixture_count", "home_history_count", "away_history_count",
    "home_history_source", "away_history_source",
    "expected_home_goals", "expected_away_goals", "poisson_over_2_5",
    "baseline_over_2_5", "pooled_probability_over25",
)
# Provider-native identifiers are deliberately excluded from direct equality.
NATIVE_IDENTIFIERS = ("home_source_team_id", "away_source_team_id",
                      "source_competition_id")
NUMERIC = set(FEATURES) - {"home_history_source", "away_history_source"}

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def read_proof(root: Path, relative: str, expected: str) -> dict:
    if (not isinstance(expected, str) or len(expected) != 64
        or any(c not in "0123456789abcdef" for c in expected)):
        raise ValueError("EVIDENCE_SHA256_NOT_VALID")
    candidate=(root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError("EVIDENCE_PATH_ESCAPE")
    if not candidate.is_file() or candidate.stat().st_size > MAX_BYTES:
        raise ValueError("EVIDENCE_MISSING_OR_OVERSIZED")
    raw=candidate.read_bytes()
    if sha(raw)!=expected:
        raise ValueError("EVIDENCE_RAW_BYTES_SHA256_MISMATCH")
    value=json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("EVIDENCE_ROOT_NOT_JSON_OBJECT")
    return value

def legacy_sha_reconstruction(root: Path, relative: str, expected: str) -> tuple[dict,str]:
    """Only a byte stream matching the pre-existing SHA can recover Git-normalized JSON.

    A source file with semantically similar but different bytes is NOT accepted.
    The source itself is never rewritten by this research comparator.
    """
    try:
        return read_proof(root,relative,expected),"RAW_FILE_BYTES_MATCH"
    except ValueError as exc:
        if str(exc)!="EVIDENCE_RAW_BYTES_SHA256_MISMATCH":
            raise
    source=(root/relative).resolve()
    if not source.is_relative_to(root.resolve()) or source.stat().st_size>MAX_BYTES:
        raise ValueError("ORIGINAL_REGISTRY_OUTSIDE_AUTHORIZED_SCOPE")
    raw=source.read_bytes()
    normalized_lf=raw.replace(b"\r\n",b"\n")
    candidates=(("CHECKOUT_LF_TO_ORIGINAL_CRLF",
                 normalized_lf.replace(b"\n",b"\r\n")),
                ("CHECKOUT_CRLF_TO_ORIGINAL_LF",normalized_lf))
    for mode,candidate in candidates:
        if sha(candidate)==expected:
            result=json.loads(candidate)
            if not isinstance(result,dict):
                raise ValueError("ORIGINAL_RECONSTRUCTED_NOT_OBJECT")
            return result,mode
    from tools.matrix_over25_source_hash_exact_repair import variants
    obj=json.loads(raw)
    if not isinstance(obj,dict):
        raise ValueError("ORIGINAL_RECONSTRUCTED_NOT_OBJECT")
    for mode,candidate in variants(obj):
        if sha(candidate)==expected:
            return obj,"ORIGINAL_SHA_REPRODUCED_FROM_JSON_SERIALIZATION_"+mode
    raise ValueError("ORIGINAL_SOURCE_SHA_NOT_RECONSTRUCTIBLE")


def diff_fields(alternative: dict, original: dict | None) -> list[dict]:
    """Differences can be asserted only for physically provided original values."""
    output=[]
    for name in FEATURES:
        av=alternative.get(name)
        ov=original.get(name) if isinstance(original,dict) else None
        if ov is None:
            state="MISSING_SHA_VERIFIED_ORIGINAL_PIT_VALUE"
        elif av is None:
            state="MISSING_ALTERNATIVE_NATIVE_VALUE"
        elif name in NUMERIC:
            if (type(ov) not in (int,float) or type(av) not in (int,float)
                or not math.isfinite(ov) or not math.isfinite(av)):
                state="INVALID_NUMERIC_VALUE"
            else:
                state="MATCH" if abs(float(av)-float(ov))<=1e-9 else "DIFFERENCE"
        else:
            state="MATCH" if type(ov)==type(av) and ov==av else "DIFFERENCE"
        output.append({"variable":name,"original_api_football_value":ov,
                       "alternative_football_data_org_value":av,"status":state})
    return output

def original_rows(root: Path, lineage: dict, stages: dict, scope: list[str]) -> tuple[list[dict],dict]:
    catalog=lineage.get("source_registry_catalog_by_sha256") or {}
    staged={(str(v["league_id"]),str(v["fixture_id"])):v
            for v in stages["fixture_decisions"]}
    seen=set(); rows=[]; counters=Counter(); cache={}
    for item in sorted(lineage["identity_rows"],key=lambda v:(str(v.get("league_id")),str(v.get("fixture_id")))):
        league=str(item.get("league_id"))
        if league not in scope or item.get("status")!="ORIGINAL_FIXTURE_IDENTITY_RECOVERED":
            continue
        fid=str(item["fixture_id"])
        if (league,fid) in seen:
            raise ValueError("ORIGINAL_DUPLICATE_FIXTURE_IDENTITY")
        seen.add((league,fid))
        source_sha=str(item.get("source_sha256") or "")
        source_path=catalog.get(source_sha)
        state="ORIGINAL_PROVENANCE_BLOCKED"
        registry_valid=False
        registry_reconstructed_mode=None
        try:
            if not isinstance(source_path,str):
                raise ValueError("ORIGINAL_FIXTURE_REGISTRY_PATH_UNKNOWN")
            if source_sha not in cache:
                cache[source_sha]=legacy_sha_reconstruction(root,source_path,source_sha)
            _,registry_reconstructed_mode=cache[source_sha]
            registry_valid=(registry_reconstructed_mode=="RAW_FILE_BYTES_MATCH")
            if registry_valid:
                state="IDENTITY_PROVEN_FROM_SHA_ARCHIVE"
                counters["original_registry_raw_sha_exact"]+=1
            else:
                state="IDENTITY_SHA_RECOVERED_IN_MEMORY_NOT_RAW_FILE"
                counters["original_registry_reconstructed_sha_exact"]+=1
        except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
            counters["original_registry_hash_or_path_blocked"]+=1
            counters["original_registry_failure:"+str(exc)[:100]]+=1
            state="ORIGINAL_PROVENANCE_BLOCKED:"+str(exc)[:85]
        item_stage=staged.get((league,fid),{})
        reported=item_stage.get("original_probability_source")
        original_probability=None
        probability_provenance=None
        if isinstance(reported,dict) and registry_reconstructed_mode is not None:
            path=reported.get("path")
            expected=reported.get("sha256")
            try:
                if (expected,path) not in cache:
                    cache[(expected,path)]=legacy_sha_reconstruction(root,path,expected)
                record,report_provenance_mode=cache[(expected,path)]
                matches=[v for v in rows_from_document(record)
                         if isinstance(v,dict)
                         and str(v.get("fixture_id"))==fid
                         and str(v.get("kickoff_utc"))==str(item["original_kickoff_utc"])
                         and numeric_probability(v.get(reported.get("field")))]
                if len(matches)!=1:
                    raise ValueError("ORIGINAL_REPORT_ROW_MISSING_OR_DUPLICATE")
                if not stamp(reported["reported_at_utc"]) < stamp(item["original_kickoff_utc"]):
                    raise ValueError("ORIGINAL_REPORT_AFTER_KICKOFF")
                original_probability=matches[0][reported["field"]]
                probability_provenance={"path":path,"sha256":expected,
                    "reported_at_utc":reported["reported_at_utc"],
                    "not_a_frozen_feature_trace":True,
                    "original_bytes_reconstruction_mode":report_provenance_mode}
                counters["original_reported_probabilities_sha_verified"]+=1
            except (ValueError,TypeError,OSError,KeyError,json.JSONDecodeError):
                state="ORIGINAL_REPORTED_PROBABILITY_SOURCE_BLOCKED"
                counters["original_report_hash_or_row_blocked"]+=1
        rows.append({"original_fixture_id":fid,"original_league_id":league,
            "kickoff_utc":item["original_kickoff_utc"],
            "original_registry_source_path":source_path,
            "original_registry_source_sha256":source_sha,
            "original_registry_bytes_verified":registry_valid,
            "original_registry_sha_reconstruction_mode":registry_reconstructed_mode,
            "original_probability_reported_not_frozen":original_probability,
            "original_probability_report_provenance":probability_provenance,
            "original_enriched_pit_feature_trace_available":False,
            "alternative_provider_fixture_crosswalk_verified":False,
            "status":state})
    return rows,dict(counters)

def paired_docs(root:Path, manifest:dict | None) -> dict[str,dict]:
    """Optional research comparisons; even an exact SHA does not certify PIT."""
    verified={}
    if manifest is None:return verified
    if (manifest.get("schema")!="MATRIX_OVER25_SHA_BOUND_PIT_FEATURE_PAIR_MANIFEST_V1"
        or manifest.get("production_p_matrix_authorized") is not False
        or manifest.get("telegram_signal_authorized") is not False
        or manifest.get("real_money")!="BLOCKED"):
        raise ValueError("PAIR_MANIFEST_UNTRUSTED_OR_PROMOTED")
    for pair in manifest.get("pairs",[]):
        if not isinstance(pair,dict):
            raise ValueError("PAIR_ROW_NOT_OBJECT")
        fid=str(pair["alternative_fixture_id"])
        if fid in verified:
            raise ValueError("DUPLICATE_ALTERNATIVE_PAIR")
        original=read_proof(root,pair["original_feature_file"],pair["original_feature_sha256"])
        cross=read_proof(root,pair["independent_crosswalk_file"],pair["independent_crosswalk_sha256"])
        if (original.get("schema")!="MATRIX_ORIGINAL_OVER25_FROZEN_FEATURE_TRACE_V1"
            or cross.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_CROSSWALK_V1"
            or original.get("provider")!="api_football"
            or str(original.get("fixture_id"))!=str(pair["original_fixture_id"])
            or not isinstance(original.get("features"),dict)):
            raise ValueError("PAIR_ORIGINAL_TRACE_OR_CROSSWALK_INVALID")
        kickoff=stamp(pair["kickoff_utc"])
        if not (stamp(original["captured_at_utc"])<kickoff
            and stamp(cross["captured_at_utc"])<kickoff):
            raise ValueError("PAIR_NOT_OBSERVED_BEFORE_KICKOFF")
        crossmatches=[x for x in cross.get("pairs",[])
            if str(x.get("original_fixture_id"))==str(pair["original_fixture_id"])
            and str(x.get("alternative_fixture_id"))==fid
            and stamp(x["kickoff_utc"])==kickoff]
        if len(crossmatches)!=1:
            raise ValueError("PAIR_EXACT_IDENTITY_MISSING_OR_AMBIGUOUS")
        verified[fid]={"original":original,"original_file":pair["original_feature_file"],
            "original_sha256":pair["original_feature_sha256"],
            "crosswalk_file":pair["independent_crosswalk_file"],
            "crosswalk_sha256":pair["independent_crosswalk_sha256"],
            "original_fixture_id":str(pair["original_fixture_id"]),
            "kickoff_utc":kickoff}
    return verified

def evaluate(root:Path, *, manifest:dict | None=None) -> dict:
    root=root.resolve()
    registry_path=root/ORIGINAL_REGISTRY
    lineage_path=root/ORIGINAL_LINEAGE
    stage_path=root/ORIGINAL_STAGES
    reg=json.loads(registry_path.read_bytes())
    scope=reg.get("original_six_league_ids")
    if (reg.get("scope_approved") is not True or not isinstance(scope,list)
        or len(scope)!=6 or len(set(scope))!=6
        or reg.get("production_p_matrix_authorized") is not False):
        raise ValueError("ORIGINAL_SCOPE_OR_GOVERNANCE_INVALID")
    lineage=json.loads(lineage_path.read_bytes())
    stages=json.loads(stage_path.read_bytes())
    # The legacy stage certificate was SHA-sealed on Windows. Git checked
    # out the same source JSON with LF on Linux, changing the raw byte SHA.
    # Reconstruct the pre-existing commitment only if its original SHA matches.
    # Neither original document nor its frozen SHA is rewritten.
    def certify_aggregate_link(path:Path,expected:str):
        if sha(path.read_bytes())==expected:
            return True,"ORIGINAL_FILE_BYTES_EXACT"
        try:
            _,mode=legacy_sha_reconstruction(root,path.relative_to(root).as_posix(),expected)
            return True,mode
        except (OSError,ValueError,TypeError,json.JSONDecodeError):
            return False,"HISTORICAL_AGGREGATE_SOURCE_SHA_NOT_RECONSTRUCTIBLE"
    scope_link_ok,scope_link_mode=certify_aggregate_link(
        registry_path,stages.get("six_league_scope_sha256"))
    lineage_link_ok,lineage_link_mode=certify_aggregate_link(
        lineage_path,stages.get("identity_source_sha256"))
    if (stages.get("six_league_ids")!=scope
        or lineage.get("status")!="RESEARCH_IDENTITY_RECOVERY_ONLY"
        or stages.get("scientific_six_league_validation_passed") is not False):
        raise ValueError("ORIGINAL_SCOPE_OR_GOVERNANCE_INVALID")
    # An out-of-date aggregate SHA must not be silently treated as certified.
    # It also must not erase individually SHA-verified original registry files.
    # Report both discrepancies, then independently authenticate each source.
    linkage_blockers=[]
    if not scope_link_ok:
        linkage_blockers.append("HISTORICAL_STEPWISE_SIX_LEAGUE_SCOPE_SHA_LINK_STALE")
    if not lineage_link_ok:
        linkage_blockers.append("HISTORICAL_STEPWISE_ORIGINAL_IDENTITY_SHA_LINK_STALE")
    if manifest is not None and linkage_blockers:
        # No actual pair can be accepted against a stale original chain.
        raise ValueError("ORIGINAL_MANIFEST_SHA_LINK_INVALID_FOR_NEW_PAIR")
    original,orig_metrics=original_rows(root,lineage,stages,scope)
    declared=paired_docs(root,manifest)
    promo=json.loads((root/PROMOTION).read_bytes())
    engine=verify_original_engine(root)
    grouped=defaultdict(list)
    for p in (root/FREEZES).glob("20??-??-??/[0-9]*_*.json"):
        if "_result_" not in p.name:
            grouped[p.name.split("_",1)[0]].append(p)
    alt=[]; blockers=Counter({k:1 for k in linkage_blockers}); compared=0
    verified_engine={v["fixture_id"] for v in engine["verified"]}
    for fid,files in sorted(grouped.items()):
        try:
            first=min(files,key=lambda p:(stamp(json.loads(p.read_bytes())["sealed_at_utc"]),p.as_posix()))
            if fid not in verified_engine:
                raise ValueError("ORIGINAL_ENGINE_ALTERNATIVE_REPLAY_NOT_VERIFIED")
            replay=verify_native(root,first,promo,include_feature_trace=True)
            feats=replay["alternative_native_features"]
            pair=declared.get(fid)
            original_values=pair["original"]["features"] if pair else None
            if pair and pair["kickoff_utc"]!=stamp(feats["kickoff_utc"]):
                raise ValueError("PAIR_KICKOFF_NOT_EQUAL_TO_NATIVE_FREEZE")
            if pair and pair["original_fixture_id"] not in {v["original_fixture_id"] for v in original}:
                raise ValueError("PAIR_ORIGINAL_ID_NOT_IN_SIX_LEAGUES")
            comparisons=diff_fields(feats,original_values)
            counters=Counter(x["status"] for x in comparisons)
            if pair:compared+=1
            else:blockers["MISSING_AUTHENTIC_EXACT_FIXTURE_CROSSWALK_AND_ORIGINAL_PIT_TRACE"]+=1
            alt.append({"alternative_fixture_id":fid,
                "alternative_competition_id":replay["provider_competition_id"],
                "kickoff_utc":feats["kickoff_utc"],
                "alternative_forecast_sha256":replay["forecast_sha256"],
                "alternative_intake_sha256":replay["authentic_intake_sha256"],
                "alternative_shadow_sha256":replay["authentic_shadow_sha256"],
                "alternative_history_payload_sha256":replay["authentic_history_sha256"],
                "alternative_source_paths":replay["alternative_native_feature_source_paths"],
                "alternative_history_observed_at_utc":replay["alternative_history_observed_at_utc"],
                "alternative_prediction_sealed_at_utc":replay["alternative_prediction_sealed_at_utc"],
                "original_fixture_id":pair["original_fixture_id"] if pair else None,
                "original_feature_evidence":({"path":pair["original_file"],
                    "sha256":pair["original_sha256"]} if pair else None),
                "independent_identity_evidence":({"path":pair["crosswalk_file"],
                    "sha256":pair["crosswalk_sha256"]} if pair else None),
                "variable_comparisons":comparisons,
                "variable_status_counts":dict(counters),
                "numeric_diff_comparison_is_research_only":True,
                "status":"SHA_BOUND_NUMERIC_RESEARCH_COMPARISON_ONLY_NOT_CERTIFIED" if pair else
                         "BLOCKED_MISSING_ORIGINAL_ENRICHED_PIT_PAIR"})
        except (ValueError,KeyError,TypeError,OSError,UnicodeError,json.JSONDecodeError) as exc:
            alt.append({"alternative_fixture_id":fid,"status":"BLOCKED_SOURCE_OR_REPLAY",
                        "reason":str(exc)[:160]})
            blockers["ALTERNATIVE_SOURCE_OR_REPLAY_FAILURE"]+=1
    for fid in sorted(set(declared)-set(grouped)):
        blockers["PAIR_REFERENCES_MISSING_ALTERNATIVE_FORECAST"]+=1
    return {"schema":"MATRIX_OVER25_PER_FIXTURE_FEATURE_EQUIVALENCE_V1",
        "status":"RESEARCH_COMPARISON_ONLY_CROSS_PROVIDER_CERTIFICATION_BLOCKED",
        "sources_sha256":{
            str(ORIGINAL_REGISTRY):sha(registry_path.read_bytes()),
            str(ORIGINAL_LINEAGE):sha(lineage_path.read_bytes()),
            str(ORIGINAL_STAGES):sha(stage_path.read_bytes()),
            str(PROMOTION):sha((root/PROMOTION).read_bytes())},
        "original_six_league_scope":scope,
        "original_historical_aggregate_sha_link_verification":{
            "identity_source_sha256_match":lineage_link_ok,
            "scope_source_sha256_match":scope_link_ok,
            "identity_link_proof_mode":lineage_link_mode,
            "scope_link_proof_mode":scope_link_mode,
            "historical_platform_newline_conversion_never_authorizes_equivalence":True,
            "status":"AGGREGATE_REFERENCE_STALE_NOT_CERTIFIED" if linkage_blockers
                     else "HISTORICAL_AGGREGATE_LINKS_MATCH",
            "linkage_blockers":linkage_blockers,
            "raw_original_sources_still_checked_individually_by_sha256":True},

        "original_fixture_provenance_rows":original,
        "original_fixture_count":len(original),
        "original_metrics":orig_metrics,
        "alternative_fixture_feature_comparisons":alt,
        "alternative_distinct_fixture_count":len(alt),
        "alternative_original_engine_verified_count":len(verified_engine),
        "authentic_sha_pair_manifest_present":manifest is not None,
        "cross_provider_research_comparison_pair_count":compared,
        "cross_provider_certified_pair_count":0,
        "blocker_counts":dict(blockers),
        "historical_original_probabilities_are_not_independent_frozen_pairs":True,
        "provider_native_ids_never_compared_without_explicit_crosswalk":True,
        "feature_values_are_not_automatically_proof_of_original_pit_availability":True,
        "original_six_league_enriched_pit_equivalence_certified":False,
        "original_model_probabilities_authorized":False,
        "production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,"automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.cwd())
    parser.add_argument("--out",type=Path,default=OUT)
    args=parser.parse_args()
    if any(p in args.out.parts for p in ("daily_prematch_reports","telegram",
              "tennis_signals","governance")):
        raise SystemExit("FEATURE_DIFF_NOT_ALLOWED_TO_WRITE_PRODUCTION")
    manifestpath=args.root/PAIR_MANIFEST
    manifest=json.loads(manifestpath.read_bytes()) if manifestpath.is_file() else None
    result=evaluate(args.root,manifest=manifest)
    path=args.out if args.out.is_absolute() else args.root/args.out
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(canonical(result))
    print(json.dumps({"original_fixture_count":result["original_fixture_count"],
        "alternative_distinct_fixture_count":result["alternative_distinct_fixture_count"],
        "verified_native_replay_count":result["alternative_original_engine_verified_count"],
        "research_paired_count":result["cross_provider_research_comparison_pair_count"],
        "certified_cross_provider_pair_count":0,
        "blocker_counts":result["blocker_counts"],"telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":
    main()
