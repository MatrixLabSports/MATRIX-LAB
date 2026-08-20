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
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BootstrapProbePolicy:
    sport: str
    provider_key: str
    manual_approval_id: str
    max_items: int
    max_requests: int
    downstream_quarantine_required: bool
    policy_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-bootstrap-probe-policy/1",
            "mode": "BOOTSTRAP_PROBE",
            "sport": self.sport,
            "provider_key": self.provider_key,
            "manual_approval_id": self.manual_approval_id,
            "max_items": self.max_items,
            "max_requests": self.max_requests,
            "downstream_quarantine_required": (
                self.downstream_quarantine_required
            ),
            "automatic_provider_switch": False,
            "automatic_health_promotion": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "policy_fingerprint": self.policy_fingerprint,
        }


def build_bootstrap_probe_policy(
    *,
    sport: str,
    provider_key: str,
    manual_approval_id: str,
    max_items: int,
    max_requests: int,
) -> BootstrapProbePolicy:
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")
    if not isinstance(provider_key, str) or not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if not isinstance(manual_approval_id, str) or not manual_approval_id:
        raise ValueError("MANUAL_APPROVAL_REQUIRED")
    if (
        not isinstance(max_items, int)
        or isinstance(max_items, bool)
        or max_items < 1
        or max_items > 5
    ):
        raise ValueError("BOOTSTRAP_ITEMS_OUT_OF_BOUNDS")
    if (
        not isinstance(max_requests, int)
        or isinstance(max_requests, bool)
        or max_requests < 1
        or max_requests > 10
    ):
        raise ValueError("BOOTSTRAP_REQUESTS_OUT_OF_BOUNDS")

    base = {
        "schema": "matrix.provider-bootstrap-probe-policy/1",
        "mode": "BOOTSTRAP_PROBE",
        "sport": sport,
        "provider_key": provider_key,
        "manual_approval_id": manual_approval_id,
        "max_items": max_items,
        "max_requests": max_requests,
        "downstream_quarantine_required": True,
        "automatic_provider_switch": False,
        "automatic_health_promotion": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return BootstrapProbePolicy(
        sport=sport,
        provider_key=provider_key,
        manual_approval_id=manual_approval_id,
        max_items=max_items,
        max_requests=max_requests,
        downstream_quarantine_required=True,
        policy_fingerprint=_sha(base),
    )
