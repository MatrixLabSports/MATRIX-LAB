from dataclasses import dataclass


@dataclass(frozen=True)
class TennisDataCoverage:
    recent_form: bool
    surface_history: bool
    serve_stats: bool
    return_stats: bool
    fatigue_context: bool
    market_data: bool

    def __post_init__(self):
        values = (
            self.recent_form,
            self.surface_history,
            self.serve_stats,
            self.return_stats,
            self.fatigue_context,
            self.market_data,
        )

        if not all(type(value) is bool for value in values):
            raise TypeError("Todas las evidencias deben ser booleanas.")

    def score(self) -> float:
        available = sum(
            [
                self.recent_form,
                self.surface_history,
                self.serve_stats,
                self.return_stats,
                self.fatigue_context,
                self.market_data,
            ]
        )

        return available / 6