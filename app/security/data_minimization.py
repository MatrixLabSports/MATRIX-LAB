from __future__ import annotations

from dataclasses import dataclass

from app.release.canonical import canonical_sha256


@dataclass(frozen=True)
class DataFieldUse:
    field_name: str
    purpose: str
    required_for_purpose: bool
    collected: bool

    def __post_init__(self) -> None:
        if not self.field_name.strip() or not self.purpose.strip():
            raise ValueError("field_name and purpose are required")


@dataclass(frozen=True)
class MinimizationReport:
    passed: bool
    unnecessary_fields: tuple[str, ...]
    missing_required_fields: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        return canonical_sha256(self)


def evaluate_minimization(fields: tuple[DataFieldUse, ...]) -> MinimizationReport:
    seen: set[str] = set()
    unnecessary: list[str] = []
    missing: list[str] = []
    for field in fields:
        key = field.field_name.casefold()
        if key in seen:
            raise ValueError(f"duplicate field declaration: {field.field_name}")
        seen.add(key)
        if field.collected and not field.required_for_purpose:
            unnecessary.append(field.field_name)
        if field.required_for_purpose and not field.collected:
            missing.append(field.field_name)
    return MinimizationReport(not unnecessary and not missing, tuple(unnecessary), tuple(missing))
