from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

def git(repo: Path, *args: str) -> tuple[int, str, str]:
    p = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    registry_path = Path(args.registry).resolve()
    output_path = Path(args.output).resolve()
    sys.path.insert(0, str(repo))

    from matrix_elite.support_contract_bindings import (
        BINDING_LAYER_VERSION,
        SOURCE_HEAD,
        registry_payload,
        repository_evidence_audit,
        validate_binding_registry,
    )

    reasons: list[str] = []

    if not repo.is_dir():
        reasons.append("REPOSITORY_MISSING")
    if not registry_path.is_file():
        reasons.append("REGISTRY_MISSING")

    code, head_out, _ = git(repo, "rev-parse", "HEAD")
    head = head_out.strip() if code == 0 else ""
    if code != 0:
        reasons.append("GIT_HEAD_UNAVAILABLE")

    code, branch_out, _ = git(repo, "branch", "--show-current")
    branch = branch_out.strip() if code == 0 else ""
    if code != 0:
        reasons.append("GIT_BRANCH_UNAVAILABLE")

    code, _, _ = git(repo, "merge-base", "--is-ancestor", SOURCE_HEAD, head) if head else (1, "", "")
    source_head_is_ancestor = code == 0
    if not source_head_is_ancestor:
        reasons.append("SOURCE_HEAD_NOT_ANCESTOR")

    expected = registry_payload()
    actual = {}
    if registry_path.is_file():
        try:
            actual = json.loads(registry_path.read_text(encoding="utf-8-sig"))
        except Exception:
            reasons.append("REGISTRY_JSON_INVALID")
    if actual != expected:
        reasons.append("REGISTRY_PAYLOAD_MISMATCH")

    structural_reasons = list(validate_binding_registry())
    reasons.extend(structural_reasons)

    evidence_audit = repository_evidence_audit(repo)
    if evidence_audit["result"] != "PASS":
        reasons.extend(str(x) for x in evidence_audit["reasons"])

    # This audit validates only the new binding layer and its exact candidate
    # evidence references. It deliberately does not promote support.
    report = {
        "schema": "MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_AUDIT_R1",
        "result": "PASS" if not reasons else "FAIL_CLOSED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "binding_layer_version": BINDING_LAYER_VERSION,
        "repository_branch": branch,
        "repository_head": head,
        "source_head": SOURCE_HEAD,
        "source_head_is_ancestor": source_head_is_ancestor,
        "required_control_count": 21,
        "required_exact_version_field_count": 19,
        "registry_payload_matches_code": actual == expected,
        "registry_fingerprint": expected["registry_fingerprint"],
        "checked_evidence_ref_count": evidence_audit["checked_evidence_ref_count"],
        "reasons": list(dict.fromkeys(reasons)),
        "support_declared": False,
        "support_status": "NOT_EVALUATED",
        "semantic_review_status": "PENDING_INDEPENDENT_SUBSTANTIVE_AUDIT",
        "supportability_pack_generated": False,
        "supportability_pack_ready": False,
        "candidate_inventory_generated": False,
        "selection_r2_executed": False,
        "builder_r2_executed": False,
        "registry_r3_executed": False,
        "freeze_r3_executed": False,
        "performance_information_used": False,
        "network_calls_performed": False,
        "push_performed": False,
        "controlled_live_admissible": False,
        "production_admissible": False,
        "next_gate": (
            "INDEPENDENT_SUBSTANTIVE_BINDING_REVIEW_BEFORE_SUPPORTABILITY_PACK_CONSTRUCTION"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("RESULT=" + report["result"])
    print("BINDING_LAYER_VERSION=" + BINDING_LAYER_VERSION)
    print("REQUIRED_CONTROLS=21")
    print("REQUIRED_EXACT_VERSION_FIELDS=19")
    print("REGISTRY_PAYLOAD_MATCHES_CODE=" + str(report["registry_payload_matches_code"]).upper())
    print("SOURCE_HEAD_IS_ANCESTOR=" + str(source_head_is_ancestor).upper())
    print("CHECKED_EVIDENCE_REFS=" + str(report["checked_evidence_ref_count"]))
    print("SUPPORT_DECLARED=FALSE")
    print("SUPPORTABILITY_PACK_READY=FALSE")
    print("SELECTION_R2_EXECUTED=FALSE")
    print("PERFORMANCE_INFORMATION_USED=FALSE")
    print("CONTROLLED_LIVE_ADMISSIBLE=FALSE")
    print("PRODUCTION_ADMISSIBLE=FALSE")
    print("AUDIT_REPORT=" + str(output_path))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
