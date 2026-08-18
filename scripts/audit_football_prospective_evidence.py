from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.application.football.prospective_evidence import (
    ValidatedMarketEvidence,
    build_prospective_readiness_bundle,
)
from app.core.evidence_writer import write_json_evidence
from app.research.football.prospective_ledger import FootballProspectiveEvidenceLedger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit prospective paper-trading and closing-line evidence for one football market."
    )
    parser.add_argument("--ledger", required=True, help="Append-only prospective JSONL ledger")
    parser.add_argument("--validation-evidence", required=True, help="JSON with protected validation/governance evidence")
    parser.add_argument("--evidence-dir", default="evidence", help="Directory for verifiable audit evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    validation_payload = json.loads(Path(args.validation_evidence).read_text(encoding="utf-8"))
    validation = ValidatedMarketEvidence.from_mapping(validation_payload)
    ledger = FootballProspectiveEvidenceLedger(args.ledger)
    bundle = build_prospective_readiness_bundle(ledger=ledger, validation=validation)
    readiness = bundle.readiness

    print(f"MATRIX_FOOTBALL_PROSPECTIVE_STATUS={readiness.status}")
    print(f"market_key={readiness.market_key}")
    print(f"model_version={readiness.model_version}")
    print(f"paper_decisions={bundle.prospective_performance.decision_count}")
    print(f"paper_settled={bundle.prospective_performance.settled_count}")
    print(f"closing_odds={bundle.prospective_performance.closing_odds_count}")
    print(f"prospective_performance_verified={str(bundle.controlled_live_evidence.prospective_performance_verified)}")
    print(f"positive_clv_confirmed={str(bundle.controlled_live_evidence.positive_clv_confirmed)}")
    print("automatic_wager_execution_enabled=False")
    print("human_approval_required=True")
    if readiness.blocked_reasons:
        print("blocked_reasons=" + ",".join(readiness.blocked_reasons))

    write_json_evidence(
        args.evidence_dir,
        prefix="football_prospective_readiness",
        payload=bundle.as_dict(),
    )
    return 0 if readiness.controlled_live_review_eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
