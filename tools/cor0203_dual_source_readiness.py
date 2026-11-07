from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

REQUIRED_PROVIDERS = ("rapidapi_tennis", "api_tennis")
READY_STATUS = "DISCOVERY_COMPLETED"


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _provider_state(payload: Mapping[str, Any], expected: str) -> dict[str, Any]:
    provider = str(payload.get("provider") or "UNKNOWN")
    status = str(payload.get("status") or "UNKNOWN")
    network_calls = int(payload.get("network_calls") or 0)
    real_money = str(payload.get("real_money") or "BLOCKED")
    automatic_wagering = bool(payload.get("automatic_wagering"))
    provider_match = provider == expected
    ready = (
        provider_match
        and status == READY_STATUS
        and network_calls > 0
        and real_money == "BLOCKED"
        and automatic_wagering is False
    )
    if not provider_match:
        cause = "PROVIDER_IDENTITY_MISMATCH"
    elif status != READY_STATUS:
        cause = "DISCOVERY_NOT_COMPLETED"
    elif network_calls <= 0:
        cause = "DISCOVERY_COMPLETED_WITHOUT_NETWORK_CALL"
    elif real_money != "BLOCKED":
        cause = "REAL_MONEY_GOVERNANCE_VIOLATION"
    elif automatic_wagering:
        cause = "AUTOMATIC_WAGERING_GOVERNANCE_VIOLATION"
    else:
        cause = "READY"
    return {
        "provider": provider,
        "expected_provider": expected,
        "provider_match": provider_match,
        "status": status,
        "network_calls": network_calls,
        "ready": ready,
        "cause": cause,
    }


def classify_dual_source_readiness(
    *,
    rapidapi: Mapping[str, Any],
    api_tennis: Mapping[str, Any],
    horizon: Mapping[str, Any],
    reconciliation: Mapping[str, Any],
) -> dict[str, Any]:
    providers = {
        "rapidapi_tennis": _provider_state(rapidapi, "rapidapi_tennis"),
        "api_tennis": _provider_state(api_tennis, "api_tennis"),
    }
    horizon_ok = (
        str(horizon.get("status") or "") == "PASS"
        and int(horizon.get("logical_horizon_days") or 0) >= 8
        and str(horizon.get("real_money") or "BLOCKED") == "BLOCKED"
    )
    reconciliation_ok = (
        str(reconciliation.get("status") or "") == "PASS"
        and str(reconciliation.get("rapidapi_provider_status") or "") == READY_STATUS
        and str(reconciliation.get("api_tennis_provider_status") or "") == READY_STATUS
        and str(reconciliation.get("real_money") or "BLOCKED") == "BLOCKED"
    )
    providers_ready = all(row["ready"] for row in providers.values())
    ready = providers_ready and horizon_ok and reconciliation_ok

    if not providers_ready:
        failed = [
            name + ":" + str(state["cause"])
            for name, state in providers.items()
            if not state["ready"]
        ]
        cause = "PAID_PROVIDER_NOT_READY:" + ",".join(failed)
    elif not horizon_ok:
        cause = "DUAL_HORIZON_NOT_READY"
    elif not reconciliation_ok:
        cause = "DUAL_RECONCILIATION_NOT_READY"
    else:
        cause = "READY"

    status = "DUAL_DISCOVERY_COMPLETED" if ready else "DUAL_DISCOVERY_BLOCKED"
    identity = {
        "provider": "dual_paid_tennis",
        "status": status,
        "ready": ready,
        "cause": cause,
        "required_providers": list(REQUIRED_PROVIDERS),
        "providers": providers,
        "horizon": {
            "status": str(horizon.get("status") or "UNKNOWN"),
            "logical_horizon_days": int(horizon.get("logical_horizon_days") or 0),
        },
        "reconciliation": {
            "status": str(reconciliation.get("status") or "UNKNOWN"),
            "rapidapi_provider_status": str(
                reconciliation.get("rapidapi_provider_status") or "UNKNOWN"
            ),
            "api_tennis_provider_status": str(
                reconciliation.get("api_tennis_provider_status") or "UNKNOWN"
            ),
        },
    }
    fingerprint = hashlib.sha256(_canonical(identity)).hexdigest()
    return {
        "schema": "MATRIX_COR0203_DUAL_SOURCE_READINESS_V1",
        **identity,
        "network_calls": sum(int(x["network_calls"]) for x in providers.values()),
        "status_fingerprint": fingerprint,
        "production_discovery_ready": ready,
        "both_paid_providers_required": True,
        "symmetric_discovery": True,
        "provider_primary": None,
        "fallback_provider": None,
        "provider_policy": "PEER_RECONCILIATION_NO_PRIMARY_FALLBACK",
        "automatic_provider_switch": False,
        "metrics_opened": False,
        "outcomes_read": 0,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def persist_transition(*, report: Mapping[str, Any], evidence_dir: Path) -> tuple[Path, bool]:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = str(report["status_fingerprint"])
    path = evidence_dir / (
        "MATRIX_COR0203_SOURCE_READINESS_DUAL_" + fingerprint[:16] + ".json"
    )
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("status_fingerprint") != fingerprint:
            raise ValueError("DUAL_SOURCE_READINESS_FINGERPRINT_COLLISION")
        return path, False
    path.write_text(
        json.dumps(dict(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path, True


def _load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("DUAL_SOURCE_INPUT_NOT_OBJECT:" + path)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rapidapi", required=True)
    parser.add_argument("--api-tennis", required=True)
    parser.add_argument("--horizon", required=True)
    parser.add_argument("--reconciliation", required=True)
    parser.add_argument("--evidence-dir", default="evidence/cor0203/source_readiness")
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args()

    report = classify_dual_source_readiness(
        rapidapi=_load(args.rapidapi),
        api_tennis=_load(args.api_tennis),
        horizon=_load(args.horizon),
        reconciliation=_load(args.reconciliation),
    )
    evidence_path, created = persist_transition(
        report=report,
        evidence_dir=Path(args.evidence_dir),
    )
    summary = {
        **report,
        "evidence_path": str(evidence_path),
        "evidence_created": created,
    }
    out = Path(args.summary_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "ready": report["ready"],
                "cause": report["cause"],
                "providers": report["providers"],
                "network_calls": report["network_calls"],
                "provider_policy": report["provider_policy"],
                "evidence_path": str(evidence_path),
                "evidence_created": created,
                "real_money": report["real_money"],
            },
            sort_keys=True,
        )
    )
    if not report["ready"]:
        raise SystemExit("DUAL_SOURCE_NOT_READY:" + str(report["cause"]))


if __name__ == "__main__":
    main()
