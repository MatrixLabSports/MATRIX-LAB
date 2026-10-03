from __future__ import annotations

import json
from pathlib import Path

from tools.cor0203_prospective_producer import load_state

TARGETS = ["Abedallah Shelbayh", "Abdullah Shelbayh", "Timofei Derepasko"]


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
    path=Path("evidence/cor0203/runtime/MATRIX_COR0203_PRE2026_STATE_R706.json.gz.b64")
    state, sha=load_state(path)
    report={
        "schema":"MATRIX_COR0203_R706_TARGET_HISTORY_READINESS_AUDIT_V1",
        "state_path":str(path),
        "state_sha256":sha,
        "targets":[audit_player(state,name) for name in TARGETS],
        "state_mutated":False,
        "metrics_opened":False,
        "outcomes_read":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    out=Path("evidence/cor0203/runtime/MATRIX_COR0203_R706_TARGET_HISTORY_READINESS_LAST.json")
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "targets":[{"name":x["name"],"ready":x["fully_history_ready"],"counts":x["counts"]} for x in report["targets"]],
        "state_sha256":sha,
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
