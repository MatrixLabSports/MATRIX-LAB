"""Six original league boundary cannot be inflated by unrelated league outcomes."""
import json
from pathlib import Path
import pytest
from tools.matrix_original_six_league_coverage import audit,REGISTRY,SCORECARD

def setup(tmp_path):
    registry={"schema":"MATRIX_ORIGINAL_SIX_LEAGUE_COHORT_REGISTRY_V1",
      "scope_approved":True,"original_six_league_ids":["39","61","78","135","140","239"],
      "leagues":[{"id":i,"name":i} for i in ["39","61","78","135","140","239"]]}
    score={"schema":"MATRIX_INDEPENDENT_OVER25_RESEARCH_SCORECARD_V1",
      "provider":"FOOTBALL_DATA_ORG","production_p_matrix_authorized":False,
      "telegram_signal_authorized":False,"real_money":"BLOCKED",
      "total_verified_settled_rows":122,
      "provider_competitions":[{"source_competition_id":k,"independent_out_of_sample_rows":v}
        for k,v in {"2002":9,"2003":9,"2013":9,"2014":16,"2015":17,
                    "2016":25,"2019":18,"2021":19}.items()]}
    for path,obj in ((REGISTRY,registry),(SCORECARD,score)):
        dest=tmp_path/path;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(obj),encoding="utf-8")
    return tmp_path/SCORECARD

def test_only_five_original_european_leagues_can_count(tmp_path):
    setup(tmp_path)
    row=audit(tmp_path)
    assert row["original_scope_corresponding_five_league_settlements"]==79
    assert row["out_of_original_scope_research_settlements"]==43
    assert row["free_source_uncovered_original_leagues"]==["239"]
    assert len(row["original_six_leagues"])==6
    assert row["production_p_matrix_authorized"] is False
    assert row["telegram_signal_authorized"] is False
    assert not row["match_level_crosswalk_verified"]

def test_championship_not_english_premier_league(tmp_path):
    setup(tmp_path)
    row=audit(tmp_path)
    epl=next(x for x in row["original_six_leagues"] if x["original_league_id"]=="39")
    assert epl["free_provider_competition_id"]=="2021"
    assert epl["independent_verified_settled_rows"]==19
    colombia=next(x for x in row["original_six_leagues"] if x["original_league_id"]=="239")
    assert colombia["free_source_coverage_missing"] is True
    assert colombia["independent_verified_settled_rows"]==0

def test_duplicate_or_inconsistent_settlements_fail_closed(tmp_path):
    path=setup(tmp_path)
    row=json.loads(path.read_text())
    row["provider_competitions"].append(dict(row["provider_competitions"][0]))
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError,match="DUPLICATE_OR_INVALID"):
        audit(tmp_path)

def test_untrusted_six_league_registry_never_passes(tmp_path):
    setup(tmp_path)
    path=tmp_path/REGISTRY
    row=json.loads(path.read_text())
    row["original_six_league_ids"].remove("239")
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError,match="SIX_LEAGUE_SOURCE_OR_GOVERNANCE_INVALID"):
        audit(tmp_path)
