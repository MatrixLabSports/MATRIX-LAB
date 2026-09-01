from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.research.football.prospective_shadow import (
    FootballProspectiveShadowLedger,
    freeze_football_operational_analysis,
)


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



def _file_sha256(path: str | Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("git command failed: " + completed.stderr.strip())
    return completed.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Freeze MATRIX FÚTBOL diagnostic probabilities prospectively in "
            "PRE_FREEZE_PROSPECTIVE_SHADOW mode. No wagering or official paper trading."
        )
    )
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--supplement")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--ledger")
    parser.add_argument("--result-json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if _git("status", "--porcelain=v1", "--untracked-files=all"):
            raise RuntimeError("repository must be clean before prospective freeze")
        repository_head = _git("rev-parse", "HEAD")
        benchmark = _load_object(args.benchmark, "benchmark")
        supplement = _load_object(args.supplement, "supplement") if args.supplement else None
        shadow_root = Path(
            os.environ.get(
                "LOCALAPPDATA",
                str(Path.home() / ".local" / "share"),
            )
        ) / "MATRIX-LAB-SPORTS" / "prospective-shadow-v1"
        ledger_path = Path(args.ledger) if args.ledger else shadow_root / "football_predictions.jsonl"
        result_path = Path(args.result_json) if args.result_json else shadow_root / "latest_freeze_result.json"
        ledger = FootballProspectiveShadowLedger(ledger_path)
        result = freeze_football_operational_analysis(
            benchmark,
            supplement=supplement,
            ledger=ledger,
            batch_id=args.batch_id,
            repository_head=repository_head,
        )
        output_path = result_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(result)
        payload["schema"] = "MATRIX_FOOTBALL_PROSPECTIVE_SHADOW_FREEZE_RESULT_V1"
        payload["analysis_mode"] = "PRE_FREEZE_PROSPECTIVE_SHADOW"
        payload["benchmark_file_sha256"] = _file_sha256(args.benchmark)
        payload["supplement_file_sha256"] = (
            None if args.supplement is None else _file_sha256(args.supplement)
        )
        payload["network_calls_performed"] = False
        payload["automatic_wagering"] = False
        output_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        print(f"MATRIX_FOOTBALL_PROSPECTIVE_SHADOW_ERROR={exc}", file=sys.stderr)
        return 2

    print("MATRIX_FOOTBALL_PROSPECTIVE_SHADOW=PASS")
    print(f"batch_id={result.batch_id}")
    print(f"prediction_count={result.prediction_count}")
    print(f"model_versions={','.join(result.model_versions)}")
    print(f"ledger_sha256={result.ledger_sha256}")
    print("money_decisions_enabled=False")
    print("official_paper_trading=False")
    print("automatic_wagering=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
