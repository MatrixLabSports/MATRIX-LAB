from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

_COMPETITION_ID = re.compile(r"^sr:competition:[1-9][0-9]*$")
_CATEGORY_ID = re.compile(r"^sr:category:[1-9][0-9]*$")


@dataclass(frozen=True)
class SportradarSoccerCompetition:
    competition_id: str
    name: str
    category_id: str
    category_name: str
    country_code: str | None
    gender: str | None
    provider_key: str = "sportradar"
    sport: str = "football"


def adapt_sportradar_soccer_competition(raw: Mapping[str, Any]) -> SportradarSoccerCompetition:
    try:
        competition_id = raw["id"]
        name = raw["name"]
        category = raw["category"]
        category_id = category["id"]
        category_name = category["name"]
    except (KeyError, TypeError) as error:
        raise ValueError("SPORTRADAR_SOCCER_COMPETITION_INCOMPLETE") from error

    values = (competition_id, name, category_id, category_name)
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("SPORTRADAR_SOCCER_COMPETITION_FIELD_INVALID")

    competition_id = competition_id.strip()
    category_id = category_id.strip()
    if not _COMPETITION_ID.fullmatch(competition_id):
        raise ValueError("SPORTRADAR_SOCCER_COMPETITION_ID_INVALID")
    if not _CATEGORY_ID.fullmatch(category_id):
        raise ValueError("SPORTRADAR_SOCCER_CATEGORY_ID_INVALID")

    country_code = category.get("country_code")
    gender = raw.get("gender")
    if country_code is not None and (not isinstance(country_code, str) or not country_code.strip()):
        raise ValueError("SPORTRADAR_SOCCER_COUNTRY_CODE_INVALID")
    if gender is not None and (not isinstance(gender, str) or not gender.strip()):
        raise ValueError("SPORTRADAR_SOCCER_GENDER_INVALID")

    return SportradarSoccerCompetition(
        competition_id=competition_id,
        name=name.strip(),
        category_id=category_id,
        category_name=category_name.strip(),
        country_code=country_code.strip() if isinstance(country_code, str) else None,
        gender=gender.strip() if isinstance(gender, str) else None,
    )
