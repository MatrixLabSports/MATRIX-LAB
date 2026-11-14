"""Offline historical Championship cross-provider raw-group feature parity.

Uses immutable paid-era API-Football archive and exact authenticated football-
data.org HTTP bytes already persisted. No network, no calibration promotion.
"""
from __future__ import annotations
import argparse
import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_independent_over25_historical_parity import (
    utc,parse_archive,parse_free,compare,compare_raw_features,
)

ARCHIVE=Path("evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z/history/raw/league_40_season_2026.bin")
CYCLE=Path("evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z/cycle_summary.json")
SOURCE_LEAGUE=2016
REFERENCE_LEAGUE=40

def audit(shadow,*,archive=ARCHIVE,cycle=CYCLE):
    if (shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        or shadow.get("source")!="FOOTBALL_DATA_ORG"
        or shadow.get("real_money")!="BLOCKED"
        or shadow.get("market_signal_authorized") is not False
        or shadow.get("parameter_refit") is not False):
        raise ValueError("CROSS_PROVIDER_RESEARCH_INPUT_GOVERNANCE_INVALID")
    data=(shadow.get("authenticated_raw_group_replay_evidence") or {}).get("2016")
    meta=(shadow.get("group_status") or {}).get("2016")
    if not isinstance(data,dict) or not isinstance(meta,dict):
        raise ValueError("CROSS_PROVIDER_MISSING_AUTHENTIC_HTTP")
    b64=data.get("response_base64")
    if not isinstance(b64,str) or len(b64)>4_200_000:
        raise ValueError("CROSS_PROVIDER_RAW_HTTP_SIZE_INVALID")
    try:
        raw=base64.b64decode(b64,validate=True)
    except binascii.Error as exc:
        raise ValueError("CROSS_PROVIDER_RAW_HTTP_BASE64_INVALID") from exc
    if not raw or len(raw)>3_000_000:
        raise ValueError("CROSS_PROVIDER_RAW_HTTP_BYTES_INVALID")
    src_sha=hashlib.sha256(raw).hexdigest()
    if (src_sha!=data.get("source_payload_sha256")
        or src_sha!=meta.get("sha256")
        or utc(data["observed_at_utc"])!=utc(meta["observed_at_utc"])):
        raise ValueError("CROSS_PROVIDER_HTTP_PROVENANCE_INVALID")
    cycle_obj=json.loads(cycle.read_text(encoding="utf-8"))
    if cycle_obj.get("status")!="PASS":
        raise ValueError("CROSS_PROVIDER_REFERENCE_CYCLE_UNVERIFIED")
    cutoff=utc(cycle_obj["finished_at_utc"])
    origin_raw=archive.read_bytes()
    original=json.loads(origin_raw.decode("utf-8"))
    independent=json.loads(raw.decode("utf-8"))
    ref_rows=parse_archive(original,cutoff,archived_league_id=REFERENCE_LEAGUE)
    src_rows=parse_free(independent,cutoff,source_league_id=SOURCE_LEAGUE)
    paired=compare(ref_rows,src_rows)
    features=compare_raw_features(
        original,independent,paired["matches"],cutoff,
        source_league_id=SOURCE_LEAGUE,archived_api_league_id=REFERENCE_LEAGUE)
    concordant=(len(paired["matches"])>=20
                and not paired["score_disagreements"]
                and not paired["ambiguous"])
    feature_ok=(features["scoreable_both"]>=10
                and features["different_raw_group_feature_or_probability_count"]==0
                and features["blocked_one_side"]==0)
    return {
        "schema":"MATRIX_CHAMPIONSHIP_HISTORICAL_CROSS_PROVIDER_HTTP_REPLAY_V1",
        "reference_paid_archive_sha256":hashlib.sha256(origin_raw).hexdigest(),
        "reference_cutoff_utc":cutoff.isoformat(),
        "source_independent_http_sha256":src_sha,
        "source_http_observed_at_utc":utc(data["observed_at_utc"]).isoformat(),
        "reference_fixture_count":len(ref_rows),
        "independent_fixture_count_prior_cutoff":len(src_rows),
        "matched_historical_result_count":len(paired["matches"]),
        "historical_result_disagreements":len(paired["score_disagreements"]),
        "historical_ambiguous_matches":len(paired["ambiguous"]),
        "historical_raw_group_score_concordance_verified":concordant,
        "historical_raw_group_model_feature_parity_verified":concordant and feature_ok,
        "raw_group_feature_parity":features,
        "status":("PASS_HISTORICAL_RAW_GROUP_FEATURE_PARITY_ONLY" if concordant and feature_ok
                  else "BLOCKED_INCOMPLETE_CROSS_PROVIDER_RAW_FEATURE_EQUIVALENCE"),
        "current_fixture_crosswalk_verified":False,
        "canonical_enriched_pit_equivalence_verified":False,
        "full_original_calibrated_model_equivalence_verified":False,
        "new_production_p_matrix_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "network_calls":0,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shadow",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if any(x in a.out.parts for x in ("daily_prematch_reports","tennis_signals","telegram")):
        raise SystemExit("CROSS_PROVIDER_HISTORY_CANNOT_CREATE_SIGNAL")
    data=json.loads(a.shadow.read_text(encoding="utf-8"))
    result=audit(data)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in (
        "status","matched_historical_result_count",
        "historical_raw_group_model_feature_parity_verified",
        "full_original_calibrated_model_equivalence_verified",
        "telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":main()
