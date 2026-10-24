from __future__ import annotations

from tools.tennis_dual_lane_event_reconcile import _same_calendar_identity


def test_pair_date_time_can_bind_provider_tournament_label_variants():
    api={
        "tournament_name":"Santa Cruz 2",
        "event_start_bogota":"2026-10-12T16:00:00-05:00",
        "player1":{"name":"B. Munk Mesa"},
        "player2":{"name":"H. Dellien"},
    }
    rapid={
        "tournament_name":"Santa Cruz de la Sierra 2 Challenger",
        "event_start_bogota":"2026-10-12T16:00:00-05:00",
        "player1":{"name":"Bernardo Munk Mesa"},
        "player2":{"name":"Hugo Dellien"},
    }
    ok,delta,basis=_same_calendar_identity(api,rapid)
    assert ok is True
    assert delta==0.0
    assert basis=="PAIR_DATE_TIME_UNIQUE_TOURNAMENT_LABEL_VARIANT"


def test_pair_date_time_rejects_wrong_player_pair():
    api={
        "tournament_name":"Santa Cruz 2",
        "event_start_bogota":"2026-10-12T16:00:00-05:00",
        "player1":{"name":"B. Munk Mesa"},
        "player2":{"name":"H. Dellien"},
    }
    rapid={
        "tournament_name":"Santa Cruz de la Sierra 2 Challenger",
        "event_start_bogota":"2026-10-12T16:00:00-05:00",
        "player1":{"name":"Different Player"},
        "player2":{"name":"Hugo Dellien"},
    }
    ok,delta,basis=_same_calendar_identity(api,rapid)
    assert ok is False
    assert delta==0.0
    assert basis is None
