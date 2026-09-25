import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "evidence/world_calendar/MATRIX_WORLD_TENNIS_CALENDAR_R712.json"
ELIGIBLE = ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_ELIGIBLE_CALENDAR_R712.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_r712_world_calendar_and_cor0203_denominators_are_separate():
    world = load(WORLD)
    eligible = load(ELIGIBLE)
    assert world["world_calendar_count"] == 16
    assert eligible["tournament_pool_count"] == 6
    assert world["world_calendar_count"] != eligible["tournament_pool_count"]


def test_r712_cor0203_pool_is_derived_subset_of_world_calendar():
    world = load(WORLD)
    eligible = load(ELIGIBLE)
    world_ids = {row["id"] for row in world["tournaments"]}
    eligible_ids = {row["id"] for row in eligible["tournament_pool"]}
    assert eligible_ids <= world_ids
    flagged = {row["id"] for row in world["tournaments"] if row["cor0203_tournament_eligible"]}
    assert eligible_ids == flagged


def test_r712_clay_and_main_tour_remain_in_world_calendar():
    world = load(WORLD)
    rows = {row["id"]: row for row in world["tournaments"]}
    assert rows["CH-BUENOSAIRES-2026"]["surface"] == "Clay"
    assert rows["CH-BUENOSAIRES-2026"]["cor0203_tournament_eligible"] is False
    assert rows["ATP-CHENGDU-2026"]["category"] == "ATP 250"
    assert rows["ATP-CHENGDU-2026"]["cor0203_tournament_eligible"] is False


def test_r712_new_identity_does_not_inflate_holdout_without_start_authority():
    eligible = load(ELIGIBLE)
    row = next(x for x in eligible["match_projection"] if x.get("event") == "Nishesh Basavareddy vs Andres Andrade")
    assert row["status"] == "IDENTITY_FIXED_START_AUTHORITY_PENDING"
    assert row["features_loaded"] is False
    assert row["preregistered"] is False
    assert eligible["counts"]["new_freezes"] == 0
    assert eligible["counts"]["window1_count"] == 7
    assert eligible["counts"]["total_count"] == 7


def test_r712_metrics_stay_sealed():
    eligible = load(ELIGIBLE)
    assert eligible["protections"]["metrics"] == "SEALED_UNTIL_600"
    assert eligible["protections"]["outcomes_read_for_performance"] == 0
    assert eligible["protections"]["real_money"] == "BLOCKED"
