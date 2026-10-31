from __future__ import annotations

import json
from pathlib import Path

from tools.api_football_prediction_store import load_chunked_json, write_chunked_json


def main() -> None:
    root=Path("evidence/api_football/model_validation")
    source=root/"retrospective_predictions.json"
    manifest_path=root/"retrospective_predictions_manifest.json"

    if source.exists():
        payload=json.loads(source.read_text(encoding="utf-8"))
        manifest=write_chunked_json(payload=payload,out_dir=root,base_name="retrospective_predictions")
        rebuilt=load_chunked_json(manifest_path)
        if rebuilt != payload:
            raise ValueError("CHUNKED_STORE_ROUNDTRIP_MISMATCH")
        source.unlink()
        print(json.dumps({"status":"MIGRATED","rows":manifest["row_count"],"chunks":manifest["chunk_count"]},sort_keys=True))
        return

    if manifest_path.exists():
        payload=load_chunked_json(manifest_path)
        count=len(payload) if isinstance(payload,list) else max((len(v) for v in payload.values() if isinstance(v,list)),default=0)
        print(json.dumps({"status":"ALREADY_MIGRATED","rows":count},sort_keys=True))
        return

    raise FileNotFoundError("RETROSPECTIVE_PREDICTIONS_SOURCE_OR_MANIFEST_NOT_FOUND")


if __name__=="__main__":
    main()
