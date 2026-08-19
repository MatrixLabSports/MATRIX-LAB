from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import re
from typing import Iterable

from .canonical import canonical_sha256

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


class StageStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


REQUIRED_CI_STAGES = (
    "SOURCE_INTEGRITY",
    "PYTHON_COMPILE",
    "TESTS",
    "SECRET_SCAN",
    "DEPENDENCY_LOCK",
    "VULNERABILITY_SCAN",
    "CONFIG_INTEGRITY",
    "ARCHITECTURE",
    "SPORT_BOUNDARY",
    "REPRODUCIBILITY",
    "BACKUP_ROLLBACK",
)


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True)
class StageEvidence:
    stage: str
    status: StageStatus
    commit_sha: str
    observed_at: datetime
    evidence_sha256: str
    tool: str
    tool_version: str

    def __post_init__(self) -> None:
        if self.stage not in REQUIRED_CI_STAGES:
            raise ValueError(f"unknown CI stage: {self.stage}")
        if not _HEX40.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a lowercase 40-character hexadecimal Git SHA")
        _aware(self.observed_at, "observed_at")
        if not _HEX64.fullmatch(self.evidence_sha256):
            raise ValueError("evidence_sha256 must be lowercase SHA-256 hex")
        if not self.tool.strip() or not self.tool_version.strip():
            raise ValueError("tool identity and version are required")

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class TestRunEvidence:
    __test__ = False

    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: int

    def __post_init__(self) -> None:
        values = (self.passed, self.failed, self.errors, self.skipped, self.duration_ms)
        if any((not isinstance(value, int) or isinstance(value, bool) or value < 0) for value in values):
            raise ValueError("test evidence values must be non-negative integers")
        if self.passed + self.failed + self.errors + self.skipped == 0:
            raise ValueError("test run cannot be empty")

    @property
    def clean(self) -> bool:
        return self.passed > 0 and self.failed == 0 and self.errors == 0

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


@dataclass(frozen=True)
class CIEvidenceSet:
    commit_sha: str
    stages: tuple[StageEvidence, ...]

    def __post_init__(self) -> None:
        if not _HEX40.fullmatch(self.commit_sha):
            raise ValueError("commit_sha must be a lowercase 40-character hexadecimal Git SHA")
        seen: set[str] = set()
        for stage in self.stages:
            if stage.stage in seen:
                raise ValueError(f"duplicate CI stage evidence: {stage.stage}")
            seen.add(stage.stage)
            if stage.commit_sha != self.commit_sha:
                raise ValueError(f"CI evidence commit mismatch for {stage.stage}")

    def missing_required_stages(self) -> tuple[str, ...]:
        present = {stage.stage for stage in self.stages}
        return tuple(stage for stage in REQUIRED_CI_STAGES if stage not in present)

    def failed_stages(self) -> tuple[str, ...]:
        return tuple(stage.stage for stage in self.stages if stage.status is StageStatus.FAIL)

    def stale_stages(self, *, now: datetime, max_age_hours: int) -> tuple[str, ...]:
        _aware(now, "now")
        if not isinstance(max_age_hours, int) or isinstance(max_age_hours, bool) or max_age_hours <= 0:
            raise ValueError("max_age_hours must be a positive integer")
        stale: list[str] = []
        for stage in self.stages:
            if stage.observed_at > now:
                stale.append(stage.stage)
                continue
            age_hours = (now - stage.observed_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                stale.append(stage.stage)
        return tuple(stale)

    @property
    def fingerprint(self) -> str:
        ordered = tuple(sorted(self.stages, key=lambda stage: stage.stage))
        return canonical_sha256({"commit_sha": self.commit_sha, "stages": ordered})


def evidence_set(commit_sha: str, stages: Iterable[StageEvidence]) -> CIEvidenceSet:
    return CIEvidenceSet(commit_sha=commit_sha, stages=tuple(stages))
