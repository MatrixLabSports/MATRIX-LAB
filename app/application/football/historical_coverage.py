from __future__ import annotations

from app.core.historical_coverage import build_coverage_ledger


def build_football_coverage_ledger(
    *,
    team_key: str,
    observations,
):
    return build_coverage_ledger(
        sport="football",
        subject_key=team_key,
        observations=observations,
    )
