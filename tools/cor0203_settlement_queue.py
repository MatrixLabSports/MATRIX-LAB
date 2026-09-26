from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.cor0203_settlement_ledger import (
    Cor0203SettlementLedger,
    build_settlement_queue,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument(
        "--integrity",
        default="evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json",
    )
    parser.add_argument(
        "--ledger",
        default="evidence/cor0203/settlement/MATRIX_COR0203_SETTLEMENT_LEDGER.jsonl",
    )
    parser.add_argument("--identity-overlay")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    integrity = json.loads(Path(args.integrity).read_text(encoding="utf-8"))
    overlay = {}
    if args.identity_overlay:
        overlay_payload = json.loads(Path(args.identity_overlay).read_text(encoding="utf-8"))
        overlay = {
            str(row.get("event_id") or ""): row
            for row in overlay_payload.get("reconciled", []) or []
            if row.get("event_id")
        }
    ledger = Cor0203SettlementLedger(Path(args.ledger))
    queue = build_settlement_queue(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
        integrity=integrity,
        ledger_records=ledger.load(),
        identity_overlay=overlay,
    )
    audit = ledger.audit()
    queue["ledger"] = {
        "records": audit.records,
        "unique_events": audit.unique_events,
        "hash_chain_verified": audit.hash_chain_verified,
        "outcomes_used_for_metrics": audit.outcomes_used_for_metrics,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(queue, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "admissible_observations": queue["admissible_observations"],
                "settled": queue["settled"],
                "ready_result_lookup": queue["ready_result_lookup"],
                "identity_mapping_required": queue["identity_mapping_required"],
                "ledger_records": audit.records,
                "metrics": queue["metrics"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
