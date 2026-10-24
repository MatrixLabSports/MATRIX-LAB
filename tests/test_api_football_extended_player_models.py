import json

from tools.api_football_extended_player_models import _internal_split, _lambda, build_lane


def _row(i, split):
    return {
        "fixture_id":str(i),
        "split":split,
        "target_count":float(i%4),
        "prior_mean_count":1.4,
        "last5_mean_count":1.6,
        "prior_mean_minutes":72.0,
        "last5_mean_minutes":75.0,
    }


def test_lambda_uses_only_prior_features():
    row=_row(1,"TRAIN")
    value=_lambda(row,0.5,0.5)
    assert value>0
    assert "current_match_minutes_postsettlement_audit_only" not in row


def test_internal_split_is_temporal_prefix():
    rows=[_row(i,"TRAIN") for i in range(300)]
    train,val=_internal_split(rows)
    assert train==rows[:len(train)]
    assert val==rows[len(train):]
    assert not ({r["fixture_id"] for r in train} & {r["fixture_id"] for r in val})


def test_final_validation_is_never_used_for_selection(tmp_path):
    path=tmp_path/"player.jsonl"
    rows=[_row(i,"TRAIN" if i<250 else "VALIDATION") for i in range(300)]
    path.write_text("".join(json.dumps(r)+"\n" for r in rows),encoding="utf-8")
    result=build_lane("PLAYER_SHOTS",path)
    assert result["train_count"]==250
    assert result["validation_count"]==50
    assert result["validation_used_for_parameter_tuning"] is False
    assert result["internal_selection"]["final_validation_used_for_selection"] is False
    assert result["prospective_freeze_allowed"] is False
    assert result["current_match_minutes_used_as_feature"] is False
