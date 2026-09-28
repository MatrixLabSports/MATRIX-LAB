import pytest

from tools.cor0203_rapidapi_profile_identity import _sanitize_profile


def test_profile_identity_keeps_biography_and_discards_competitive_fields():
    payload={
        "data":{
            "id":92649,
            "name":"Tiago Pereira",
            "birthday":"2004-06-21",
            "countryAcr":"POR",
            "currentRank":332,
            "points":161,
            "information":{"plays":"Right-handed"},
        }
    }
    row=_sanitize_profile("92649","Tiago Pereira",payload)
    assert row["numeric_player_id"]=="92649"
    assert row["birthday"]=="2004-06-21"
    assert row["country_acr"]=="POR"
    assert "currentRank" in row["competitive_fields_discarded"]
    assert "points" in row["competitive_fields_discarded"]
    assert "currentRank" not in row
    assert "points" not in row


def test_profile_identity_rejects_wrong_numeric_id():
    with pytest.raises(ValueError,match="PROFILE_ID_MISMATCH"):
        _sanitize_profile("92649","Tiago Pereira",{"data":{"id":123,"name":"Tiago Pereira"}})
