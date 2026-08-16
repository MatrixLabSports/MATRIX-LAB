from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class ApiFootballHealth:
    available: bool
    daily_limit: int | None
    daily_remaining: int | None


def check_api_football_health(client: Any) -> ApiFootballHealth:
    try:
        client.get("/status")
    except requests.RequestException:
        return ApiFootballHealth(
            available=False,
            daily_limit=client.daily_limit,
            daily_remaining=client.daily_remaining,
        )

    return ApiFootballHealth(
        available=True,
        daily_limit=client.daily_limit,
        daily_remaining=client.daily_remaining,
    )