from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.release.canonical import canonical_sha256


class DataClass(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


@dataclass(frozen=True)
class DataAsset:
    asset_id: str
    name: str
    data_class: DataClass
    contains_personal_data: bool
    contains_credentials: bool
    purpose: str
    owner: str

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.name.strip() or not self.purpose.strip() or not self.owner.strip():
            raise ValueError("asset_id, name, purpose and owner are required")
        if self.contains_credentials and self.data_class is not DataClass.RESTRICTED:
            raise ValueError("credential-bearing assets must be RESTRICTED")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class ClassificationPolicy:
    personal_data_minimum_class: DataClass = DataClass.CONFIDENTIAL


_CLASS_RANK = {
    DataClass.PUBLIC: 1,
    DataClass.INTERNAL: 2,
    DataClass.CONFIDENTIAL: 3,
    DataClass.RESTRICTED: 4,
}


def classification_is_acceptable(asset: DataAsset, policy: ClassificationPolicy = ClassificationPolicy()) -> bool:
    if asset.contains_personal_data and _CLASS_RANK[asset.data_class] < _CLASS_RANK[policy.personal_data_minimum_class]:
        return False
    return True
