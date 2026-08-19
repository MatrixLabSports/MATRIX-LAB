from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class Threat:
    threat_id: str
    asset: str
    trust_boundary: str
    scenario: str
    severity: Severity
    mitigations: tuple[str, ...]
    residual_risk_accepted: bool = False

    def __post_init__(self) -> None:
        for name in ("threat_id", "asset", "trust_boundary", "scenario"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if len(set(self.mitigations)) != len(self.mitigations):
            raise ValueError("mitigations must be unique")


@dataclass(frozen=True)
class ThreatModelReport:
    blocking_threat_ids: tuple[str, ...]
    review_threat_ids: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.blocking_threat_ids


def evaluate_threats(threats: Iterable[Threat]) -> ThreatModelReport:
    seen: set[str] = set()
    blocking: list[str] = []
    review: list[str] = []
    for threat in threats:
        if threat.threat_id in seen:
            raise ValueError(f"duplicate threat_id: {threat.threat_id}")
        seen.add(threat.threat_id)
        mitigated = bool(threat.mitigations)
        if threat.severity in {Severity.CRITICAL, Severity.HIGH} and not mitigated:
            blocking.append(threat.threat_id)
        elif threat.severity in {Severity.CRITICAL, Severity.HIGH} and threat.residual_risk_accepted:
            review.append(threat.threat_id)
        elif threat.severity == Severity.MEDIUM and not mitigated:
            review.append(threat.threat_id)
    return ThreatModelReport(tuple(blocking), tuple(review))
