from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient

TARGETS = {
    "92649": "Tiago Pereira",
    "102670": "Enzo Aguiard",
    "76126": "Keisuke Saitoh",
    "73055": "Alexandr Binda",
    "80183": "Marat Sharipov (RUS)",
    "95918": "Mitsuki Wei Kang Leong",
}


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _parse_target_spec(value: str) -> tuple[str, str]:
    token = str(value or "").strip()
    if "=" not in token:
        raise argparse.ArgumentTypeError("TARGET_MUST_BE_NUMERIC_ID=EXPECTED_NAME")
    player_id, expected_name = token.split("=", 1)
    player_id = player_id.strip()
    expected_name = expected_name.strip()
    if not player_id.isdigit():
        raise argparse.ArgumentTypeError("TARGET_PLAYER_ID_MUST_BE_NUMERIC")
    if not expected_name:
        raise argparse.ArgumentTypeError("TARGET_EXPECTED_NAME_REQUIRED")
    return player_id, expected_name


def _sanitize_profile(player_id: str, expected_name: str, payload: Any) -> dict[str, Any]:
    root = _mapping(payload)
    data = _mapping(root.get("data")) or root
    actual_id = str(data.get("id") or "")
    if actual_id and actual_id != player_id:
        raise ValueError(f"PROFILE_ID_MISMATCH:{player_id}:{actual_id}")

    name = str(data.get("name") or "").strip()
    if not name:
        raise ValueError(f"PROFILE_NAME_MISSING:{player_id}")

    info = _mapping(data.get("information"))
    birthday = str(data.get("birthday") or "").strip() or None
    country = str(data.get("countryAcr") or "").strip() or None
    plays = str(info.get("plays") or info.get("hand") or "").strip() or None

    return {
        "provider_player_id": f"rapidapi-tennis:player:{player_id}",
        "numeric_player_id": player_id,
        "expected_display_name": expected_name,
        "profile_name": name,
        "birthday": birthday,
        "country_acr": country,
        "plays": plays,
        "profile_response_sha256": _sha(payload),
        "competitive_fields_discarded": [
            key
            for key in ("currentRank", "points", "progress", "careerMoney")
            if key in data
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="evidence/cor0203/identity/MATRIX_COR0203_RAPIDAPI_PROFILE_IDENTITY_R732.json",
    )
    parser.add_argument(
        "--target",
        action="append",
        type=_parse_target_spec,
        default=[],
        help="Exact governed profile target in NUMERIC_ID=EXPECTED_NAME form. Repeatable.",
    )
    parser.add_argument(
        "--schema",
        default="MATRIX_COR0203_RAPIDAPI_PROFILE_IDENTITY_R732_V1",
    )
    parser.add_argument(
        "--purpose",
        default="Identity/biography only for six R730 blocked players.",
    )
    args = parser.parse_args()

    targets = dict(args.target) if args.target else dict(TARGETS)
    if len(targets) != len(args.target) and args.target:
        raise SystemExit("DUPLICATE_TARGET_PLAYER_ID")

    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")

    client = RapidApiTennisClient(key)
    rows = []
    for player_id, expected_name in targets.items():
        payload = client._get(f"/tennis/v2/atp/player/profile/{player_id}")
        rows.append(_sanitize_profile(player_id, expected_name, payload))

    out = {
        "schema": args.schema,
        "provider": "rapidapi_tennis",
        "provider_plan_required": "Ultra_or_compatible",
        "acquired_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": args.purpose,
        "source_endpoint_pattern": "/tennis/v2/atp/player/profile/{numeric_player_id}",
        "targets": [
            {
                "numeric_player_id": player_id,
                "expected_display_name": expected_name,
            }
            for player_id, expected_name in targets.items()
        ],
        "records": rows,
        "request_count": client.request_count,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "current_ranking_fields_used": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    out["records_sha256"] = _sha(rows)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "records": len(rows),
                "request_count": client.request_count,
                "records_sha256": out["records_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
