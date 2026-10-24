from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("IDENTITY_AUTHORITY_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def merge_authorities(
    base: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    for label, obj in (("BASE", base), ("OVERLAY", overlay)):
        if obj.get("post_cut_competitive_data_used") is not False:
            raise ValueError(label + "_POST_CUT_FLAG_INVALID")
        if obj.get("outcomes_used") is not False:
            raise ValueError(label + "_OUTCOME_FLAG_INVALID")
        if obj.get("odds_used") is not False:
            raise ValueError(label + "_ODDS_FLAG_INVALID")

    merged: dict[str, dict[str, Any]] = {}
    provenance: dict[str, str] = {}
    for label, obj in (("base", base), ("overlay", overlay)):
        for row in obj.get("records", []) or []:
            if not isinstance(row, Mapping):
                continue
            provider_id = str(row.get("provider_player_id") or "").strip()
            if not provider_id:
                raise ValueError("IDENTITY_AUTHORITY_PROVIDER_ID_MISSING")
            payload = dict(row)
            old = merged.get(provider_id)
            if old is not None and old != payload:
                raise ValueError("IDENTITY_AUTHORITY_CONFLICT:" + provider_id)
            merged[provider_id] = payload
            provenance[provider_id] = label

    return {
        "schema": "MATRIX_COR0203_IDENTITY_AUTHORITY_MERGED_V1",
        "ranking_cut": "2026-09-21",
        "country_code_aliases": dict(base.get("country_code_aliases") or {}),
        "records": [merged[key] for key in sorted(merged)],
        "sources": [
            {
                "schema": str(base.get("schema") or ""),
                "role": "base_identity_authority",
            },
            {
                "schema": str(overlay.get("schema") or ""),
                "role": "governed_identity_authority_overlay",
            },
        ],
        "merge_provenance": provenance,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "silent_imputation": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--overlay", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    result = merge_authorities(
        _load(Path(args.base)),
        _load(Path(args.overlay)),
    )
    _write(Path(args.out), result)
    print(
        json.dumps(
            {
                "records": len(result["records"]),
                "overlay_records": len(_load(Path(args.overlay)).get("records", []) or []),
                "real_money": "BLOCKED",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
