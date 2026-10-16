from tools.matrix_benter_all_candidate_settlement import settle

def test_settlement_keeps_full_cohort_and_only_final_rows():
    snapshot={
        "target_date_bogota":"2026-10-16",
        "artifact_sha256":"snap",
        "rows":[
            {"fixture_id":"1","model_probability":0.62,"market_probability_devigged_consensus":0.58},
            {"fixture_id":"2","model_probability":0.55,"market_probability_devigged_consensus":0.51},
            {"fixture_id":"3","model_probability":0.49,"market_probability_devigged_consensus":None},
        ],
    }
    provider={"response":[
        {"fixture":{"id":1,"status":{"short":"FT"}},"goals":{"home":2,"away":1}},
        {"fixture":{"id":2,"status":{"short":"NS"}},"goals":{"home":None,"away":None}},
        {"fixture":{"id":3,"status":{"short":"AET"}},"goals":{"home":1,"away":1}},
    ]}
    out=settle(snapshot,provider,raw_sha256="raw")
    assert out["row_count"]==3
    assert out["final_outcome_count"]==2
    assert out["devigged_market_plus_final_count"]==1
    assert out["remaining_to_300_triplets"]==299
    assert out["rows"][0]["outcome_over25"] is True
    assert out["rows"][1]["outcome_over25"] is None
    assert out["rows"][2]["outcome_over25"] is False
    assert out["source_policy"]["operational_priority"]==["SOFASCORE","FLASHSCORE","API_FOOTBALL"]
    assert out["governance"]["fusion_fit_allowed"] is False
    assert out["governance"]["real_money"]=="BLOCKED"

def test_nonfinal_provider_status_never_backfills_outcome():
    snapshot={"target_date_bogota":"2026-10-16","rows":[{"fixture_id":"9","market_probability_devigged_consensus":0.5}]}
    provider={"response":[{"fixture":{"id":9,"status":{"short":"2H"}},"goals":{"home":3,"away":0}}]}
    out=settle(snapshot,provider)
    assert out["final_outcome_count"]==0
    assert out["rows"][0]["outcome_status"]=="PENDING_FINAL_OUTCOME"
