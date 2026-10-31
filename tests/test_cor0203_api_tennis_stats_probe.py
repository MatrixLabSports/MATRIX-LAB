from tools.cor0203_api_tennis_stats_probe import summarize_payload


def test_probe_preserves_only_safe_stat_fields_and_target_ids():
    payload={
        "result":[{
            "event_type_type":"Challenger Men Singles",
            "event_key":"10",
            "event_date":"2026-09-14",
            "event_first_player":"A. Andrade",
            "first_player_key":"111",
            "event_second_player":"Other Player",
            "second_player_key":"222",
            "event_winner":"First Player",
            "event_status":"Finished",
            "tournament_name":"Test Challenger",
            "tournament_key":"55",
            "tournament_round":"Quarter-finals",
            "statistics":[{
                "player_key":"111",
                "stat_period":"match",
                "stat_type":"Service",
                "stat_name":"1st serve points won",
                "stat_value":"64%",
                "stat_won":31,
                "stat_total":48,
                "secret_extra":"must not leak",
            }],
        }]
    }
    out=summarize_payload(payload,label="x")
    assert out["challenger_rows"]==1
    assert out["rows_with_statistics"]==1
    assert out["target_rows"][0]["first_player_key"]=="111"
    stat=out["sample_with_statistics"]["statistics"][0]
    assert stat["stat_won"]==31
    assert stat["stat_total"]==48
    assert "secret_extra" not in stat
