"""Contract tests: original archived result history is preserved but never promoted."""
import json
from pathlib import Path
import pytest
from tools.matrix_original_six_last_good_history_audit import inspect,INVENTORY,SCOPE

def setup(tmp_path):
    groups=[]
    for lid in SCOPE:
        path=f"evidence/api_football/prospective_daily/2026-10-28/20261028T054128Z/history/raw/league_{lid}_season_2026.bin"
        group={"parameters":{"league":str(lid),"season":"2026"},
          "response":[{"league":{"id":lid,"season":2026},
             "fixture":{"id":lid*100,"date":"2026-10-27T20:00:00+00:00","status":{"short":"FT"}},
             "teams":{"home":{"id":1},"away":{"id":2}},
             "goals":{"home":2,"away":1}}]}
        target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(group))
        groups.append({"original_league_id":lid,"archive_files":[path]})
    p=tmp_path/INVENTORY;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps({"reference_groups":groups}))
    return tmp_path

def test_original_all_six_are_historic_only(tmp_path):
    setup(tmp_path)
    doc=inspect(tmp_path)
    assert doc["six_league_archived_finished_total"]==6
    assert doc["original_six_league_ids"]==[str(x) for x in SCOPE]
    assert doc["leagues"][-1]["original_league_id"]=="239"
    assert doc["leagues"][-1]["strictly_prior_finished_usable_goals_count"]==1
    assert doc["canonical_p_matrix_authorized"] is False
    assert doc["telegram_signal_authorized"] is False

def test_fixture_after_archive_capture_rejected(tmp_path):
    setup(tmp_path)
    path=tmp_path/INVENTORY
    source=tmp_path/json.loads(path.read_text())["reference_groups"][-1]["archive_files"][0]
    data=json.loads(source.read_text())
    data["response"][0]["fixture"]["date"]="2026-10-28T06:00:00Z"
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="ORIGINAL_FINISHED_FIXTURE_NOT_PIT"):
        inspect(tmp_path)

def test_source_header_league_swap_rejected(tmp_path):
    setup(tmp_path)
    p=tmp_path/json.loads((tmp_path/INVENTORY).read_text())["reference_groups"][-1]["archive_files"][0]
    data=json.loads(p.read_text());data["parameters"]["league"]="39"
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="ORIGINAL_ARCHIVE_HEADER_MISMATCH"):
        inspect(tmp_path)

def test_missing_original_colombia_archive_rejected(tmp_path):
    setup(tmp_path)
    p=tmp_path/INVENTORY;j=json.loads(p.read_text())
    j["reference_groups"]=[x for x in j["reference_groups"] if x["original_league_id"]!=239]
    p.write_text(json.dumps(j))
    with pytest.raises(ValueError,match="MISSING_OR_AMBIGUOUS_ORIGINAL_LEAGUE_ARCHIVES"):
        inspect(tmp_path)
