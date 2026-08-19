from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import re

from app.release.canonical import canonical_sha256

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class SCAFinding:
    advisory_id: str
    package: str
    installed_version: str
    severity: Severity
    fixed_version: str | None = None

    def __post_init__(self) -> None:
        if not self.advisory_id.strip() or not self.package.strip() or not self.installed_version.strip():
            raise ValueError("finding identity is required")
        if self.fixed_version is not None and not self.fixed_version.strip():
            raise ValueError("fixed_version cannot be blank")


@dataclass(frozen=True)
class SCAExecutionEvidence:
    scanner: str
    scanner_version: str
    database_updated_at: datetime
    scanned_at: datetime
    source_commit_sha: str
    dependency_lock_sha256: str
    result_artifact_sha256: str
    exit_code: int
    findings: tuple[SCAFinding, ...]

    def __post_init__(self) -> None:
        if not self.scanner.strip() or not self.scanner_version.strip():
            raise ValueError("scanner identity is required")
        _aware(self.database_updated_at, "database_updated_at")
        _aware(self.scanned_at, "scanned_at")
        if not _HEX40.fullmatch(self.source_commit_sha):
            raise ValueError("source_commit_sha must be Git SHA-1 hex")
        for name in ("dependency_lock_sha256", "result_artifact_sha256"):
            if not _HEX64.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be SHA-256 hex")
        if not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be int")
        keys: set[tuple[str, str]] = set()
        for finding in self.findings:
            key = (finding.advisory_id.casefold(), finding.package.casefold())
            if key in keys:
                raise ValueError("duplicate SCA finding")
            keys.add(key)

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


class SCAStatus(str, Enum):
    PASS = "PASS"
    WATCH = "WATCH"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class SCAContractResult:
    status: SCAStatus
    reasons: tuple[str, ...]


def evaluate_sca_contract(
    evidence: SCAExecutionEvidence,
    *,
    now: datetime,
    expected_commit_sha: str,
    expected_dependency_lock_sha256: str,
    allowed_scanners: tuple[str, ...],
    max_scan_age_hours: int = 24,
    max_database_age_hours: int = 24,
) -> SCAContractResult:
    _aware(now, "now")
    blockers: list[str] = []
    watches: list[str] = []
    if evidence.scanner not in allowed_scanners:
        blockers.append("SCA_SCANNER_NOT_ALLOWED")
    if evidence.source_commit_sha != expected_commit_sha:
        blockers.append("SCA_SOURCE_COMMIT_MISMATCH")
    if evidence.dependency_lock_sha256 != expected_dependency_lock_sha256:
        blockers.append("SCA_DEPENDENCY_LOCK_MISMATCH")
    if evidence.exit_code != 0:
        blockers.append("SCA_SCANNER_NONZERO_EXIT")
    if evidence.scanned_at > now or evidence.database_updated_at > now:
        blockers.append("SCA_FUTURE_TIMESTAMP")
    else:
        if now - evidence.scanned_at > timedelta(hours=max_scan_age_hours):
            blockers.append("SCA_SCAN_STALE")
        if now - evidence.database_updated_at > timedelta(hours=max_database_age_hours):
            blockers.append("SCA_DATABASE_STALE")
    severities = {finding.severity for finding in evidence.findings}
    if Severity.CRITICAL in severities:
        blockers.append("SCA_CRITICAL_VULNERABILITY")
    if Severity.HIGH in severities:
        blockers.append("SCA_HIGH_VULNERABILITY")
    if Severity.MEDIUM in severities:
        watches.append("SCA_MEDIUM_VULNERABILITY_REVIEW")
    reasons = tuple(dict.fromkeys(blockers + watches))
    if blockers:
        return SCAContractResult(SCAStatus.BLOCK, reasons)
    if watches:
        return SCAContractResult(SCAStatus.WATCH, reasons)
    return SCAContractResult(SCAStatus.PASS, ())
