from dataclasses import dataclass


@dataclass
class DataQualityResult:
    passed: bool
    score: int
    status: str
    messages: list[str]


class MatrixDataQualityEngine:
    """
    Motor encargado de validar la calidad básica de los datos
    antes de que sean procesados por MATRIX.
    """

    def __init__(self):
        self.name = "MATRIX DATA QUALITY ENGINE"
        self.version = "0.2"

    def _validate_players(self, match: dict) -> list[str]:
        """
        Valida que los jugadores existan, tengan nombres válidos
        y no representen a la misma persona.
        """

        messages = []

        player1_raw = match.get("player1")
        player2_raw = match.get("player2")

        if not isinstance(player1_raw, str):
            messages.append("player1 debe ser un texto válido.")
            player1 = ""
        else:
            player1 = player1_raw.strip()

        if not isinstance(player2_raw, str):
            messages.append("player2 debe ser un texto válido.")
            player2 = ""
        else:
            player2 = player2_raw.strip()

        if len(player1) < 2:
            messages.append(
                "player1 debe contener al menos 2 caracteres."
            )

        if len(player2) < 2:
            messages.append(
                "player2 debe contener al menos 2 caracteres."
            )

        if (
            player1
            and player2
            and player1.casefold() == player2.casefold()
        ):
            messages.append(
                "player1 y player2 no pueden ser iguales."
            )

        return messages

    def _validate_catalogs(self, match: dict) -> list[str]:
            """
            Valida que superficie, estado y ronda pertenezcan
            a los catálogos permitidos por MATRIX.
            """

            messages = []

            allowed_surfaces = {
                "hard",
                "clay",
                "grass",
                "carpet",
            }

            allowed_statuses = {
                "scheduled",
                "live",
                "finished",
                "retired",
                "walkover",
                "cancelled",
            }

            allowed_rounds = {
                "Q1",
                "Q2",
                "Q3",
                "R128",
                "R64",
                "R32",
                "R16",
                "QF",
                "SF",
                "F",
            }

            surface = match.get("surface")
            status = match.get("status")
            round_name = match.get("round")

            if isinstance(surface, str):
                if surface.strip().casefold() not in allowed_surfaces:
                    messages.append("surface contiene un valor no permitido.")
            else:
                messages.append("surface debe ser un texto válido.")

            if isinstance(status, str):
                if status.strip().casefold() not in allowed_statuses:
                    messages.append("status contiene un valor no permitido.")
            else:
                messages.append("status debe ser un texto válido.")

            if isinstance(round_name, str):
                if round_name.strip().upper() not in allowed_rounds:
                    messages.append("round contiene un valor no permitido.")
            else:
                messages.append("round debe ser un texto válido.")

            return messages

    def validate_core_record(self, match: dict) -> DataQualityResult:
        """
        Valida únicamente requisitos transversales necesarios
        antes de delegar el registro al motor deportivo.
        """
        messages: list[str] = []

        if not isinstance(match, dict):
            return DataQualityResult(
                passed=False,
                score=0,
                status="BLOQUEADO",
                messages=["El registro debe ser un diccionario."],
            )

        sport = match.get("sport")

        if not isinstance(sport, str) or not sport.strip():
            messages.append("Falta un sport válido.")

        if messages:
            return DataQualityResult(
                passed=False,
                score=0,
                status="BLOQUEADO",
                messages=messages,
            )

        return DataQualityResult(
            passed=True,
            score=1,
            status="APROBADO",
            messages=["Calidad transversal aceptable."],
        )

    def validate_match(self, match: dict) -> DataQualityResult:
        """
        Valida que el partido contenga los campos mínimos requeridos.
        """

        messages = []
        score = 0

        required_fields = [
            "player1",
            "player2",
            "tournament",
            "tour",
            "surface",
            "round",
            "datetime",
            "status",
        ]

        for field in required_fields:
            if field in match and str(match[field]).strip() != "":
                score += 1
            else:
                messages.append(f"Falta el campo: {field}")

        player_messages = self._validate_players(match)
        messages.extend(player_messages)

        catalog_messages = self._validate_catalogs(match)
        messages.extend(catalog_messages)

        if (
            score == len(required_fields)
            and not player_messages
            and not catalog_messages
        ):
            status = "APROBADO"
            passed = True

        elif (
            score >= 6
            and not player_messages
            and not catalog_messages
        ):
            status = "REVISAR"
            passed = True

        else:
            status = "BLOQUEADO"
            passed = False

        if passed:
            messages.append("Calidad de datos aceptable.")

        return DataQualityResult(
            passed=passed,
            score=score,
            status=status,
            messages=messages,
        )


if __name__ == "__main__":
    prueba = {
        "player1": "Michael Zheng",
        "player2": "Miomir Kecmanovic",
        "tournament": "Montreal",
        "tour": "ATP",
        "surface": "Hard",
        "round": "R128",
        "datetime": "2026-08-03",
        "status": "scheduled",
    }

    engine = MatrixDataQualityEngine()
    result = engine.validate_match(prueba)

    print("=" * 45)
    print(engine.name)
    print("=" * 45)
    print("Estado:", result.status)
    print("Puntuación:", result.score, "/8")

    for message in result.messages:
        print("-", message)