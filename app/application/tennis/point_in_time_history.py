from app.core.point_in_time_history import (
    build_point_in_time_history,
)
from app.core.sport_history_event_contract import (
    tennis_history_event_from_observation,
)


DEFAULT_TENNIS_HISTORY_SCHEMA = (
    "tennis.player.match_history"
)


def build_tennis_point_in_time_history(
    *,
    observation_store,
    canonical_id,
    as_of,
    season_key,
    schema_name=DEFAULT_TENNIS_HISTORY_SCHEMA,
    windows=(5, 10, 20, 30, 50),
):
    observations = observation_store.list_as_of(
        sport="tennis",
        canonical_id=canonical_id,
        schema_name=schema_name,
        as_of=as_of,
    )

    events = tuple(
        tennis_history_event_from_observation(
            observation
        )
        for observation in observations
    )

    return build_point_in_time_history(
        sport="tennis",
        canonical_id=canonical_id,
        events=events,
        as_of=as_of,
        season_key=season_key,
        windows=windows,
    )
