import json
from pathlib import Path
from tools.matrix_over25_source_hash_exact_repair import restore,sha,canonical,ROOT

def test_exact_sha_restore_preserves_modified_bytes_in_forensic_sidecar(tmp_path):
    folder=tmp_path/ROOT/"2026-11-05"/"sources"
    folder.mkdir(parents=True)
    doc={"schema":"REAL_CAPTURE","long":"évidence","nested":{"x":1,"z":2}}
    original=canonical(doc)
    expected=sha(original)
    current=json.dumps(doc,indent=2,sort_keys=True,ensure_ascii=False).encode("utf-8")
    assert current!=original
    f=folder/(expected+".json");f.write_bytes(current)
    result=restore(tmp_path,write=True)
    assert len(result["verified_sha_restorations"])==1
    assert result["unrecoverable_sources"]==[]
    assert f.read_bytes()==original
    sidecar=folder/"corrupted_originals"/(sha(current)+".json")
    assert sidecar.read_bytes()==current
    assert restore(tmp_path,write=True)["total_valid_sources"]==1

def test_unmatched_sha_is_never_forged_or_mutated(tmp_path):
    folder=tmp_path/ROOT/"2026-11-05"/"sources"
    folder.mkdir(parents=True)
    content=b'{"trusted":false}'
    f=folder/("f"*64+".json")
    f.write_bytes(content)
    r=restore(tmp_path,write=True)
    assert r["verified_sha_restorations"]==[]
    assert len(r["unrecoverable_sources"])==1
    assert f.read_bytes()==content
    assert not (folder/"corrupted_originals").exists()

def test_dry_run_reports_only_and_cannot_write(tmp_path):
    folder=tmp_path/ROOT/"2026-11-05"/"sources"
    folder.mkdir(parents=True)
    doc={"a":"b","c":4}
    original=canonical(doc)
    f=folder/(sha(original)+".json")
    modified=json.dumps(doc,indent=4).encode("utf-8")
    f.write_bytes(modified)
    r=restore(tmp_path,write=False)
    assert r["verified_sha_restorations"][0]["action"]=="RESTORABLE_NOT_WRITTEN"
    assert f.read_bytes()==modified
    assert not (folder/"corrupted_originals").exists()
