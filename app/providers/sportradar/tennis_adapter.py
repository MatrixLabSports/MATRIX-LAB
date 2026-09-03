from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any

_COMPETITION_ID = re.compile(r"^sr:competition:[1-9][0-9]*$")
_CATEGORY_ID = re.compile(r"^sr:category:[1-9][0-9]*$")


@dataclass(frozen=True)
class SportradarTennisCompetition:
    competition_id: str
    name: str
    competition_type: str
    gender: str
    category_id: str
    category_name: str
    provider_key: str = "sportradar"
    sport: str = "tennis"


def adapt_sportradar_tennis_competition(raw: Mapping[str, Any]) -> SportradarTennisCompetition:
    try:
        competition_id = raw["id"]
        name = raw["name"]
        competition_type = raw["type"]
        gender = raw["gender"]
        category = raw["category"]
        category_id = category["id"]
        category_name = category["name"]
    except (KeyError, TypeError) as error:
        raise ValueError("SPORTRADAR_TENNIS_COMPETITION_INCOMPLETE") from error

    values = (competition_id, name, competition_type, gender, category_id, category_name)
    if any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError("SPORTRADAR_TENNIS_COMPETITION_FIELD_INVALID")

    competition_id = competition_id.strip()
    category_id = category_id.strip()
    if not _COMPETITION_ID.fullmatch(competition_id):
        raise ValueError("SPORTRADAR_TENNIS_COMPETITION_ID_INVALID")
    if not _CATEGORY_ID.fullmatch(category_id):
        raise ValueError("SPORTRADAR_TENNIS_CATEGORY_ID_INVALID")

    return SportradarTennisCompetition(
        competition_id=competition_id,
        name=name.strip(),
        competition_type=competition_type.strip(),
        gender=gender.strip(),
        category_id=category_id,
        category_name=category_name.strip(),
    )
