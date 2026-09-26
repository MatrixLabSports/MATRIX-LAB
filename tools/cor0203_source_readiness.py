from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


READY_STATUS = "DISCOVERY_COMPLETED"


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def classify_source_readiness(discovery: Mapping[str, Any]) -> dict[str, Any]:
    provider = str(discovery.get("provider") or "UNKNOWN")
    status = str(discovery.get("status") or "UNKNOWN")
    network_calls = int(discovery.get("network_calls") or 0)
    blocker = str(discovery.get("blocker") or "")

    ready = status == READY_STATUS and network_calls > 0
    if ready:
        cause = "READY"
    elif status == "API_TENNIS_KEY_NOT_CONFIGURED":
        cause = "PROVIDER_CREDENTIAL_NOT_CONFIGURED"
    elif status == "PROVIDER_DISCOVERY_BLOCKED":
        cause = "PROVIDER_DISCOVERY_BLOCKED"
    elif status == READY_STATUS and network_calls <= 0:
        cause = "DISCOVERY_COMPLETED_WITHOUT_NETWORK_CALL"
    else:
        cause = "UNEXPECTED_DISCOVERY_STATUS"

    identity = {
        "provider": provider,
        "status": status,
        "ready": ready,
        "cause": cause,
        "blocker": blocker,
    }
    fingerprint = hashlib.sha256(_canonical(identity)).hexdigest()
    return {
        "schema": "MATRIX_COR0203_SOURCE_READINESS_V1",
        **identity,
        "network_calls": network_calls,
        "status_fingerprint": fingerprint,
        "production_discovery_ready": ready,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def persist_transition(*, report: Mapping[str, Any], evidence_dir: Path) -> tuple[Path, bool]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = str(report["status_fingerprint"])
    path = evidence_dir / f"MATRIX_COR0203_SOURCE_READINESS_{fingerprint[:16]}.json"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != dict(report):
            raise ValueError("SOURCE_READINESS_FINGERPRINT_COLLISION")
        return path, False
    path.write_text(
        json.dumps(dict(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path, True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--evidence-dir", default="evidence/cor0203/source_readiness")
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args()

    discovery = json.loads(Path(args.discovery).read_text(encoding="utf-8"))
    report = classify_source_readiness(discovery)
    path, created = persist_transition(
        report=report,
        evidence_dir=Path(args.evidence_dir),
    )
    summary = {
        **report,
        "evidence_path": str(path),
        "evidence_created": created,
    }
    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "provider": report["provider"],
        "status": report["status"],
        "ready": report["ready"],
        "cause": report["cause"],
        "network_calls": report["network_calls"],
        "evidence_created": created,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
