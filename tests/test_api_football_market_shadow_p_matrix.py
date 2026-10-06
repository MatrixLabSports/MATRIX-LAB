from datetime import datetime, timezone
from pathlib import Path
import json

from tools.api_football_market_shadow_p_matrix import build_shadow_p_matrix, PARAMS_1X2, PARAMS_OVER25


def _raw_fixture(fid, date, hid, aid, hg, ag):
    return {"fixture":{"id":fid,"date":date,"status":{"short":"FT"}},"teams":{"home":{"id":hid},"away":{"id":aid}},"goals":{"home":hg,"away":ag}}


def test_frozen_parameters_are_exact():
    assert PARAMS_1X2 == {"a": 1.0, "c": 0.8}
    assert PARAMS_OVER25 == {"a": 0.6, "b": 0.0, "c": 0.4}


def test_missing_raw_group_blocks_without_imputation(tmp_path: Path):
    bundle={"inputs":[{"target_key":"x","fixture_id":"1","kickoff_utc":"2026-10-06T12:00:00+00:00","competition_id":"999","season":2026,"home_team_id":"1","away_team_id":"2","canonical_sha256":"abc"}]}
    manifest={"status":"PASS","real_money":"BLOCKED","p_matrix_status":"NOT_GENERATED","bundle_sha256":"source"}
    out=build_shadow_p_matrix(canonical_bundle=bundle,canonical_manifest=manifest,raw_dir=tmp_path,generated_at=datetime(2026,10,5,tzinfo=timezone.utc))
    assert out["scored_count"] == 0
    assert out["blocked"][0]["reason"] == "BLOCKED_RAW_GROUP_MISSING"
    assert out["protections"]["real_money"] == "BLOCKED"
    assert out["protections"]["automatic_wagering"] is False


def test_scoring_uses_prior_group_only_and_btts_stays_blocked(tmp_path: Path):
    rows=[]
    # 24 prior fixtures; both target teams appear at least 5 times.
    for i in range(24):
        hid = 1 if i % 4 == 0 else 10 + (i % 5)
        aid = 2 if i % 4 == 1 else 20 + (i % 5)
        rows.append(_raw_fixture(100+i, f"2026-09-{(i%24)+1:02d}T12:00:00+00:00", hid, aid, i%3, (i+1)%3))
    # Ensure extra appearances for both target teams.
    for j in range(6):
        rows.append(_raw_fixture(200+j, f"2026-09-{25+j:02d}T12:00:00+00:00", 1, 2, j%2, (j+1)%2))
    raw={"response":rows}
    (tmp_path/"league_9_season_2026.bin").write_text(json.dumps(raw),encoding="utf-8")
    target={"target_key":"x","fixture_id":"999","kickoff_utc":"2026-10-06T12:00:00+00:00","competition_id":"9","season":2026,"home_team_id":"1","away_team_id":"2","home_team_name":"H","away_team_name":"A","canonical_sha256":"abc"}
    manifest={"status":"PASS","real_money":"BLOCKED","p_matrix_status":"NOT_GENERATED","bundle_sha256":"source"}
    out=build_shadow_p_matrix(canonical_bundle={"inputs":[target]},canonical_manifest=manifest,raw_dir=tmp_path,generated_at=datetime(2026,10,5,tzinfo=timezone.utc))
    assert out["p_matrix_status"] == "GENERATED_SHADOW"
    assert out["scored_count"] == 1
    row=out["rows"][0]
    assert abs(sum(row["p_matrix_shadow"]["1x2"].values())-1.0) < 1e-8
    assert 0 < row["p_matrix_shadow"]["over_2_5"] < 1
    assert row["btts_status"] == "BLOCKED_FINAL_HOLDOUT_NOT_SUPERIOR"
    assert row["odds_used_to_generate_probability"] is False
    assert row["outcomes_used_from_target"] is False
    assert out["protections"]["parameter_refit"] is False
    assert out["protections"]["final_holdout_reused"] is False
