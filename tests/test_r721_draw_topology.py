import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPO = ROOT / "evidence/cor0203/runtime/MATRIX_COR0203_DRAW_TOPOLOGY_R721.json"


def load():
    return json.loads(TOPO.read_text(encoding="utf-8"))


def test_r721_san_diego_topology_is_explicit():
    x = load()
    assert x["round_mapping"]["QF1"] == "Nishesh Basavareddy vs Andres Andrade"
    assert x["round_mapping"]["QF2"] == "Dylan Dietrich vs Henry Searle"
    assert x["round_mapping"]["QF3"] == "Tristan Boyer vs Timo Legout"
    assert x["round_mapping"]["QF4"] == "Igor Marcondes vs Federico Agustin Gomez"
    assert x["semifinal_mapping"]["SF1"] == "WINNER_QF1 vs WINNER_QF2"
    assert x["semifinal_mapping"]["SF2"] == "WINNER_QF3 vs WINNER_QF4"


def test_r721_partial_identity_cannot_be_preregistered():
    x = load()
    assert x["fixed_progression"]["QF4_winner"] == "Igor Marcondes"
    assert x["fixed_progression"]["SF2_partial"] == "WINNER_TRISTAN_BOYER_TIMO_LEGOUT vs Igor Marcondes"
    assert x["governance"]["placeholder_is_not_identity"] is True
    assert x["governance"]["preregistration_requires_two_real_players"] is True
    assert x["governance"]["live_result_not_model_feature"] is True
    assert x["governance"]["same_period_result_for_identity_only"] is True
