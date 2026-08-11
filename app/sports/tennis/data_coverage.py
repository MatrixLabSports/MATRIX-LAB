from dataclasses import dataclass, fields

@dataclass(frozen=True)
class TennisDataCoverage:
    recent_form: bool
    surface_history: bool
    serve_stats: bool
    return_stats: bool
    fatigue_context: bool
    market_data: bool
    def _evidence_values(self) -> tuple[bool, ...]:
        return tuple(getattr(self, field.name) for field in fields(self))

    def __post_init__(self):
        values = self._evidence_values()

        if not all(type(value) is bool for value in values):
            raise TypeError("Todas las evidencias deben ser booleanas.")

    def score(self) -> float:
        values = self._evidence_values()
        return sum(values) / len(values)