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



def _provider_production_readiness_boundary(
    root: Path,
) -> None:
    violations: list[str] = []

    required_paths = {
        "rights": (
            root
            / "app"
            / "core"
            / "provider_rights_authorization.py"
        ),
        "legal_evidence": (
            root
            / "app"
            / "core"
            / "provider_legal_evidence.py"
        ),
        "contract_endpoint": (
            root
            / "app"
            / "core"
            / "provider_contract_endpoint_binding.py"
        ),
        "attempt_intent": (
            root
            / "app"
            / "core"
            / "provider_attempt_intent.py"
        ),
        "attempt_certification": (
            root
            / "app"
            / "core"
            / "provider_attempt_certification.py"
        ),
        "recovery": (
            root
            / "app"
            / "core"
            / "provider_interruption_recovery.py"
        ),
        "runtime_reconciliation": (
            root
            / "app"
            / "core"
            / "runtime_reconciliation.py"
        ),
        "governed_client": (
            root
            / "app"
            / "providers"
            / "api_football"
            / "governed_client.py"
        ),
        "contracts": (
            root
            / "app"
            / "providers"
            / "api_football"
            / "request_contracts.py"
        ),
        "shadow": (
            root
            / "app"
            / "providers"
            / "api_football"
            / "shadow_runtime.py"
        ),
    }

    for name, path in required_paths.items():
        if not path.exists():
            violations.append(
                f"MISSING_PROVIDER_READINESS_MODULE:{name}:{path}"
            )

    if violations:
        raise SystemExit(
            "PROVIDER_PRODUCTION_READINESS_BOUNDARY_VIOLATION\n"
            + "\n".join(
                violations
            )
        )

    sources = {
        name: path.read_text(
            encoding="utf-8-sig"
        )
        for name, path
        in required_paths.items()
    }

    requirements = {
        "rights": (
            "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED",
            "legal_evidence_store",
        ),
        "legal_evidence": (
            "HUMAN_VERIFIED",
            "SQLiteProviderLegalEvidenceStore",
        ),
        "contract_endpoint": (
            "endpoint_manifest_id",
            "request_contract_id",
            "CONTRACT_ENDPOINT_BINDING_MISMATCH",
        ),
        "attempt_intent": (
            "ProviderAttemptIntentEvidence",
            "permit_id TEXT NOT NULL UNIQUE",
            "list_verified_for_run",
        ),
        "attempt_certification": (
            "NO_PHYSICAL_ATTEMPTS_TO_CERTIFY",
            "NETWORK_PERMIT_REUSED_ACROSS_ATTEMPTS",
            "enforce_provider_attempt_certification",
        ),
        "recovery": (
            "INTERRUPTED_UNKNOWN_OUTCOME",
            "recover_all_started_only_network_attempts",
            "scan_started_only_network_attempts",
            "pre_network_binding_intent_id",
            "request_contract_id",
        ),
        "runtime_reconciliation": (
            "reconcile_runtime_provider_readiness",
            "recover_started_only_network_attempt",
            "enforce_provider_attempt_certification",
            "PROVIDER_RIGHTS_NOT_AUTHORIZED",
        ),
        "governed_client": (
            "attempt_intent_store",
            "ATTEMPT_INTENT_STORE_REQUIRED",
        ),
        "contracts": (
            "register_api_football_contract_endpoint_bindings",
            "endpoint_manifest_ids",
        ),
        "shadow": (
            "GovernedProviderRequestClient",
            "ProviderNetworkAuthority",
            "BindingAuditPinnedHttpsTransport",
            "JitSecretPinnedHttpsTransport",
            "ShadowNoNetworkSession",
            "network_call_performed=False",
            "secret_resolved=False",
        ),
    }

    for name, tokens in requirements.items():
        source = sources[name]
        for token in tokens:
            if token not in source:
                violations.append(
                    f"{name}:MISSING_PROVIDER_READINESS_TOKEN:{token}"
                )

    shadow = sources["shadow"]

    for forbidden in (
        "import requests",
        "requests.get(",
        "requests.post(",
        "socket.create_connection",
    ):
        if forbidden in shadow:
            violations.append(
                f"shadow:SHADOW_NETWORK_BYPASS:{forbidden}"
            )

    combined = "\n".join(
        sources.values()
    )

    for forbidden in (
        "real_provider_execution_authorized=True",
        "automatic_provider_switch=True",
        "automatic_wagering=True",
    ):
        if forbidden in combined:
            violations.append(
                f"PROVIDER_READINESS_FORBIDDEN_TRUE:{forbidden}"
            )

    if violations:
        raise SystemExit(
            "PROVIDER_PRODUCTION_READINESS_BOUNDARY_VIOLATION\n"
            + "\n".join(
                violations
            )
        )



def _provider_network_activation_hardening_boundary(
    root: Path,
) -> None:
    violations: list[str] = []

    required_paths = {
        "transport": (
            root
            / "app"
            / "core"
            / "pinned_https_transport.py"
        ),
        "connector_trust": (
            root
            / "app"
            / "core"
            / "provider_connector_trust.py"
        ),
        "activation_readiness": (
            root
            / "app"
            / "core"
            / "provider_activation_readiness.py"
        ),
        "activation_rehearsal": (
            root
            / "app"
            / "core"
            / "provider_activation_rehearsal.py"
        ),
    }

    for name, candidate in required_paths.items():
        if not candidate.exists():
            violations.append(
                "P127_P131_MISSING_MODULE:"
                + name
            )

    if violations:
        raise SystemExit(
            "PROVIDER_NETWORK_ACTIVATION_HARDENING_VIOLATION\n"
            + "\n".join(
                violations
            )
        )

    sources = {
        name: candidate.read_text(
            encoding="utf-8-sig"
        )
        for name, candidate
        in required_paths.items()
    }

    requirements = {
        "transport": (
            "TLSVersion.TLSv1_2",
            "DUPLICATE_HTTP_HEADER",
            "NON_CANONICAL_HTTP_PATH",
            "HTTP_RESPONSE_FRAMING_CONFLICT",
            "CONTENT_LENGTH_MISMATCH",
            "UNSUPPORTED_TRANSFER_ENCODING",
            "settimeout",
        ),
        "connector_trust": (
            "require_trusted_production_connector",
            "DEFAULT_SOCKET_CONNECTOR_REQUIRED",
            "TLS12_MINIMUM_REQUIRED",
        ),
        "activation_readiness": (
            "CANONICAL_SECRET_RESOLVER_REQUIRED",
            "NONEMPTY_REQUEST_CONTRACT_EVIDENCE_REQUIRED",
            "TECHNICALLY_READY_RIGHTS_BLOCKED",
            "PROVIDER_ACTIVATION_SCHEMA_NOT_ENABLED",
        ),
        "activation_rehearsal": (
            "REHEARSAL_CERTIFIED_FAIL_CLOSED",
            "SHADOW_NETWORK_CALL_DETECTED",
            "INTERRUPTION_RECOVERY_REHEARSAL_REQUIRED",
            "PROVIDER_ACTIVATION_REHEARSAL_SCHEMA_NOT_ENABLED",
        ),
    }

    for name, tokens in requirements.items():
        source_text = sources[
            name
        ]

        for token in tokens:
            if token not in source_text:
                violations.append(
                    name
                    + ":MISSING_P127_P131_TOKEN:"
                    + token
                )

    combined = "\n".join(
        sources.values()
    )

    for forbidden in (
        "real_provider_execution_authorized=True",
        "automatic_provider_switch=True",
        "automatic_wagering=True",
    ):
        if forbidden in combined:
            violations.append(
                "P127_P131_FORBIDDEN_TRUE:"
                + forbidden
            )

    if violations:
        raise SystemExit(
            "PROVIDER_NETWORK_ACTIVATION_HARDENING_VIOLATION\n"
            + "\n".join(
                violations
            )
        )




def _provider_network_activation_semantic_boundary(
    root: Path,
) -> None:
    violations: list[str] = []

    paths = {
        "transport": (
            root / "app" / "core"
            / "pinned_https_transport.py"
        ),
        "connector": (
            root / "app" / "core"
            / "provider_connector_trust.py"
        ),
        "readiness": (
            root / "app" / "core"
            / "provider_activation_readiness.py"
        ),
        "rehearsal": (
            root / "app" / "core"
            / "provider_activation_rehearsal.py"
        ),
        "shadow_evidence": (
            root / "app" / "core"
            / "provider_shadow_rehearsal_evidence.py"
        ),
        "shadow_runtime": (
            root / "app" / "providers"
            / "api_football"
            / "shadow_runtime.py"
        ),
        "governed_client": (
            root / "app" / "providers"
            / "api_football"
            / "governed_client.py"
        ),
        "authoritative_admission": (
            root / "app" / "core"
            / "authoritative_runtime_admission.py"
        ),
    }

    trees: dict[str, ast.AST] = {}
    sources: dict[str, str] = {}

    for name, candidate in paths.items():
        if not candidate.exists():
            violations.append(
                "P127_P131_SEMANTIC_MISSING:"
                + name
            )
            continue

        text = candidate.read_text(
            encoding="utf-8-sig"
        )
        sources[name] = text

        try:
            trees[name] = ast.parse(
                text,
                filename=str(
                    candidate
                ),
            )
        except SyntaxError:
            violations.append(
                "P127_P131_SEMANTIC_AST_FAILURE:"
                + name
            )

    def function_args(
        module_name: str,
        function_name: str,
    ) -> set[str]:
        tree = trees.get(
            module_name
        )

        if tree is None:
            return set()

        for node in tree.body:
            if (
                isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                    ),
                )
                and node.name
                == function_name
            ):
                return {
                    argument.arg
                    for argument
                    in (
                        list(
                            node.args.posonlyargs
                        )
                        + list(
                            node.args.args
                        )
                        + list(
                            node.args.kwonlyargs
                        )
                    )
                }

        return set()

    readiness_args = function_args(
        "readiness",
        "certify_provider_activation_readiness",
    )

    for required in (
        "endpoint_authorization_registry",
        "endpoint_base_url",
        "as_of",
        "legal_evidence_ids",
        "attempt_intent_store",
    ):
        if required not in readiness_args:
            violations.append(
                "P130_MISSING_SEMANTIC_ARGUMENT:"
                + required
            )

    rehearsal_args = function_args(
        "rehearsal",
        "certify_provider_activation_rehearsal",
    )

    for required in (
        "shadow_evidence_store",
        "shadow_readiness_evidence_id",
        "interruption_recovery_store",
        "interruption_permit_ids",
    ):
        if required not in rehearsal_args:
            violations.append(
                "P131_MISSING_DURABLE_ARGUMENT:"
                + required
            )

    client_args = function_args(
        "governed_client",
        "build_governed_api_football_client",
    )

    for required in (
        "activation_readiness_certification",
        "activation_rehearsal_certification",
    ):
        if required not in client_args:
            violations.append(
                "OFFICIAL_CLIENT_MISSING_ACTIVATION_GATE:"
                + required
            )

    authoritative_args = function_args(
        "authoritative_admission",
        "evaluate_authoritative_provider_runtime_admission",
    )

    for required in (
        "activation_readiness_certification",
        "activation_rehearsal_certification",
    ):
        if required not in authoritative_args:
            violations.append(
                "AUTHORITATIVE_ADMISSION_MISSING_ACTIVATION_GATE:"
                + required
            )

    required_source_tokens = {
        "transport": (
            "CONTENT_LENGTH_HEADER_FORBIDDEN",
            "TRANSFER_ENCODING_HEADER_FORBIDDEN",
            "HOP_BY_HOP_HEADER_FORBIDDEN",
        ),
        "connector": (
            "type(transport) is StdlibPinnedHttpsTransport",
            "PINNED_TRANSPORT_METHOD_OVERRIDE_FORBIDDEN",
        ),
        "readiness": (
            "getattr(governed_transport, \"attempt_intent_store\", None)",
            "ENDPOINT_MANIFEST_SEMANTIC_AUTHORIZATION_REQUIRED",
            "NONEMPTY_LEGAL_EVIDENCE_REQUIRED",
        ),
        "rehearsal": (
            "shadow_evidence_store.get_verified",
            "interruption_recovery_store.get_by_permit",
            "SHADOW_EVIDENCE_STORE_INTEGRITY_FAILED",
        ),
        "shadow_runtime": (
            "shadow_evidence_store",
            "build_provider_shadow_rehearsal_evidence",
        ),
        "governed_client": (
            "require_provider_activation_authorized",
            "require_activation_rehearsal_for_real_execution",
        ),
        "authoritative_admission": (
            "evaluate_authoritative_provider_runtime_admission",
            "verify_provider_activation_readiness_certification",
            "verify_provider_activation_rehearsal_certification",
        ),
    }

    for name, tokens in required_source_tokens.items():
        text = sources.get(
            name,
            "",
        )

        for token in tokens:
            if token not in text:
                violations.append(
                    name
                    + ":P127_P131_SEMANTIC_TOKEN_MISSING:"
                    + token
                )

    if violations:
        raise SystemExit(
            "PROVIDER_NETWORK_ACTIVATION_SEMANTIC_BOUNDARY_VIOLATION\n"
            + "\n".join(
                violations
            )
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
    _provider_production_readiness_boundary(ROOT)
    _provider_network_activation_hardening_boundary(ROOT)
    _provider_network_activation_semantic_boundary(ROOT)
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
