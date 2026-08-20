from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class RepositoryQualityPolicy:
    python_minimum: str
    required_test_command: tuple[str, ...]
    required_static_checks: tuple[str, ...]
    forbidden_tracked_names: tuple[str, ...]
    automatic_deploy: bool
    automatic_model_promotion: bool
    automatic_wagering: bool
    policy_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.repository-quality-policy/1",
            "python_minimum": self.python_minimum,
            "required_test_command": list(
                self.required_test_command
            ),
            "required_static_checks": list(
                self.required_static_checks
            ),
            "forbidden_tracked_names": list(
                self.forbidden_tracked_names
            ),
            "automatic_deploy": self.automatic_deploy,
            "automatic_model_promotion": (
                self.automatic_model_promotion
            ),
            "automatic_wagering": self.automatic_wagering,
            "policy_fingerprint": self.policy_fingerprint,
        }


def build_repository_quality_policy(
    *,
    python_minimum: str = "3.11",
    required_test_command: Sequence[str] = (
        "python",
        "-m",
        "pytest",
        "-q",
    ),
    required_static_checks: Sequence[str] = (
        "compileall",
        "tracked_secret_scan",
        "git_diff_check",
        "sport_boundary",
        "safety_invariants",
    ),
    forbidden_tracked_names: Sequence[str] = (
        ".env",
        ".env.local",
        "id_rsa",
        "id_ed25519",
        "secrets.json",
        "credentials.json",
    ),
) -> RepositoryQualityPolicy:
    if (
        not isinstance(python_minimum, str)
        or not python_minimum.strip()
    ):
        raise ValueError("INVALID_PYTHON_MINIMUM")

    def normalize(
        name: str,
        values: Sequence[str],
    ) -> tuple[str, ...]:
        if (
            isinstance(values, (str, bytes))
            or not values
        ):
            raise ValueError(f"EMPTY_{name}")

        result = tuple(
            str(value).strip()
            for value in values
        )

        if any(not value for value in result):
            raise ValueError(f"INVALID_{name}")

        return result

    tests = normalize(
        "REQUIRED_TEST_COMMAND",
        required_test_command,
    )
    checks = normalize(
        "REQUIRED_STATIC_CHECKS",
        required_static_checks,
    )
    forbidden = tuple(
        sorted(
            set(
                normalize(
                    "FORBIDDEN_TRACKED_NAMES",
                    forbidden_tracked_names,
                )
            )
        )
    )

    base = {
        "schema": "matrix.repository-quality-policy/1",
        "python_minimum": python_minimum.strip(),
        "required_test_command": list(tests),
        "required_static_checks": list(checks),
        "forbidden_tracked_names": list(forbidden),
        "automatic_deploy": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    return RepositoryQualityPolicy(
        python_minimum=python_minimum.strip(),
        required_test_command=tests,
        required_static_checks=checks,
        forbidden_tracked_names=forbidden,
        automatic_deploy=False,
        automatic_model_promotion=False,
        automatic_wagering=False,
        policy_fingerprint=_sha(base),
    )
