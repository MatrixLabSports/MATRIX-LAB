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
        "attempt_intent_store",
        "network_call_evidence_store",
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
            "AUTHORITATIVE_ACTIVATION_STORE_TYPES_REQUIRED",
            "SQLiteProviderEndpointAuthorizationRegistry",
            "SQLiteProviderLegalEvidenceStore",
            "SQLiteProviderAttemptIntentStore",
        ),
        "rehearsal": (
            "shadow_evidence_store.get_verified",
            "verify_provider_shadow_rehearsal_attestation",
            "interruption_recovery_store.get_by_permit",
            "reconcile_network_attempt_with_recovery",
            "attempt_intent_store",
            "network_call_evidence_store",
            "SHADOW_EVIDENCE_STORE_INTEGRITY_FAILED",
            "INTERRUPTION_ATTEMPT_PROVENANCE_NOT_CROSS_BOUND",
            "AUTHORITATIVE_REHEARSAL_EVIDENCE_REQUIRED",
            "SQLiteProviderInterruptionRecoveryStore",
            "SQLiteProviderAttemptIntentStore",
            "SQLiteProviderNetworkCallEvidenceStore",
        ),
        "shadow_runtime": (
            "shadow_evidence_store",
            "_build_attested_provider_shadow_rehearsal_evidence",
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




def _provider_shadow_rehearsal_provenance_boundary(
    root: Path,
) -> None:
    violations: list[str] = []

    private_issuer = (
        "_build_attested_provider_shadow_rehearsal_evidence"
    )
    allowed_issuer_importer = (
        "app/providers/api_football/shadow_runtime.py"
    )
    evidence_module = (
        "app/core/provider_shadow_rehearsal_evidence.py"
    )

    for candidate in (
        root
        / "app"
    ).rglob(
        "*.py"
    ):
        relative = candidate.relative_to(
            root
        ).as_posix()
        text = candidate.read_text(
            encoding="utf-8-sig"
        )

        try:
            tree = ast.parse(
                text,
                filename=str(
                    candidate
                ),
            )
        except SyntaxError:
            violations.append(
                "SHADOW_PROVENANCE_AST_FAILURE:"
                + relative
            )
            continue

        for node in ast.walk(
            tree
        ):
            if (
                isinstance(
                    node,
                    ast.ImportFrom,
                )
                and any(
                    alias.name
                    == private_issuer
                    for alias
                    in node.names
                )
                and relative
                != allowed_issuer_importer
            ):
                violations.append(
                    f"{relative}:{node.lineno}:"
                    "PRIVATE_SHADOW_ATTESTED_ISSUER_IMPORT"
                )

        if relative != evidence_module:
            for forbidden in (
                "ProviderShadowRehearsalAuthority",
                "_new_provider_shadow_rehearsal_authority",
                "shadow_rehearsal_authority",
            ):
                if forbidden in text:
                    violations.append(
                        f"{relative}:LEGACY_SHADOW_AUTHORITY_SURFACE:"
                        + forbidden
                    )

    evidence_source = (
        root
        / evidence_module
    ).read_text(
        encoding="utf-8-sig"
    )

    for token in (
        "build_provider_shadow_attestation_key_reference",
        "MATRIX_SHADOW_REHEARSAL_ATTESTATION_KEY",
        "resolve_secret_runtime",
        "attestation_key_reference_fingerprint",
        "raw_attestation_key_persisted",
        "hmac.compare_digest",
        "matrix.provider-shadow-rehearsal-evidence/3",
        "verify_provider_shadow_rehearsal_attestation",
    ):
        if token not in evidence_source:
            violations.append(
                "SHADOW_DURABLE_ATTESTATION_TOKEN_MISSING:"
                + token
            )

    for forbidden in (
        "secrets.token_bytes",
        "_AUTHORITY_CONSTRUCTION_TOKEN",
        "ProviderShadowRehearsalAuthority",
        "_new_provider_shadow_rehearsal_authority",
    ):
        if forbidden in evidence_source:
            violations.append(
                "LEGACY_OR_EPHEMERAL_SHADOW_AUTHORITY_PRESENT:"
                + forbidden
            )

    evidence_tree = ast.parse(
        evidence_source,
        filename=evidence_module,
    )
    reference_function = next(
        (
            node
            for node
            in evidence_tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "build_provider_shadow_attestation_key_reference"
        ),
        None,
    )

    if (
        reference_function is None
        or reference_function.args.args
        or reference_function.args.kwonlyargs
        or reference_function.args.vararg
        is not None
        or reference_function.args.kwarg
        is not None
    ):
        violations.append(
            "SHADOW_ATTESTATION_ROOT_MUST_NOT_BE_CALLER_PARAMETERIZED"
        )

    runtime_source = (
        root
        / allowed_issuer_importer
    ).read_text(
        encoding="utf-8-sig"
    )

    if private_issuer not in runtime_source:
        violations.append(
            "OFFICIAL_SHADOW_RUNTIME_ATTESTED_ISSUER_MISSING"
        )

    for forbidden in (
        "_shadow_rehearsal_authority",
        "def shadow_rehearsal_authority",
        "_new_provider_shadow_rehearsal_authority",
    ):
        if forbidden in runtime_source:
            violations.append(
                "SHADOW_RUNTIME_SIGNING_CAPABILITY_EXPOSED:"
                + forbidden
            )

    rehearsal_path = (
        root
        / "app"
        / "core"
        / "provider_activation_rehearsal.py"
    )
    rehearsal_source = rehearsal_path.read_text(
        encoding="utf-8-sig"
    )
    rehearsal_tree = ast.parse(
        rehearsal_source,
        filename=str(
            rehearsal_path
        ),
    )

    certify = next(
        (
            node
            for node
            in rehearsal_tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "certify_provider_activation_rehearsal"
        ),
        None,
    )

    if certify is None:
        violations.append(
            "PROVIDER_ACTIVATION_REHEARSAL_CERTIFIER_MISSING"
        )
    else:
        args = {
            argument.arg
            for argument
            in (
                list(
                    certify.args.args
                )
                + list(
                    certify.args.kwonlyargs
                )
            )
        }

        for required in (
            "shadow_evidence_store",
            "interruption_recovery_store",
            "attempt_intent_store",
            "network_call_evidence_store",
        ):
            if required not in args:
                violations.append(
                    "REHEARSAL_AUTHORITATIVE_SOURCE_ARGUMENT_MISSING:"
                    + required
                )

        for forbidden in (
            "shadow_evidence_authority",
            "shadow_attestation_key_reference",
            "shadow_attestation_key_resolver",
        ):
            if forbidden in args:
                violations.append(
                    "CALLER_CONTROLLED_SHADOW_ATTESTATION_ROOT:"
                    + forbidden
                )

    for token in (
        "type(shadow_evidence_store)",
        "SQLiteProviderShadowRehearsalEvidenceStore",
        "type(interruption_recovery_store)",
        "SQLiteProviderInterruptionRecoveryStore",
        "type(attempt_intent_store)",
        "SQLiteProviderAttemptIntentStore",
        "type(network_call_evidence_store)",
        "SQLiteProviderNetworkCallEvidenceStore",
        "verify_provider_shadow_rehearsal_attestation",
        "reconcile_network_attempt_with_recovery",
        "INTERRUPTION_ATTEMPT_PROVENANCE_NOT_CROSS_BOUND",
    ):
        if token not in rehearsal_source:
            violations.append(
                "SHADOW_REHEARSAL_PROVENANCE_CONTROL_MISSING:"
                + token
            )

    if violations:
        raise SystemExit(
            "PROVIDER_SHADOW_REHEARSAL_PROVENANCE_BOUNDARY_VIOLATION\n"
            + "\n".join(
                violations
            )
        )




def _p137_p141_history_identity_lifecycle_boundary(
    root,
) -> None:
    canonical_lifecycle = (
        root
        / "app/core/canonical_identity_lifecycle.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    provider_lifecycle = (
        root
        / "app/core/provider_identity_lifecycle.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    football_adapter = (
        root
        / "app/application/football/identity_lifecycle.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    tennis_adapter = (
        root
        / "app/application/tennis/identity_lifecycle.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    canonical_observation = (
        root
        / "app/core/canonical_observation_store.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    point_in_time_history = (
        root
        / "app/core/point_in_time_history.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    football_repository = (
        root
        / "app/sports/football/repository.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for token in (
        "class SQLiteCanonicalIdentityLifecycleLedger",
        "ALIAS_ADDED",
        "DISPLAY_NAME_CHANGED",
        "SUPERSEDED",
        "effective_at",
        "known_at",
        "resolve_terminal_canonical_id_as_of",
        "name_join_allowed",
        "automatic_model_promotion",
        "automatic_provider_switch",
        "automatic_wagering",
    ):
        if token not in canonical_lifecycle:
            raise RuntimeError(
                "P137_CANONICAL_IDENTITY_LIFECYCLE_CONTROL_MISSING:"
                + token
            )

    for token in (
        "class SQLiteTemporalProviderIdentityLedger",
        "valid_from",
        "valid_to",
        "known_at",
        "predecessor_binding_id",
        "corrects_binding_id",
        "def resolve_as_of(",
        "def remap(",
        "PROVIDER_REMAP_REQUIRES_HUMAN_REVIEW",
        "TEMPORAL_PROVIDER_MAPPING_SUCCESSOR_KNOWN_BEFORE_PREDECESSOR",
        "name_join_allowed",
    ):
        if token not in provider_lifecycle:
            raise RuntimeError(
                "P138_TEMPORAL_PROVIDER_IDENTITY_CONTROL_MISSING:"
                + token
            )

    for source, label in (
        (
            canonical_lifecycle,
            "CANONICAL",
        ),
        (
            provider_lifecycle,
            "PROVIDER",
        ),
    ):
        upper = source.upper()

        for destructive in (
            '"UPDATE ',
            '"DELETE ',
            "'UPDATE ",
            "'DELETE ",
        ):
            if destructive in upper:
                raise RuntimeError(
                    "P139_APPEND_ONLY_IDENTITY_LEDGER_VIOLATION:"
                    + label
                )

        for forbidden_api in (
            "def resolve_by_name(",
            "def get_by_alias(",
            "def find_by_name(",
        ):
            if forbidden_api in source:
                raise RuntimeError(
                    "P137_NAME_BASED_IDENTITY_RESOLUTION_FORBIDDEN:"
                    + forbidden_api
                )

    if (
        'sport="tennis"'
        in football_adapter
        or "app.application.tennis"
        in football_adapter
    ):
        raise RuntimeError(
            "P140_FOOTBALL_IDENTITY_LIFECYCLE_CROSS_SPORT"
        )

    if (
        'sport="football"'
        in tennis_adapter
        or "app.application.football"
        in tennis_adapter
    ):
        raise RuntimeError(
            "P140_TENNIS_IDENTITY_LIFECYCLE_CROSS_SPORT"
        )

    for token in (
        "append_admitted_record",
        "list_as_of",
    ):
        if token not in canonical_observation:
            raise RuntimeError(
                "P139_EXISTING_APPEND_ONLY_HISTORY_FOUNDATION_MISSING:"
                + token
            )

    for token in (
        "build_point_in_time_history",
        "as_of",
    ):
        if token not in point_in_time_history:
            raise RuntimeError(
                "P139_POINT_IN_TIME_HISTORY_FOUNDATION_MISSING:"
                + token
            )

    for token in (
        "upsert",
        "reconcile",
    ):
        if token not in football_repository:
            raise RuntimeError(
                "P139_FOOTBALL_CURRENT_STATE_REPOSITORY_SEMANTICS_MISSING:"
                + token
            )

    safety_targets = {
        "name_join_allowed",
        "automatic_model_promotion",
        "automatic_provider_switch",
        "automatic_wagering",
    }

    for label, source in (
        (
            "CANONICAL",
            canonical_lifecycle,
        ),
        (
            "PROVIDER",
            provider_lifecycle,
        ),
        (
            "FOOTBALL",
            football_adapter,
        ),
        (
            "TENNIS",
            tennis_adapter,
        ),
    ):
        tree = ast.parse(
            source,
            filename=label,
        )

        for node in ast.walk(
            tree
        ):
            if (
                isinstance(
                    node,
                    ast.keyword,
                )
                and node.arg
                in safety_targets
                and isinstance(
                    node.value,
                    ast.Constant,
                )
                and node.value.value is True
            ):
                raise RuntimeError(
                    "P141_IDENTITY_SAFETY_TRUE_BINDING_FORBIDDEN:"
                    + label
                    + ":"
                    + str(
                        node.lineno
                    )
                )

            if isinstance(
                node,
                ast.Dict,
            ):
                for key, value in zip(
                    node.keys,
                    node.values,
                ):
                    if not (
                        isinstance(
                            key,
                            ast.Constant,
                        )
                        and isinstance(
                            key.value,
                            str,
                        )
                        and key.value
                        in safety_targets
                    ):
                        continue

                    if (
                        isinstance(
                            value,
                            ast.Constant,
                        )
                        and value.value is True
                    ):
                        raise RuntimeError(
                            "P141_IDENTITY_SAFETY_TRUE_BINDING_FORBIDDEN:"
                            + label
                            + ":"
                            + str(
                                node.lineno
                            )
                        )


def _provider_response_ingest_boundary(
    root,
) -> None:
    response_validation = (
        root
        / "app/providers/api_football/response_validation.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    fixture_service = (
        root
        / "app/providers/api_football/fixture_service.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    odds_service = (
        root
        / "app/providers/api_football/odds_service.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    replay = (
        root
        / "app/providers/api_football/offline_ingest_certification.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    pinned_transport = (
        root
        / "app/core/pinned_https_transport.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for token in (
        "class ApiFootballProviderResponseError",
        "def request_and_validate_api_football_response(",
        "API_FOOTBALL_RESPONSE_ITEM_NOT_MAPPING",
        '"SCHEMA"',
        '"HTTP_STATUS"',
        '"CONTENT_TYPE"',
        '"JSON_DECODE"',
        '"TRANSPORT"',
    ):
        if token not in response_validation:
            raise RuntimeError(
                "P133_RESPONSE_CONTROL_MISSING:"
                + token
            )

    if fixture_service.count(
        "request_and_validate_api_football_response("
    ) < 3:
        raise RuntimeError(
            "P133_FIXTURE_PROTOCOL_BINDING_MISSING"
        )

    if odds_service.count(
        "request_and_validate_api_football_response("
    ) < 1:
        raise RuntimeError(
            "P133_ODDS_PROTOCOL_BINDING_MISSING"
        )

    for token in (
        "class PinnedHttpProtocolError",
        "def json_strict(",
        "PINNED_HTTP_CONTENT_TYPE_REQUIRED",
        "PINNED_HTTP_JSON_INVALID",
        "strict_protocol=True",
    ):
        if token not in pinned_transport:
            raise RuntimeError(
                "P133_PINNED_PROTOCOL_CONTROL_MISSING:"
                + token
            )

    for token in (
        "class SQLiteApiFootballOfflineIngestEvidenceStore",
        "SQLiteProviderShadowRehearsalEvidenceStore",
        "request_parameter_values_fingerprint",
        "evidence_store.get_verified",
        "OFFLINE_INGEST_PAYLOAD_DATE_MISMATCH",
        "OFFLINE_INGEST_SHADOW_PARAMETER_VALUES_FINGERPRINT_MISMATCH",
        "OFFLINE_INGEST_SHADOW_REQUEST_EVIDENCE_NOT_FOUND",
        "AUTHORITATIVE_OFFLINE_INGEST_EVIDENCE_PATH_ENV",
        "require_authoritative_store",
        "_source_revision()",
        "hmac.compare_digest",
        "code_fingerprint",
        "zero_network_topology_verified",
    ):
        if token not in replay:
            raise RuntimeError(
                "P136_FINAL_PROVENANCE_CONTROL_MISSING:"
                + token
            )

    if "network_call_count" in replay:
        raise RuntimeError(
            "P136_SELF_REPORTED_NETWORK_COUNTER_FORBIDDEN"
        )

    replay_tree = ast.parse(
        replay,
        filename=(
            "offline_ingest_certification.py"
        ),
    )

    certifier = next(
        (
            node
            for node in replay_tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "certify_api_football_offline_fixture_ingest"
        ),
        None,
    )

    if certifier is None:
        raise RuntimeError(
            "P136_CERTIFIER_NOT_FOUND"
        )

    certifier_parameters = {
        argument.arg
        for argument
        in (
            certifier.args.posonlyargs
            + certifier.args.args
            + certifier.args.kwonlyargs
        )
    }

    if "source_revision" in certifier_parameters:
        raise RuntimeError(
            "P136_SOURCE_REVISION_CALLER_CONTROL_FORBIDDEN"
        )

    for required_parameter in (
        "shadow_evidence_store",
        "shadow_request_evidence_id",
        "evidence_store",
    ):
        if (
            required_parameter
            not in certifier_parameters
        ):
            raise RuntimeError(
                "P136_DURABLE_PROVENANCE_PARAMETER_REQUIRED:"
                + required_parameter
            )

    forbidden_roots = {
        "socket",
        "requests",
        "urllib",
        "http",
        "httpx",
        "aiohttp",
    }

    for node in ast.walk(
        replay_tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            for alias in node.names:
                if (
                    alias.name.split(".")[0]
                    in forbidden_roots
                ):
                    raise RuntimeError(
                        "P136_NETWORK_IMPORT_FORBIDDEN"
                    )

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if (
                node.module
                and node.module.split(".")[0]
                in forbidden_roots
            ):
                raise RuntimeError(
                    "P136_NETWORK_IMPORT_FORBIDDEN"
                )

    safety_targets = {
        "real_provider_execution_authorized",
        "automatic_provider_switch",
        "automatic_wagering",
    }

    false_counts = {
        name: 0
        for name in safety_targets
    }

    true_bindings = []

    for node in ast.walk(
        replay_tree
    ):
        if isinstance(
            node,
            ast.Dict,
        ):
            for key, value in zip(
                node.keys,
                node.values,
            ):
                if not (
                    isinstance(
                        key,
                        ast.Constant,
                    )
                    and isinstance(
                        key.value,
                        str,
                    )
                    and key.value
                    in safety_targets
                ):
                    continue

                if (
                    isinstance(
                        value,
                        ast.Constant,
                    )
                    and value.value is False
                ):
                    false_counts[
                        key.value
                    ] += 1
                elif (
                    isinstance(
                        value,
                        ast.Constant,
                    )
                    and value.value is True
                ):
                    true_bindings.append(
                        (
                            key.value,
                            node.lineno,
                            "DICT",
                        )
                    )

        elif isinstance(
            node,
            ast.keyword,
        ):
            if (
                node.arg
                not in safety_targets
            ):
                continue

            if (
                isinstance(
                    node.value,
                    ast.Constant,
                )
                and node.value.value is False
            ):
                false_counts[
                    node.arg
                ] += 1
            elif (
                isinstance(
                    node.value,
                    ast.Constant,
                )
                and node.value.value is True
            ):
                true_bindings.append(
                    (
                        node.arg,
                        node.lineno,
                        "KEYWORD",
                    )
                )

    if true_bindings:
        raise RuntimeError(
            "P136_SAFETY_FLAG_TRUE_BINDING_FORBIDDEN"
        )

    for name in sorted(
        safety_targets
    ):
        if false_counts[name] < 1:
            raise RuntimeError(
                "P136_SAFETY_FLAG_FALSE_BINDING_REQUIRED:"
                + name
            )


def _provider_p131_real_attempt_cross_binding_boundary(
    root: Path,
) -> None:
    path = (
        root
        / "app"
        / "core"
        / "provider_activation_rehearsal.py"
    )
    source = path.read_text(
        encoding="utf-8-sig"
    )
    tree = ast.parse(
        source,
        filename=str(path),
    )

    certify = next(
        (
            node
            for node in tree.body
            if isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "certify_provider_activation_rehearsal"
        ),
        None,
    )

    violations: list[str] = []

    if certify is None:
        violations.append(
            "P131_REHEARSAL_CERTIFIER_MISSING"
        )
    else:
        args = {
            argument.arg
            for argument in (
                list(certify.args.args)
                + list(certify.args.kwonlyargs)
            )
        }

        for required in (
            "attempt_intent_store",
            "network_call_evidence_store",
            "network_permit_store",
            "contract_endpoint_binding_store",
        ):
            if required not in args:
                violations.append(
                    "P131_REAL_ATTEMPT_ARGUMENT_MISSING:"
                    + required
                )

    permit_consumed_at_get = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "permit"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "consumed_at"
        for node in ast.walk(tree)
    )

    if not permit_consumed_at_get:
        violations.append(
            "P131_REAL_ATTEMPT_CONTROL_MISSING:"
            'permit.get("consumed_at")'
        )

    for token in (
        "type(network_permit_store)",
        "SQLiteProviderNetworkPermitStore",
        "type(contract_endpoint_binding_store)",
        "SQLiteProviderContractEndpointBindingStore",
        "network_permit_store.get_verified",
        "network_call_evidence_store.list_verified_events_for_permit",
        "NETWORK_CALL_STARTED",
        "contract_endpoint_binding_store.authorize",
        "pre_network_binding_intent_id",
        "reconcile_network_attempt_with_recovery",
        "INTERRUPTION_REAL_NETWORK_ATTEMPT_CROSS_BINDING_REQUIRED",
    ):
        if token not in source:
            violations.append(
                "P131_REAL_ATTEMPT_CONTROL_MISSING:"
                + token
            )

    if (
        "real_provider_execution_authorized=True"
        in source
    ):
        violations.append(
            "P131_REAL_PROVIDER_EXECUTION_MUST_REMAIN_DISABLED"
        )

    if violations:
        raise SystemExit(
            "PROVIDER_P131_REAL_ATTEMPT_CROSS_BINDING_BOUNDARY_VIOLATION\n"
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
    _provider_production_readiness_boundary(ROOT)
    _provider_network_activation_hardening_boundary(ROOT)
    _provider_network_activation_semantic_boundary(ROOT)
    _provider_p131_real_attempt_cross_binding_boundary(ROOT)
    _provider_response_ingest_boundary(ROOT)
    _p137_p141_history_identity_lifecycle_boundary(ROOT)
    _provider_shadow_rehearsal_provenance_boundary(ROOT)
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
