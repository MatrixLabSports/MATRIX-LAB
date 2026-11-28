"""Read-only premarket parity audit: no synthesized probabilities or canonical inputs.

Source observations here are research metadata only; parity is independently
unverified until provider-native PIT rows and provenance meet the original
MatchAnalysisInput and freeze contracts.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

NAMES={
 "calendar":"MATRIX_TRIPLE_SOURCE_CALENDAR_IDENTITY_CERTIFICATE.json",
 "research":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
 "intake":"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
 "quotes":"MATRIX_INDEPENDENT_OVER25_QUOTE_AUDIT.json",
}
REQUIRED=(
 "source_provider_id_crosswalk",
 "league_season_namespace_crosswalk",
 "pre_match_fixture_payload_observed_timestamp_and_hash",
 "provider_native_team_history_rows_at_least_five_each",
 "history_identity_utc_scores_and_observed_at_before_analysis",
 "same_feature_definition_and_model_calibration_parity",
 "future_only_freeze_and_no_original_holdout_overlap",
)

def _load(path:Path)->dict[str,Any]:
    data=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data,dict):
        raise ValueError("PARITY_AUDIT_SOURCE_NOT_OBJECT")
    return data

def _map(rows:list, key:str)->dict[str,dict]:
    out={}
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("PARITY_SOURCE_ROW_INVALID")
        ident=str(row.get(key) or "").strip()
        if not ident or ident in out:
            raise ValueError("PARITY_SOURCE_ID_MISSING_OR_DUPLICATE")
        out[ident]=row
    return out

def evaluate(folder:Path, day:str)->dict[str,Any]:
    paths={k:folder/v for k,v in NAMES.items()}
    docs={k:_load(p) for k,p in paths.items()}
    c,h,i,q=docs["calendar"],docs["research"],docs["intake"],docs["quotes"]
    if c.get("target_date_bogota") != day or c.get("canonical_model_input_authorized") is not False:
        raise ValueError("PARITY_CALENDAR_SCOPE_OR_GOVERNANCE_INVALID")
    if h.get("historical_source_equivalence_verified") is not False or h.get("market_signal_authorized") is not False:
        raise ValueError("PARITY_RESEARCH_GOVERNANCE_INVALID")
    if i.get("governed_feature_equivalence_verified") is not False or i.get("signal_generation_authorized") is not False:
        raise ValueError("PARITY_INTAKE_GOVERNANCE_INVALID")
    if q.get("signal_generation_authorized") is not False:
        raise ValueError("PARITY_QUOTE_GOVERNANCE_INVALID")
    ids=_map(c.get("rows") or [], "independent_fixture_id")
    research=_map(h.get("scored") or [], "source_fixture_id")
    intake=_map(i.get("fixtures") or [], "source_fixture_id")
    if len(ids)!=c.get("triple_source_calendar_identities") or len(intake)!=i.get("fixture_count"):
        raise ValueError("PARITY_COUNT_MISMATCH")
    results=[]
    for ident,row in sorted(ids.items()):
        base=intake.get(ident)
        if base is None or base.get("kickoff_utc")!=row.get("kickoff_utc"):
            raise ValueError("PARITY_FIXTURE_SOURCE_MISMATCH")
        shadow=research.get(ident)
        counts=shadow.get("feature_counts") if isinstance(shadow,dict) else None
        counts=counts if isinstance(counts,dict) else {}
        home=counts.get("home_history_count")
        away=counts.get("away_history_count")
        # Counts describe research data availability ONLY; they never certify
        # provider-native identity, row-level timestamps or source parity.
        enough_research=(isinstance(home,int) and not isinstance(home,bool)
                         and isinstance(away,int) and not isinstance(away,bool)
                         and home>=5 and away>=5)
        results.append({
           "independent_fixture_id":ident,
           "calendar_identity_verified":row.get("calendar_identity_verified") is True,
           "research_rows_available":shadow is not None,
           "research_home_history_count":home,
           "research_away_history_count":away,
           "research_minimum_history_counts":enough_research,
           "provider_native_history_rows_verified":False,
           "api_football_fixture_id_crosswalk_verified":False,
           "historical_source_equivalence_verified":False,
           "calibrated_model_feature_parity_verified":False,
           "required_evidence_not_certified":list(REQUIRED),
           "production_p_matrix_authorized":False,
           "canonical_input_authorized":False,
           "telegram_signal_authorized":False,
        })
    return {
      "schema":"MATRIX_INDEPENDENT_FEATURE_PARITY_AUDIT_V1",
      "target_date_bogota":day,
      "status":"RESEARCH_METADATA_AUDITED_MODEL_FEATURE_PARITY_NOT_CERTIFIED",
      "contract_sources":[
        "app/research/football/match_analysis_input.py",
        "tools/api_football_canonicalize_analysis_inputs.py",
        "tools/api_football_prospective_market_freeze.py",
      ],
      "calendar_certified_fixture_count":len(results),
      "research_fixture_count":sum(r["research_rows_available"] for r in results),
      "research_minimum_history_fixture_count":sum(r["research_minimum_history_counts"] for r in results),
      "provider_native_history_certified_count":0,
      "model_feature_parity_certified_count":0,
      "rows":results,
      "required_evidence_fields":list(REQUIRED),
      "source_sha256":{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in paths.items()},
      "research_probability_must_never_be_promoted":True,
      "old_holdout_untouched":True,
      "calibration_parameters_untouched":True,
      "canonical_inputs_generated":False,
      "telegram_signal_authorized":False,
      "automatic_wagering":False,
      "real_money":"BLOCKED",
    }

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--day",required=True)
    p.add_argument("--root",default=".")
    p.add_argument("--out",required=True)
    args=p.parse_args()
    payload=evaluate(Path(args.root)/"evidence"/"football_world_inventory"/args.day,args.day)
    dest=Path(args.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:payload[k] for k in ("status","calendar_certified_fixture_count","research_fixture_count","research_minimum_history_fixture_count","model_feature_parity_certified_count","telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
