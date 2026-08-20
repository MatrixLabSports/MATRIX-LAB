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
class BootstrapHealthReview:
    review_id: str
    sport: str
    provider_key: str
    bootstrap_run_id: str
    reconciliation_fingerprint: str
    runtime_admission_evidence_fingerprint: str
    reviewer_id: str
    decision: str
    review_fingerprint: str

    def payload(
        self,
    ) -> Mapping[str, Any]:
        return {
            "schema": (
                "matrix.bootstrap-health-review/2"
            ),
            "review_id": self.review_id,
            "sport": self.sport,
            "provider_key": (
                self.provider_key
            ),
            "bootstrap_run_id": (
                self.bootstrap_run_id
            ),
            "reconciliation_fingerprint": (
                self
                .reconciliation_fingerprint
            ),
            "runtime_admission_evidence_fingerprint": (
                self
                .runtime_admission_evidence_fingerprint
            ),
            "reviewer_id": (
                self.reviewer_id
            ),
            "decision": (
                self.decision
            ),
            "automatic_health_promotion": False,
            "automatic_provider_switch": False,
            "review_fingerprint": (
                self.review_fingerprint
            ),
        }


class SQLiteBootstrapHealthReviewStore:
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
                CREATE TABLE IF NOT EXISTS bootstrap_health_reviews (
                    review_id TEXT PRIMARY KEY,
                    sport TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    bootstrap_run_id TEXT NOT NULL UNIQUE,
                    decision TEXT NOT NULL,
                    review_fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    CHECK (
                        sport IN (
                            'football',
                            'tennis'
                        )
                    ),
                    CHECK (
                        decision IN (
                            'APPROVE_PRODUCTION',
                            'KEEP_QUARANTINED'
                        )
                    )
                )
                """
            )

    @staticmethod
    def build_review(
        *,
        sport: str,
        provider_key: str,
        bootstrap_run_id: str,
        reconciliation_fingerprint: str,
        runtime_admission_evidence_fingerprint: str,
        reviewer_id: str,
        decision: str,
    ) -> BootstrapHealthReview:
        if sport not in {
            "football",
            "tennis",
        }:
            raise ValueError(
                "INVALID_SPORT"
            )

        for name, value in {
            "PROVIDER_KEY": (
                provider_key
            ),
            "BOOTSTRAP_RUN_ID": (
                bootstrap_run_id
            ),
            "REVIEWER_ID": (
                reviewer_id
            ),
        }.items():
            if (
                not isinstance(
                    value,
                    str,
                )
                or not value
            ):
                raise ValueError(
                    f"INVALID_{name}"
                )

        reconciliation_fingerprint = _hex64(
            "RECONCILIATION_FINGERPRINT",
            reconciliation_fingerprint,
        )
        runtime_admission_evidence_fingerprint = _hex64(
            "RUNTIME_ADMISSION_EVIDENCE_FINGERPRINT",
            runtime_admission_evidence_fingerprint,
        )

        if decision not in {
            "APPROVE_PRODUCTION",
            "KEEP_QUARANTINED",
        }:
            raise ValueError(
                "INVALID_BOOTSTRAP_REVIEW_DECISION"
            )

        base = {
            "schema": (
                "matrix.bootstrap-health-review/2"
            ),
            "sport": sport,
            "provider_key": (
                provider_key
            ),
            "bootstrap_run_id": (
                bootstrap_run_id
            ),
            "reconciliation_fingerprint": (
                reconciliation_fingerprint
            ),
            "runtime_admission_evidence_fingerprint": (
                runtime_admission_evidence_fingerprint
            ),
            "reviewer_id": (
                reviewer_id
            ),
            "decision": decision,
            "automatic_health_promotion": False,
            "automatic_provider_switch": False,
        }

        review_fingerprint = _sha(
            base
        )
        review_id = _sha(
            {
                "schema": (
                    "matrix.bootstrap-health-review-id/2"
                ),
                "review_fingerprint": (
                    review_fingerprint
                ),
            }
        )

        return BootstrapHealthReview(
            review_id=review_id,
            sport=sport,
            provider_key=provider_key,
            bootstrap_run_id=(
                bootstrap_run_id
            ),
            reconciliation_fingerprint=(
                reconciliation_fingerprint
            ),
            runtime_admission_evidence_fingerprint=(
                runtime_admission_evidence_fingerprint
            ),
            reviewer_id=(
                reviewer_id
            ),
            decision=decision,
            review_fingerprint=(
                review_fingerprint
            ),
        )

    def record(
        self,
        review: BootstrapHealthReview,
    ) -> BootstrapHealthReview:
        expected = self.build_review(
            sport=review.sport,
            provider_key=(
                review.provider_key
            ),
            bootstrap_run_id=(
                review.bootstrap_run_id
            ),
            reconciliation_fingerprint=(
                review
                .reconciliation_fingerprint
            ),
            runtime_admission_evidence_fingerprint=(
                review
                .runtime_admission_evidence_fingerprint
            ),
            reviewer_id=(
                review.reviewer_id
            ),
            decision=(
                review.decision
            ),
        )

        if expected != review:
            raise ValueError(
                "BOOTSTRAP_HEALTH_REVIEW_DERIVATION_MISMATCH"
            )

        payload_json = _canonical_json(
            review.payload()
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
                    review_id,
                    payload_sha256
                FROM bootstrap_health_reviews
                WHERE bootstrap_run_id = ?
                """,
                (
                    review
                    .bootstrap_run_id,
                ),
            ).fetchone()

            if existing is not None:
                connection.execute(
                    "ROLLBACK"
                )

                if (
                    str(existing[0])
                    == review.review_id
                    and str(existing[1])
                    == payload_sha
                ):
                    return review

                raise ValueError(
                    "BOOTSTRAP_RUN_ALREADY_REVIEWED"
                )

            connection.execute(
                """
                INSERT INTO bootstrap_health_reviews (
                    review_id,
                    sport,
                    provider_key,
                    bootstrap_run_id,
                    decision,
                    review_fingerprint,
                    payload_json,
                    payload_sha256
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.sport,
                    review.provider_key,
                    review
                    .bootstrap_run_id,
                    review.decision,
                    review
                    .review_fingerprint,
                    payload_json,
                    payload_sha,
                ),
            )
            connection.execute(
                "COMMIT"
            )

        return review

    def get_by_run(
        self,
        bootstrap_run_id: str,
    ) -> Mapping[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    review_id,
                    sport,
                    provider_key,
                    decision,
                    review_fingerprint,
                    payload_json,
                    payload_sha256
                FROM bootstrap_health_reviews
                WHERE bootstrap_run_id = ?
                """,
                (
                    bootstrap_run_id,
                ),
            ).fetchone()

        if row is None:
            return None

        (
            review_id,
            sport,
            provider_key,
            decision,
            review_fingerprint,
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
                "BOOTSTRAP_REVIEW_PAYLOAD_HASH_MISMATCH"
            )

        expected = self.build_review(
            sport=payload["sport"],
            provider_key=(
                payload["provider_key"]
            ),
            bootstrap_run_id=(
                payload[
                    "bootstrap_run_id"
                ]
            ),
            reconciliation_fingerprint=(
                payload[
                    "reconciliation_fingerprint"
                ]
            ),
            runtime_admission_evidence_fingerprint=(
                payload[
                    "runtime_admission_evidence_fingerprint"
                ]
            ),
            reviewer_id=(
                payload["reviewer_id"]
            ),
            decision=(
                payload["decision"]
            ),
        )

        if (
            expected.review_id
            != review_id
            or expected
            .review_fingerprint
            != review_fingerprint
            or expected.payload()
            != payload
            or payload["sport"]
            != sport
            or payload[
                "provider_key"
            ]
            != provider_key
            or payload["decision"]
            != decision
        ):
            raise ValueError(
                "BOOTSTRAP_REVIEW_REDERIVATION_MISMATCH"
            )

        return payload
