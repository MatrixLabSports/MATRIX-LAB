from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.cor0203_prospective_producer import load_state

BASE_TARGETS = ["Abedallah Shelbayh", "Abdullah Shelbayh", "Timofei Derepasko"]


def discover_target_names(
    *,
    world_discovery_path: Path,
    authority_path: Path,
) -> list[str]:
    names = set(BASE_TARGETS)
    authority_ids = set()
    if authority_path.exists():
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
        authority_ids = {
            str(row.get("provider_player_id") or "")
            for row in authority.get("records", []) or []
            if isinstance(row, dict)
        }
    if not world_discovery_path.exists():
        return sorted(names)

    discovery = json.loads(world_discovery_path.read_text(encoding="utf-8"))
    for event in discovery.get("eligible_candidates", []) or []:
        for identity in event.get("player_identities", []) or []:
            if not isinstance(identity, dict):
                continue
            provider_id = str(identity.get("provider_player_id") or "")
            display_name = str(identity.get("display_name") or "").strip()
            if display_name and provider_id not in authority_ids:
                names.add(display_name)
    for event in discovery.get("provider_rejected", []) or []:
        for player in event.get("players", []) or []:
            if not isinstance(player, dict):
                continue
            provider_id = str(player.get("provider_player_id") or "")
            display_name = str(player.get("name") or "").strip()
            if display_name and provider_id not in authority_ids:
                names.add(display_name)
    return sorted(names)


def audit_player(state, name: str) -> dict:
    history=state.get("history", {})
    matches=list(history.get("matches", {}).get(name, []))
    overall=history.get("overall", {}).get(name)
    surface=history.get("surface", {}).get(name, {}).get("Hard")
    serve=history.get("serve", {}).get(name)
    ret=history.get("ret", {}).get(name)
    opp=history.get("opp_strength", {}).get(name)
    elo_o=state.get("elo_overall", {}).get(name)
    elo_h=state.get("elo_surface", {}).get("Hard", {}).get(name)
    gl_o=state.get("glicko_overall", {}).get(name)
    gl_h=state.get("glicko_surface", {}).get("Hard", {}).get(name)
    required={
        "form_history": bool(matches),
        "overall_history": isinstance(overall,list) and len(overall)>=2 and float(overall[1])>0,
        "hard_history": isinstance(surface,list) and len(surface)>=2 and float(surface[1])>0,
        "serve_history": isinstance(serve,list) and len(serve)>=2 and float(serve[1])>0,
        "return_history": isinstance(ret,list) and len(ret)>=2 and float(ret[1])>0,
        "opponent_strength_history": isinstance(opp,list) and len(opp)>=2 and float(opp[1])>0,
        "elo_overall": elo_o is not None,
        "elo_hard": elo_h is not None,
        "glicko_overall": gl_o is not None,
        "glicko_hard": gl_h is not None,
    }
    return {
        "name":name,
        "fully_history_ready":all(required.values()),
        "required_components":required,
        "counts":{
            "form_matches":len(matches),
            "overall_n": overall[1] if isinstance(overall,list) and len(overall)>=2 else 0,
            "hard_n": surface[1] if isinstance(surface,list) and len(surface)>=2 else 0,
            "serve_n": serve[1] if isinstance(serve,list) and len(serve)>=2 else 0,
            "return_n": ret[1] if isinstance(ret,list) and len(ret)>=2 else 0,
            "opponent_strength_n": opp[1] if isinstance(opp,list) and len(opp)>=2 else 0,
        },
        "ratings":{
            "elo_overall_present":elo_o is not None,
            "elo_hard_present":elo_h is not None,
            "glicko_overall_present":gl_o is not None,
            "glicko_hard_present":gl_h is not None,
        },
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument(
        "--world-discovery",
        default="evidence/cor0203/runtime/MATRIX_COR0203_WORLD_DERIVED_DISCOVERY_LAST.json",
    )
    parser.add_argument(
        "--authority",
        default="evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json",
    )
    parser.add_argument(
        "--out",
        default="evidence/cor0203/runtime/MATRIX_COR0203_R706_TARGET_HISTORY_READINESS_LAST.json",
    )
    args=parser.parse_args()

    path=Path("evidence/cor0203/runtime/MATRIX_COR0203_PRE2026_STATE_R706.json.gz.b64")
    state, sha=load_state(path)
    target_names=discover_target_names(
        world_discovery_path=Path(args.world_discovery),
        authority_path=Path(args.authority),
    )
    report={
        "schema":"MATRIX_COR0203_R706_TARGET_HISTORY_READINESS_AUDIT_V2",
        "state_path":str(path),
        "state_sha256":sha,
        "target_selection":"BASE_TARGETS_PLUS_CURRENT_WORLD_PLAYERS_WITHOUT_AUTHORITY",
        "target_count":len(target_names),
        "targets":[audit_player(state,name) for name in target_names],
        "state_mutated":False,
        "metrics_opened":False,
        "outcomes_read":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    out=Path(args.out)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "targets":[{"name":x["name"],"ready":x["fully_history_ready"],"counts":x["counts"]} for x in report["targets"]],
        "state_sha256":sha,
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
