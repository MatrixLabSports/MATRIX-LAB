from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.release.canonical import canonical_sha256
from .data_classification import DataClass


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class ExportDecision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ExportRequest:
    request_id: str
    asset_id: str
    data_class: DataClass
    destination: str
    purpose: str
    requested_by: str
    requested_at: datetime
    encrypted_transport: bool
    recipient_verified: bool
    approval_reference: str | None = None

    def __post_init__(self) -> None:
        if not all(v.strip() for v in (self.request_id, self.asset_id, self.destination, self.purpose, self.requested_by)):
            raise ValueError("request identity, destination, purpose and requester are required")
        _aware(self.requested_at, "requested_at")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def evaluate_export(request: ExportRequest) -> ExportDecision:
    if request.data_class is DataClass.PUBLIC:
        return ExportDecision.ALLOW
    if not request.recipient_verified or not request.encrypted_transport:
        return ExportDecision.BLOCK
    if request.data_class is DataClass.INTERNAL:
        return ExportDecision.ALLOW
    if request.data_class in {DataClass.CONFIDENTIAL, DataClass.RESTRICTED}:
        return ExportDecision.REQUIRE_REVIEW if request.approval_reference else ExportDecision.BLOCK
    return ExportDecision.BLOCK
