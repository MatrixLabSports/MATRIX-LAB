from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def config_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ConfigIntegrityCheck:
    expected_sha256: str

    def __post_init__(self) -> None:
        if len(self.expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.expected_sha256):
            raise ValueError("expected_sha256 must be lowercase SHA-256 hex")

    def verify(self, config: Mapping[str, Any]) -> bool:
        return config_sha256(config) == self.expected_sha256
