from tools.cor0203_merge_prereg_results import merge_prereg_results


def test_merge_counts_both_sources():
    rapid={"status":"PREREGISTERED","events_registered":2,"event_ids":["R1","R2"],"revision":10,"path":"r10.json","starting_observation_count":85,"skipped":[]}
    api={"status":"PREREGISTERED","events_registered":1,"event_ids":["A1"],"revision":11,"path":"r11.json","starting_observation_count":85,"skipped":[]}
    out=merge_prereg_results(rapid,api)
    assert out["status"]=="PREREGISTERED"
    assert out["events_registered"]==3
    assert out["event_ids"]==["R1","R2","A1"]
    assert len(out["revisions"])==2
    assert out["real_money"]=="BLOCKED"


def test_merge_no_new_events():
    out=merge_prereg_results(
        {"status":"NO_NEW_EVENTS","events_registered":0,"skipped":[]},
        {"status":"NO_NEW_EVENTS","events_registered":0,"skipped":[]},
    )
    assert out["status"]=="NO_NEW_EVENTS"
    assert out["events_registered"]==0
