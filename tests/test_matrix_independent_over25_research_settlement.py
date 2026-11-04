"""Research settlement: a final score cannot rewrite or create predictions."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from tools.matrix_independent_over25_research_settlement import settle
from tools.matrix_independent_over25_prematch_freeze import canonical,SCHEMA

T=lambda x:datetime.fromisoformat(x.replace("Z","+00:00"))
BASE=Path("evidence/football_research_freezes/2026-11-04")

def setup(root):
    folder=root/BASE
    folder.joinpath("sources").mkdir(parents=True)
    a=b'{"intake":"untouched"}'
    b=b'{"shadow":"untouched"}'
    ha=hashlib.sha256(a).hexdigest()
    hb=hashlib.sha256(b).hexdigest()
    (folder/"sources"/(ha+".json")).write_bytes(a)
    (folder/"sources"/(hb+".json")).write_bytes(b)
    frozen={"schema":SCHEMA,"provider":"FOOTBALL_DATA_ORG",
      "provider_fixture_id":"555","provider_competition_id":"2019",
      "kickoff_utc":"2026-11-04T20:00:00+00:00",
      "sealed_at_utc":"2026-11-04T12:00:00+00:00",
      "research_probability_over25":0.63,
      "source_intake_file_sha256":ha,"source_shadow_file_sha256":hb,
      "source_intake_file_path":(BASE/"sources"/(ha+".json")).as_posix(),
      "source_shadow_file_path":(BASE/"sources"/(hb+".json")).as_posix(),
      "telegram_signal_authorized":False,"real_money":"BLOCKED"}
    sealed=folder/"555_valid.json"
    sealed.write_bytes(canonical(frozen))
    return sealed

class Response:
    status=200
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return json.dumps(self.body).encode()

def source(status="FINISHED",home=2,away=1,competition=2019):
    return {"id":555,"status":status,"utcDate":"2026-11-04T20:00:00Z",
      "competition":{"id":competition},"score":{"fullTime":{"home":home,"away":away}},
      "lastUpdated":"2026-11-04T22:00:00Z"}

def test_no_score_before_kickoff(tmp_path):
    setup(tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError("NETWORK_BEFORE_KICKOFF")
    x=settle(tmp_path,now=T("2026-11-04T18:00:00Z"),
             token="configured",opener=forbidden)
    assert x["http_calls"]==0
    assert x["decisions"][0]["status"]=="AWAITING_KICKOFF"

def test_authentic_final_settlement_is_immutable_and_idempotent(tmp_path):
    old=setup(tmp_path).read_bytes()
    def opener(req,timeout):
        assert req.full_url=="https://api.football-data.org/v4/matches/555"
        assert req.get_header("X-auth-token")=="configured"
        return Response(source())
    x=settle(tmp_path,now=T("2026-11-04T22:30:00Z"),
             token="configured",opener=opener)
    assert x["http_calls"]==1
    assert x["settled_total"]==1
    assert x["decisions"][0]["status"]=="SETTLED_RESEARCH_ONLY"
    entry=tmp_path/x["decisions"][0]["result_path"]
    result=json.loads(entry.read_text())
    assert result["over25_outcome"]==1
    assert result["home_goals"]==2
    assert result["brier_loss"]==round((0.63-1)**2,12)
    assert result["telegram_signal_authorized"] is False
    assert (tmp_path/BASE/"555_valid.json").read_bytes()==old
    def no_call(*args,**kwargs):raise AssertionError("DUPLICATE_SETTLEMENT_NETWORK")
    y=settle(tmp_path,now=T("2026-11-04T22:40:00Z"),
             token="configured",opener=no_call)
    assert y["decisions"][0]["status"]=="ALREADY_SETTLED"
    assert y["http_calls"]==0
    assert y["settled_total"]==1

def test_nonfinal_or_conflicting_provider_result_never_settles(tmp_path):
    setup(tmp_path)
    x=settle(tmp_path,now=T("2026-11-04T22:30:00Z"),
       token="configured",opener=lambda *a,**kw:Response(source(status="IN_PLAY")))
    assert x["settled_total"]==0
    assert x["decisions"][0]["status"]=="RESULT_NOT_FINAL_OR_IDENTITY_MISMATCH"
    assert not list((tmp_path/BASE).glob("555_result_*"))

def test_changed_original_shadow_source_hash_fails_closed(tmp_path):
    setup(tmp_path)
    source_files=list((tmp_path/BASE/"sources").glob("*.json"))
    source_files[0].write_text('{"changed":true}')
    x=settle(tmp_path,now=T("2026-11-04T22:30:00Z"),
             token="configured",opener=lambda *a,**kw:(_ for _ in ()).throw(AssertionError()))
    assert x["http_calls"]==0
    assert x["decisions"][0]["status"]=="BLOCKED_INVALID_SOURCE"
    assert x["decisions"][0]["reason"]=="SOURCE_HASH_MISMATCH"

def test_finished_result_before_update_is_refused(tmp_path):
    setup(tmp_path)
    x=settle(tmp_path,now=T("2026-11-04T21:40:00Z"),
             token="configured",opener=lambda *a,**kw:Response(source()))
    assert x["settled_total"]==0
    assert x["decisions"][0]["status"]=="INVALID_RESULT_PROVIDER_UPDATE"
