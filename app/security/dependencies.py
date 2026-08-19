from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable

_LOCK_RE = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:([0-9a-f]{64})$")


@dataclass(frozen=True)
class LockedDependency:
    name: str
    version: str
    sha256: str


def parse_locked_dependencies(lines: Iterable[str]) -> tuple[LockedDependency, ...]:
    deps: list[LockedDependency] = []
    names: set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LOCK_RE.fullmatch(line)
        if not match:
            raise ValueError(f"dependency is not exact-version + hash locked: {line}")
        dep = LockedDependency(*match.groups())
        key = dep.name.casefold()
        if key in names:
            raise ValueError(f"duplicate dependency: {dep.name}")
        names.add(key)
        deps.append(dep)
    if not deps:
        raise ValueError("dependency lock cannot be empty")
    return tuple(deps)


@dataclass(frozen=True)
class VulnerabilityScanEvidence:
    scanner: str
    scanner_version: str
    database_updated_at: datetime
    scanned_at: datetime
    critical_count: int
    high_count: int

    def __post_init__(self) -> None:
        if not self.scanner.strip() or not self.scanner_version.strip():
            raise ValueError("scanner identity is required")
        for value in (self.database_updated_at, self.scanned_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timestamps must be timezone-aware")
        if self.critical_count < 0 or self.high_count < 0:
            raise ValueError("vulnerability counts cannot be negative")

    def acceptable(self, *, now: datetime, max_scan_age_hours: float, max_db_age_hours: float) -> bool:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if self.scanned_at > now or self.database_updated_at > now:
            return False
        scan_age = (now - self.scanned_at).total_seconds() / 3600
        db_age = (now - self.database_updated_at).total_seconds() / 3600
        return (
            self.critical_count == 0
            and self.high_count == 0
            and scan_age <= max_scan_age_hours
            and db_age <= max_db_age_hours
        )
