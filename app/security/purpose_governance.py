from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .data_inventory import DataInventoryRecord


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class PurposeStatus(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class PurposeSpecification:
    purpose_id: str
    description: str
    allowed_data_categories: tuple[str, ...]
    allowed_operations: tuple[str, ...]
    owner: str
    version: str
    active: bool = True

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.purpose_id, self.description, self.owner, self.version)):
            raise ValueError("purpose metadata is required")
        if not self.allowed_data_categories or not self.allowed_operations:
            raise ValueError("purpose must define categories and operations")
        if len(set(self.allowed_data_categories)) != len(self.allowed_data_categories):
            raise ValueError("duplicate allowed_data_categories")
        if len(set(self.allowed_operations)) != len(self.allowed_operations):
            raise ValueError("duplicate allowed_operations")


@dataclass(frozen=True)
class PurposeUseRequest:
    asset_id: str
    purpose_id: str
    operation: str
    data_categories: tuple[str, ...]
    requested_at: datetime

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.purpose_id.strip() or not self.operation.strip():
            raise ValueError("asset_id, purpose_id and operation are required")
        if not self.data_categories or any(not item.strip() for item in self.data_categories):
            raise ValueError("data_categories are required")
        if len(set(self.data_categories)) != len(self.data_categories):
            raise ValueError("duplicate requested data category")
        _aware(self.requested_at, "requested_at")


@dataclass(frozen=True)
class PurposeAssessment:
    status: PurposeStatus
    reasons: tuple[str, ...]


def evaluate_purpose_use(
    inventory: DataInventoryRecord,
    specification: PurposeSpecification,
    request: PurposeUseRequest,
) -> PurposeAssessment:
    reasons: list[str] = []
    if request.asset_id != inventory.asset.asset_id:
        reasons.append("ASSET_MISMATCH")
    if request.purpose_id != specification.purpose_id:
        reasons.append("PURPOSE_SPECIFICATION_MISMATCH")
    if request.purpose_id not in inventory.purpose_ids:
        reasons.append("PURPOSE_NOT_IN_INVENTORY")
    if not specification.active:
        reasons.append("PURPOSE_INACTIVE")
    if request.operation not in specification.allowed_operations:
        reasons.append("OPERATION_NOT_ALLOWED_FOR_PURPOSE")
    inventory_categories = set(inventory.data_categories)
    purpose_categories = set(specification.allowed_data_categories)
    requested = set(request.data_categories)
    if not requested.issubset(inventory_categories):
        reasons.append("REQUESTED_CATEGORY_NOT_IN_INVENTORY")
    if not requested.issubset(purpose_categories):
        reasons.append("REQUESTED_CATEGORY_NOT_ALLOWED_FOR_PURPOSE")
    return PurposeAssessment(PurposeStatus.BLOCK if reasons else PurposeStatus.PASS, tuple(dict.fromkeys(reasons)))
