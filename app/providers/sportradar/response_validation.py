from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Any


_ALLOWED_COLLECTIONS = {
    "competitions",
    "seasons",
    "summaries",
    "sport_events",
}


@dataclass(frozen=True)
class SportradarEnvelope:
    collection_name: str
    items: tuple[Mapping[str, Any], ...]
    generated_at: str
    payload_fingerprint: str


class SportradarProviderResponseError(ValueError):
    def __init__(self, code: str, category: str) -> None:
        self.code = code
        self.category = category
        super().__init__(code)


def _error(code: str, category: str) -> SportradarProviderResponseError:
    return SportradarProviderResponseError(code, category)


def _validated_generated_at(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(
            "SPORTRADAR_GENERATED_AT_REQUIRED",
            "MALFORMED_ENVELOPE",
        )
    canonical = value.strip()
    candidate = canonical[:-1] + "+00:00" if canonical.endswith("Z") else canonical
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise _error(
            "SPORTRADAR_GENERATED_AT_INVALID",
            "TEMPORAL_SCHEMA",
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(
            "SPORTRADAR_GENERATED_AT_TIMEZONE_REQUIRED",
            "TEMPORAL_SCHEMA",
        )
    return canonical


def validate_sportradar_collection(
    payload: object,
    *,
    collection_name: str,
) -> SportradarEnvelope:
    if collection_name not in _ALLOWED_COLLECTIONS:
        raise ValueError("INVALID_SPORTRADAR_COLLECTION")
    if not isinstance(payload, Mapping):
        raise _error("SPORTRADAR_RESPONSE_NOT_MAPPING", "MALFORMED_ENVELOPE")
    if any(not isinstance(key, str) for key in payload):
        raise _error("SPORTRADAR_RESPONSE_KEY_NOT_STRING", "MALFORMED_ENVELOPE")

    generated_at = _validated_generated_at(payload.get("generated_at"))

    if collection_name not in payload:
        raise _error("SPORTRADAR_COLLECTION_REQUIRED", "MALFORMED_ENVELOPE")
    raw_items = payload[collection_name]
    if not isinstance(raw_items, list):
        raise _error("SPORTRADAR_COLLECTION_INVALID", "MALFORMED_ENVELOPE")

    items = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            raise _error("SPORTRADAR_ITEM_NOT_MAPPING", "SCHEMA")
        if any(not isinstance(key, str) for key in item):
            raise _error("SPORTRADAR_ITEM_KEY_NOT_STRING", "SCHEMA")
        items.append(dict(item))

    try:
        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise _error(
            "SPORTRADAR_RESPONSE_NOT_CANONICAL_JSON",
            "MALFORMED_ENVELOPE",
        ) from error

    return SportradarEnvelope(
        collection_name=collection_name,
        items=tuple(items),
        generated_at=generated_at,
        payload_fingerprint=sha256(payload_json.encode("utf-8")).hexdigest(),
    )
