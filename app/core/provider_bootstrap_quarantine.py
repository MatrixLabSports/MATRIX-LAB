from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _shape(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _shape(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(value, list):
        return {
            "type": "list",
            "length": len(value),
            "sample_shape": (
                [_shape(value[0])]
                if value
                else []
            ),
        }

    if value is None:
        return "null"

    if isinstance(value, bool):
        return "bool"

    if isinstance(value, int):
        return "int"

    if isinstance(value, float):
        return "float"

    if isinstance(value, str):
        return "str"

    return type(value).__name__


@dataclass(frozen=True)
class BootstrapProbeSummary:
    status: str
    top_level_keys: tuple[str, ...]
    shape_fingerprint: str
    raw_payload_retained: bool = False
    production_admissible: bool = False
    retroactive_promotion_allowed: bool = False


def summarize_bootstrap_payload(
    payload: Mapping[str, Any],
) -> BootstrapProbeSummary:
    if not isinstance(payload, Mapping):
        raise ValueError(
            "BOOTSTRAP_PAYLOAD_MUST_BE_MAPPING"
        )

    return BootstrapProbeSummary(
        status="QUARANTINED_PROBE_ONLY",
        top_level_keys=tuple(
            sorted(
                str(key)
                for key in payload
            )
        ),
        shape_fingerprint=_sha(
            {
                "schema": (
                    "matrix.bootstrap-payload-shape/1"
                ),
                "shape": _shape(payload),
            }
        ),
    )


def execute_bootstrap_probe(
    *,
    authority,
    client,
    endpoint: str,
    params: Mapping[str, Any] | None = None,
) -> BootstrapProbeSummary:
    if authority.mode != "BOOTSTRAP_PROBE":
        raise ValueError(
            "BOOTSTRAP_PROBE_MODE_REQUIRED"
        )

    raw_payload = client.get(
        endpoint,
        params=(
            dict(params)
            if params is not None
            else None
        ),
    )

    summary = summarize_bootstrap_payload(
        raw_payload
    )
    del raw_payload
    return summary
