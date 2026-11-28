"""Regression gates: URL integrity is research-only, not production certification."""
import copy
import json
from pathlib import Path

import pytest

from tools.matrix_football_opera_cross_source_guard import check

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence/football_calendar_reconciliation/2026-11-06/MATRIX_OPERA_CROSS_SOURCE_RESEARCH_MATCHES_20261106.json"


def source():
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def test_actual_archived_opera_links_are_research_only():
    result = check(source(), "2026-11-06")
    assert result["source_link_pairs_verified"] == 6
    assert result["production_candidates_authorized"] == 0
    assert result["telegram_signal_authorized"] is False


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(production_candidate_count=1),
    lambda x: x.update(telegram_signal_authorized=True),
    lambda x: x["matches"][0].update(source_event_equivalence_certified=True),
    lambda x: x["matches"][0].update(original_enriched_features_equivalent=True),
    lambda x: x["matches"][0].update(sofascore_event_id="fake"),
    lambda x: x["matches"][0].update(flashscore_url="https://unsafe.example/fixture"),
    lambda x: x["matches"].append(copy.deepcopy(x["matches"][0])),
])
def test_fail_closed_on_fake_admission_or_corrupt_sources(mutation):
    doc = source()
    mutation(doc)
    with pytest.raises(ValueError):
        check(doc, "2026-11-06")
