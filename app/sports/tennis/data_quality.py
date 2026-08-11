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
        if not isinstance(match, dict):
            raise TypeError("match must be a dictionary")

        messages = []

        player1_value = match.get("player1", "")
        player2_value = match.get("player2", "")

        if not isinstance(player1_value, str):
            raise TypeError("player1 must be a string")

        if not isinstance(player2_value, str):
            raise TypeError("player2 must be a string")

        player1 = player1_value.strip()
        player2 = player2_value.strip()

        if not player1:
            messages.append("player1 es obligatorio.")

        if not player2:
            messages.append("player2 es obligatorio.")

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
