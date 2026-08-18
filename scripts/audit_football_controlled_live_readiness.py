from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.application.football.controlled_live_readiness import (
    ControlledLiveEvidence,
    assess_controlled_live_readiness,
    human_summary,
)
from app.core.evidence_writer import write_json_evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit fail-closed controlled-live readiness for one football market.")
    parser.add_argument("--evidence", required=True, help="JSON file containing market-specific promotion evidence")
    parser.add_argument("--evidence-dir", default="evidence", help="Directory for immutable readiness audit evidence")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    evidence = ControlledLiveEvidence.from_mapping(payload)
    readiness = assess_controlled_live_readiness(evidence)
    print(human_summary(readiness))
    write_json_evidence(
        args.evidence_dir,
        prefix="football_controlled_live_readiness",
        payload={
            "input_evidence": asdict(evidence),
            "readiness": readiness.as_dict(),
        },
    )
    return 0 if readiness.controlled_live_review_eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
