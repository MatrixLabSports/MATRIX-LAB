from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .data_classification import DataAsset, DataClass


class Environment(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    PRODUCTION = "PRODUCTION"


@dataclass(frozen=True)
class StorageZone:
    zone_id: str
    environment: Environment
    maximum_class: DataClass
    allows_personal_data: bool
    allows_credentials: bool
    externally_shared: bool = False

    def __post_init__(self) -> None:
        if not self.zone_id.strip():
            raise ValueError("zone_id is required")


_RANK = {
    DataClass.PUBLIC: 1,
    DataClass.INTERNAL: 2,
    DataClass.CONFIDENTIAL: 3,
    DataClass.RESTRICTED: 4,
}


def placement_allowed(asset: DataAsset, zone: StorageZone) -> bool:
    if _RANK[asset.data_class] > _RANK[zone.maximum_class]:
        return False
    if asset.contains_personal_data and not zone.allows_personal_data:
        return False
    if asset.contains_credentials and not zone.allows_credentials:
        return False
    if zone.externally_shared and asset.data_class in {DataClass.CONFIDENTIAL, DataClass.RESTRICTED}:
        return False
    if zone.environment is Environment.DEVELOPMENT and asset.contains_credentials:
        return False
    return True
