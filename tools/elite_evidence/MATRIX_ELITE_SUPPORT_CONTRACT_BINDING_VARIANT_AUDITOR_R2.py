from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Iterable

sys.dont_write_bytecode = True

SCHEMA = "MATRIX_ELITE_SUPPORT_CONTRACT_BINDING_VARIANT_AUDIT_R2"
EXPECTED_BRANCH = "integration/c2-private-live-foundation"
BASELINE_HEAD = "1a3f54c4c375577b8cf1ca7380014f5882f42ea6"
EXPECTED_COMMIT_SUBJECT = "MATRIX: harden support-contract semantic bindings R2"
EXPECTED_REGISTRY_FINGERPRINT = "db8a39dbda4a705c569a9566a06203ecba381bb4445ec5f8b7634794cd80cc80"
EXPECTED_PROVIDER_KEY = "api_football"

TARGET_PATH = "tools/elite_evidence/MATRIX_ELITE_SUPPORT_CONTRACT_BINDING_VARIANT_AUDITOR_R2.py"
EXPECTED_TARGET_HASHES = {
    "matrix_elite/support_contract_binding_variants.py": "0ea6efa0f90f28fd7f43c297b0330234efa91e6e663542005a19ec23dece6137",
    "app/core/canonical_market_semantics.py": "0a97fc484d49c33734d12ac5ad0bb1f70a336b08c5040ca444204a3a8b8db1bc",
    "app/core/settlement_rules.py": "b8c21123053b0e55cd82a7294553573ad5853b23897bd7b60c82a0e5a32cabdb",
    "app/security/provider_failover_rollback.py": "3b40d3fc005b8db30bc668eef51488a7a425486e0c143a35f06642a21b5272bc",
    "tests/elite_remediation/test_support_contract_binding_variants.py": "72ef2f4f30dc64c55dfffc739eae964d7c7c146bb3186004668f81a6237674c9",
    "tests/test_canonical_market_semantics.py": "ee05f31e9b7490e0484656155e2cac8d899a189b45529667c1ba4acddfa4c621",
    "tests/test_settlement_rules.py": "fc4f8c087908616f7b73796a07073e852491131b2c6c351fb3e80ee9e4519975",
    "tests/security/test_provider_failover_rollback.py": "96cbc8ada62c957c37ae01b8f86918ac5c54aaa8cd309baf9c619db7d681263c",
    "docs/elite_remediation/support_contract_bindings/MATRIX_ELITE_SUPPORT_CONTRACT_BINDING_REGISTRY_R2.json": "9bc2a54b09fada44d4ebc5a49d7237e895b7ec2e358894ef61879c49b9657688",
    "docs/elite_remediation/support_contract_bindings/MATRIX_ELITE_SUPPORT_CONTRACT_BINDING_DESIGN_R2.md": "3c18748cf78e7e426ed814a7ceff60bc3ffdf170795a4fe1051ea99208214250",
}
TARGET_PATHS = tuple((*EXPECTED_TARGET_HASHES.keys(), TARGET_PATH))

R49_HISTORICAL_HASHES = {
    "matrix_elite/support_contract_bindings.py": "d43449b5429b0ba197c27058c02cf0e3db23cd4a36762ead81ea14143fe2fa78",
    "tools/elite_evidence/MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_AUDITOR_R1.py": "a6ffb1b6838860c2c4a5eb12ea3190f2c2fbe0480ed8839ab156c8b4cdf42d15",
    "tests/elite_remediation/test_support_contract_version_bindings.py": "50fdf9dbecf1ec690fee71f63a5fa8b624ac1c8b9f2ff903bf9bf607af7aabc9",
    "docs/elite_remediation/support_contract_bindings/MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_REGISTRY_R1.json": "a02d3807a39a800e783a785c172689f6396773db544f0b0e8d301ee2482f2a1b",
    "docs/elite_remediation/support_contract_bindings/MATRIX_ELITE_SUPPORT_CONTRACT_VERSION_BINDING_DESIGN_R1.md": "6c7ffd170da3e485bf6af06ed281c822ce89222e1ca4cfa624c0c6320927ccaa",
}

FORBIDDEN_RESULT_KEYS = {
    "roi", "win_rate", "hit_rate", "brier", "logloss", "profit", "profitability",
    "pnl", "wins", "losses", "campaign_result", "campaign_results", "realized_ev",
    "model_edge", "net_return", "ece", "calibration_error",
}
REQUIRED_FALSE_BOUNDARIES = (
    "support_declared",
    "supportability_pack_ready",
    "candidate_inventory_generated",
    "selection_r2_executed",
    "builder_r2_executed",
    "registry_r3_executed",
    "freeze_r3_executed",
    "performance_information_used_for_scope_selection",
    "controlled_live_admissible",
    "production_admissible",
)


def _sha_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "GIT_COMMAND_FAILED:" + " ".join(args) + ":" +
            result.stderr.decode("utf-8", errors="replace").strip()
        )
    return result


def _git_text(root: Path, *args: str) -> str:
    return _git(root, *args).stdout.decode("utf-8", errors="strict").strip()


def _git_blob(root: Path, head: str, relative_path: str) -> bytes:
    return _git(root, "show", f"{head}:{relative_path}").stdout


def _git_index_blob(root: Path, relative_path: str) -> bytes:
    return _git(root, "show", f":{relative_path}").stdout


def _load_binding_module(root: Path):
    path = root / "matrix_elite/support_contract_binding_variants.py"
    spec = importlib.util.spec_from_file_location("matrix_r51_binding_variants_audit", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R51_BINDING_MODULE_LOAD_SPEC_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scan_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key).lower())
            keys.update(_scan_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_scan_keys(item))
    return keys


def _target_bytes(root: Path, relative_path: str, *, committed_head: str | None) -> bytes:
    if committed_head is None:
        return (root / relative_path).read_bytes()
    return _git_blob(root, committed_head, relative_path)


def _verify_exact_target_fileset(root: Path) -> int:
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
    }
    expected = set(TARGET_PATHS)
    if actual != expected:
        raise RuntimeError(
            "TARGET_FILESET_MISMATCH:missing=" + repr(sorted(expected - actual)) +
            ":extra=" + repr(sorted(actual - expected))
        )
    return len(actual)


def _verify_target_hashes(root: Path, *, committed_head: str | None = None) -> dict[str, str]:
    actual: dict[str, str] = {}
    for relative_path, expected in EXPECTED_TARGET_HASHES.items():
        if committed_head is None and not (root / relative_path).is_file():
            raise RuntimeError(f"TARGET_FILE_MISSING:{relative_path}")
        digest = _sha_bytes(_target_bytes(root, relative_path, committed_head=committed_head))
        if digest != expected:
            raise RuntimeError(f"TARGET_SHA_MISMATCH:{relative_path}:{digest}:{expected}")
        actual[relative_path] = digest
    if committed_head is None and not (root / TARGET_PATH).is_file():
        raise RuntimeError(f"TARGET_FILE_MISSING:{TARGET_PATH}")
    if committed_head is not None:
        _git_blob(root, committed_head, TARGET_PATH)
    return actual


def _verify_registry_semantics(root: Path):
    module = _load_binding_module(root)
    module.validate_binding_registry()
    if tuple(module.REQUIRED_CONTROLS) != tuple(module.PREDICTIVE_CONTROLS + module.LIVE_CONTROLS + module.FAILOVER_CONTROLS):
        raise RuntimeError("R51_REQUIRED_CONTROL_ORDER_MISMATCH")
    if len(module.BINDING_VARIANTS) != 21 or len({x.control_id for x in module.BINDING_VARIANTS}) != 21:
        raise RuntimeError("R51_CONTROL_VARIANT_COUNT_MISMATCH")
    if len(module.EXPECTED_VERSION_FIELDS) != 19 or len(set(module.EXPECTED_VERSION_FIELDS)) != 19:
        raise RuntimeError("R51_VERSION_FIELD_COUNT_MISMATCH")
    mapped = tuple(
        module.VERSION_FIELD_BY_CONTROL[x.control_id]
        for x in module.BINDING_VARIANTS
        if x.control_id in module.VERSION_FIELD_BY_CONTROL
    )
    if len(mapped) != 19 or set(mapped) != set(module.EXPECTED_VERSION_FIELDS):
        raise RuntimeError("R51_VERSION_FIELD_MAPPING_MISMATCH")
    if module.CANONICAL_API_FOOTBALL_PROVIDER_KEY != EXPECTED_PROVIDER_KEY:
        raise RuntimeError("R51_PROVIDER_KEY_MISMATCH")
    if module.registry_fingerprint() != EXPECTED_REGISTRY_FINGERPRINT:
        raise RuntimeError("R51_REGISTRY_FINGERPRINT_MISMATCH")

    registry_path = root / "docs/elite_remediation/support_contract_bindings/MATRIX_ELITE_SUPPORT_CONTRACT_BINDING_REGISTRY_R2.json"
    disk_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if disk_payload != module.registry_payload():
        raise RuntimeError("R51_REGISTRY_JSON_PYTHON_PAYLOAD_MISMATCH")
    if disk_payload.get("support_status") != "NOT_EVALUATED":
        raise RuntimeError("R51_REGISTRY_SUPPORT_STATUS_MISMATCH")
    for key in REQUIRED_FALSE_BOUNDARIES:
        if disk_payload.get(key) is not False:
            raise RuntimeError(f"R51_REGISTRY_BOUNDARY_MISMATCH:{key}")
    if tuple(disk_payload.get("expected_version_fields", ())) != tuple(module.EXPECTED_VERSION_FIELDS):
        raise RuntimeError("R51_REGISTRY_EXACT_VERSION_FIELDS_MISMATCH")
    for row in disk_payload.get("variants", []):
        expected_field = module.VERSION_FIELD_BY_CONTROL.get(row["control_id"])
        if row.get("version_field") != expected_field:
            raise RuntimeError(f"R51_REGISTRY_VARIANT_VERSION_FIELD_MISMATCH:{row['control_id']}")
        if row.get("support_status") != "NOT_EVALUATED" or row.get("support_declared") is not False:
            raise RuntimeError(f"R51_VARIANT_SUPPORT_PROMOTION_FORBIDDEN:{row['control_id']}")
    forbidden = sorted(_scan_keys(disk_payload).intersection(FORBIDDEN_RESULT_KEYS))
    if forbidden:
        raise RuntimeError("R51_REGISTRY_FORBIDDEN_RESULT_KEYS:" + ",".join(forbidden))
    return module, disk_payload


def _verify_anchor_bytes(relative_path: str, raw: bytes, anchors: Iterable[str]) -> None:
    text = raw.decode("utf-8-sig", errors="strict")
    for anchor in anchors:
        if anchor == "test_":
            raise RuntimeError(f"GENERIC_TEST_ANCHOR_FORBIDDEN:{relative_path}")
        if anchor not in text:
            raise RuntimeError(f"EVIDENCE_ANCHOR_MISSING:{relative_path}:{anchor}")


_TEXT_EVIDENCE_SUFFIXES = {
    ".py",
    ".json",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
}


def _lf_bytes(raw: bytes) -> bytes:
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _verify_historical_evidence_sha(
    relative_path: str,
    raw_git_blob: bytes,
    expected_sha256: str,
) -> str:
    exact = _sha_bytes(raw_git_blob)
    if exact == expected_sha256:
        return "GIT_BLOB_EXACT"

    suffix = Path(relative_path).suffix.lower()
    if suffix not in _TEXT_EVIDENCE_SUFFIXES:
        raise RuntimeError(
            f"EVIDENCE_SHA_MISMATCH:{relative_path}:{exact}:{expected_sha256}"
        )

    lf = _lf_bytes(raw_git_blob)
    crlf = lf.replace(b"\n", b"\r\n")
    candidates = {
        "LF_TEXT_EQUIVALENT": _sha_bytes(lf),
        "CRLF_TEXT_EQUIVALENT": _sha_bytes(crlf),
    }
    for mode, digest in candidates.items():
        if digest == expected_sha256:
            return mode

    raise RuntimeError(
        "EVIDENCE_SHA_MISMATCH:"
        f"{relative_path}:git_blob={exact}:"
        f"lf={candidates['LF_TEXT_EQUIVALENT']}:"
        f"crlf={candidates['CRLF_TEXT_EQUIVALENT']}:"
        f"expected={expected_sha256}"
    )


def _verify_repo_evidence(root: Path, module: object, *, committed_head_for_targets: str | None = None) -> tuple[int, int]:
    checked_refs = 0
    unique_paths: set[str] = set()
    target_set = set(TARGET_PATHS)
    for variant in module.BINDING_VARIANTS:
        for ref in (*variant.implementation_refs, *variant.test_refs):
            if ref.path in target_set:
                raw = _target_bytes(root, ref.path, committed_head=committed_head_for_targets)
                digest = _sha_bytes(raw)
                if digest != ref.sha256:
                    raise RuntimeError(
                        f"EVIDENCE_SHA_MISMATCH:{ref.path}:{digest}:{ref.sha256}"
                    )
            else:
                raw = _git_blob(root, BASELINE_HEAD, ref.path)
                _verify_historical_evidence_sha(
                    ref.path,
                    raw,
                    ref.sha256,
                )
            _verify_anchor_bytes(ref.path, raw, ref.anchors)
            checked_refs += 1
            unique_paths.add(ref.path)
    return checked_refs, len(unique_paths)


def _verify_target_new_evidence(root: Path, module: object) -> tuple[int, int]:
    target_set = set(TARGET_PATHS)
    refs = []
    for variant in module.BINDING_VARIANTS:
        refs.extend(ref for ref in (*variant.implementation_refs, *variant.test_refs) if ref.path in target_set)
    unique: set[str] = set()
    for ref in refs:
        raw = (root / ref.path).read_bytes()
        digest = _sha_bytes(raw)
        if digest != ref.sha256:
            raise RuntimeError(f"TARGET_EVIDENCE_SHA_MISMATCH:{ref.path}:{digest}:{ref.sha256}")
        _verify_anchor_bytes(ref.path, raw, ref.anchors)
        unique.add(ref.path)
    return len(refs), len(unique)


def _verify_r49_history(root: Path, *, head: str) -> int:
    verified = 0
    for relative_path, expected in R49_HISTORICAL_HASHES.items():
        digest = _sha_bytes(_git_blob(root, head, relative_path))
        if digest != expected:
            raise RuntimeError(f"R49_HISTORICAL_SHA_MISMATCH:{relative_path}:{digest}:{expected}")
        verified += 1
    return verified


def _verify_precommit_repository_state(root: Path, expected_branch: str) -> dict[str, object]:
    branch = _git_text(root, "branch", "--show-current")
    head = _git_text(root, "rev-parse", "HEAD")
    if branch != expected_branch:
        raise RuntimeError(f"REPOSITORY_BRANCH_MISMATCH:{branch}")
    if head != BASELINE_HEAD:
        raise RuntimeError(f"REPOSITORY_HEAD_MISMATCH:{head}")
    if _git_text(root, "stash", "list"):
        raise RuntimeError("REPOSITORY_STASH_NOT_EMPTY")
    if _git_text(root, "diff", "--cached", "--name-only"):
        raise RuntimeError("R51_PRECOMMIT_INDEX_MUST_BE_EMPTY")

    for relative_path in TARGET_PATHS:
        if _git(root, "cat-file", "-e", f"{BASELINE_HEAD}:{relative_path}", check=False).returncode == 0:
            raise RuntimeError(f"R51_ADD_ONLY_PATH_ALREADY_EXISTS_AT_BASELINE:{relative_path}")

    expected_status = {f"?? {path}" for path in TARGET_PATHS}
    status_lines = set(filter(None, _git_text(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()))
    if status_lines != expected_status:
        raise RuntimeError(
            "R51_WORKTREE_FILESET_MISMATCH:missing=" + repr(sorted(expected_status - status_lines)) +
            ":extra=" + repr(sorted(status_lines - expected_status))
        )
    return {
        "repository_branch": branch,
        "repository_head": head,
        "stash_empty": True,
        "index_empty": True,
        "exact_untracked_r51_files": len(status_lines),
        "r49_historical_files_verified": _verify_r49_history(root, head=BASELINE_HEAD),
    }


def _verify_staged_repository_state(root: Path, expected_branch: str) -> dict[str, object]:
    branch = _git_text(root, "branch", "--show-current")
    head = _git_text(root, "rev-parse", "HEAD")
    if branch != expected_branch:
        raise RuntimeError(f"REPOSITORY_BRANCH_MISMATCH:{branch}")
    if head != BASELINE_HEAD:
        raise RuntimeError(f"REPOSITORY_HEAD_MISMATCH:{head}")
    if _git_text(root, "stash", "list"):
        raise RuntimeError("REPOSITORY_STASH_NOT_EMPTY")
    if _git_text(root, "diff", "--name-only"):
        raise RuntimeError("R51_STAGED_MODE_UNSTAGED_DIFF_FORBIDDEN")

    staged = set(filter(None, _git_text(root, "diff", "--cached", "--name-only", "--diff-filter=A").splitlines()))
    if staged != set(TARGET_PATHS):
        raise RuntimeError(
            "R51_STAGED_FILESET_MISMATCH:missing=" + repr(sorted(set(TARGET_PATHS) - staged)) +
            ":extra=" + repr(sorted(staged - set(TARGET_PATHS)))
        )
    all_staged = set(filter(None, _git_text(root, "diff", "--cached", "--name-only").splitlines()))
    if all_staged != set(TARGET_PATHS):
        raise RuntimeError("R51_STAGED_NON_ADD_CHANGE_FORBIDDEN")

    for relative_path in TARGET_PATHS:
        if _git(root, "cat-file", "-e", f"{BASELINE_HEAD}:{relative_path}", check=False).returncode == 0:
            raise RuntimeError(f"R51_STAGED_ADD_ONLY_VIOLATION:{relative_path}")
        worktree = (root / relative_path).read_bytes()
        index = _git_index_blob(root, relative_path)
        if worktree != index:
            raise RuntimeError(f"R51_STAGED_BYTE_MISMATCH:{relative_path}")
        if relative_path in EXPECTED_TARGET_HASHES:
            digest = _sha_bytes(index)
            if digest != EXPECTED_TARGET_HASHES[relative_path]:
                raise RuntimeError(f"R51_STAGED_SHA_MISMATCH:{relative_path}:{digest}")

    return {
        "repository_branch": branch,
        "repository_head": head,
        "stash_empty": True,
        "unstaged_diff_empty": True,
        "exact_staged_add_file_count": len(staged),
        "r49_historical_files_verified": _verify_r49_history(root, head=BASELINE_HEAD),
    }


def _verify_postcommit_repository_state(root: Path, expected_branch: str) -> tuple[dict[str, object], str]:
    branch = _git_text(root, "branch", "--show-current")
    head = _git_text(root, "rev-parse", "HEAD")
    if branch != expected_branch:
        raise RuntimeError(f"REPOSITORY_BRANCH_MISMATCH:{branch}")
    if head == BASELINE_HEAD:
        raise RuntimeError("R51_POSTCOMMIT_HEAD_DID_NOT_ADVANCE")
    parents = _git_text(root, "rev-list", "--parents", "-n", "1", head).split()
    if len(parents) != 2 or parents[1] != BASELINE_HEAD:
        raise RuntimeError("R51_POSTCOMMIT_PARENT_MISMATCH")
    subject = _git_text(root, "show", "-s", "--format=%s", head)
    if subject != EXPECTED_COMMIT_SUBJECT:
        raise RuntimeError(f"R51_POSTCOMMIT_SUBJECT_MISMATCH:{subject}")
    if _git_text(root, "stash", "list"):
        raise RuntimeError("REPOSITORY_STASH_NOT_EMPTY")
    status = _git_text(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise RuntimeError("R51_POSTCOMMIT_WORKTREE_NOT_CLEAN:" + status.replace("\n", "|"))
    changed = set(filter(None, _git_text(root, "diff-tree", "--no-commit-id", "--name-only", "-r", head).splitlines()))
    if changed != set(TARGET_PATHS):
        raise RuntimeError(
            "R51_POSTCOMMIT_FILESET_MISMATCH:missing=" + repr(sorted(set(TARGET_PATHS) - changed)) +
            ":extra=" + repr(sorted(changed - set(TARGET_PATHS)))
        )
    for relative_path in TARGET_PATHS:
        if _git(root, "cat-file", "-e", f"{BASELINE_HEAD}:{relative_path}", check=False).returncode == 0:
            raise RuntimeError(f"R51_POSTCOMMIT_ADD_ONLY_VIOLATION:{relative_path}")
    if _file_sha(root / TARGET_PATH) != _sha_bytes(_git_blob(root, head, TARGET_PATH)):
        raise RuntimeError("R51_POSTCOMMIT_AUDITOR_WORKTREE_COMMIT_MISMATCH")
    return ({
        "repository_branch": branch,
        "repository_head": head,
        "repository_parent_head": BASELINE_HEAD,
        "commit_subject": subject,
        "stash_empty": True,
        "worktree_clean": True,
        "exact_commit_file_count": len(changed),
        "r49_historical_files_verified": _verify_r49_history(root, head=head),
    }, head)


def audit(root: Path, mode: str, expected_branch: str) -> dict[str, object]:
    root = root.resolve()
    committed_head: str | None = None
    repository_state: dict[str, object] | None = None
    exact_target_file_count: int | None = None

    if mode == "target":
        exact_target_file_count = _verify_exact_target_fileset(root)
    elif mode == "repository":
        repository_state = _verify_precommit_repository_state(root, expected_branch)
    elif mode == "staged":
        repository_state = _verify_staged_repository_state(root, expected_branch)
    elif mode == "postcommit":
        repository_state, committed_head = _verify_postcommit_repository_state(root, expected_branch)
    else:
        raise RuntimeError("AUDIT_MODE_INVALID")

    target_hashes = _verify_target_hashes(root, committed_head=committed_head)
    module, payload = _verify_registry_semantics(root)

    if mode == "target":
        checked_refs, unique_evidence_paths = _verify_target_new_evidence(root, module)
    else:
        checked_refs, unique_evidence_paths = _verify_repo_evidence(
            root, module, committed_head_for_targets=committed_head
        )

    producer_sha = _file_sha(root / TARGET_PATH)
    if committed_head is not None and producer_sha != _sha_bytes(_git_blob(root, committed_head, TARGET_PATH)):
        raise RuntimeError("R51_POSTCOMMIT_PRODUCER_SHA_MISMATCH")

    result = {
        "target": "PASS_TARGET_BYTES",
        "repository": "PASS_PRECOMMIT",
        "staged": "PASS_STAGED_PRECOMMIT",
        "postcommit": "PASS_POSTCOMMIT",
    }[mode]
    next_gate = {
        "target": "R51_DETERMINISTIC_TARGET_FREEZE_THEN_REPOSITORY_PRECOMMIT_AUDIT",
        "repository": "R51_EXACT_STAGE_THEN_STAGED_BYTE_AUDIT",
        "staged": "R51_GOVERNED_EXACT_COMMIT_THEN_POSTCOMMIT_AUDIT",
        "postcommit": "INDEPENDENT_SUBSTANTIVE_REVIEW_BEFORE_SUPPORTABILITY_PACK_CONSTRUCTION",
    }[mode]

    return {
        "schema": SCHEMA,
        "result": result,
        "mode": mode.upper(),
        "producer_sha256": producer_sha,
        "baseline_head": BASELINE_HEAD,
        "expected_branch": expected_branch,
        "expected_commit_subject": EXPECTED_COMMIT_SUBJECT,
        "target_file_count": len(TARGET_PATHS),
        "exact_target_file_count": exact_target_file_count,
        "pinned_target_hash_count_excluding_self": len(EXPECTED_TARGET_HASHES),
        "target_hashes": target_hashes,
        "registry_fingerprint": module.registry_fingerprint(),
        "registry_payload_matches_code": payload == module.registry_payload(),
        "required_control_count": len(module.REQUIRED_CONTROLS),
        "required_version_field_count": len(module.EXPECTED_VERSION_FIELDS),
        "canonical_api_football_provider_key": module.CANONICAL_API_FOOTBALL_PROVIDER_KEY,
        "repository_state": repository_state,
        "checked_evidence_refs": checked_refs,
        "unique_evidence_paths": unique_evidence_paths,
        "repository_mutation_performed": False,
        "network_calls_performed": False,
        "aws_login_performed": False,
        "push_performed": False,
        "performance_information_used_for_scope_selection": False,
        "support_declared": False,
        "support_status": "NOT_EVALUATED",
        "supportability_pack_generated": False,
        "supportability_pack_ready": False,
        "candidate_inventory_generated": False,
        "selection_r2_executed": False,
        "builder_r2_executed": False,
        "registry_r3_executed": False,
        "freeze_r3_executed": False,
        "controlled_live_admissible": False,
        "production_admissible": False,
        "next_gate": next_gate,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=("target", "repository", "staged", "postcommit"), default="target")
    parser.add_argument("--expected-branch", default=EXPECTED_BRANCH)
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.root)
    report = audit(root, args.mode, args.expected_branch)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).resolve()
        try:
            output.relative_to(root.resolve())
        except ValueError:
            pass
        else:
            raise RuntimeError("AUDIT_OUTPUT_MUST_BE_OUTSIDE_REPOSITORY_OR_TARGET_ROOT")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
