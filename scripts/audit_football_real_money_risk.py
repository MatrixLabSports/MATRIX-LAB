from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.application.football.real_money_risk import (
    FootballCapitalState,
    FootballHumanApproval,
    FootballRiskGateInput,
    FootballRiskPolicy,
    FootballWagerCandidate,
    assess_football_real_money_risk,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    candidate_data = dict(payload["candidate"])
    candidate_data["quoted_at"] = datetime.fromisoformat(candidate_data["quoted_at"])
    candidate_data["evaluated_at"] = datetime.fromisoformat(candidate_data["evaluated_at"])
    candidate = FootballWagerCandidate(**candidate_data)
    capital = FootballCapitalState(**payload["capital"])
    approval = None
    if payload.get("approval") is not None:
        approval_data = dict(payload["approval"])
        approval_data["approved_at"] = datetime.fromisoformat(approval_data["approved_at"])
        approval_data["expires_at"] = datetime.fromisoformat(approval_data["expires_at"])
        approval = FootballHumanApproval(**approval_data)
    gate = FootballRiskGateInput(
        candidate=candidate,
        capital=capital,
        controlled_live_review_eligible=bool(payload["controlled_live_review_eligible"]),
        odds_source_authorized=bool(payload["odds_source_authorized"]),
        data_quality_passed=bool(payload["data_quality_passed"]),
        compliance_review_complete=bool(payload["compliance_review_complete"]),
        kill_switch_manual_active=bool(payload.get("kill_switch_manual_active", False)),
        approval=approval,
    )
    policy = FootballRiskPolicy(**payload.get("policy", {}))
    result = assess_football_real_money_risk(gate, policy=policy).as_dict()
    result["audited_at_utc"] = datetime.now(timezone.utc).isoformat()
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
