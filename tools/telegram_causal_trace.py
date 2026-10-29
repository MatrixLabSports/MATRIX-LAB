"""Read-only causal trace from verified immutable Telegram quote-attempt ledger."""
import argparse
import json
from collections import Counter
from pathlib import Path
from tools.telegram_quote_attempt_telemetry import SCHEMA, load_verified

LEDGER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_QUOTE_ATTEMPTS.jsonl")
OUTPUT = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_CAUSAL_TRACE_LAST.json")
IDENTITY_BAD = {"LOW_SCORE", "AMBIGUOUS", "NOT_COVERED"}


def build(rows):
    current = [r for r in rows if r.get("schema") == SCHEMA]
    states = Counter(str((r.get("identity_match") or {}).get("state") or "UNKNOWN") for r in current)
    discards = Counter(str(r.get("final_discard_reason") or "UNSPECIFIED") for r in current)
    exact = [r for r in current if r.get("over_2_5_seen_any_authorized")]
    matched = [r for r in current if (r.get("identity_match") or {}).get("state") not in IDENTITY_BAD]
    return {
        "schema": "MATRIX_TELEGRAM_CAUSAL_TRACE_V1",
        "source": str(LEDGER),
        "verified_immutable_chain_required": True,
        "current_schema_attempts": len(current),
        "identity_states": dict(sorted(states.items())),
        "discard_reasons": dict(sorted(discards.items())),
        "exact_over_2_5_seen_attempts": len(exact),
        "identity_not_flagged_attempts": len(matched),
        "both_identity_not_flagged_and_exact_line": sum(
            bool(r.get("over_2_5_seen_any_authorized")) for r in matched
        ),
        "latest_attempt_observation": [
            {"attempt_id": r.get("attempt_id"), "query_at_utc": r.get("query_at_utc"),
             "identity_state": (r.get("identity_match") or {}).get("state"),
             "exact_line_seen": bool(r.get("over_2_5_seen_any_authorized")),
             "final_discard_reason": r.get("final_discard_reason"),
             "terminal_state_independent": r.get("terminal_state_independent")}
            for r in sorted(current, key=lambda x: str(x.get("query_at_utc") or ""))[-5:]
        ],
        "telegram_delivery_acknowledgment": "NOT_VERIFIED_BY_QUOTE_LEDGER",
        "real_money": "BLOCKED",
        "automatic_wagering": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = build(load_verified(args.ledger))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert json.loads(args.output.read_text(encoding="utf-8")) == report
    print(json.dumps({k: report[k] for k in ("current_schema_attempts", "exact_over_2_5_seen_attempts", "both_identity_not_flagged_and_exact_line")}))


if __name__ == "__main__":
    main()
