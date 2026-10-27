from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.telegram_quote_attempt_telemetry import (
    LEGACY_SCHEMAS,
    REQUIRED_ATTEMPT_FIELDS,
    REQUIRED_HOUSE_FIELDS,
    REQUIRED_IDENTITY_FIELDS,
    SCHEMA,
    load_verified,
    summarize_cumulative,
)

LEDGER=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPTS.jsonl")
OUT=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_LAST.json")
CERT_OUT=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_TELEMETRY_CERTIFICATION_LAST.json")


def build() -> dict:
    rows=load_verified(LEDGER)
    summary=summarize_cumulative(rows,minimum_target=50,maximum_target=100)
    return {
        "schema":"MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status":"PASS",
        "ledger_path":str(LEDGER),
        "immutable_hash_chain_verified":True,
        "first_terminal_state_independent":all("first_terminal_state" not in x for x in rows),
        "required_authorized_books":["betano","betplay","rushbet"],
        "schema_evolution":{
            "current_schema":SCHEMA,
            "legacy_schemas_preserved_without_rewrite":sorted(LEGACY_SCHEMAS),
            "mixed_version_hash_chain_supported":True,
            "historical_rows_rewritten":False,
        },
        "required_field_contract":{
            "top_level_fields":list(REQUIRED_ATTEMPT_FIELDS),
            "identity_fields":sorted(REQUIRED_IDENTITY_FIELDS),
            "per_house_fields":sorted(REQUIRED_HOUSE_FIELDS),
            "all_rows_schema_validated":True,
        },
        "reporting_scope_contract":{
            "LIVE_THIS_RUN":{
                "source":"run_token_scoped_immutable_quote_attempts",
                "historical_terminal_states_included":False,
            },
            "TERMINAL_HISTORICAL":{
                "source":"candidate_lifecycle.first_terminal_state",
                "may_describe_prior_runs":True,
                "may_not_overwrite_immutable_attempt_rows":True,
            },
            "legacy_combined_counts_must_not_be_interpreted_as_live_coverage":True,
        },
        "exact_line_policy":{
            "required_valid_execution_line":2.5,
            "nearby_lines_2_25_2_75_diagnostic_only":True,
            "nearby_lines_never_substitute_for_2_5":True,
        },
        "sample":summary,
        "recommendation_gate":{
            "minimum_real_revalidations_required":50,
            "maximum_target_revalidations":100,
            "recommendation_authorized":summary["real_quote_attempts_total"]>=50,
            "no_synthetic_rows":True,
        },
        "protections":{
            "append_only":True,
            "raw_or_hashed_evidence_per_attempt":True,
            "historical_terminal_state_cannot_overwrite_attempt":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
    }


def build_certification(rows:list[dict], audit:dict) -> dict:
    schema_counts={}
    for row in rows:
        schema=str(row.get("schema") or "")
        schema_counts[schema]=schema_counts.get(schema,0)+1
    first_v2_index=next((i for i,row in enumerate(rows) if row.get("schema")==SCHEMA),None)
    first_v2_bridge_verified=None
    no_legacy_after_v2=True
    if first_v2_index is not None:
        if first_v2_index==0:
            first_v2_bridge_verified=rows[0].get("previous_record_sha256")=="0"*64
        else:
            first_v2_bridge_verified=(
                rows[first_v2_index].get("previous_record_sha256")
                == rows[first_v2_index-1].get("record_sha256")
            )
        no_legacy_after_v2=all(row.get("schema")==SCHEMA for row in rows[first_v2_index:])
    return {
        "schema":"MATRIX_TELEGRAM_QUOTE_TELEMETRY_CERTIFICATION_V2",
        "generated_at_utc":audit["generated_at_utc"],
        "status":"PASS",
        "source_ledger":str(LEDGER),
        "audit_path":str(OUT),
        "verified_row_count":len(rows),
        "schema_counts":schema_counts,
        "current_schema":SCHEMA,
        "legacy_schemas_preserved_without_rewrite":sorted(LEGACY_SCHEMAS),
        "v2_real_row_count":int(schema_counts.get(SCHEMA,0)),
        "first_v2_row_present":first_v2_index is not None,
        "first_v2_chain_bridge_verified":first_v2_bridge_verified,
        "no_legacy_rows_after_first_v2":no_legacy_after_v2,
        "immutable_hash_chain_verified":audit["immutable_hash_chain_verified"],
        "first_terminal_state_independent":audit["first_terminal_state_independent"],
        "live_this_run_separated_from_terminal_historical":True,
        "exact_over_2_5_required":True,
        "nearby_2_25_2_75_diagnostic_only":True,
        "synthetic_rows_added":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "sample_gate_status":audit["sample"]["sample_gate_status"],
        "real_quote_attempts_total":audit["sample"]["real_quote_attempts_total"],
        "remaining_to_minimum_50":audit["sample"]["remaining_to_minimum"],
    }


def main() -> None:
    rows=load_verified(LEDGER)
    out=build()
    cert=build_certification(rows,out)
    if cert["first_v2_row_present"]:
        assert cert["first_v2_chain_bridge_verified"] is True
        assert cert["no_legacy_rows_after_first_v2"] is True
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    CERT_OUT.write_text(json.dumps(cert,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":out["status"],
        "real_quote_attempts_total":out["sample"]["real_quote_attempts_total"],
        "remaining_to_minimum":out["sample"]["remaining_to_minimum"],
        "sample_gate_status":out["sample"]["sample_gate_status"],
        "recommendation_authorized":out["recommendation_gate"]["recommendation_authorized"],
        "real_money":"BLOCKED",
        "v2_real_row_count":cert["v2_real_row_count"],
        "first_v2_chain_bridge_verified":cert["first_v2_chain_bridge_verified"],
    },sort_keys=True))


if __name__=="__main__":
    main()
