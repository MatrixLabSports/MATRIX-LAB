from __future__ import annotations

from pathlib import Path

from tools.cor0203_build_static_cut_index import build_static_cut_index


HEADER = (
    "tourney_id,tourney_name,surface,draw_size,tourney_level,indoor,tourney_date,match_num,"
    "winner_id,winner_seed,winner_entry,winner_name,winner_hand,winner_ht,winner_ioc,winner_age,"
    "winner_rank,winner_rank_points,loser_id,loser_seed,loser_entry,loser_name,loser_hand,loser_ht,"
    "loser_ioc,loser_age,loser_rank,loser_rank_points,score,best_of,round,minutes,w_ace,w_df,w_svpt,"
    "w_1stIn,w_1stWon,w_2ndWon,w_SvGms,w_bpSaved,w_bpFaced,l_ace,l_df,l_svpt,l_1stIn,l_1stWon,"
    "l_2ndWon,l_SvGms,l_bpSaved,l_bpFaced\n"
)


def row(date, winner_id="A1", winner_name="Player A", winner_rank="100", winner_points="300",
        loser_id="B1", loser_name="Player B", loser_rank="120", loser_points="250"):
    values = [
        "2026-X","Test","Hard","32","C","O",str(date),"1",
        winner_id,"","","" + winner_name,"R","180","USA","24.5",winner_rank,winner_points,
        loser_id,"","","" + loser_name,"L","185","FRA","25.5",loser_rank,loser_points,
        "6-4 6-4","3","R32","90",
        "1","1","50","30","20","10","10","1","2",
        "1","1","50","30","20","10","10","1","2",
    ]
    return ",".join(values) + "\n"


def test_only_exact_cut_challenger_rows_contribute(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(
        HEADER
        + row(20260920, winner_id="OLD")
        + row(20260921)
        + row(20260922, winner_id="FUTURE"),
        encoding="utf-8",
    )

    result = build_static_cut_index(path)

    assert result["exact_cut_challenger_rows"] == 1
    assert result["players_pass"] == 2
    assert "A1" in result["players"]
    assert "B1" in result["players"]
    assert "OLD" not in result["players"]
    assert "FUTURE" not in result["players"]
    assert result["post_cut_data_used"] is False


def test_exact_cut_static_fields_are_preserved_without_imputation(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(HEADER + row(20260921), encoding="utf-8")

    result = build_static_cut_index(path)
    a = result["players"]["A1"]

    assert a["canonical_name"] == "Player A"
    assert a["hand"] == "R"
    assert a["age"] == 24.5
    assert a["rank"] == 100
    assert a["rank_points"] == 300
    assert a["ioc"] == "USA"
    assert a["observed_exact_cut"] is True
    assert result["silent_imputation"] is False
    assert result["missing_as_zero"] is False


def test_missing_static_field_quarantines_player(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(
        HEADER + row(20260921, winner_rank=""),
        encoding="utf-8",
    )

    result = build_static_cut_index(path)

    assert "A1" not in result["players"]
    assert "B1" in result["players"]
    conflict = next(x for x in result["conflicts"] if x["canonical_source_id"] == "A1")
    assert "rank" in conflict["missing"]


def test_conflicting_exact_cut_values_quarantine_player(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(
        HEADER
        + row(20260921, winner_id="A1", winner_rank="100")
        + row(20260921, winner_id="A1", winner_rank="101", loser_id="C1", loser_name="Player C"),
        encoding="utf-8",
    )

    result = build_static_cut_index(path)

    assert "A1" not in result["players"]
    conflict = next(x for x in result["conflicts"] if x["canonical_source_id"] == "A1")
    assert conflict["signature_count"] == 2
