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
    request_contract_id: str,
    params: Mapping[str, Any] | None = None,
) -> BootstrapProbeSummary:
    if authority.mode != "BOOTSTRAP_PROBE":
        raise ValueError(
            "BOOTSTRAP_PROBE_MODE_REQUIRED"
        )

    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("/")
        or "?" in endpoint
        or "#" in endpoint
    ):
        raise ValueError(
            "BOOTSTRAP_CONTRACT_PATH_REQUIRED"
        )

    if (
        not isinstance(request_contract_id, str)
        or len(request_contract_id) != 64
    ):
        raise ValueError(
            "BOOTSTRAP_REQUEST_CONTRACT_ID_REQUIRED"
        )
    try:
        int(request_contract_id, 16)
    except ValueError as error:
        raise ValueError(
            "BOOTSTRAP_REQUEST_CONTRACT_ID_REQUIRED"
        ) from error

    raw_response = client.get(
        path=endpoint,
        request_contract_id=request_contract_id,
        params=(
            dict(params)
            if params is not None
            else None
        ),
    )

    if isinstance(raw_response, Mapping):
        raw_payload = raw_response
    else:
        json_strict = getattr(
            raw_response,
            "json_strict",
            None,
        )
        if not callable(json_strict):
            raise ValueError(
                "BOOTSTRAP_RESPONSE_JSON_DECODER_REQUIRED"
            )
        raw_payload = json_strict()

    del raw_response

    summary = summarize_bootstrap_payload(
        raw_payload
    )
    del raw_payload
    return summary
