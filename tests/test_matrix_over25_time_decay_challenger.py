from pathlib import Path
from tools.matrix_over25_time_decay_challenger import _wmean

def test_weighted_mean_prefers_recent_when_weights_higher():
    assert _wmean([(1.0,1.0),(3.0,3.0)]) == 2.5

def test_time_decay_challenger_governance_contract_source():
    text=Path("tools/matrix_over25_time_decay_challenger.py").read_text()
    assert '"research_only":True' in text
    assert '"production_engine_modified":False' in text
    assert '"holdout_used_for_parameter_selection":False' in text
    assert '"odds_used_to_generate_probability":False' in text
    assert '"real_money":"BLOCKED"' in text
