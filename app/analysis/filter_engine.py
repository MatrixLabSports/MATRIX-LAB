from dataclasses import dataclass
from typing import Any

from app.data.match_repository import MatchRepository


@dataclass
class FilterResult:
    player1: str
    player2: str
    tournament: str
    status: str
    score: int
    reasons: list[str]


class MatrixFilterEngine:
    def __init__(self) -> None:
        self.name = "MATRIX FILTER ENGINE"
        self.version = "0.1"

    def evaluate_match(self, match: dict[str, Any]) -> FilterResult:
        score = 0
        reasons: list[str] = []

        if match["status"].lower() == "scheduled":
            score += 2
            reasons.append("Partido programado correctamente.")
        else:
            reasons.append("El partido no está programado.")

        if match["tour"].upper() in {"ATP", "WTA"}:
            score += 2
            reasons.append("Circuito principal con mejor calidad de datos.")
        else:
            score += 1
            reasons.append("Circuito secundario: requiere más validación.")

        if match["surface"].lower() in {"hard", "clay", "grass"}:
            score += 2
            reasons.append("Superficie reconocida.")
        else:
            reasons.append("Superficie no reconocida.")

        if match["round"].strip():
            score += 1
            reasons.append("Ronda identificada.")

        if score >= 7:
            decision = "APROBADO"
        elif score >= 5:
            decision = "EN VIGILANCIA"
        else:
            decision = "DESCARTADO"

        return FilterResult(
            player1=match["player1"],
            player2=match["player2"],
            tournament=match["tournament"],
            status=decision,
            score=score,
            reasons=reasons,
        )

    def evaluate_all(
        self,
        matches: list[dict[str, Any]],
    ) -> list[FilterResult]:
        return [self.evaluate_match(match) for match in matches]

    def print_results(self, results: list[FilterResult]) -> None:
        print("=" * 50)
        print(f"{self.name} - VERSION {self.version}")
        print("=" * 50)

        for index, result in enumerate(results, start=1):
            print(f"\nPARTIDO {index}")
            print(f"{result.player1} vs {result.player2}")
            print(f"Torneo: {result.tournament}")
            print(f"Clasificación: {result.status}")
            print(f"Puntuación inicial: {result.score}/7")
            print("Razones:")

            for reason in result.reasons:
                print(f"- {reason}")

        print("\nEvaluación finalizada.")


if __name__ == "__main__":
    repository = MatchRepository()
    engine = MatrixFilterEngine()

    try:
        daily_matches = repository.load_matches()
        filter_results = engine.evaluate_all(daily_matches)
        engine.print_results(filter_results)

    except (FileNotFoundError, ValueError) as error:
        print(f"\nERROR DE MATRIX: {error}")