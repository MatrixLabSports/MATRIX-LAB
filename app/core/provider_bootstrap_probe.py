from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


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


def _hex64(
    name: str,
    value: object,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
    ):
        raise ValueError(
            f"INVALID_{name}"
        )
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(
            f"INVALID_{name}"
        ) from error
    return value.lower()


@dataclass(frozen=True)
class BootstrapProbePolicy:
    policy_id: str
    sport: str
    provider_key: str
    manual_approval_id: str
    max_items: int
    max_requests: int
    downstream_quarantine_required: bool
    policy_fingerprint: str

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-bootstrap-probe-policy/2"
            ),
            "policy_id": self.policy_id,
            "mode": "BOOTSTRAP_PROBE",
            "sport": self.sport,
            "provider_key": (
                self.provider_key
            ),
            "manual_approval_id": (
                self.manual_approval_id
            ),
            "max_items": self.max_items,
            "max_requests": (
                self.max_requests
            ),
            "downstream_quarantine_required": (
                self.downstream_quarantine_required
            ),
            "automatic_provider_switch": False,
            "automatic_health_promotion": False,
            "automatic_model_promotion": False,
            "automatic_wagering": False,
            "policy_fingerprint": (
                self.policy_fingerprint
            ),
        }


def build_bootstrap_probe_policy(
    *,
    sport: str,
    provider_key: str,
    manual_approval_id: str,
    max_items: int,
    max_requests: int,
) -> BootstrapProbePolicy:
    if sport not in {
        "football",
        "tennis",
    }:
        raise ValueError(
            "INVALID_SPORT"
        )

    if (
        not isinstance(
            provider_key,
            str,
        )
        or not provider_key
    ):
        raise ValueError(
            "INVALID_PROVIDER_KEY"
        )

    if (
        not isinstance(
            manual_approval_id,
            str,
        )
        or not manual_approval_id
    ):
        raise ValueError(
            "MANUAL_APPROVAL_REQUIRED"
        )

    if (
        not isinstance(
            max_items,
            int,
        )
        or isinstance(
            max_items,
            bool,
        )
        or max_items < 1
        or max_items > 5
    ):
        raise ValueError(
            "BOOTSTRAP_ITEMS_OUT_OF_BOUNDS"
        )

    if (
        not isinstance(
            max_requests,
            int,
        )
        or isinstance(
            max_requests,
            bool,
        )
        or max_requests < 1
        or max_requests > 10
    ):
        raise ValueError(
            "BOOTSTRAP_REQUESTS_OUT_OF_BOUNDS"
        )

    base = {
        "schema": (
            "matrix.provider-bootstrap-probe-policy/2"
        ),
        "mode": "BOOTSTRAP_PROBE",
        "sport": sport,
        "provider_key": provider_key,
        "manual_approval_id": (
            manual_approval_id
        ),
        "max_items": max_items,
        "max_requests": max_requests,
        "downstream_quarantine_required": True,
        "automatic_provider_switch": False,
        "automatic_health_promotion": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
    }

    policy_fingerprint = _sha(
        base
    )
    policy_id = _sha(
        {
            "schema": (
                "matrix.provider-bootstrap-probe-policy-id/1"
            ),
            "policy_fingerprint": (
                policy_fingerprint
            ),
        }
    )

    return BootstrapProbePolicy(
        policy_id=policy_id,
        sport=sport,
        provider_key=provider_key,
        manual_approval_id=(
            manual_approval_id
        ),
        max_items=max_items,
        max_requests=max_requests,
        downstream_quarantine_required=True,
        policy_fingerprint=(
            policy_fingerprint
        ),
    )


class SQLiteBootstrapProbePolicyRegistry:
    def __init__(
        self,
        path: str | Path,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self._initialize()

    def _connect(
        self,
    ) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            isolation_level=None,
        )
        connection.execute(
            "PRAGMA journal_mode = WAL"
        )
        connection.execute(
            "PRAGMA synchronous = FULL"
        )
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS bootstrap_probe_policies (
                    policy_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    policy_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    CHECK (
                        sport IN (
                            'football',
                            'tennis'
                        )
                    )
                )
                """
            )

    def register(
        self,
        policy: BootstrapProbePolicy,
    ) -> BootstrapProbePolicy:
        expected = (
            build_bootstrap_probe_policy(
                sport=policy.sport,
                provider_key=(
                    policy.provider_key
                ),
                manual_approval_id=(
                    policy.manual_approval_id
                ),
                max_items=(
                    policy.max_items
                ),
                max_requests=(
                    policy.max_requests
                ),
            )
        )

        if expected != policy:
            raise ValueError(
                "BOOTSTRAP_POLICY_DERIVATION_MISMATCH"
            )

        payload_json = (
            _canonical_json(
                policy.payload()
            )
        )
        payload_sha = sha256(
            payload_json.encode(
                "utf-8"
            )
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            existing = connection.execute(
                """
                SELECT
                    policy_id,
                    payload_sha256
                FROM bootstrap_probe_policies
                WHERE policy_fingerprint = ?
                """,
                (
                    policy
                    .policy_fingerprint,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == policy.policy_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return policy

                raise ValueError(
                    "BOOTSTRAP_POLICY_MUTATION_VIOLATION"
                )

            connection.execute(
                """
                INSERT INTO bootstrap_probe_policies (
                    policy_id,
                    sport,
                    provider_key,
                    policy_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    policy.policy_id,
                    policy.sport,
                    policy.provider_key,
                    policy
                    .policy_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return policy

    def get_by_fingerprint(
        self,
        fingerprint: str,
    ) -> Mapping[str, Any] | None:
        fingerprint = _hex64(
            "BOOTSTRAP_POLICY_FINGERPRINT",
            fingerprint,
        )

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    policy_id,
                    sport,
                    provider_key,
                    payload_json,
                    payload_sha256
                FROM bootstrap_probe_policies
                WHERE policy_fingerprint = ?
                """,
                (fingerprint,),
            ).fetchone()

        if row is None:
            return None

        (
            policy_id,
            sport,
            provider_key,
            payload_json,
            stored_sha,
        ) = row

        payload = json.loads(
            payload_json
        )
        actual_sha = sha256(
            _canonical_json(
                payload
            ).encode("utf-8")
        ).hexdigest()

        if actual_sha != stored_sha:
            raise ValueError(
                "BOOTSTRAP_POLICY_PAYLOAD_HASH_MISMATCH"
            )

        expected = (
            build_bootstrap_probe_policy(
                sport=payload["sport"],
                provider_key=(
                    payload[
                        "provider_key"
                    ]
                ),
                manual_approval_id=(
                    payload[
                        "manual_approval_id"
                    ]
                ),
                max_items=(
                    payload["max_items"]
                ),
                max_requests=(
                    payload[
                        "max_requests"
                    ]
                ),
            )
        )

        if (
            expected.policy_id
            != policy_id
            or expected
            .policy_fingerprint
            != fingerprint
            or expected.payload()
            != payload
            or payload["sport"]
            != sport
            or payload[
                "provider_key"
            ]
            != provider_key
        ):
            raise ValueError(
                "BOOTSTRAP_POLICY_REDERIVATION_MISMATCH"
            )

        return payload
