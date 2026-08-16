from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class ApiFootballConfig:
    api_key: str
    base_url: str = "https://v3.football.api-sports.io"
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls) -> "ApiFootballConfig":
        load_dotenv()

        api_key = os.getenv("API_FOOTBALL_KEY", "").strip()

        if not api_key:
            raise ValueError(
                "API_FOOTBALL_KEY no está configurada."
            )

        return cls(api_key=api_key)