from __future__ import annotations

from app.core.coverage_gap_prioritizer import rank_gap_candidates


def prioritize_tennis_coverage_gaps(*, candidates):
    return rank_gap_candidates(
        sport="tennis",
        candidates=candidates,
    )
