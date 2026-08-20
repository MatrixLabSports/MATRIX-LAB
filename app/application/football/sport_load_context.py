from app.core.sport_load_context import build_sport_load_context


def build_football_load_context(**kwargs):
    return build_sport_load_context(
        sport="football",
        **kwargs,
    )
