import json
from pathlib import Path

import pytest

from tools.api_football_prediction_store import load_chunked_json, write_chunked_json


def test_chunked_json_roundtrip_dict_with_rows(tmp_path):
    payload={
        "schema":"TEST",
        "rows":[{"i":i,"text":"x"*1000} for i in range(4000)],
    }
    manifest=write_chunked_json(payload=payload,out_dir=tmp_path,base_name="sample")
    assert manifest["chunk_count"] > 1
    assert all(int(x["bytes"]) <= 1_500_000 for x in manifest["chunks"])
    rebuilt=load_chunked_json(tmp_path/"sample_manifest.json")
    assert rebuilt == payload


def test_chunked_json_detects_tampering(tmp_path):
    payload={"schema":"TEST","rows":[{"i":1},{"i":2}]}
    manifest=write_chunked_json(payload=payload,out_dir=tmp_path,base_name="sample")
    first=Path(manifest["chunks"][0]["path"])
    first.write_text(json.dumps([{"i":999}])+"\n",encoding="utf-8")
    with pytest.raises(ValueError,match="CHUNK_SHA256_MISMATCH"):
        load_chunked_json(tmp_path/"sample_manifest.json")
