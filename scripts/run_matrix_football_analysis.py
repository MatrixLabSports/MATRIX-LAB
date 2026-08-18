from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.application.football.analysis_runner import (
    build_football_operational_analysis,
    human_summary,
)
from app.core.evidence_writer import verify_evidence_sha256, write_json_evidence


def _load_object(path: str | Path, label: str) -> dict:
    target = Path(path)
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} file not found: {target}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {target}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run MATRIX FÚTBOL pre-match analysis in auditable experimental mode. "
            "This command never enables real-money decisions."
        )
    )
    parser.add_argument("--benchmark", required=True, help="Frozen benchmark JSON")
    parser.add_argument("--supplement", help="Optional verified supplemental pre-match JSON")
    parser.add_argument(
        "--evidence-dir",
        default="validation_artifacts/football-match-analysis",
        help="Directory for sanitized JSON evidence and SHA-256 sidecar",
    )
    parser.add_argument(
        "--prefix",
        default="football_match_analysis",
        help="Evidence filename prefix",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        benchmark = _load_object(args.benchmark, "benchmark")
        supplement = _load_object(args.supplement, "supplement") if args.supplement else None
        result = build_football_operational_analysis(benchmark, supplement=supplement)
        observed_at = datetime.now(timezone.utc)
        evidence = write_json_evidence(
            args.evidence_dir,
            prefix=args.prefix,
            payload=result.as_dict(),
            observed_at_utc=observed_at,
        )
        if not verify_evidence_sha256(evidence):
            raise RuntimeError("evidence SHA-256 verification failed after write")
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"MATRIX_FOOTBALL_ANALYSIS_ERROR={exc}", file=sys.stderr)
        return 2

    print(human_summary(result))
    print(f"evidence={evidence}")
    print("evidence_sha256_verified=True")
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
