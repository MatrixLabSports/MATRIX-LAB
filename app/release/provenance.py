from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from .canonical import canonical_sha256

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def _sha256(value: str, name: str) -> None:
    if not _HEX64.fullmatch(value):
        raise ValueError(f"{name} must be lowercase SHA-256 hex")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class ReleaseProvenance:
    release_id: str
    source_repository: str
    commit_sha: str
    source_tree_clean: bool
    source_commit_verified: bool
    builder_id: str
    builder_identity_verified: bool
    build_started_at: datetime
    build_finished_at: datetime
    source_archive_sha256: str
    build_recipe_sha256: str
    dependency_lock_sha256: str
    environment_lock_sha256: str
    artifact_sha256: str
    ci_evidence_sha256: str
    security_evidence_sha256: str
    rollback_plan_sha256: str
    parent_release_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.release_id.strip():
            raise ValueError("release_id is required")
        if not self.source_repository.strip():
            raise ValueError("source_repository is required")
        if not _HEX40.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a lowercase 40-character hexadecimal Git SHA")
        if not isinstance(self.source_tree_clean, bool):
            raise TypeError("source_tree_clean must be bool")
        if not isinstance(self.source_commit_verified, bool):
            raise TypeError("source_commit_verified must be bool")
        if not self.builder_id.strip():
            raise ValueError("builder_id is required")
        if not isinstance(self.builder_identity_verified, bool):
            raise TypeError("builder_identity_verified must be bool")
        _aware(self.build_started_at, "build_started_at")
        _aware(self.build_finished_at, "build_finished_at")
        if self.build_finished_at < self.build_started_at:
            raise ValueError("build_finished_at cannot precede build_started_at")
        for name in (
            "source_archive_sha256",
            "build_recipe_sha256",
            "dependency_lock_sha256",
            "environment_lock_sha256",
            "artifact_sha256",
            "ci_evidence_sha256",
            "security_evidence_sha256",
            "rollback_plan_sha256",
        ):
            _sha256(getattr(self, name), name)
        if self.parent_release_sha256 is not None:
            _sha256(self.parent_release_sha256, "parent_release_sha256")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)
