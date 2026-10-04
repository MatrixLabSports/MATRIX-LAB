from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from app.application.tennis.acquisition_worker import execute_tennis_acquisition_queue
from app.application.tennis.governed_acquisition_queue import build_tennis_acquisition_queue
from app.core.acquisition_persistence import SQLiteAcquisitionStore
from app.core.acquisition_worker import WorkerLimits
from app.core.governed_acquisition_queue import AcquisitionCandidate, ProviderBudget
from tools.cor0203_api_tennis_discovery import (
    API_URL,
    CHALLENGER_MEN_SINGLES_KEY,
    MAX_DRAW_REQUESTS,
    ApiTennisDiscoveryClient,
    ApiTennisDiscoveryError,
    fetch_discovery,
)


MAX_REQUESTS_PER_BUCKET = 2 + MAX_DRAW_REQUESTS
EXPECTED_ROWS_BUDGET = 5000


def _canonical(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("AS_OF_UTC_MUST_BE_AWARE")
    return parsed.astimezone(timezone.utc)


def build_hourly_discovery_queue(*, as_of_utc: str, days: int = 2) -> Mapping[str, Any]:
    now = _parse_utc(as_of_utc)
    days = max(1, min(int(days), 4))
    bucket = now.replace(minute=0, second=0, microsecond=0)
    start = now.date()
    stop = start + timedelta(days=days - 1)
    identity = {
        "schema": "MATRIX_COR0203_DURABLE_DISCOVERY_SOURCE_V1",
        "provider": "api_tennis",
        "api_url": API_URL,
        "event_type_key": CHALLENGER_MEN_SINGLES_KEY,
        "bucket_utc": bucket.isoformat(),
        "start_date": start.isoformat(),
        "stop_date": stop.isoformat(),
        "draw_request_limit": MAX_DRAW_REQUESTS,
    }
    fingerprint = _sha(identity)
    subject_key = (
        "cor0203-discovery:"
        + bucket.strftime("%Y%m%dT%H")
        + ":"
        + start.isoformat()
        + ":"
        + stop.isoformat()
    )
    candidate = AcquisitionCandidate(
        sport="tennis",
        subject_key=subject_key,
        provider_key="api_tennis",
        competition_key="ATP_CHALLENGER_MEN_SINGLES",
        season_key=str(start.year),
        disposition="PRIORITIZE",
        priority_score=100.0,
        expected_rows=EXPECTED_ROWS_BUDGET,
        estimated_request_cost=MAX_REQUESTS_PER_BUCKET,
        rights_status="RESEARCH_ONLY",
        identity_status="PASS",
        chronology_status="PASS",
        provider_status="PASS",
        source_fingerprint=fingerprint,
    )
    return build_tennis_acquisition_queue(
        candidates=[candidate],
        budgets=[
            ProviderBudget(
                provider_key="api_tennis",
                max_requests=MAX_REQUESTS_PER_BUCKET,
                max_rows=EXPECTED_ROWS_BUDGET,
            )
        ],
        queue_limit=1,
    )


@dataclass
class ApiTennisDiscoveryFetcher:
    client: ApiTennisDiscoveryClient
    start: date
    stop: date
    as_of_utc: str

    def fetch(self, queue_item: Mapping[str, Any]) -> Mapping[str, Any]:
        if queue_item.get("provider_key") != "api_tennis":
            raise ValueError("DURABLE_DISCOVERY_PROVIDER_MISMATCH")
        payload = fetch_discovery(
            client=self.client,
            start=self.start,
            stop=self.stop,
            as_of_utc=self.as_of_utc,
        )
        payload["status"] = "DISCOVERY_COMPLETED"
        payload["network_calls"] = self.client.request_count
        payload["durable_acquisition"] = True
        payload["acquisition_queue_item_fingerprint"] = queue_item["queue_item_fingerprint"]
        return payload


def execute_durable_discovery(
    *,
    api_key: str,
    as_of_utc: str,
    days: int,
    store_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now = _parse_utc(as_of_utc)
    days = max(1, min(int(days), 4))
    queue = build_hourly_discovery_queue(as_of_utc=now.isoformat(), days=days)
    if len(queue.get("queue", [])) != 1:
        raise ValueError("DURABLE_DISCOVERY_QUEUE_NOT_SINGLETON")
    item = queue["queue"][0]

    client = ApiTennisDiscoveryClient(api_key)
    store = SQLiteAcquisitionStore(store_path)
    fetcher = ApiTennisDiscoveryFetcher(
        client=client,
        start=now.date(),
        stop=now.date() + timedelta(days=days - 1),
        as_of_utc=now.isoformat(),
    )
    result = execute_tennis_acquisition_queue(
        queue_manifest=queue,
        fetcher=fetcher,
        raw_ledger=store,
        checkpoints=store,
        limits=WorkerLimits(max_items=1, max_requests=MAX_REQUESTS_PER_BUCKET),
    )

    queue_fp = str(item["queue_item_fingerprint"])
    evidence_id = store.find_evidence_for_queue_item(queue_fp)
    if evidence_id is None:
        raise ValueError("DURABLE_DISCOVERY_EVIDENCE_MISSING")
    envelope = store.get_raw(evidence_id)
    if not isinstance(envelope, Mapping):
        raise ValueError("DURABLE_DISCOVERY_RAW_ENVELOPE_MISSING")
    raw_payload = envelope.get("raw_payload")
    if not isinstance(raw_payload, Mapping):
        raise ValueError("DURABLE_DISCOVERY_RAW_PAYLOAD_MISSING")

    integrity = store.audit_integrity()
    if not integrity.ok:
        raise ValueError("DURABLE_DISCOVERY_STORE_INTEGRITY_FAIL")

    summary = {
        "schema": "MATRIX_COR0203_DURABLE_DISCOVERY_SUMMARY_V1",
        "queue_fingerprint": queue["queue_fingerprint"],
        "queue_item_fingerprint": queue_fp,
        "processed": result.processed,
        "skipped_completed": result.skipped_completed,
        "recovered_without_fetch": result.recovered_without_fetch,
        "failed": result.failed,
        "worker_request_budget_used": result.requests_used,
        "provider_network_calls": int(raw_payload.get("network_calls", 0) or 0),
        "evidence_id": evidence_id,
        "store_raw_records": integrity.raw_records,
        "store_checkpoints": integrity.checkpoints,
        "store_integrity_ok": integrity.ok,
        "bucket_reuse": bool(result.skipped_completed or result.recovered_without_fetch),
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    return dict(raw_payload), summary


def _missing_key_payload(as_of_utc: str) -> dict[str, Any]:
    now = _parse_utc(as_of_utc)
    return {
        "schema": "MATRIX_COR0203_API_TENNIS_DISCOVERY_V1",
        "provider": "api_tennis",
        "as_of_utc": now.isoformat(),
        "status": "API_TENNIS_KEY_NOT_CONFIGURED",
        "network_calls": 0,
        "durable_acquisition": True,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-out", required=True)
    parser.add_argument(
        "--store",
        default="evidence/cor0203/acquisition/MATRIX_COR0203_ACQUISITION.sqlite3",
    )
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--as-of-utc")
    args = parser.parse_args()

    as_of = args.as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    key = os.environ.get("API_TENNIS_KEY", "").strip()

    if not key:
        payload = _missing_key_payload(as_of)
        summary = {
            "schema": "MATRIX_COR0203_DURABLE_DISCOVERY_SUMMARY_V1",
            "status": "SOURCE_NOT_CONFIGURED",
            "processed": 0,
            "skipped_completed": 0,
            "recovered_without_fetch": 0,
            "failed": 0,
            "worker_request_budget_used": 0,
            "provider_network_calls": 0,
            "store_integrity_ok": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }
    else:
        try:
            payload, summary = execute_durable_discovery(
                api_key=key,
                as_of_utc=as_of,
                days=args.days,
                store_path=Path(args.store),
            )
            summary["status"] = "PASS"
        except ApiTennisDiscoveryError as error:
            payload = {
                "schema": "MATRIX_COR0203_API_TENNIS_DISCOVERY_V1",
                "provider": "api_tennis",
                "as_of_utc": _parse_utc(as_of).isoformat(),
                "status": "PROVIDER_DISCOVERY_BLOCKED",
                "blocker": type(error).__name__ + ":" + str(error),
                "network_calls": 0,
                "durable_acquisition": True,
                "automatic_model_promotion": False,
                "automatic_wagering": False,
                "real_money": "BLOCKED",
            }
            summary = {
                "schema": "MATRIX_COR0203_DURABLE_DISCOVERY_SUMMARY_V1",
                "status": "PROVIDER_DISCOVERY_BLOCKED",
                "processed": 0,
                "skipped_completed": 0,
                "recovered_without_fetch": 0,
                "failed": 1,
                "worker_request_budget_used": 0,
                "provider_network_calls": 0,
                "store_integrity_ok": True,
                "automatic_wagering": False,
                "real_money": "BLOCKED",
            }

    Path(args.out).write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    Path(args.summary_out).write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": payload.get("status"),
        "durable_status": summary.get("status"),
        "processed": summary.get("processed", 0),
        "skipped_completed": summary.get("skipped_completed", 0),
        "recovered_without_fetch": summary.get("recovered_without_fetch", 0),
        "provider_network_calls": summary.get("provider_network_calls", 0),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
