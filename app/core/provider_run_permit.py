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
class ProviderRunPermit:
    permit_id: str
    run_id: str
    sport: str
    provider_key: str
    mode: str
    queue_fingerprint: str
    scheduling_evidence_fingerprint: str
    rights_manifest_fingerprint: str
    bootstrap_policy_fingerprint: str | None
    max_items: int
    max_requests: int
    permit_fingerprint: str

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.provider-run-permit/2"
            ),
            "permit_id": self.permit_id,
            "run_id": self.run_id,
            "sport": self.sport,
            "provider_key": (
                self.provider_key
            ),
            "mode": self.mode,
            "queue_fingerprint": (
                self.queue_fingerprint
            ),
            "scheduling_evidence_fingerprint": (
                self
                .scheduling_evidence_fingerprint
            ),
            "rights_manifest_fingerprint": (
                self
                .rights_manifest_fingerprint
            ),
            "bootstrap_policy_fingerprint": (
                self
                .bootstrap_policy_fingerprint
            ),
            "max_items": self.max_items,
            "max_requests": (
                self.max_requests
            ),
            "one_use": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "permit_fingerprint": (
                self.permit_fingerprint
            ),
        }


class SQLiteProviderRunPermitStore:
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
                CREATE TABLE IF NOT EXISTS provider_run_permits (
                    permit_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    queue_fingerprint TEXT NOT NULL,
                    permit_fingerprint TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    consumed_at TEXT,
                    CHECK (
                        sport IN (
                            'football',
                            'tennis'
                        )
                    ),
                    CHECK (
                        mode IN (
                            'PRODUCTION',
                            'BOOTSTRAP_PROBE'
                        )
                    ),
                    CHECK (
                        state IN (
                            'ISSUED',
                            'CONSUMED'
                        )
                    )
                )
                """
            )

    @staticmethod
    def build_permit(
        *,
        run_id: str,
        sport: str,
        provider_key: str,
        mode: str,
        queue_fingerprint: str,
        scheduling_evidence_fingerprint: str,
        rights_manifest_fingerprint: str,
        bootstrap_policy_fingerprint: str | None,
        max_items: int,
        max_requests: int,
    ) -> ProviderRunPermit:
        if (
            not isinstance(
                run_id,
                str,
            )
            or not run_id
        ):
            raise ValueError(
                "INVALID_RUN_ID"
            )

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

        if mode not in {
            "PRODUCTION",
            "BOOTSTRAP_PROBE",
        }:
            raise ValueError(
                "INVALID_PROVIDER_MODE"
            )

        queue_fingerprint = _hex64(
            "QUEUE_FINGERPRINT",
            queue_fingerprint,
        )
        scheduling_evidence_fingerprint = _hex64(
            "SCHEDULING_EVIDENCE_FINGERPRINT",
            scheduling_evidence_fingerprint,
        )
        rights_manifest_fingerprint = _hex64(
            "RIGHTS_MANIFEST_FINGERPRINT",
            rights_manifest_fingerprint,
        )

        if mode == "BOOTSTRAP_PROBE":
            if (
                bootstrap_policy_fingerprint
                is None
            ):
                raise ValueError(
                    "BOOTSTRAP_POLICY_REQUIRED"
                )

            bootstrap_policy_fingerprint = _hex64(
                "BOOTSTRAP_POLICY_FINGERPRINT",
                bootstrap_policy_fingerprint,
            )

        elif (
            bootstrap_policy_fingerprint
            is not None
        ):
            raise ValueError(
                "BOOTSTRAP_POLICY_NOT_ALLOWED_IN_PRODUCTION"
            )

        for name, value in {
            "MAX_ITEMS": max_items,
            "MAX_REQUESTS": (
                max_requests
            ),
        }.items():
            if (
                not isinstance(
                    value,
                    int,
                )
                or isinstance(
                    value,
                    bool,
                )
                or value < 1
            ):
                raise ValueError(
                    f"INVALID_{name}"
                )

        base = {
            "schema": (
                "matrix.provider-run-permit/2"
            ),
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "queue_fingerprint": (
                queue_fingerprint
            ),
            "scheduling_evidence_fingerprint": (
                scheduling_evidence_fingerprint
            ),
            "rights_manifest_fingerprint": (
                rights_manifest_fingerprint
            ),
            "bootstrap_policy_fingerprint": (
                bootstrap_policy_fingerprint
            ),
            "max_items": max_items,
            "max_requests": max_requests,
            "one_use": True,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }

        permit_fingerprint = _sha(
            base
        )
        permit_id = _sha(
            {
                "schema": (
                    "matrix.provider-run-permit-id/2"
                ),
                "permit_fingerprint": (
                    permit_fingerprint
                ),
            }
        )

        return ProviderRunPermit(
            permit_id=permit_id,
            run_id=run_id,
            sport=sport,
            provider_key=provider_key,
            mode=mode,
            queue_fingerprint=(
                queue_fingerprint
            ),
            scheduling_evidence_fingerprint=(
                scheduling_evidence_fingerprint
            ),
            rights_manifest_fingerprint=(
                rights_manifest_fingerprint
            ),
            bootstrap_policy_fingerprint=(
                bootstrap_policy_fingerprint
            ),
            max_items=max_items,
            max_requests=max_requests,
            permit_fingerprint=(
                permit_fingerprint
            ),
        )

    @classmethod
    def _rederive(
        cls,
        payload: Mapping[str, Any],
    ) -> ProviderRunPermit:
        return cls.build_permit(
            run_id=payload["run_id"],
            sport=payload["sport"],
            provider_key=(
                payload["provider_key"]
            ),
            mode=payload["mode"],
            queue_fingerprint=(
                payload[
                    "queue_fingerprint"
                ]
            ),
            scheduling_evidence_fingerprint=(
                payload[
                    "scheduling_evidence_fingerprint"
                ]
            ),
            rights_manifest_fingerprint=(
                payload[
                    "rights_manifest_fingerprint"
                ]
            ),
            bootstrap_policy_fingerprint=(
                payload[
                    "bootstrap_policy_fingerprint"
                ]
            ),
            max_items=payload[
                "max_items"
            ],
            max_requests=payload[
                "max_requests"
            ],
        )

    def issue(
        self,
        permit: ProviderRunPermit,
    ) -> ProviderRunPermit:
        expected = self.build_permit(
            run_id=permit.run_id,
            sport=permit.sport,
            provider_key=permit.provider_key,
            mode=permit.mode,
            queue_fingerprint=(
                permit.queue_fingerprint
            ),
            scheduling_evidence_fingerprint=(
                permit
                .scheduling_evidence_fingerprint
            ),
            rights_manifest_fingerprint=(
                permit
                .rights_manifest_fingerprint
            ),
            bootstrap_policy_fingerprint=(
                permit
                .bootstrap_policy_fingerprint
            ),
            max_items=permit.max_items,
            max_requests=(
                permit.max_requests
            ),
        )

        if expected != permit:
            raise ValueError(
                "PROVIDER_RUN_PERMIT_DERIVATION_MISMATCH"
            )

        payload_json = _canonical_json(
            permit.payload()
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
                    permit_id,
                    payload_sha256,
                    state
                FROM provider_run_permits
                WHERE run_id = ?
                """,
                (permit.run_id,),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == permit.permit_id
                    and str(existing[1])
                    == payload_sha
                    and str(existing[2])
                    == "ISSUED"
                ):
                    return permit

                raise ValueError(
                    "RUN_ALREADY_HAS_PERMIT"
                )

            connection.execute(
                """
                INSERT INTO provider_run_permits (
                    permit_id,
                    run_id,
                    sport,
                    provider_key,
                    mode,
                    queue_fingerprint,
                    permit_fingerprint,
                    state,
                    payload_json,
                    payload_sha256
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    'ISSUED', ?, ?
                )
                """,
                (
                    permit.permit_id,
                    permit.run_id,
                    permit.sport,
                    permit.provider_key,
                    permit.mode,
                    permit
                    .queue_fingerprint,
                    permit
                    .permit_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return permit

    def get_verified(
        self,
        permit_id: str,
    ) -> Mapping[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    run_id,
                    sport,
                    provider_key,
                    mode,
                    queue_fingerprint,
                    permit_fingerprint,
                    state,
                    payload_json,
                    payload_sha256
                FROM provider_run_permits
                WHERE permit_id = ?
                """,
                (permit_id,),
            ).fetchone()

        if row is None:
            raise ValueError(
                "UNKNOWN_PROVIDER_RUN_PERMIT"
            )

        (
            run_id,
            sport,
            provider_key,
            mode,
            queue_fingerprint,
            permit_fingerprint,
            state,
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
                "PROVIDER_RUN_PERMIT_PAYLOAD_HASH_MISMATCH"
            )

        expected = self._rederive(
            payload
        )

        if (
            expected.permit_id
            != permit_id
            or expected
            .permit_fingerprint
            != permit_fingerprint
            or expected.payload()
            != payload
        ):
            raise ValueError(
                "PROVIDER_RUN_PERMIT_REDERIVATION_MISMATCH"
            )

        for key, value in {
            "run_id": run_id,
            "sport": sport,
            "provider_key": provider_key,
            "mode": mode,
            "queue_fingerprint": (
                queue_fingerprint
            ),
            "permit_fingerprint": (
                permit_fingerprint
            ),
        }.items():
            if payload.get(key) != value:
                raise ValueError(
                    "PROVIDER_RUN_PERMIT_DB_PAYLOAD_MISMATCH"
                )

        result = dict(payload)
        result["state"] = state
        return result

    def consume(
        self,
        *,
        permit_id: str,
        run_id: str,
        sport: str,
        provider_key: str,
        mode: str,
        queue_fingerprint: str,
        scheduling_evidence_fingerprint: str,
        rights_manifest_fingerprint: str,
        bootstrap_policy_fingerprint: str | None,
        max_items: int,
        max_requests: int,
    ) -> Mapping[str, Any]:
        expected_bindings = {
            "run_id": run_id,
            "sport": sport,
            "provider_key": (
                provider_key
            ),
            "mode": mode,
            "queue_fingerprint": (
                _hex64(
                    "QUEUE_FINGERPRINT",
                    queue_fingerprint,
                )
            ),
            "scheduling_evidence_fingerprint": (
                _hex64(
                    "SCHEDULING_EVIDENCE_FINGERPRINT",
                    scheduling_evidence_fingerprint,
                )
            ),
            "rights_manifest_fingerprint": (
                _hex64(
                    "RIGHTS_MANIFEST_FINGERPRINT",
                    rights_manifest_fingerprint,
                )
            ),
            "bootstrap_policy_fingerprint": (
                None
                if bootstrap_policy_fingerprint
                is None
                else _hex64(
                    "BOOTSTRAP_POLICY_FINGERPRINT",
                    bootstrap_policy_fingerprint,
                )
            ),
            "max_items": max_items,
            "max_requests": max_requests,
        }

        with self._connect() as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            row = connection.execute(
                """
                SELECT
                    run_id,
                    sport,
                    provider_key,
                    mode,
                    queue_fingerprint,
                    permit_fingerprint,
                    state,
                    payload_json,
                    payload_sha256
                FROM provider_run_permits
                WHERE permit_id = ?
                """,
                (permit_id,),
            ).fetchone()

            if row is None:
                connection.execute(
                    "ROLLBACK"
                )
                raise ValueError(
                    "UNKNOWN_PROVIDER_RUN_PERMIT"
                )

            (
                db_run_id,
                db_sport,
                db_provider_key,
                db_mode,
                db_queue_fp,
                db_permit_fp,
                state,
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
                connection.execute(
                    "ROLLBACK"
                )
                raise ValueError(
                    "PROVIDER_RUN_PERMIT_PAYLOAD_HASH_MISMATCH"
                )

            try:
                expected = self._rederive(
                    payload
                )
            except Exception as error:
                connection.execute(
                    "ROLLBACK"
                )
                raise ValueError(
                    "PROVIDER_RUN_PERMIT_REDERIVATION_MISMATCH"
                ) from error

            if (
                expected.permit_id
                != permit_id
                or expected
                .permit_fingerprint
                != db_permit_fp
                or expected.payload()
                != payload
            ):
                connection.execute(
                    "ROLLBACK"
                )
                raise ValueError(
                    "PROVIDER_RUN_PERMIT_REDERIVATION_MISMATCH"
                )

            db_pairs = {
                "run_id": db_run_id,
                "sport": db_sport,
                "provider_key": (
                    db_provider_key
                ),
                "mode": db_mode,
                "queue_fingerprint": (
                    db_queue_fp
                ),
            }

            for key, value in db_pairs.items():
                if payload.get(key) != value:
                    connection.execute(
                        "ROLLBACK"
                    )
                    raise ValueError(
                        "PROVIDER_RUN_PERMIT_DB_PAYLOAD_MISMATCH"
                    )

            if state != "ISSUED":
                connection.execute(
                    "ROLLBACK"
                )
                raise ValueError(
                    "PROVIDER_RUN_PERMIT_ALREADY_CONSUMED"
                )

            for (
                key,
                value,
            ) in expected_bindings.items():
                if payload.get(key) != value:
                    connection.execute(
                        "ROLLBACK"
                    )
                    raise ValueError(
                        "PROVIDER_RUN_PERMIT_BINDING_MISMATCH:"
                        f"{key}"
                    )

            cursor = connection.execute(
                """
                UPDATE provider_run_permits
                SET
                    state = 'CONSUMED',
                    consumed_at = strftime(
                        '%Y-%m-%dT%H:%M:%fZ',
                        'now'
                    )
                WHERE
                    permit_id = ?
                    AND state = 'ISSUED'
                """,
                (permit_id,),
            )

            if cursor.rowcount != 1:
                connection.execute(
                    "ROLLBACK"
                )
                raise ValueError(
                    "PROVIDER_RUN_PERMIT_CONSUME_RACE"
                )

            connection.execute(
                "COMMIT"
            )

            return payload
