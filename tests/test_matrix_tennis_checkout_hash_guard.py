"""Guard Windows newline conversion without weakening source SHA256 binding."""
import hashlib
import json
from pathlib import Path

import pytest
from tools import matrix_tennis_checkout_hash_guard as guard


def test_source_attributes_keep_tennis_sha_bytes_exact():
    attrs=(Path(__file__).resolve().parents[1]/".gitattributes").read_text()
    for pattern in (
        "evidence/tennis_calendar_physical/** -text",
        "evidence/tennis_calendar_reconciliation/** -text",
        "evidence/cor0203/** -text",
        "evidence/tennis_parallel_lanes/** -text",
        "evidence/free_providers/** -text",
    ):
        assert pattern in attrs


def prepare(tmp_path, monkeypatch):
    source={}
    # Minimal committed JSON fixtures. Each is a byte-exact Git-blob stand-in.
    for i,path in enumerate(guard.TRACKED):
        if i==2:
            continue
        source[path]=(json.dumps({"source":i,"data":"genuine"},indent=2)+"\n").encode()
    research={"source_sha256":{
        "prematch_details":hashlib.sha256(source[guard.TRACKED[0]]).hexdigest(),
        "source_crossmatch":hashlib.sha256(source[guard.TRACKED[1]]).hexdigest(),
        "original_authorities":{
            "Hard":hashlib.sha256(source[guard.TRACKED[3]]).hexdigest(),
            "Clay":hashlib.sha256(source[guard.TRACKED[4]]).hexdigest(),
        }}}
    source[guard.TRACKED[2]]=(json.dumps(research,indent=2)+"\n").encode()
    for path,raw in source.items():
        f=tmp_path/path
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_bytes(raw)
    monkeypatch.setattr(guard,"git_blob",lambda root,path:source[path])
    return source


def test_byte_exact_checkout_and_bound_sha_pass(tmp_path,monkeypatch):
    prepare(tmp_path,monkeypatch)
    r=guard.verify(tmp_path)
    assert r["verified_files"]==5
    assert r["research_evidence_source_bindings_verified"] is True
    assert all(s["status"]=="BYTE_EXACT" for s in r["sources"])
    assert r["holdout_admissions"]==0 and r["real_money"]=="BLOCKED"


def test_windows_crlf_checkout_restored_only_when_lossless(tmp_path,monkeypatch):
    source=prepare(tmp_path,monkeypatch)
    p=tmp_path/guard.TRACKED[0]
    p.write_bytes(source[guard.TRACKED[0]].replace(b"\n",b"\r\n"))
    with pytest.raises(ValueError,match="MATRIX_CHECKOUT_SOURCE_DRIFT"):
        guard.verify(tmp_path)
    r=guard.verify(tmp_path,restore_safe_newlines=True)
    assert r["sources"][0]["status"]=="LOSSLESS_CRLF_CHECKOUT_RESTORED"
    assert p.read_bytes()==source[guard.TRACKED[0]]


def test_arbitrary_changed_evidence_not_overwritten(tmp_path,monkeypatch):
    prepare(tmp_path,monkeypatch)
    p=tmp_path/guard.TRACKED[1]
    p.write_bytes(p.read_bytes()+b"tampered")
    with pytest.raises(ValueError,match="MATRIX_CHECKOUT_SOURCE_DRIFT"):
        guard.verify(tmp_path,restore_safe_newlines=True)
    assert p.read_bytes().endswith(b"tampered")


def test_research_source_sha_mismatch_always_blocks(tmp_path,monkeypatch):
    source=prepare(tmp_path,monkeypatch)
    research=json.loads(source[guard.TRACKED[2]])
    research["source_sha256"]["prematch_details"]="0"*64
    fake=(json.dumps(research,indent=2)+"\n").encode()
    source[guard.TRACKED[2]]=fake
    (tmp_path/guard.TRACKED[2]).write_bytes(fake)
    with pytest.raises(ValueError,match="MATRIX_ORIGINAL_PREMATCH_DETAIL_HASH_MISMATCH"):
        guard.verify(tmp_path,restore_safe_newlines=True)
