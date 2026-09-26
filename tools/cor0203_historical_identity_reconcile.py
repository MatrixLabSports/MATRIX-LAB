from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
    CHALLENGER_MEN_SINGLES_NAME,
)


class FixtureDateClient(Protocol):
    request_count: int
    def fixtures(self, start: date, stop: date) -> Mapping[str, Any]:
        ...


def _norm_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _event_date_from_start(value: object) -> date:
    token = str(value or "").strip()
    if not token:
        raise ValueError("HISTORICAL_IDENTITY_EVENT_START_REQUIRED")
    return date.fromisoformat(token[:10])


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list):
        raise ValueError("HISTORICAL_IDENTITY_FIXTURE_RESULT_NOT_LIST")
    return [row for row in result if isinstance(row, Mapping)]


def _positive_numeric(value: object) -> str | None:
    token = str(value or "").strip()
    return token if token.isdigit() and int(token) > 0 else None


def reconcile_historical_identity(
    *,
    queue: Mapping[str, Any],
    client: FixtureDateClient,
    max_date_requests: int = 10,
) -> dict[str, Any]:
    if max_date_requests <= 0:
        raise ValueError("MAX_DATE_REQUESTS_MUST_BE_POSITIVE")

    pending = [
        row for row in queue.get("items", []) or []
        if str(row.get("status") or "") == "IDENTITY_MAPPING_REQUIRED"
    ]
    by_date: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
    for row in pending:
        by_date[_event_date_from_start(row.get("event_start_utc"))].append(row)

    reconciled: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    requests_before = int(getattr(client, "request_count", 0))

    for event_date in sorted(by_date):
        used = int(getattr(client, "request_count", 0)) - requests_before
        if used >= max_date_requests:
            for item in by_date[event_date]:
                blocked.append({
                    "event_id": item.get("event_id"),
                    "reason": "HISTORICAL_IDENTITY_REQUEST_BUDGET_REACHED",
                    "event_date": event_date.isoformat(),
                })
            continue

        try:
            payload = client.fixtures(event_date, event_date)
            fixture_rows = _rows(payload)
        except (ApiTennisDiscoveryError, ValueError) as error:
            for item in by_date[event_date]:
                blocked.append({
                    "event_id": item.get("event_id"),
                    "reason": type(error).__name__ + ":" + str(error),
                    "event_date": event_date.isoformat(),
                })
            continue

        for item in by_date[event_date]:
            expected_pair = frozenset({
                _norm_name(item.get("alphabetical_player_a")),
                _norm_name(item.get("alphabetical_player_b")),
            })
            candidates: list[Mapping[str, Any]] = []
            for fixture in fixture_rows:
                if str(fixture.get("event_type_type") or "").strip() != CHALLENGER_MEN_SINGLES_NAME:
                    continue
                if str(fixture.get("event_date") or "").strip() != event_date.isoformat():
                    continue
                pair = frozenset({
                    _norm_name(fixture.get("event_first_player")),
                    _norm_name(fixture.get("event_second_player")),
                })
                if pair != expected_pair:
                    continue
                event_key = _positive_numeric(fixture.get("event_key"))
                p1 = _positive_numeric(fixture.get("first_player_key"))
                p2 = _positive_numeric(fixture.get("second_player_key"))
                if event_key is None or p1 is None or p2 is None or p1 == p2:
                    continue
                candidates.append(fixture)

            if len(candidates) != 1:
                blocked.append({
                    "event_id": item.get("event_id"),
                    "reason": (
                        "HISTORICAL_IDENTITY_NO_EXACT_UNIQUE_MATCH"
                        if len(candidates) == 0
                        else "HISTORICAL_IDENTITY_AMBIGUOUS_EXACT_MATCH"
                    ),
                    "event_date": event_date.isoformat(),
                    "exact_candidate_count": len(candidates),
                })
                continue

            fixture = candidates[0]
            event_key = str(fixture["event_key"])
            p1 = str(fixture["first_player_key"])
            p2 = str(fixture["second_player_key"])
            first_name = str(fixture.get("event_first_player") or "").strip()
            second_name = str(fixture.get("event_second_player") or "").strip()

            reconciled.append({
                "event_id": str(item.get("event_id") or ""),
                "provider": "api_tennis",
                "provider_match_key": event_key,
                "canonical_source_event_id": "api-tennis:event:" + event_key,
                "provider_player_map": {
                    "api-tennis:player:" + p1: first_name,
                    "api-tennis:player:" + p2: second_name,
                },
                "match_rule": "EXACT_DATE_EXACT_UNORDERED_PLAYER_PAIR_UNIQUE",
                "event_date": event_date.isoformat(),
            })

    return {
        "schema": "MATRIX_COR0203_HISTORICAL_IDENTITY_RECONCILIATION_V1",
        "status": "PASS",
        "input_pending": len(pending),
        "reconciled": reconciled,
        "reconciled_count": len(reconciled),
        "blocked": blocked,
        "blocked_count": len(blocked),
        "network_calls": int(getattr(client, "request_count", 0)) - requests_before,
        "automatic_fuzzy_matching": False,
        "freeze_mutation": False,
        "metrics_opened": False,
        "real_money": "BLOCKED",
    }


def overlay_by_event(result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row.get("event_id") or ""): row
        for row in result.get("reconciled", []) or []
        if row.get("event_id")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-date-requests", type=int, default=10)
    args = parser.parse_args()

    queue = json.loads(Path(args.queue).read_text(encoding="utf-8"))
    key = os.environ.get("API_TENNIS_KEY", "").strip()
    if not key:
        result = {
            "schema": "MATRIX_COR0203_HISTORICAL_IDENTITY_RECONCILIATION_V1",
            "status": "SOURCE_NOT_CONFIGURED",
            "input_pending": sum(
                1 for row in queue.get("items", []) or []
                if str(row.get("status") or "") == "IDENTITY_MAPPING_REQUIRED"
            ),
            "reconciled": [],
            "reconciled_count": 0,
            "blocked": [{
                "event_id": None,
                "reason": "API_TENNIS_KEY_NOT_CONFIGURED",
            }],
            "blocked_count": 1,
            "network_calls": 0,
            "automatic_fuzzy_matching": False,
            "freeze_mutation": False,
            "metrics_opened": False,
            "real_money": "BLOCKED",
        }
    else:
        result = reconcile_historical_identity(
            queue=queue,
            client=ApiTennisDiscoveryClient(key),
            max_date_requests=args.max_date_requests,
        )

    Path(args.out).write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": result["status"],
        "input_pending": result["input_pending"],
        "reconciled_count": result["reconciled_count"],
        "blocked_count": result["blocked_count"],
        "network_calls": result["network_calls"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
