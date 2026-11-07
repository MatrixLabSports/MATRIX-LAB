from tools.matrix_football_oos_4001_5000_refresh import build

def row(i):
    return {
      "fixture_id":str(i),
      "source_terminal_status":"FT",
      "used_for_parameter_tuning":False,
      "parameters_mutated_after_freeze":False,
    }

def checkpoint():
    return {
      "checkpoint_sha256":"x",
      "source":{
        "first_fixture_id":"1",
        "last_fixture_id":"4000",
        "unique_fixture_ids":4000,
      }
    }

def test_refresh_counts_real_rows_after_fixed_4000_prefix():
    rows=[row(i) for i in range(1,4797)]
    out=build(rows,checkpoint())
    assert out["current_source_rows"]==4796
    assert out["current_oos_observations"]==796
    assert out["remaining_to_1000"]==204
    assert out["status"]=="ACTIVE_SEALED_PENDING"
    assert out["metrics_opened"] is False
    assert out["frozen_policy"]["parameter_tuning_allowed"] is False
    assert out["frozen_policy"]["real_money"]=="BLOCKED"

def test_refresh_closes_at_exact_1000_without_auto_promotion():
    rows=[row(i) for i in range(1,5001)]
    out=build(rows,checkpoint())
    assert out["current_oos_observations"]==1000
    assert out["remaining_to_1000"]==0
    assert out["status"]=="READY_FOR_FINAL_1000_ADJUDICATION"
    assert out["adjudication"]["promotion_before_1000"]=="FORBIDDEN"

def test_duplicate_in_oos_fails_closed():
    rows=[row(i) for i in range(1,4002)]
    rows.append(row(4001))
    try:
        build(rows,checkpoint())
    except ValueError as exc:
        assert str(exc)=="OOS_FIXTURE_DUPLICATE"
    else:
        raise AssertionError("expected fail closed")
