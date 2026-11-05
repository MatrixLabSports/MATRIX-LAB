"""SHA-bound Over2.5 cross-provider comparisons must never invent missing PIT pairs."""
import json
import hashlib
from pathlib import Path

import pytest

from tools.matrix_over25_per_fixture_feature_equivalence import (
    OUT, FEATURES, NUMERIC, diff_fields, read_proof, paired_docs, evaluate,
    legacy_sha_reconstruction,
)


def test_each_variable_requires_real_original_value():
    alt={k:(0.62 if k in NUMERIC else "RAW_GROUP_PIT") for k in FEATURES}
    result=diff_fields(alt,None)
    assert len(result)==len(FEATURES)
    assert all(x["status"]=="MISSING_SHA_VERIFIED_ORIGINAL_PIT_VALUE" for x in result)
    assert all(x["original_api_football_value"] is None for x in result)


def test_exact_numeric_feature_difference_not_confused_with_namespace_ids():
    a={k:(0.6 if k in NUMERIC else "RAW_GROUP_PIT") for k in FEATURES}
    o=dict(a)
    o["expected_home_goals"]=1.8
    o["poisson_over_2_5"]=0.6000000002
    o["home_history_source"]="CANONICAL_ENRICHED_PIT"
    compared={v["variable"]:v for v in diff_fields(a,o)}
    assert compared["expected_home_goals"]["status"]=="DIFFERENCE"
    assert compared["poisson_over_2_5"]["status"]=="MATCH"
    assert compared["home_history_source"]["status"]=="DIFFERENCE"
    assert compared["baseline_over_2_5"]["status"]=="MATCH"
    assert "home_source_team_id" not in compared


def test_evidence_raw_bytes_must_match_sha_and_stay_within_repo(tmp_path):
    good=tmp_path/"raw.json"
    data=b'{"fixture_id":"1557"}'
    good.write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    assert read_proof(tmp_path,"raw.json",sha)["fixture_id"]=="1557"
    good.write_text('{"fixture_id":"1558"}')
    with pytest.raises(ValueError, match="EVIDENCE_RAW_BYTES_SHA256_MISMATCH"):
        read_proof(tmp_path,"raw.json",sha)
    with pytest.raises(ValueError, match="EVIDENCE_PATH_ESCAPE"):
        read_proof(tmp_path,"../outside.json",sha)


def make(tmp_path, rel, payload):
    raw=(json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n").encode()
    file=tmp_path/rel
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(raw)
    return rel,hashlib.sha256(raw).hexdigest()


def test_sha_bound_identity_and_early_original_feature_comparison_is_research_only(tmp_path):
    original_path,osh=make(tmp_path,"proof/original.json",{
        "schema":"MATRIX_ORIGINAL_OVER25_FROZEN_FEATURE_TRACE_V1",
        "provider":"api_football", "fixture_id":"1557418",
        "captured_at_utc":"2026-11-05T08:00:00Z",
        "features":{"expected_home_goals":1.4,
                    "poisson_over_2_5":0.61}})
    crosspath,csh=make(tmp_path,"proof/crosswalk.json",{
        "schema":"MATRIX_INDEPENDENT_FIXTURE_CROSSWALK_V1",
        "captured_at_utc":"2026-11-05T08:01:00Z",
        "pairs":[{"original_fixture_id":"1557418",
                  "alternative_fixture_id":"555070",
                  "kickoff_utc":"2026-11-05T18:00:00Z"}]})
    row={"original_fixture_id":"1557418","alternative_fixture_id":"555070",
         "original_feature_file":original_path,"original_feature_sha256":osh,
         "independent_crosswalk_file":crosspath,
         "independent_crosswalk_sha256":csh,
         "kickoff_utc":"2026-11-05T18:00:00Z"}
    manifest={"schema":"MATRIX_OVER25_SHA_BOUND_PIT_FEATURE_PAIR_MANIFEST_V1",
              "production_p_matrix_authorized":False,
              "telegram_signal_authorized":False,"real_money":"BLOCKED",
              "pairs":[row]}
    result=paired_docs(tmp_path,manifest)
    assert result["555070"]["original"]["features"]["expected_home_goals"]==1.4
    assert diff_fields({"expected_home_goals":1.2},result["555070"]["original"]["features"])[5]["status"]=="DIFFERENCE"
    assert manifest["production_p_matrix_authorized"] is False
    # A SHA-valid research manifest by itself is not a scientific PIT certificate.


def test_crosswalk_can_never_be_backdated_to_fake_pre_match_capture(tmp_path):
    original_path,osh=make(tmp_path,"original.json",{
        "schema":"MATRIX_ORIGINAL_OVER25_FROZEN_FEATURE_TRACE_V1",
        "provider":"api_football","fixture_id":"1557418",
        "captured_at_utc":"2026-11-05T18:10:00Z","features":{}})
    crosspath,csh=make(tmp_path,"cross.json",{
        "schema":"MATRIX_INDEPENDENT_FIXTURE_CROSSWALK_V1",
        "captured_at_utc":"2026-11-05T08:00:00Z",
        "pairs":[{"original_fixture_id":"1557418",
                  "alternative_fixture_id":"555070",
                  "kickoff_utc":"2026-11-05T18:00:00Z"}]})
    data={"schema":"MATRIX_OVER25_SHA_BOUND_PIT_FEATURE_PAIR_MANIFEST_V1",
          "production_p_matrix_authorized":False,
          "telegram_signal_authorized":False,"real_money":"BLOCKED",
          "pairs":[{"original_fixture_id":"1557418",
                    "alternative_fixture_id":"555070",
                    "original_feature_file":original_path,
                    "original_feature_sha256":osh,
                    "independent_crosswalk_file":crosspath,
                    "independent_crosswalk_sha256":csh,
                    "kickoff_utc":"2026-11-05T18:00:00Z"}]}
    with pytest.raises(ValueError,match="PAIR_NOT_OBSERVED_BEFORE_KICKOFF"):
        paired_docs(tmp_path,data)


def test_live_repo_has_real_fixture_and_native_per_field_evidence():
    # Actual GitHub checkout evidence; never synthesize any provider observation.
    root=Path(__file__).resolve().parents[1]
    if not (root/"evidence/football_research_freezes").is_dir():
        pytest.skip("Full archived source evidence not available")
    report=evaluate(root)
    assert report["original_fixture_count"]>=174
    assert report["alternative_distinct_fixture_count"]>=12
    assert report["alternative_original_engine_verified_count"]>=12
    assert report["cross_provider_certified_pair_count"]==0
    assert report["original_six_league_enriched_pit_equivalence_certified"] is False
    assert report["telegram_signal_authorized"] is False
    assert report["production_p_matrix_authorized"] is False
    for row in report["alternative_fixture_feature_comparisons"]:
        assert row["status"]=="BLOCKED_MISSING_ORIGINAL_ENRICHED_PIT_PAIR"
        assert len(row["variable_comparisons"])==len(FEATURES)
        assert all(x["status"]=="MISSING_SHA_VERIFIED_ORIGINAL_PIT_VALUE"
                   for x in row["variable_comparisons"])
        assert row["alternative_history_payload_sha256"]

def test_reconstruct_old_windows_original_sha_without_silently_approving_wrong_bytes(tmp_path):
    expected_document={"registry":[{"fixture_id":"1557","team":"Bogotá"}],
                       "captured_at_utc":"2026-10-20T12:00:00Z"}
    original=(json.dumps(expected_document,ensure_ascii=False,sort_keys=True,indent=2)+"\r\n").encode("utf-8").replace(b"\n",b"\r\n")
    # Remove duplicated CR caused by generic replacement on the trailing line:
    original=original.replace(b"\r\r\n",b"\r\n")
    checked_out=original.replace(b"\r\n",b"\n")
    item=tmp_path/"registry.json";item.write_bytes(checked_out)
    digest=hashlib.sha256(original).hexdigest()
    value,mode=legacy_sha_reconstruction(tmp_path,"registry.json",digest)
    assert value==expected_document
    assert mode=="CHECKOUT_LF_TO_ORIGINAL_CRLF"
    assert item.read_bytes()==checked_out  # Research comparator never mutates bytes
    with pytest.raises(ValueError,match="ORIGINAL_SOURCE_SHA_NOT_RECONSTRUCTIBLE"):
        legacy_sha_reconstruction(tmp_path,"registry.json","f"*64)

