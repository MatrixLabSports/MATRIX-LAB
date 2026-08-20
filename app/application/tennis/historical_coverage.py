from __future__ import annotations

from app.core.historical_coverage import build_coverage_ledger


def build_tennis_coverage_ledger(
    *,
    player_key: str,
    observations,
):
    return build_coverage_ledger(
        sport="tennis",
        subject_key=player_key,
        observations=observations,
    )
