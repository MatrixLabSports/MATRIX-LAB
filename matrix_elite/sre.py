from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ContinuityEvidence:
    backup_created: bool
    restore_tested: bool
    recovery_time_seconds: float | None
    recovery_point_seconds: float | None
    load_tested: bool
    chaos_tested: bool
    alerting_tested: bool


def production_continuity_gate(e: ContinuityEvidence, *, max_rto_s: float, max_rpo_s: float) -> bool:
    if not all((e.backup_created,e.restore_tested,e.load_tested,e.chaos_tested,e.alerting_tested)):
        return False
    if e.recovery_time_seconds is None or e.recovery_point_seconds is None:
        return False
    return e.recovery_time_seconds <= max_rto_s and e.recovery_point_seconds <= max_rpo_s
