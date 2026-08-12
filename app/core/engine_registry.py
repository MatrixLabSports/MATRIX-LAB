from app.core.interfaces.sport_engine import SportEngine


class EngineRegistry:
    def __init__(self):
        self._engines: dict[str, SportEngine] = {}

    def register(self, engine: SportEngine) -> None:
        code = engine.sport_code.strip().upper()

        if code in self._engines:
            raise ValueError(f"Engine already registered for sport: {code}")

        self._engines[code] = engine

    def get(self, code: str) -> SportEngine:
        normalized_code = code.strip().upper()

        if normalized_code not in self._engines:
            raise ValueError(
                f"No engine registered for sport: {normalized_code}"
            )

        return self._engines[normalized_code]
