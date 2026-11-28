from tools.tennis_world_coverage_audit import _meta, _rows


def test_rows_requires_list():
    assert _rows({"data": [{"id": 1}]}) == [{"id": 1}]


def test_meta_extracts_tournament_country_rank():
    row = {
        "tournament": {
            "name": "Example Challenger",
            "rankId": 1,
            "country": {"name": "Portugal"},
        }
    }
    assert _meta(row) == ("Example Challenger", "Portugal", "1")
