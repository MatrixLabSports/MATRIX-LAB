import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tools.matrix_independent_over25_historical_parity import compare,parse_archive,parse_free,inspect

CUTOFF=datetime(2026,10,28,5,41,tzinfo=timezone.utc)

def payloads(count=24):
    api=[]; free=[]
    for i in range(count):
        stamp=(datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=i)).isoformat()
        api.append({"fixture":{"id":100+i,"date":stamp,"status":{"short":"FT"}},
                    "league":{"id":135,"season":2026},
                    "teams":{"home":{"name":"Atalanta"},"away":{"name":"Parma"}},
                    "goals":{"home":i%3,"away":i%2}})
        free.append({"id":200+i,"status":"FINISHED","utcDate":stamp,
                     "competition":{"id":2019},"homeTeam":{"name":"Atalanta BC"},
                     "awayTeam":{"name":"Parma Calcio 1913"},
                     "score":{"fullTime":{"home":i%3,"away":i%2}}})
    return {"response":api},{"matches":free}

class Resp:
    status=200
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,_limit):return json.dumps(self.payload).encode()

def files(tmp_path,api):
    a=tmp_path/"archive.bin";a.write_text(json.dumps(api))
    c=tmp_path/"cycle.json";c.write_text(json.dumps({"status":"PASS","finished_at_utc":CUTOFF.isoformat()}))
    return a,c

def test_real_archive_comparison_accepts_24_agreeing_results(tmp_path):
    a,b=payloads()
    archive,cycle=files(tmp_path,a)
    def fake(req,timeout):
        assert "competitions/SA/matches" in req.full_url
        assert req.get_header("X-auth-token")=="secret"
        return Resp(b)
    result=inspect("secret",archive=archive,cycle=cycle,opener=fake)
    assert result["status"]=="PASS_SERIE_A_HISTORICAL_SCORE_CONCORDANCE_ONLY"
    assert result["matched_exact_result_count"]==24
    assert result["history_result_concordance_verified"] is True
    assert result["calibrated_model_feature_equivalence_verified"] is False
    assert result["equivalence_across_all_six_leagues_verified"] is False
    assert result["signal_generation_authorized"] is False
    assert result["real_money"]=="BLOCKED"

def test_one_score_disagreement_blocks_concordance(tmp_path):
    a,b=payloads()
    b["matches"][4]["score"]["fullTime"]["home"]=9
    archive,cycle=files(tmp_path,a)
    result=inspect("secret",archive=archive,cycle=cycle,opener=lambda *_a,**_kw:Resp(b))
    assert result["score_disagreement_count"]==1
    assert result["history_result_concordance_verified"] is False
    assert result["signal_generation_authorized"] is False

def test_wrong_competition_fails_closed(tmp_path):
    a,b=payloads()
    b["matches"][0]["competition"]["id"]=999
    archive,cycle=files(tmp_path,a)
    result=inspect("secret",archive=archive,cycle=cycle,opener=lambda *_a,**_kw:Resp(b))
    assert result["status"]=="BLOCKED_PARITY_PROBE_ERROR"
    assert result["history_result_concordance_verified"] is False

def test_no_credential_never_networks(tmp_path):
    a,b=payloads()
    archive,cycle=files(tmp_path,a)
    def never(*a,**kw):raise AssertionError("NETWORK_FORBIDDEN")
    result=inspect("",archive=archive,cycle=cycle,opener=never)
    assert result["network_calls"]==0
    assert result["status"]=="BLOCKED_MISSING_FREE_PROVIDER_KEY"

def test_swapped_fixture_sides_are_not_equivalent():
    a,b=payloads()
    raw=parse_archive(a,CUTOFF)
    f=parse_free(b,CUTOFF)
    for row in f:
        row["home"],row["away"]=row["away"],row["home"]
    result=compare(raw,f)
    assert len(result["matches"])==0

def test_too_few_matches_fail_not_pretend_full_parity(tmp_path):
    a,b=payloads(count=4)
    archive,cycle=files(tmp_path,a)
    result=inspect("secret",archive=archive,cycle=cycle,opener=lambda *_a,**_kw:Resp(b))
    assert result["history_result_concordance_verified"] is False
    assert result["status"]=="BLOCKED_SOURCE_SCORE_PARITY_INCOMPLETE"


def _realistic_pit_payloads(total=36):
    """Four stable named teams and distinct provider IDs, prior-only chronology."""
    from datetime import datetime, timedelta, timezone
    names = ("Atalanta", "Parma", "Torino", "Udinese")
    api, free = [], []
    for i in range(total):
        start = datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(hours=14 * i)
        home, away = i % 4, (i + 1) % 4
        hg, ag = i % 4, (i // 4) % 3
        api.append({
            "fixture": {"id": 1000 + i, "date": start.isoformat(), "status": {"short": "FT"}},
            "league": {"id": 135, "season": 2026},
            "teams": {"home": {"id": 100 + home, "name": names[home]},
                      "away": {"id": 100 + away, "name": names[away]}},
            "goals": {"home": hg, "away": ag}
        })
        free.append({
            "id": 2000 + i, "utcDate": start.isoformat(), "status": "FINISHED",
            "competition": {"id": 2019},
            "homeTeam": {"id": 500 + home, "name": names[home]},
            "awayTeam": {"id": 500 + away, "name": names[away]},
            "score": {"fullTime": {"home": hg, "away": ag}}
        })
    return {"response": api}, {"matches": free}


def test_exact_raw_pit_replay_can_be_proven_without_promoting_model(tmp_path):
    archive_payload, free_payload = _realistic_pit_payloads()
    archive, cycle = files(tmp_path, archive_payload)
    result = inspect("token", archive=archive, cycle=cycle,
                     opener=lambda *_args, **_kw: Resp(free_payload))
    trace = result["raw_group_feature_parity"]
    assert trace["pairs_with_matching_full_time_score"] == 36
    assert trace["pairs_with_valid_raw_provider_ids"] == 36
    assert trace["scoreable_both"] > 0
    assert trace["different_raw_group_feature_or_probability_count"] == 0
    assert trace["same_raw_group_feature_and_probability_count"] == trace["scoreable_both"]
    assert trace["max_absolute_model_probability_difference"] == 0
    assert trace["canonical_enriched_pit_parity_verified"] is False
    assert trace["all_six_leagues_equivalence_verified"] is False
    assert result["calibrated_model_feature_equivalence_verified"] is False
    assert result["signal_generation_authorized"] is False


def test_mismatched_historical_goals_detected_in_future_pit_feature_replay(tmp_path):
    archive_payload, free_payload = _realistic_pit_payloads()
    free_payload["matches"][4]["score"]["fullTime"]["home"] += 2
    archive, cycle = files(tmp_path, archive_payload)
    result = inspect("token", archive=archive, cycle=cycle,
                     opener=lambda *_args, **_kw: Resp(free_payload))
    trace = result["raw_group_feature_parity"]
    assert result["score_disagreement_count"] == 1
    assert trace["scoreable_both"] > 0
    assert trace["different_raw_group_feature_or_probability_count"] > 0
    assert trace["max_absolute_model_probability_difference"] > 0
    assert result["history_result_concordance_verified"] is False
    assert result["signal_generation_authorized"] is False


def test_missing_raw_team_ids_cannot_be_claimed_as_feature_parity(tmp_path):
    archived, free = payloads()
    archive, cycle = files(tmp_path, archived)
    result = inspect("secret", archive=archive, cycle=cycle,
                     opener=lambda *_args, **_kw: Resp(free))
    trace = result["raw_group_feature_parity"]
    assert result["history_result_concordance_verified"] is True
    assert trace["scoreable_both"] == 0
    assert trace["pairs_with_valid_raw_provider_ids"] == 0
    assert trace["canonical_enriched_pit_parity_verified"] is False
    assert result["calibrated_model_feature_equivalence_verified"] is False
