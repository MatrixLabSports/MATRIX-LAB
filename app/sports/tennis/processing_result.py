from dataclasses import dataclass


@dataclass(frozen=True)
class TennisProcessingResult:
    accepted: bool
    reason: str