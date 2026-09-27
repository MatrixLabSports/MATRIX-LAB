from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
)
from tools.cor0203_settlement_ledger import (
    Cor0203SettlementLedger,
    settlement_from_api_tennis,
    settlement_from_rapidapi_tennis,
)
from tools.cor0203_rapidapi_tennis_discovery import (
    RapidApiTennisClient,
    RapidApiTennisDiscoveryError,
)


NONSTANDARD_TERMINAL = {
    "RETIRED",
    "WALKOVER",
    "WO",
    "CANCELLED",
    "CANCELED",
    "ABANDONED",
}


class MatchLookupClient(Protocol):
    request_count: int

    def fixture_by_match_key(self, match_key: str) -> Mapping[str, Any]:
        ...


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return parsed.astimezone(timezone.utc)


def _fixture_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("result")
    if not isinstance(rows, list):
        raise ValueError("SETTLEMENT_FIXTURE_RESULT_NOT_LIST")
    return [row for row in rows if isinstance(row, Mapping)]


def sync_settlements(
    *,
    queue: Mapping[str, Any],
    ledger: Cor0203SettlementLedger,
    client: MatchLookupClient,
    now_utc: str,
    max_requests: int = 50,
) -> dict[str, Any]:
    now = _utc(now_utc)
    if max_requests <= 0:
        raise ValueError("MAX_REQUESTS_MUST_BE_POSITIVE")

    existing = {str(row.get("event_id") or "") for row in ledger.load()}
    settled: list[str] = []
    pending: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped_already_settled: list[str] = []
    requests_before = int(getattr(client, "request_count", 0))

    for item in queue.get("items", []) or []:
        if str(item.get("status") or "") != "READY_RESULT_LOOKUP":
            continue

        event_id = str(item.get("event_id") or "")
        if event_id in existing:
            skipped_already_settled.append(event_id)
            continue

        start = _utc(str(item.get("event_start_utc") or ""))
        if now <= start:
            pending.append({
                "event_id": event_id,
                "reason": "WAITING_EVENT_START",
            })
            continue

        requests_used = int(getattr(client, "request_count", 0)) - requests_before
        if requests_used >= max_requests:
            blocked.append({
                "event_id": event_id,
                "reason": "SETTLEMENT_REQUEST_BUDGET_REACHED",
            })
            continue

        match_key = str(item.get("provider_match_key") or "")
        try:
            payload = client.fixture_by_match_key(match_key)
            rows = _fixture_rows(payload)
        except (ApiTennisDiscoveryError, ValueError) as error:
            blocked.append({
                "event_id": event_id,
                "reason": type(error).__name__ + ":" + str(error),
            })
            continue

        exact = [row for row in rows if str(row.get("event_key") or "") == match_key]
        if len(exact) != 1:
            blocked.append({
                "event_id": event_id,
                "reason": "SETTLEMENT_EXACT_MATCH_ROW_REQUIRED",
                "rows": len(exact),
            })
            continue

        fixture = exact[0]
        status = str(fixture.get("event_status") or "").strip().upper()

        if status in NONSTANDARD_TERMINAL:
            blocked.append({
                "event_id": event_id,
                "reason": "NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION:" + status,
            })
            continue

        if status != "FINISHED":
            pending.append({
                "event_id": event_id,
                "reason": "RESULT_NOT_FINAL",
                "provider_status": status,
            })
            continue

        try:
            record = settlement_from_api_tennis(
                queue_item=item,
                fixture=fixture,
                settled_at_utc=now.isoformat(),
                source_reference="get_fixtures:match_key=" + match_key,
            )
            ledger.append(record)
        except ValueError as error:
            blocked.append({
                "event_id": event_id,
                "reason": type(error).__name__ + ":" + str(error),
            })
            continue

        existing.add(event_id)
        settled.append(event_id)

    audit = ledger.audit()
    return {
        "schema": "MATRIX_COR0203_SETTLEMENT_SYNC_V1",
        "status": "PASS",
        "settled_event_ids": settled,
        "new_settlements": len(settled),
        "pending": pending,
        "blocked": blocked,
        "skipped_already_settled": skipped_already_settled,
        "network_calls": int(getattr(client, "request_count", 0)) - requests_before,
        "ledger_records": audit.records,
        "ledger_hash_chain_verified": audit.hash_chain_verified,
        "outcomes_used_for_metrics": audit.outcomes_used_for_metrics,
        "metrics": "SEALED_UNTIL_600",
        "real_money": "BLOCKED",
    }



def _rapidapi_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("RAPIDAPI_SETTLEMENT_RESULT_NOT_LIST")
    return [row for row in rows if isinstance(row, Mapping)]


def sync_mixed_settlements(
    *,
    queue: Mapping[str, Any],
    ledger: Cor0203SettlementLedger,
    api_tennis_client: MatchLookupClient | None,
    rapidapi_client: RapidApiTennisClient | None,
    now_utc: str,
    max_requests: int = 50,
) -> dict[str, Any]:
    now = _utc(now_utc)
    if max_requests <= 0:
        raise ValueError("MAX_REQUESTS_MUST_BE_POSITIVE")

    existing = {str(row.get("event_id") or "") for row in ledger.load()}
    settled: list[str] = []
    pending: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped_already_settled: list[str] = []
    api_before = (
        int(getattr(api_tennis_client, "request_count", 0))
        if api_tennis_client is not None
        else 0
    )
    rapid_before = (
        int(getattr(rapidapi_client, "request_count", 0))
        if rapidapi_client is not None
        else 0
    )

    for item in queue.get("items", []) or []:
        if str(item.get("status") or "") != "READY_RESULT_LOOKUP":
            continue

        event_id = str(item.get("event_id") or "")
        if event_id in existing:
            skipped_already_settled.append(event_id)
            continue

        start = _utc(str(item.get("event_start_utc") or ""))
        if now <= start:
            pending.append({
                "event_id": event_id,
                "reason": "WAITING_EVENT_START",
            })
            continue

        used = 0
        if api_tennis_client is not None:
            used += (
                int(getattr(api_tennis_client, "request_count", 0))
                - api_before
            )
        if rapidapi_client is not None:
            used += (
                int(getattr(rapidapi_client, "request_count", 0))
                - rapid_before
            )
        if used >= max_requests:
            blocked.append({
                "event_id": event_id,
                "reason": "SETTLEMENT_REQUEST_BUDGET_REACHED",
            })
            continue

        provider = str(item.get("provider") or "")
        match_key = str(item.get("provider_match_key") or "")

        if provider == "api_tennis":
            if api_tennis_client is None:
                blocked.append({
                    "event_id": event_id,
                    "reason": "API_TENNIS_KEY_NOT_CONFIGURED",
                })
                continue
            try:
                payload = api_tennis_client.fixture_by_match_key(match_key)
                rows = _fixture_rows(payload)
            except (ApiTennisDiscoveryError, ValueError) as error:
                blocked.append({
                    "event_id": event_id,
                    "reason": type(error).__name__ + ":" + str(error),
                })
                continue
            exact = [
                row
                for row in rows
                if str(row.get("event_key") or "") == match_key
            ]
            if len(exact) != 1:
                blocked.append({
                    "event_id": event_id,
                    "reason": "SETTLEMENT_EXACT_MATCH_ROW_REQUIRED",
                    "rows": len(exact),
                })
                continue
            fixture = exact[0]
            status = str(
                fixture.get("event_status") or ""
            ).strip().upper()
            if status in NONSTANDARD_TERMINAL:
                blocked.append({
                    "event_id": event_id,
                    "reason": (
                        "NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION:"
                        + status
                    ),
                })
                continue
            if status != "FINISHED":
                pending.append({
                    "event_id": event_id,
                    "reason": "RESULT_NOT_FINAL",
                    "provider_status": status,
                })
                continue
            try:
                record = settlement_from_api_tennis(
                    queue_item=item,
                    fixture=fixture,
                    settled_at_utc=now.isoformat(),
                    source_reference=(
                        "get_fixtures:match_key=" + match_key
                    ),
                )
                ledger.append(record)
            except ValueError as error:
                blocked.append({
                    "event_id": event_id,
                    "reason": type(error).__name__ + ":" + str(error),
                })
                continue

        elif provider == "rapidapi_tennis":
            if rapidapi_client is None:
                blocked.append({
                    "event_id": event_id,
                    "reason": "RAPIDAPI_TENNIS_KEY_NOT_CONFIGURED",
                })
                continue
            try:
                payload = rapidapi_client.results_for_date(start.date())
                rows = _rapidapi_rows(payload)
            except (RapidApiTennisDiscoveryError, ValueError) as error:
                blocked.append({
                    "event_id": event_id,
                    "reason": type(error).__name__ + ":" + str(error),
                })
                continue
            exact = [
                row
                for row in rows
                if str(
                    row.get("matchId")
                    or row.get("id")
                    or ""
                )
                == match_key
            ]
            if len(exact) != 1:
                pending.append({
                    "event_id": event_id,
                    "reason": "RESULT_NOT_FINAL_OR_NOT_PUBLISHED",
                    "rows": len(exact),
                })
                continue
            result_row = exact[0]
            result_type = str(
                result_row.get("result_type")
                or result_row.get("resultType")
                or ""
            ).strip().casefold()
            if result_type != "completed":
                if result_type in {
                    "retired",
                    "walkover",
                    "cancelled",
                    "canceled",
                    "abandoned",
                }:
                    blocked.append({
                        "event_id": event_id,
                        "reason": (
                            "NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION:"
                            + result_type.upper()
                        ),
                    })
                else:
                    pending.append({
                        "event_id": event_id,
                        "reason": "RESULT_NOT_FINAL",
                        "provider_status": result_type,
                    })
                continue
            try:
                record = settlement_from_rapidapi_tennis(
                    queue_item=item,
                    result_row=result_row,
                    settled_at_utc=now.isoformat(),
                    source_reference=(
                        "results:"
                        + start.date().isoformat()
                        + ":matchId="
                        + match_key
                    ),
                )
                ledger.append(record)
            except ValueError as error:
                blocked.append({
                    "event_id": event_id,
                    "reason": type(error).__name__ + ":" + str(error),
                })
                continue
        else:
            blocked.append({
                "event_id": event_id,
                "reason": "SETTLEMENT_PROVIDER_UNSUPPORTED:" + provider,
            })
            continue

        existing.add(event_id)
        settled.append(event_id)

    audit = ledger.audit()
    network_calls = 0
    if api_tennis_client is not None:
        network_calls += (
            int(getattr(api_tennis_client, "request_count", 0))
            - api_before
        )
    if rapidapi_client is not None:
        network_calls += (
            int(getattr(rapidapi_client, "request_count", 0))
            - rapid_before
        )
    return {
        "schema": "MATRIX_COR0203_SETTLEMENT_SYNC_V2",
        "status": "PASS",
        "settled_event_ids": settled,
        "new_settlements": len(settled),
        "pending": pending,
        "blocked": blocked,
        "skipped_already_settled": skipped_already_settled,
        "network_calls": network_calls,
        "ledger_records": audit.records,
        "ledger_hash_chain_verified": audit.hash_chain_verified,
        "outcomes_used_for_metrics": audit.outcomes_used_for_metrics,
        "metrics": "SEALED_UNTIL_600",
        "real_money": "BLOCKED",
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True)
    parser.add_argument(
        "--ledger",
        default="evidence/cor0203/settlement/MATRIX_COR0203_SETTLEMENT_LEDGER.jsonl",
    )
    parser.add_argument("--summary-out", required=True)
    parser.add_argument("--max-requests", type=int, default=50)
    args = parser.parse_args()

    queue = json.loads(Path(args.queue).read_text(encoding="utf-8"))
    ledger = Cor0203SettlementLedger(Path(args.ledger))
    api_key = os.environ.get("API_TENNIS_KEY", "").strip()
    rapid_key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()

    api_client = (
        ApiTennisDiscoveryClient(api_key)
        if api_key
        else None
    )
    rapid_client = (
        RapidApiTennisClient(rapid_key)
        if rapid_key
        else None
    )
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = sync_mixed_settlements(
        queue=queue,
        ledger=ledger,
        api_tennis_client=api_client,
        rapidapi_client=rapid_client,
        now_utc=now,
        max_requests=args.max_requests,
    )

    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "new_settlements": result["new_settlements"],
        "network_calls": result["network_calls"],
        "ledger_records": result["ledger_records"],
        "outcomes_used_for_metrics": result["outcomes_used_for_metrics"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
