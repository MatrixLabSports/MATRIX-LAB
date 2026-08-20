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
    legacy = "app.providers.api_football.client"
    allowed = "app/providers/api_football/governed_client.py"

    for path in (root / "app").rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(
            path.read_text(encoding="utf-8-sig"),
            filename=str(path),
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == legacy and relative != allowed:
                    violations.append(
                        f"{relative}:{node.lineno}:LEGACY_PROVIDER_CLIENT_IMPORT"
                    )

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == legacy and relative != allowed:
                        violations.append(
                            f"{relative}:{node.lineno}:LEGACY_PROVIDER_CLIENT_IMPORT"
                        )

            elif isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "requests"
                ):
                    network_verbs = {
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                        "head",
                        "options",
                        "request",
                    }

                    if (
                        node.func.attr in network_verbs
                        and relative
                        != "app/providers/api_football/client.py"
                    ):
                        violations.append(
                            f"{relative}:{node.lineno}:DIRECT_REQUESTS_CALL"
                        )

                    if (
                        node.func.attr == "Session"
                        and relative
                        not in {
                            "app/providers/api_football/client.py",
                            "app/providers/api_football/governed_client.py",
                        }
                    ):
                        violations.append(
                            f"{relative}:{node.lineno}:UNAUTHORIZED_REQUESTS_SESSION"
                        )

    if violations:
        raise SystemExit(
            "PROVIDER_HTTP_BOUNDARY_VIOLATION\n"
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
