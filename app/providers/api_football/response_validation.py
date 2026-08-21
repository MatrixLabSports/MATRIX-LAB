from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any


@dataclass(frozen=True)
class ApiFootballResponseEnvelope:
    endpoint: str
    response: tuple[Any, ...]
    request_name: str | None
    results: int | None
    paging_current: int | None
    paging_total: int | None
    payload_fingerprint: str


class ApiFootballProviderResponseError(ValueError):
    def __init__(
        self,
        code: str,
        category: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.category = category
        self.retryable = bool(retryable)
        super().__init__(code)


def _provider_error(
    code: str,
    category: str,
    *,
    retryable: bool = False,
) -> ApiFootballProviderResponseError:
    return ApiFootballProviderResponseError(
        code,
        category,
        retryable=retryable,
    )


def _canonical_endpoint(endpoint: str) -> str:
    if (
        not isinstance(endpoint, str)
        or not endpoint.startswith("/")
        or endpoint == "/"
        or "?" in endpoint
        or "#" in endpoint
        or "\\" in endpoint
        or "//" in endpoint
    ):
        raise ValueError(
            "INVALID_API_FOOTBALL_EXPECTED_ENDPOINT"
        )

    return endpoint


def _errors_are_empty(errors: object) -> bool:
    if errors is None:
        return True

    if isinstance(errors, Mapping):
        return len(errors) == 0

    if isinstance(errors, list):
        return len(errors) == 0

    if isinstance(errors, str):
        return errors.strip() == ""

    raise _provider_error(
        "API_FOOTBALL_ERRORS_FIELD_INVALID",
        "MALFORMED_ENVELOPE",
    )


def validate_api_football_response_envelope(
    payload: object,
    *,
    endpoint: str,
) -> ApiFootballResponseEnvelope:
    expected_endpoint = _canonical_endpoint(
        endpoint
    )

    if not isinstance(payload, Mapping):
        raise _provider_error(
            "API_FOOTBALL_RESPONSE_NOT_MAPPING",
            "MALFORMED_ENVELOPE",
        )

    if any(
        not isinstance(key, str)
        for key in payload.keys()
    ):
        raise _provider_error(
            "API_FOOTBALL_RESPONSE_KEY_NOT_STRING",
            "MALFORMED_ENVELOPE",
        )

    try:
        payload_json = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise _provider_error(
            "API_FOOTBALL_RESPONSE_NOT_CANONICAL_JSON",
            "MALFORMED_ENVELOPE",
        ) from error

    if "response" not in payload:
        raise _provider_error(
            "API_FOOTBALL_RESPONSE_FIELD_REQUIRED",
            "MALFORMED_ENVELOPE",
        )

    response = payload["response"]

    if not isinstance(response, list):
        raise _provider_error(
            "API_FOOTBALL_RESPONSE_FIELD_INVALID",
            "MALFORMED_ENVELOPE",
        )

    errors = payload.get("errors")

    if not _errors_are_empty(errors):
        raise _provider_error(
            "API_FOOTBALL_PROVIDER_ERROR_PRESENT",
            "PROVIDER_DECLARED_ERROR",
        )

    request_name = payload.get("get")

    if request_name is not None:
        if (
            not isinstance(request_name, str)
            or not request_name.strip()
        ):
            raise _provider_error(
                "API_FOOTBALL_GET_FIELD_INVALID",
                "MALFORMED_ENVELOPE",
            )

        normalized_request = (
            "/"
            + request_name.strip().lstrip("/")
        )

        if normalized_request != expected_endpoint:
            raise _provider_error(
                "API_FOOTBALL_ENDPOINT_MISMATCH",
                "CONTRACT_MISMATCH",
            )

    parameters = payload.get("parameters")

    if (
        parameters is not None
        and not isinstance(
            parameters,
            Mapping,
        )
    ):
        raise _provider_error(
            "API_FOOTBALL_PARAMETERS_FIELD_INVALID",
            "MALFORMED_ENVELOPE",
        )

    results = payload.get("results")

    if results is not None:
        if (
            isinstance(results, bool)
            or not isinstance(results, int)
            or results < 0
        ):
            raise _provider_error(
                "API_FOOTBALL_RESULTS_FIELD_INVALID",
                "MALFORMED_ENVELOPE",
            )

        if results != len(response):
            raise _provider_error(
                "API_FOOTBALL_RESULTS_COUNT_MISMATCH",
                "CONTRACT_MISMATCH",
            )

    paging_current = None
    paging_total = None
    paging = payload.get("paging")

    if paging is not None:
        if not isinstance(paging, Mapping):
            raise _provider_error(
                "API_FOOTBALL_PAGING_FIELD_INVALID",
                "MALFORMED_ENVELOPE",
            )

        if (
            "current" not in paging
            or "total" not in paging
        ):
            raise _provider_error(
                "API_FOOTBALL_PAGING_FIELDS_REQUIRED",
                "MALFORMED_ENVELOPE",
            )

        paging_current = paging["current"]
        paging_total = paging["total"]

        for value in (
            paging_current,
            paging_total,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise _provider_error(
                    "API_FOOTBALL_PAGING_VALUE_INVALID",
                    "MALFORMED_ENVELOPE",
                )

    return ApiFootballResponseEnvelope(
        endpoint=expected_endpoint,
        response=tuple(response),
        request_name=(
            request_name
            if isinstance(request_name, str)
            else None
        ),
        results=(
            results
            if isinstance(results, int)
            and not isinstance(results, bool)
            else None
        ),
        paging_current=paging_current,
        paging_total=paging_total,
        payload_fingerprint=sha256(
            payload_json.encode("utf-8")
        ).hexdigest(),
    )
