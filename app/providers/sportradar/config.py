from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from urllib.parse import urlsplit


_TENNIS_LANGUAGE_CODES = frozenset({
    "de", "en", "en_us", "es", "fr", "id", "it", "ja",
    "ru", "th", "zh", "zht",
})

_SOCCER_LANGUAGE_CODES = frozenset({
    "da", "de", "el", "en", "es", "fi", "fr", "id", "it",
    "ja", "nl", "pt", "ru", "sr", "sr1", "th", "tr", "zh", "zht",
})

_ALL_LANGUAGE_CODES = _TENNIS_LANGUAGE_CODES | _SOCCER_LANGUAGE_CODES


@dataclass(frozen=True)
class SportradarConfig:
    base_url: str = "https://api.sportradar.com"
    access_level: str = "trial"
    language_code: str = "en"
    tennis_version: str = "v3"
    soccer_version: str = "v4"
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.base_url, str):
            raise ValueError("INVALID_SPORTRADAR_BASE_URL")
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
        except (TypeError, ValueError) as error:
            raise ValueError("INVALID_SPORTRADAR_BASE_URL") from error
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.sportradar.com"
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("INVALID_SPORTRADAR_BASE_URL")
        if self.access_level not in {"trial", "production"}:
            raise ValueError("INVALID_SPORTRADAR_ACCESS_LEVEL")
        if self.language_code not in _ALL_LANGUAGE_CODES:
            raise ValueError("INVALID_SPORTRADAR_LANGUAGE_CODE")
        if self.tennis_version != "v3":
            raise ValueError("UNSUPPORTED_SPORTRADAR_TENNIS_VERSION")
        if self.soccer_version != "v4":
            raise ValueError("UNSUPPORTED_SPORTRADAR_SOCCER_VERSION")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, Real)
            or not math.isfinite(float(self.timeout_seconds))
            or self.timeout_seconds <= 0
            or self.timeout_seconds > 30
        ):
            raise ValueError("INVALID_SPORTRADAR_TIMEOUT")

    def _language_for_sport(self, sport: str) -> str:
        if sport == "tennis":
            allowed = _TENNIS_LANGUAGE_CODES
        elif sport == "football":
            allowed = _SOCCER_LANGUAGE_CODES
        else:
            raise ValueError("INVALID_SPORTRADAR_SPORT")
        if self.language_code not in allowed:
            raise ValueError("UNSUPPORTED_SPORTRADAR_LANGUAGE_FOR_SPORT")
        return self.language_code

    def static_path(self, *, sport: str, feed: str) -> str:
        language_code = self._language_for_sport(sport)
        if sport == "tennis":
            version = self.tennis_version
            prefix = "tennis"
        elif sport == "football":
            version = self.soccer_version
            prefix = "soccer"
        else:
            raise ValueError("INVALID_SPORTRADAR_SPORT")
        if feed not in {"competitions", "seasons", "live_schedule"}:
            raise ValueError("UNSUPPORTED_SPORTRADAR_STATIC_FEED")
        if feed == "competitions":
            suffix = "competitions.json"
        elif feed == "seasons":
            suffix = "seasons.json"
        elif sport == "tennis":
            suffix = "schedules/live/summaries.json"
        else:
            suffix = "schedules/live/schedules.json"
        return (
            f"/{prefix}/{self.access_level}/{version}/"
            f"{language_code}/{suffix}"
        )
