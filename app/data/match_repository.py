import json
from pathlib import Path
from typing import Any


class MatchRepository:
    REQUIRED_FIELDS = {
        "player1",
        "player2",
        "tournament",
        "tour",
        "surface",
        "round",
        "datetime",
        "status",
    }

    def __init__(self, file_path: str = "app/data/daily_matches.json") -> None:
        self.file_path = Path(file_path)

    def load_matches(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo: {self.file_path}"
            )

        try:
            with self.file_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"El archivo JSON tiene un error en la línea "
                f"{error.lineno}, columna {error.colno}."
            ) from error

        if not isinstance(data, list):
            raise ValueError(
                "El calendario debe contener una lista de partidos."
            )

        valid_matches: list[dict[str, Any]] = []

        for position, match in enumerate(data, start=1):
            self._validate_match(match, position)
            valid_matches.append(match)

        return valid_matches

    def _validate_match(
        self,
        match: Any,
        position: int,
    ) -> None:
        if not isinstance(match, dict):
            raise ValueError(
                f"El partido {position} no tiene un formato válido."
            )

        missing_fields = self.REQUIRED_FIELDS - match.keys()

        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(
                f"Al partido {position} le faltan estos campos: {missing}"
            )

        for field in self.REQUIRED_FIELDS:
            value = match[field]

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"El campo '{field}' del partido {position} "
                    "debe contener texto."
                )


if __name__ == "__main__":
    repository = MatchRepository()

    try:
        matches = repository.load_matches()

        print("=" * 45)
        print("MATCH REPOSITORY - MATRIX")
        print("=" * 45)
        print(f"Partidos válidos encontrados: {len(matches)}")

        for index, match in enumerate(matches, start=1):
            print(
                f"{index}. {match['player1']} vs "
                f"{match['player2']} - {match['tournament']}"
            )

        print("\nValidación completada correctamente.")

    except (FileNotFoundError, ValueError) as error:
        print(f"\nERROR DE DATOS: {error}")