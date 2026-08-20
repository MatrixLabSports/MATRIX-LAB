from __future__ import annotations

from pathlib import Path
import sys

# Direct execution uses scripts/ as sys.path[0] on Windows/Linux.
# Add the repository root before importing the application package.
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


def _ast_safety(root: Path) -> None:
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
            if not isinstance(
                node,
                ast.Dict,
            ):
                continue

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

    if violations:
        raise SystemExit(
            "SAFETY_INVARIANT_VIOLATION\n"
            + "\n".join(
                violations
            )
        )


def main() -> int:
    policy = (
        build_repository_quality_policy()
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

    _ast_safety(ROOT)

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
            "git",
            "diff",
            "--check",
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
