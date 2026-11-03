"""Real archived-source replay tests: never invent live quotas or signal authorization."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import pytest

from tools.matrix_championship_atomic_pit_cycle import pack,unpack
from tools.matrix_championship_quote_window_scope import atomic_cycles
from tools.matrix_championship_prospective_pit_attestation import report

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/"evidence"/"football_world_inventory"/"2026-11-03"
NAMES={
    "intake":"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
    "shadow":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
    "sofa":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
    "flash":"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
}
def originals():
    docs={k:json.loads((FOLDER/file).read_text(encoding="utf-8"))
          for k,file in NAMES.items()}
    # Reconstruct a research-only attestation for the *matching* real cycle,
    # not the stale daily document from an earlier capture.
    stamp=datetime.fromisoformat(docs["shadow"]["completed_at_utc"].replace("Z","+00:00"))
    docs["attestation"]=report(docs["intake"],docs["sofa"],docs["flash"],
                                docs["shadow"],now=stamp+timedelta(seconds=1))
    return docs

def test_real_matching_source_replay_can_be_packed_without_signals():
    docs=originals()
    b=pack(docs,run_id="123")
    assert b["schema"]=="MATRIX_CHAMPIONSHIP_ATOMIC_PIT_CYCLE_V1"
    assert b["prospective_research_history_certified_count"]>=1
    assert b["production_probability_authorized"] is False
    assert b["telegram_signal_authorized"] is False
    assert unpack(b)["shadow"]==docs["shadow"]

def test_stale_daily_attestation_cannot_match_new_intake():
    docs=originals()
    daily=json.loads((FOLDER/"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json").read_text(encoding="utf-8"))
    docs["attestation"]=daily
    with pytest.raises(ValueError,match="ATOMIC_PIT_SOURCE_HASH_MISMATCH"):
        pack(docs,run_id="123")

def test_mutated_one_source_breaks_bundle_hash():
    b=pack(originals(),run_id="123")
    altered=deepcopy(b)
    altered["documents"]["shadow"]["scored"][0]["p_over25_research"]=0.999
    with pytest.raises(ValueError,match="ATOMIC_PIT"):
        unpack(altered)

def test_expired_bundle_cannot_enter_quote_window_even_if_hash_correct(tmp_path):
    b=pack(originals(),run_id="123")
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    (folder/"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_123.json").write_text(
        json.dumps(b),encoding="utf-8")
    att=datetime.fromisoformat(b["attested_at_utc"])
    assert len(atomic_cycles(folder,"2026-11-03",now=att+timedelta(minutes=5)))==1
    assert atomic_cycles(folder,"2026-11-03",now=att+timedelta(days=2))==[]

def test_bundle_fixture_or_team_mutation_is_never_accepted(tmp_path):
    b=pack(originals(),run_id="123")
    bad=deepcopy(b)
    bad["documents"]["intake"]["fixtures"][0]["home"]="Invented club"
    folder=tmp_path/"evidence"/"football_world_inventory"/"2026-11-03"
    folder.mkdir(parents=True)
    (folder/"MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_123.json").write_text(
        json.dumps(bad),encoding="utf-8")
    at=datetime.fromisoformat(b["attested_at_utc"])
    assert atomic_cycles(folder,"2026-11-03",now=at+timedelta(minutes=1))==[]

def test_malformed_run_id_and_mixed_fixtures_fail_closed():
    docs=originals()
    with pytest.raises(ValueError,match="ATOMIC_PIT_UNTRUSTED"):
        pack(docs,run_id="not-numeric")
    bad=deepcopy(docs)
    bad["intake"]["fixtures"][0]["home"]="Wrong"
    with pytest.raises(ValueError,match="SOURCE_HASH"):
        pack(bad,run_id="123")
