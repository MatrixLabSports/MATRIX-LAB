"""Regresión: nombres oficiales FC/AFC frente a títulos de evento Betano.

Datos sintéticos derivados de la forma de los títulos observados; no son cuotas.
"""
from tools.matrix_selfhosted_browser_quote_collector import (
    same_team_name, teams_in_betano_title, betano_event_from_payload,
)

def test_betano_title_retains_both_teams_despite_fc_suffix():
    assert teams_in_betano_title(
        "Derby County - Norwich City Fútbol Cuotas | Betano",
        "Derby County FC", "Norwich City FC",
    )
    assert teams_in_betano_title(
        "Birmingham - Millwall FC Fútbol Cuotas | Betano",
        "Birmingham City FC", "Millwall FC",
    ) is False  # City cannot be silently removed.
    assert teams_in_betano_title(
        "Portsmouth - Swansea City Fútbol Cuotas | Betano",
        "Portsmouth FC", "Swansea City AFC",
    )

def test_never_promote_wrong_club_or_one_team():
    assert not teams_in_betano_title(
        "Derby County - Norwich City Fútbol Cuotas | Betano",
        "Derby County FC", "Swansea City AFC",
    )
    assert not same_team_name("Derby County", "Derby City")
    assert not same_team_name("Norwich City FC", "Norwich United FC")
    assert same_team_name("Swansea City AFC", "Swansea City")

def test_structured_event_matches_suffix_only():
    payload={"events":[
      {"id":111,"url":"/sport/futbol/foo/111","participants":[
         {"name":"Derby County"},{"name":"Norwich City"}]}
    ]}
    assert betano_event_from_payload(payload,"Derby County FC","Norwich City FC")["id"] == 111
    assert betano_event_from_payload(payload,"Derby County FC","Norwich United FC") is None
