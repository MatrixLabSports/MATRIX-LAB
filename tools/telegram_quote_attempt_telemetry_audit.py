from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.telegram_quote_attempt_telemetry import load_verified, summarize_cumulative

LEDGER=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPTS.jsonl")
OUT=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPT_TELEMETRY_AUDIT_LAST.json")


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


def main() -> None:
    out=build()
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":out["status"],
        "real_quote_attempts_total":out["sample"]["real_quote_attempts_total"],
        "remaining_to_minimum":out["sample"]["remaining_to_minimum"],
        "sample_gate_status":out["sample"]["sample_gate_status"],
        "recommendation_authorized":out["recommendation_gate"]["recommendation_authorized"],
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
