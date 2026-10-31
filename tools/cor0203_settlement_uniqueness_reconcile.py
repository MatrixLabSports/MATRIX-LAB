from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def reconcile_settlement_uniqueness(
    *,
    uniqueness: Mapping[str, Any],
    settlement_records: list[Mapping[str, Any]],
) -> dict[str, Any]:
    canonical_ids = {
        str(row.get("event_id") or "")
        for row in uniqueness.get("canonical_observations", []) or []
        if row.get("event_id")
    }
    duplicate_ids = {
        str(row.get("event_id") or "")
        for row in uniqueness.get("quarantined_duplicates", []) or []
        if row.get("event_id")
    }
    if canonical_ids & duplicate_ids:
        raise ValueError("CANONICAL_DUPLICATE_EVENT_SET_OVERLAP")

    settled_canonical: list[str] = []
    settled_duplicate: list[str] = []
    unknown_settlement_events: list[str] = []
    result_key_to_canonical: dict[str, set[str]] = {}

    duplicate_to_canonical = {
        str(row.get("event_id") or ""): str(row.get("canonical_event_id") or "")
        for row in uniqueness.get("quarantined_duplicates", []) or []
        if row.get("event_id")
    }

    for record in settlement_records:
        event_id = str(record.get("event_id") or "")
        if event_id in canonical_ids:
            settled_canonical.append(event_id)
            canonical_event_id = event_id
        elif event_id in duplicate_ids:
            settled_duplicate.append(event_id)
            canonical_event_id = duplicate_to_canonical.get(event_id, "")
        else:
            unknown_settlement_events.append(event_id)
            canonical_event_id = ""

        result_key = str(
            record.get("provider_result_match_key")
            or record.get("provider_match_key")
            or ""
        )
        if result_key and canonical_event_id:
            result_key_to_canonical.setdefault(result_key, set()).add(
                canonical_event_id
            )

    conflicting_result_keys = [
        {
            "provider_result_match_key": key,
            "canonical_event_ids": sorted(values),
        }
        for key, values in sorted(result_key_to_canonical.items())
        if len(values) > 1
    ]

    duplicate_result_aliases = sum(
        max(0, sum(
            1
            for record in settlement_records
            if str(
                record.get("provider_result_match_key")
                or record.get("provider_match_key")
                or ""
            ) == key
        ) - 1)
        for key in result_key_to_canonical
    )

    blockers: list[str] = []
    if unknown_settlement_events:
        blockers.append("SETTLEMENT_EVENT_OUTSIDE_UNIQUENESS_AUDIT")
    if conflicting_result_keys:
        blockers.append("PROVIDER_RESULT_MAPS_TO_MULTIPLE_CANONICAL_MATCHES")
    if len(set(settled_canonical)) != len(settled_canonical):
        blockers.append("CANONICAL_EVENT_SETTLED_MORE_THAN_ONCE")

    return {
        "schema": "MATRIX_COR0203_SETTLEMENT_UNIQUENESS_RECONCILIATION_V1",
        "physical_frozen_rows": uniqueness.get("physical_frozen_rows"),
        "unique_calibration_observations": uniqueness.get(
            "unique_calibration_observations"
        ),
        "duplicate_observations_quarantined": uniqueness.get(
            "duplicate_observations_quarantined"
        ),
        "ledger_records": len(settlement_records),
        "settled_unique_canonical_events": len(set(settled_canonical)),
        "settled_duplicate_alias_records": len(settled_duplicate),
        "duplicate_result_aliases_detected": duplicate_result_aliases,
        "unsettled_unique_canonical_events": max(
            0,
            len(canonical_ids) - len(set(settled_canonical)),
        ),
        "unknown_settlement_events": sorted(set(unknown_settlement_events)),
        "conflicting_result_keys": conflicting_result_keys,
        "duplicate_aliases_used_for_metrics": 0,
        "outcome_values_used_for_reconciliation": 0,
        "metrics_opened": False,
        "metrics": "SEALED_UNTIL_600",
        "canonical_only_metric_policy": True,
        "result": "PASS" if not blockers else "FAIL",
        "blockers": blockers,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--uniqueness",
        default="evidence/cor0203/runtime/MATRIX_COR0203_PHYSICAL_UNIQUENESS_LAST.json",
    )
    parser.add_argument(
        "--ledger",
        default="evidence/cor0203/settlement/MATRIX_COR0203_SETTLEMENT_LEDGER.jsonl",
    )
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    report = reconcile_settlement_uniqueness(
        uniqueness=_load_json(Path(args.uniqueness)),
        settlement_records=_load_jsonl(Path(args.ledger)),
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    if report["result"] != "PASS":
        raise SystemExit("SETTLEMENT_UNIQUENESS_RECONCILIATION_FAILED")


if __name__ == "__main__":
    main()
