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



def _canonical_history(team_id, opponent_id, start_day=1, n=6):
    rows=[]
    for i in range(n):
        rows.append({
            "fixture_id": f"c-{team_id}-{i}",
            "kickoff_utc": f"2026-08-{start_day+i:02d}T12:00:00+00:00",
            "team_id": str(team_id),
            "team_name": f"Team {team_id}",
            "opponent_id": str(opponent_id),
            "opponent_name": f"Opponent {opponent_id}",
            "venue_role": "home" if i % 2 == 0 else "away",
            "goals_for": 1 + (i % 2),
            "goals_against": i % 2,
            "competition": "Bundesliga",
            "source_provider": "api_football",
            "observed_at_utc": "2026-09-30T00:00:00+00:00",
            "source_payload_sha256": None,
            "source_reference": "TEAM_LAST_FALLBACK",
            "time_precision": "datetime",
            "match_date": None,
            "fixture_identity_kind": "provider",
        })
    return rows


def test_enriched_canonical_pit_history_unlocks_team_history_without_changing_model(tmp_path: Path):
    rows=[]
    # Group baseline has >20 prior fixtures, but the two target teams only have four
    # appearances in the league-group payload. This reproduces the Bundesliga bridge gap.
    for i in range(24):
        hid=1 if i in {0,4,8,12} else 10+(i%6)
        aid=2 if i in {1,5,9,13} else 20+(i%6)
        rows.append(_raw_fixture(300+i,f"2026-09-{(i%24)+1:02d}T12:00:00+00:00",hid,aid,i%3,(i+1)%3))
    (tmp_path/"league_78_season_2026.bin").write_text(json.dumps({"response":rows}),encoding="utf-8")

    target={
        "target_key":"api_football:fixture:1575178",
        "fixture_id":"1575178",
        "kickoff_utc":"2026-10-10T13:30:00+00:00",
        "competition_id":"78",
        "season":2026,
        "home_team_id":"1",
        "away_team_id":"2",
        "home_team_name":"Hoffenheim",
        "away_team_name":"Hamburger SV",
        "canonical_sha256":"canonical-enriched",
        "home_history":_canonical_history(1,99,n=6),
        "away_history":_canonical_history(2,98,n=6),
    }
    manifest={"status":"PASS","real_money":"BLOCKED","p_matrix_status":"NOT_GENERATED","bundle_sha256":"source"}
    out=build_shadow_p_matrix(
        canonical_bundle={"inputs":[target]},
        canonical_manifest=manifest,
        raw_dir=tmp_path,
        generated_at=datetime(2026,10,10,7,0,tzinfo=timezone.utc),
    )

    assert out["scored_count"]==1
    row=out["rows"][0]
    assert row["fixture_id"]=="1575178"
    assert row["feature_counts"]["home_history_count"]==6
    assert row["feature_counts"]["away_history_count"]==6
    assert row["history_sources"]=={
        "home":"CANONICAL_ENRICHED_PIT",
        "away":"CANONICAL_ENRICHED_PIT",
    }
    assert row["model"]=="calibrated_log_pool_v1"
    assert row["parameters"]["over_2_5"]==PARAMS_OVER25
    assert row["odds_used_to_generate_probability"] is False
    assert out["protections"]["canonical_enriched_pit_history_allowed"] is True
    assert out["protections"]["parameter_refit"] is False


def test_enriched_canonical_history_rejects_future_leakage(tmp_path: Path):
    rows=[_raw_fixture(500+i,f"2026-09-{(i%24)+1:02d}T12:00:00+00:00",10+i,30+i,i%3,(i+1)%3) for i in range(24)]
    (tmp_path/"league_78_season_2026.bin").write_text(json.dumps({"response":rows}),encoding="utf-8")
    bad=_canonical_history(1,99,n=6)
    bad[0]["kickoff_utc"]="2026-10-10T14:00:00+00:00"
    target={
        "target_key":"x","fixture_id":"999","kickoff_utc":"2026-10-10T13:30:00+00:00",
        "competition_id":"78","season":2026,"home_team_id":"1","away_team_id":"2",
        "home_team_name":"H","away_team_name":"A","canonical_sha256":"abc",
        "home_history":bad,"away_history":_canonical_history(2,98,n=6),
    }
    manifest={"status":"PASS","real_money":"BLOCKED","p_matrix_status":"NOT_GENERATED","bundle_sha256":"source"}
    import pytest
    with pytest.raises(ValueError,match="CANONICAL_HOME_HISTORY_LEAKAGE"):
        build_shadow_p_matrix(
            canonical_bundle={"inputs":[target]},
            canonical_manifest=manifest,
            raw_dir=tmp_path,
            generated_at=datetime(2026,10,10,7,0,tzinfo=timezone.utc),
        )
