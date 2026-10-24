from datetime import datetime, timezone

from tools.matrix_42_lane_football_freeze_bridge import build_rows


def _source():
    return {
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_MARKET_FREEZE_V1",
        "frozen_event_count":1,
        "protections":{
            "future_only":True,
            "freeze_strictly_before_kickoff":True,
            "missing_feature_imputation":False,
            "outcomes_read_at_freeze":False,
            "odds_used_to_generate_probability":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "rows":[{
            "fixture_id":"7",
            "kickoff_utc":"2026-10-25T18:00:00+00:00",
            "freeze_at_utc":"2026-10-24T18:00:00+00:00",
            "frozen_research_probabilities":{
                "1x2":{"H":0.5,"D":0.25,"A":0.25},
                "over_2_5":0.6,
            },
            "outcome":None,
            "settlement_status":"PENDING_FINAL",
        }],
    }


def test_bridge_emits_five_governed_lanes():
    rows,audit=build_rows(
        _source(),
        now_utc=datetime(2026,10,24,20,0,tzinfo=timezone.utc),
        existing_keys=set(),
    )
    assert len(rows)==5
    assert {x["market_lane"] for x in rows}=={
        "MATCH_RESULT_1X2","DOUBLE_CHANCE_1X","DOUBLE_CHANCE_X2","DOUBLE_CHANCE_12","TOTAL_GOALS_OVER_UNDER"
    }
    one={x["market_lane"]:x for x in rows}
    assert one["DOUBLE_CHANCE_1X"]["prediction"]["1X"]==0.75
    assert one["DOUBLE_CHANCE_X2"]["prediction"]["X2"]==0.5
    assert one["DOUBLE_CHANCE_12"]["prediction"]["12"]==0.75
    assert all(x["prospective_admitted"] is True for x in rows)
    assert all(x["counts_toward_100_300_600"] is True for x in rows)
    assert audit["protections"]["outcomes_read"]==0


def test_bridge_rejects_post_start_and_dedups():
    source=_source()
    source["rows"].append({
        **source["rows"][0],
        "fixture_id":"8",
        "kickoff_utc":"2026-10-24T19:00:00+00:00",
        "freeze_at_utc":"2026-10-24T19:01:00+00:00",
    })
    rows,audit=build_rows(
        source,
        now_utc=datetime(2026,10,24,18,30,tzinfo=timezone.utc),
        existing_keys={"football|MATCH_RESULT_1X2|fixture:7|freeze:2026-10-24T18:00:00+00:00"},
    )
    assert len(rows)==4
    assert audit["blocked_count"]==1
    assert audit["blocked"][0]["reason"]=="SOURCE_FREEZE_NOT_PREMATCH"
