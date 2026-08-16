from typing import Any

import requests

from app.providers.api_football.config import ApiFootballConfig


class ApiFootballClient:
    def __init__(
        self,
        config: ApiFootballConfig,
        session: Any | None = None,
    ) -> None:
        self.config = config
        self.session = session or requests.Session()
        self.daily_limit: int | None = None
        self.daily_remaining: int | None = None
        self.minute_limit: int | None = None
        self.minute_remaining: int | None = None

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.get(
            f"{self.config.base_url}{endpoint}",
            headers={
                "x-apisports-key": self.config.api_key,
            },
            params=params,
            timeout=self.config.timeout_seconds,
        )

        response.raise_for_status()

        self.daily_limit = self._parse_int_header(
            response.headers,
            "x-ratelimit-requests-limit",
        )
        self.daily_remaining = self._parse_int_header(
            response.headers,
            "x-ratelimit-requests-remaining",
        )
        self.minute_limit = self._parse_int_header(
            response.headers,
            "X-RateLimit-Limit",
        )
        self.minute_remaining = self._parse_int_header(
            response.headers,
            "X-RateLimit-Remaining",
        )

        return response.json()

    @staticmethod
    def _parse_int_header(
        headers: Any,
        name: str,
    ) -> int | None:
        value = headers.get(name)

        if value is None:
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None
