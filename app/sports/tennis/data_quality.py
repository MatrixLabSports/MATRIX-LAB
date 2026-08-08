from dataclasses import dataclass


@dataclass
class TennisDataQualityResult:
    passed: bool
    messages: list[str]


class TennisDataQualityEngine:
    """
    Motor especializado en la calidad de datos de MATRIX TENIS.
    """

    ALLOWED_SURFACES = frozenset(
        {
            "hard",
            "clay",
            "grass",
            "carpet",
        }
    )

    def __init__(self):
        self.name = "MATRIX TENNIS DATA QUALITY ENGINE"
        self.version = "0.1"

    def validate_match(self, match: dict) -> TennisDataQualityResult:
        messages = []

        player1 = str(match.get("player1", "")).strip()
        player2 = str(match.get("player2", "")).strip()

        if player1 and player2 and player1.casefold() == player2.casefold():
            messages.append("player1 y player2 no pueden ser iguales.")

        surface = match.get("surface")

        if surface is not None:
             
            if (
                    not isinstance(surface, str)
                    or surface.strip().casefold() not in self.ALLOWED_SURFACES
                ):
                    messages.append("surface contiene un valor no permitido.")

        return TennisDataQualityResult(
            passed=not messages,
            messages=messages,
        )

    