from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(ROOT),
    )

import ast
import subprocess

from app.core.repository_quality_policy import (
    build_repository_quality_policy,
)
from app.core.tracked_secret_scanner import (
    scan_tracked_repository,
)


FORBIDDEN_TRUE = {
    "automatic_deploy",
    "automatic_model_promotion",
    "automatic_provider_switch",
    "automatic_wagering",
    "automatic_schema_promotion",
    "automatic_transformation_promotion",
    "raw_secret_persisted",
    "raw_secret_logged",
    "secret_value_fingerprinted",
    "name_join_used",
    "missing_is_zero",
}

IMPLEMENTED_CHECKS = {
    "compileall",
    "tracked_secret_scan",
    "git_diff_check",
    "sport_boundary",
    "safety_invariants",
}


def _run(
    root: Path,
    args: list[str],
) -> None:
    completed = subprocess.run(
        args,
        cwd=root,
    )

    if completed.returncode != 0:
        raise SystemExit(
            f"GATE_FAILED:{' '.join(args)}"
        )


def _python_minimum(
    minimum: str,
) -> None:
    parts = minimum.split(".")

    if len(parts) < 2:
        raise SystemExit(
            "INVALID_PYTHON_MINIMUM_POLICY"
        )

    required = (
        int(parts[0]),
        int(parts[1]),
    )

    if sys.version_info[:2] < required:
        raise SystemExit(
            "PYTHON_VERSION_BELOW_POLICY"
        )


def _safety_ast(root: Path) -> None:
    violations: list[str] = []

    for path in (
        root / "app"
    ).rglob("*.py"):
        source = path.read_text(
            encoding="utf-8-sig"
        )
        tree = ast.parse(
            source,
            filename=str(path),
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(
                    node.keys,
                    node.values,
                ):
                    if (
                        isinstance(
                            key,
                            ast.Constant,
                        )
                        and isinstance(
                            key.value,
                            str,
                        )
                        and key.value
                        in FORBIDDEN_TRUE
                        and isinstance(
                            value,
                            ast.Constant,
                        )
                        and value.value
                        is True
                    ):
                        violations.append(
                            f"{path}:"
                            f"{getattr(node, 'lineno', '?')}:"
                            f"{key.value}=True"
                        )

            elif isinstance(
                node,
                ast.Assign,
            ):
                if (
                    isinstance(
                        node.value,
                        ast.Constant,
                    )
                    and node.value.value
                    is True
                ):
                    for target in node.targets:
                        if (
                            isinstance(
                                target,
                                ast.Name,
                            )
                            and target.id
                            in FORBIDDEN_TRUE
                        ):
                            violations.append(
                                f"{path}:"
                                f"{node.lineno}:"
                                f"{target.id}=True"
                            )

            elif isinstance(
                node,
                ast.AnnAssign,
            ):
                if (
                    isinstance(
                        node.target,
                        ast.Name,
                    )
                    and node.target.id
                    in FORBIDDEN_TRUE
                    and isinstance(
                        node.value,
                        ast.Constant,
                    )
                    and node.value.value
                    is True
                ):
                    violations.append(
                        f"{path}:"
                        f"{node.lineno}:"
                        f"{node.target.id}=True"
                    )

            elif isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if (
                        keyword.arg
                        in FORBIDDEN_TRUE
                        and isinstance(
                            keyword.value,
                            ast.Constant,
                        )
                        and keyword.value.value
                        is True
                    ):
                        violations.append(
                            f"{path}:"
                            f"{node.lineno}:"
                            f"{keyword.arg}=True"
                        )

    if violations:
        raise SystemExit(
            "SAFETY_INVARIANT_VIOLATION\n"
            + "\n".join(
                violations
            )
        )


def _sport_boundary(root: Path) -> None:
    violations: list[str] = []

    roots = {
        "football": root / "app" / "sports" / "football",
        "tennis": root / "app" / "sports" / "tennis",
    }

    for sport, sport_root in roots.items():
        if not sport_root.exists():
            continue

        other = (
            "tennis"
            if sport == "football"
            else "football"
        )
        forbidden_prefix = (
            f"app.sports.{other}"
        )

        for path in sport_root.rglob(
            "*.py"
        ):
            tree = ast.parse(
                path.read_text(
                    encoding="utf-8-sig"
                ),
                filename=str(path),
            )

            for node in ast.walk(tree):
                if isinstance(
                    node,
                    ast.Import,
                ):
                    for alias in node.names:
                        if alias.name.startswith(
                            forbidden_prefix
                        ):
                            violations.append(
                                f"{path}:"
                                f"{node.lineno}:"
                                f"{alias.name}"
                            )

                elif isinstance(
                    node,
                    ast.ImportFrom,
                ):
                    module = (
                        node.module
                        or ""
                    )

                    if module.startswith(
                        forbidden_prefix
                    ):
                        violations.append(
                            f"{path}:"
                            f"{node.lineno}:"
                            f"{module}"
                        )

    if violations:
        raise SystemExit(
            "SPORT_BOUNDARY_VIOLATION\n"
            + "\n".join(
                violations
            )
        )


def _git_diff_checks(root: Path) -> None:
    _run(
        root,
        [
            "git",
            "diff",
            "--check",
        ],
    )
    _run(
        root,
        [
            "git",
            "diff",
            "--cached",
            "--check",
        ],
    )

    parent = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            "HEAD^",
        ],
        cwd=root,
        capture_output=True,
    )

    if parent.returncode == 0:
        _run(
            root,
            [
                "git",
                "diff",
                "--check",
                "HEAD^",
                "HEAD",
            ],
        )



def _provider_http_boundary(
    root: Path,
) -> None:
    violations: list[str] = []
    legacy_module = "app.providers.api_football.client"
    bootstrap_module = "app.providers.api_football.bootstrap_client"
    governed_http_module = "app.core.governed_provider_http"
    governed_client = "app/providers/api_football/governed_client.py"
    bootstrap_client = "app/providers/api_football/bootstrap_client.py"
    legacy_client = "app/providers/api_football/client.py"

    for path in (root / "app").rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(
            path.read_text(encoding="utf-8-sig"),
            filename=str(path),
        )

        for item in ast.walk(tree):
            if isinstance(item, ast.ImportFrom):
                module = item.module or ""

                if module == legacy_module and relative != bootstrap_client:
                    violations.append(
                        f"{relative}:{item.lineno}:"
                        "OFFICIAL_PROVIDER_LEGACY_BYPASS"
                    )

                if module == bootstrap_module and relative != governed_client:
                    violations.append(
                        f"{relative}:{item.lineno}:"
                        "BOOTSTRAP_PROVIDER_CLIENT_IMPORT"
                    )

                if (
                    module == governed_http_module
                    and any(
                        alias.name == "GovernedProviderHttpSession"
                        for alias in item.names
                    )
                    and relative not in {
                        governed_client,
                        bootstrap_client,
                    }
                ):
                    violations.append(
                        f"{relative}:{item.lineno}:"
                        "DIRECT_GOVERNED_HTTP_SESSION_IMPORT"
                    )

            elif isinstance(item, ast.Import):
                for alias in item.names:
                    if (
                        alias.name == "requests"
                        and relative in {
                            governed_client,
                            bootstrap_client,
                            "app/core/governed_provider_http.py",
                        }
                    ):
                        violations.append(
                            f"{relative}:{item.lineno}:"
                            "REQUESTS_IMPORT_IN_GOVERNED_BOUNDARY"
                        )

            elif isinstance(item, ast.Call):
                if (
                    isinstance(item.func, ast.Attribute)
                    and isinstance(item.func.value, ast.Name)
                    and item.func.value.id == "requests"
                ):
                    verbs = {
                        "get", "post", "put", "patch",
                        "delete", "head", "options", "request",
                    }
                    if item.func.attr in verbs and relative != legacy_client:
                        violations.append(
                            f"{relative}:{item.lineno}:DIRECT_REQUESTS_CALL"
                        )
                    if item.func.attr == "Session" and relative != legacy_client:
                        violations.append(
                            f"{relative}:{item.lineno}:"
                            "UNAUTHORIZED_REQUESTS_SESSION"
                        )

    governed_source = (root / governed_client).read_text(
        encoding="utf-8-sig"
    )
    for required in (
        "GovernedProviderRequestClient",
        "JitSecretPinnedHttpsTransport",
        "BindingAuditPinnedHttpsTransport",
        "require_real_provider_execution_authorized",
    ):
        if required not in governed_source:
            violations.append(
                f"{governed_client}:"
                f"MISSING_OFFICIAL_GOVERNED_COMPONENT:{required}"
            )

    for forbidden in (
        "ApiFootballClient",
        "config.api_key",
        "app.providers.api_football.client",
    ):
        if forbidden in governed_source:
            violations.append(
                f"{governed_client}:"
                f"OFFICIAL_PROVIDER_LEGACY_BYPASS:{forbidden}"
            )

    bootstrap_source = (root / bootstrap_client).read_text(
        encoding="utf-8-sig"
    )
    if (
        "BOOTSTRAP_PROBE" not in bootstrap_source
        or "execute_bootstrap_probe" not in bootstrap_source
    ):
        violations.append(
            f"{bootstrap_client}:BOOTSTRAP_QUARANTINE_REQUIRED"
        )

    if violations:
        raise SystemExit(
            "PROVIDER_HTTP_BOUNDARY_VIOLATION\n"
            + "\n".join(violations)
        )



def _authoritative_runtime_admission_boundary(
    root: Path,
) -> None:
    violations: list[str] = []
    base_module = "app.core.runtime_admission_gate"
    allowed = "app/core/authoritative_runtime_admission.py"

    for path in (root / "app").rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and (node.module or "") == base_module
                and any(alias.name == "evaluate_reconciled_runtime_admission" for alias in node.names)
            ):
                violations.append(f"{relative}:{node.lineno}:BASE_RUNTIME_ADMISSION_IMPORT")

    if violations:
        raise SystemExit(
            "AUTHORITATIVE_RUNTIME_ADMISSION_BOUNDARY_VIOLATION\n"
            + "\n".join(violations)
        )


def main() -> int:
    policy = (
        build_repository_quality_policy()
    )

    declared = set(
        policy.required_static_checks
    )
    unknown = declared - IMPLEMENTED_CHECKS
    missing = IMPLEMENTED_CHECKS - declared

    if unknown or missing:
        raise SystemExit(
            "QUALITY_POLICY_IMPLEMENTATION_MISMATCH:"
            f"unknown={sorted(unknown)}:"
            f"missing={sorted(missing)}"
        )

    _python_minimum(
        policy.python_minimum
    )

    report = scan_tracked_repository(
        ROOT,
        forbidden_names=(
            policy.forbidden_tracked_names
        ),
    )

    if not report.ok:
        details = "\n".join(
            f"{item.path}:{item.rule}"
            for item in report.findings
        )
        raise SystemExit(
            "TRACKED_SECRET_SCAN_FAILED\n"
            + details
        )

    _safety_ast(ROOT)
    _sport_boundary(ROOT)
    _provider_http_boundary(ROOT)
    _authoritative_runtime_admission_boundary(ROOT)
    _git_diff_checks(ROOT)

    _run(
        ROOT,
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "app",
            "tests",
        ],
    )
    _run(
        ROOT,
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
        ],
    )

    print(
        "MATRIX CI QUALITY GATE: PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
