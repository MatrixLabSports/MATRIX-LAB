from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


API_EVENT = re.compile(r"^api-tennis:event:(\d+)$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
FINISHED = "FINISHED"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _event_revision(path: Path) -> int:
    match = re.search(r"_R(\d+)\.json$", path.name)
    return int(match.group(1)) if match else -1


def _provider_match_key(canonical_source_event_id: object) -> str | None:
    match = API_EVENT.fullmatch(str(canonical_source_event_id or ""))
    return match.group(1) if match else None


def _settlement_id(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("settlement_id", None)
    body.pop("record_sha256", None)
    body.pop("previous_record_sha256", None)
    return _sha({"schema": "MATRIX_COR0203_SETTLEMENT_ID_V1", "payload": body})


def _record_sha(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("record_sha256", None)
    return _sha(body)


@dataclass(frozen=True)
class SettlementLedgerAudit:
    records: int
    unique_events: int
    hash_chain_verified: bool
    outcomes_used_for_metrics: int


class Cor0203SettlementLedger:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        previous: str | None = None
        seen: set[str] = set()
        for line_number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(f"INVALID_SETTLEMENT_JSON:{line_number}") from error
            event_id = str(row.get("event_id") or "")
            if not event_id or event_id in seen:
                raise ValueError("DUPLICATE_OR_MISSING_SETTLEMENT_EVENT")
            if row.get("previous_record_sha256") != previous:
                raise ValueError("SETTLEMENT_HASH_CHAIN_BROKEN")
            if row.get("record_sha256") != _record_sha(row):
                raise ValueError("SETTLEMENT_RECORD_SHA_MISMATCH")
            expected_id = _settlement_id(row)
            if row.get("settlement_id") != expected_id:
                raise ValueError("SETTLEMENT_ID_MISMATCH")
            if row.get("metrics_opened") is not False or row.get("used_for_metrics") is not False:
                raise ValueError("SETTLEMENT_METRICS_MUST_REMAIN_SEALED")
            if row.get("real_money") != "BLOCKED":
                raise ValueError("SETTLEMENT_REAL_MONEY_MUST_BE_BLOCKED")
            previous = str(row["record_sha256"])
            seen.add(event_id)
            records.append(row)
        return records

    def append(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        records = self.load()
        event_id = str(payload.get("event_id") or "")
        if not event_id:
            raise ValueError("SETTLEMENT_EVENT_ID_REQUIRED")
        if any(row["event_id"] == event_id for row in records):
            raise ValueError("DUPLICATE_SETTLEMENT_EVENT")
        row = dict(payload)
        row["previous_record_sha256"] = records[-1]["record_sha256"] if records else None
        row["settlement_id"] = _settlement_id(row)
        row["record_sha256"] = _record_sha(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(row) + "\n")
            handle.flush()
        self.load()
        return row

    def audit(self) -> SettlementLedgerAudit:
        records = self.load()
        return SettlementLedgerAudit(
            records=len(records),
            unique_events=len({row["event_id"] for row in records}),
            hash_chain_verified=True,
            outcomes_used_for_metrics=sum(1 for row in records if row.get("used_for_metrics") is True),
        )


def _admissible_revisions(integrity: Mapping[str, Any]) -> set[int]:
    return {int(value) for value in integrity.get("admissible_batch_revisions", []) or []}


def build_settlement_queue(
    *,
    runtime_dir: Path,
    holdout_dir: Path,
    integrity: Mapping[str, Any],
    ledger_records: Sequence[Mapping[str, Any]],
    identity_overlay: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    settled_ids = {str(row.get("event_id") or "") for row in ledger_records}
    overlay = dict(identity_overlay or {})
    admissible = _admissible_revisions(integrity)
    items: list[dict[str, Any]] = []

    for batch_path in sorted(holdout_dir.glob("MATRIX_COR0203_HOLDOUT_BATCH_R*.json"), key=_event_revision):
        revision = _event_revision(batch_path)
        if revision not in admissible:
            continue
        batch = _load(batch_path)
        event_path = runtime_dir / f"MATRIX_COR0203_PROSPECTIVE_EVENTS_R{revision}.json"
        if not event_path.exists():
            raise ValueError(f"SETTLEMENT_EVENT_MANIFEST_MISSING:R{revision}")
        events = {
            str(row.get("event_id") or ""): row
            for row in _load(event_path).get("events", []) or []
        }
        pre_path = runtime_dir / f"MATRIX_COR0203_PREFEATURE_REGISTRY_R{revision}.json"
        pre = _load(pre_path) if pre_path.exists() else {}
        pre_events = {
            str(row.get("event_id") or ""): row
            for row in pre.get("events", []) or []
        }
        cross_path = runtime_dir / f"MATRIX_COR0203_IDENTITY_CROSSWALK_R{revision}.json"
        cross = _load(cross_path) if cross_path.exists() else {}
        cross_map = {
            str(row.get("provider_player_id") or ""): str(row.get("canonical_name") or "")
            for row in cross.get("mappings", []) or []
            if row.get("status") == "PASS"
        }

        for obs in batch.get("observations", []) or []:
            event_id = str(obs.get("event_id") or "")
            event = events.get(event_id)
            if not isinstance(event, Mapping):
                raise ValueError("SETTLEMENT_EVENT_ROW_MISSING:" + event_id)
            canonical_source = str(event.get("canonical_source_event_id") or "")
            match_key = _provider_match_key(canonical_source)
            overlay_row = overlay.get(event_id, {})
            if match_key is None and isinstance(overlay_row, Mapping):
                overlay_match_key = str(overlay_row.get("provider_match_key") or "")
                if overlay_match_key.isdigit() and int(overlay_match_key) > 0:
                    match_key = overlay_match_key
                    canonical_source = str(
                        overlay_row.get("canonical_source_event_id")
                        or ("api-tennis:event:" + overlay_match_key)
                    )
            pre_event = pre_events.get(event_id, {})
            provider_identities = list(pre_event.get("player_identities") or []) if isinstance(pre_event, Mapping) else []
            provider_map = {
                str(row.get("provider_player_id") or ""): cross_map.get(
                    str(row.get("provider_player_id") or ""),
                    str(row.get("display_name") or ""),
                )
                for row in provider_identities
                if row.get("provider_player_id")
            }
            if isinstance(overlay_row, Mapping) and overlay_row.get("provider_player_map"):
                provider_map = {
                    str(key): str(value)
                    for key, value in dict(overlay_row["provider_player_map"]).items()
                }
            if event_id in settled_ids:
                status = "SETTLED"
                blocker = None
            elif match_key is None:
                status = "IDENTITY_MAPPING_REQUIRED"
                blocker = "PROVIDER_MATCH_KEY_MISSING"
            elif len(provider_map) != 2:
                status = "IDENTITY_MAPPING_REQUIRED"
                blocker = "PROVIDER_PLAYER_MAPPING_INCOMPLETE"
            else:
                status = "READY_RESULT_LOOKUP"
                blocker = None

            items.append({
                "revision": revision,
                "event_id": event_id,
                "observation_index": int(obs.get("observation_index")),
                "observation_sha256": obs.get("observation_sha256"),
                "alphabetical_player_a": obs.get("alphabetical_player_a"),
                "alphabetical_player_b": obs.get("alphabetical_player_b"),
                "event_start_utc": obs.get("event_start_utc"),
                "canonical_source_event_id": canonical_source,
                "provider": "api_tennis" if match_key else None,
                "identity_overlay_applied": bool(match_key and overlay_row),
                "provider_match_key": match_key,
                "provider_player_map": provider_map,
                "status": status,
                "blocker": blocker,
            })

    return {
        "schema": "MATRIX_COR0203_SETTLEMENT_QUEUE_V1",
        "holdout_id": integrity.get("holdout_id"),
        "admissible_observations": int(integrity.get("admissible_observations", 0)),
        "settled": sum(1 for row in items if row["status"] == "SETTLED"),
        "ready_result_lookup": sum(1 for row in items if row["status"] == "READY_RESULT_LOOKUP"),
        "identity_mapping_required": sum(1 for row in items if row["status"] == "IDENTITY_MAPPING_REQUIRED"),
        "items": items,
        "metrics": "SEALED_UNTIL_600",
        "outcomes_used_for_metrics": 0,
        "real_money": "BLOCKED",
    }


def settlement_from_api_tennis(
    *,
    queue_item: Mapping[str, Any],
    fixture: Mapping[str, Any],
    settled_at_utc: str,
    source_reference: str,
) -> dict[str, Any]:
    if queue_item.get("status") != "READY_RESULT_LOOKUP":
        raise ValueError("SETTLEMENT_ITEM_NOT_READY")
    match_key = str(queue_item.get("provider_match_key") or "")
    if str(fixture.get("event_key") or "") != match_key:
        raise ValueError("SETTLEMENT_PROVIDER_EVENT_MISMATCH")

    status = str(fixture.get("event_status") or "").strip().upper()
    if status != FINISHED:
        raise ValueError("SETTLEMENT_NOT_STANDARD_FINAL:" + status)

    winner = str(fixture.get("event_winner") or "").strip()
    if winner not in {"First Player", "Second Player"}:
        raise ValueError("SETTLEMENT_WINNER_NOT_FIXED")

    first_id = "api-tennis:player:" + str(fixture.get("first_player_key") or "")
    second_id = "api-tennis:player:" + str(fixture.get("second_player_key") or "")
    provider_map = dict(queue_item.get("provider_player_map") or {})
    if first_id not in provider_map or second_id not in provider_map:
        raise ValueError("SETTLEMENT_PROVIDER_PLAYER_MAPPING_MISSING")

    winner_name = provider_map[first_id] if winner == "First Player" else provider_map[second_id]
    player_a = str(queue_item.get("alphabetical_player_a") or "")
    player_b = str(queue_item.get("alphabetical_player_b") or "")
    if winner_name == player_a:
        outcome_a = True
    elif winner_name == player_b:
        outcome_a = False
    else:
        raise ValueError("SETTLEMENT_CANONICAL_WINNER_MISMATCH")

    source_payload_sha = _sha(dict(fixture))
    payload = {
        "schema": "MATRIX_COR0203_SETTLEMENT_RECORD_V1",
        "event_id": queue_item["event_id"],
        "observation_index": int(queue_item["observation_index"]),
        "observation_sha256": queue_item["observation_sha256"],
        "event_start_utc": queue_item["event_start_utc"],
        "settled_at_utc": settled_at_utc,
        "terminal_status": FINISHED,
        "winner_canonical_name": winner_name,
        "outcome_player_a": outcome_a,
        "result_source_provider": "api_tennis",
        "result_source_reference": source_reference,
        "result_payload_sha256": source_payload_sha,
        "provider_match_key": match_key,
        "event_final_result": fixture.get("event_final_result"),
        "metrics_opened": False,
        "used_for_metrics": False,
        "real_money": "BLOCKED",
    }
    if not isinstance(payload["observation_sha256"], str) or not SHA64.fullmatch(payload["observation_sha256"]):
        raise ValueError("SETTLEMENT_OBSERVATION_SHA_INVALID")
    return payload
