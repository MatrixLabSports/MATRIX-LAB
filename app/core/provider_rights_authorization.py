from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


_ALLOWED_USE_CASES = {
    "INTERNAL_ANALYTICS",
    "PUBLICATION",
    "BETTING_PLATFORM",
}

_ALLOWED_ENVIRONMENTS = {
    "SHADOW",
    "PRODUCTION",
}

_ALLOWED_STATUSES = {
    "PENDING_REVIEW",
    "APPROVED",
}


def _json(value: Any) -> str:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    )


def _sha(value: Any) -> str:
    return sha256(
        _json(value).encode("utf-8")
    ).hexdigest()


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("TIMEZONE_UNVERIFIED")
    return value.astimezone(timezone.utc)


def _hex64(name: str, value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"INVALID_{name}")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"INVALID_{name}") from error
    return value.lower()


@dataclass(frozen=True)
class ProviderRightsGrant:
    grant_id: str
    provider_key: str
    sport: str
    use_case: str
    environment: str
    status: str
    provider_terms_reference: str
    provider_terms_fingerprint: str
    rights_holder_evidence_reference: str | None
    rights_holder_evidence_fingerprint: str | None
    commercial_use_allowed: bool
    publication_allowed: bool
    betting_platform_use_allowed: bool
    redistribution_allowed: bool
    effective_from: datetime
    expires_at: datetime | None
    approved_by: str | None
    approval_reference: str | None
    created_at: datetime

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-rights-grant/1",
            "grant_id": self.grant_id,
            "provider_key": self.provider_key,
            "sport": self.sport,
            "use_case": self.use_case,
            "environment": self.environment,
            "status": self.status,
            "provider_terms_reference": self.provider_terms_reference,
            "provider_terms_fingerprint": self.provider_terms_fingerprint,
            "rights_holder_evidence_reference": (
                self.rights_holder_evidence_reference
            ),
            "rights_holder_evidence_fingerprint": (
                self.rights_holder_evidence_fingerprint
            ),
            "commercial_use_allowed": self.commercial_use_allowed,
            "publication_allowed": self.publication_allowed,
            "betting_platform_use_allowed": (
                self.betting_platform_use_allowed
            ),
            "redistribution_allowed": self.redistribution_allowed,
            "effective_from": self.effective_from.isoformat(),
            "expires_at": (
                self.expires_at.isoformat()
                if self.expires_at is not None
                else None
            ),
            "approved_by": self.approved_by,
            "approval_reference": self.approval_reference,
            "created_at": self.created_at.isoformat(),
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "real_provider_execution_authorized": False,
        }


@dataclass(frozen=True)
class ProviderRightsDecision:
    authorized: bool
    grant_id: str | None
    provider_key: str
    sport: str
    use_case: str
    environment: str
    blockers: tuple[str, ...]

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.provider-rights-decision/1",
            "authorized": self.authorized,
            "grant_id": self.grant_id,
            "provider_key": self.provider_key,
            "sport": self.sport,
            "use_case": self.use_case,
            "environment": self.environment,
            "blockers": list(self.blockers),
            "automatic_provider_switch": False,
            "automatic_wagering": False,
            "real_provider_execution_authorized": False,
        }


def build_provider_rights_grant(
    *,
    provider_key: str,
    sport: str,
    use_case: str,
    environment: str,
    status: str,
    provider_terms_reference: str,
    provider_terms_fingerprint: str,
    rights_holder_evidence_reference: str | None,
    rights_holder_evidence_fingerprint: str | None,
    commercial_use_allowed: bool,
    publication_allowed: bool,
    betting_platform_use_allowed: bool,
    redistribution_allowed: bool,
    effective_from: datetime,
    expires_at: datetime | None,
    approved_by: str | None,
    approval_reference: str | None,
    created_at: datetime,
) -> ProviderRightsGrant:
    if not provider_key:
        raise ValueError("INVALID_PROVIDER_KEY")
    if sport not in {"football", "tennis"}:
        raise ValueError("INVALID_SPORT")
    if use_case not in _ALLOWED_USE_CASES:
        raise ValueError("INVALID_PROVIDER_USE_CASE")
    if environment not in _ALLOWED_ENVIRONMENTS:
        raise ValueError("INVALID_PROVIDER_ENVIRONMENT")
    if status not in _ALLOWED_STATUSES:
        raise ValueError("INVALID_PROVIDER_RIGHTS_STATUS")
    if not provider_terms_reference:
        raise ValueError("PROVIDER_TERMS_REFERENCE_REQUIRED")

    provider_terms_fingerprint = _hex64(
        "PROVIDER_TERMS_FINGERPRINT",
        provider_terms_fingerprint,
    )

    if rights_holder_evidence_fingerprint is not None:
        rights_holder_evidence_fingerprint = _hex64(
            "RIGHTS_HOLDER_EVIDENCE_FINGERPRINT",
            rights_holder_evidence_fingerprint,
        )

    effective_from = _aware(effective_from)
    created_at = _aware(created_at)

    if expires_at is not None:
        expires_at = _aware(expires_at)
        if expires_at <= effective_from:
            raise ValueError("INVALID_PROVIDER_RIGHTS_VALIDITY")

    if status == "APPROVED":
        if not approved_by or not approval_reference:
            raise ValueError("HUMAN_RIGHTS_APPROVAL_REQUIRED")
        _hex64("APPROVAL_REFERENCE", approval_reference)

    if use_case in {"PUBLICATION", "BETTING_PLATFORM"}:
        if (
            not rights_holder_evidence_reference
            or rights_holder_evidence_fingerprint is None
        ):
            raise ValueError(
                "RIGHTS_HOLDER_EVIDENCE_REQUIRED"
            )

    if use_case == "PUBLICATION" and not publication_allowed:
        raise ValueError("PUBLICATION_RIGHTS_REQUIRED")

    if use_case == "BETTING_PLATFORM":
        if not betting_platform_use_allowed:
            raise ValueError(
                "BETTING_PLATFORM_RIGHTS_REQUIRED"
            )
        if not commercial_use_allowed:
            raise ValueError(
                "COMMERCIAL_USE_RIGHTS_REQUIRED"
            )

    base = {
        "schema": "matrix.provider-rights-grant-id/1",
        "provider_key": provider_key,
        "sport": sport,
        "use_case": use_case,
        "environment": environment,
        "status": status,
        "provider_terms_reference": provider_terms_reference,
        "provider_terms_fingerprint": provider_terms_fingerprint,
        "rights_holder_evidence_reference": (
            rights_holder_evidence_reference
        ),
        "rights_holder_evidence_fingerprint": (
            rights_holder_evidence_fingerprint
        ),
        "commercial_use_allowed": commercial_use_allowed,
        "publication_allowed": publication_allowed,
        "betting_platform_use_allowed": betting_platform_use_allowed,
        "redistribution_allowed": redistribution_allowed,
        "effective_from": effective_from.isoformat(),
        "expires_at": (
            expires_at.isoformat()
            if expires_at is not None
            else None
        ),
        "approved_by": approved_by,
        "approval_reference": approval_reference,
        "created_at": created_at.isoformat(),
        "automatic_provider_switch": False,
        "automatic_wagering": False,
        "real_provider_execution_authorized": False,
    }

    return ProviderRightsGrant(
        grant_id=_sha(base),
        provider_key=provider_key,
        sport=sport,
        use_case=use_case,
        environment=environment,
        status=status,
        provider_terms_reference=provider_terms_reference,
        provider_terms_fingerprint=provider_terms_fingerprint,
        rights_holder_evidence_reference=(
            rights_holder_evidence_reference
        ),
        rights_holder_evidence_fingerprint=(
            rights_holder_evidence_fingerprint
        ),
        commercial_use_allowed=commercial_use_allowed,
        publication_allowed=publication_allowed,
        betting_platform_use_allowed=betting_platform_use_allowed,
        redistribution_allowed=redistribution_allowed,
        effective_from=effective_from,
        expires_at=expires_at,
        approved_by=approved_by,
        approval_reference=approval_reference,
        created_at=created_at,
    )


class SQLiteProviderRightsAuthorizationStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_rights_grant (
                    grant_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )

    def _connect(self):
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

    def register(
        self,
        grant: ProviderRightsGrant,
    ) -> ProviderRightsGrant:
        rebuilt = build_provider_rights_grant(
            provider_key=grant.provider_key,
            sport=grant.sport,
            use_case=grant.use_case,
            environment=grant.environment,
            status=grant.status,
            provider_terms_reference=(
                grant.provider_terms_reference
            ),
            provider_terms_fingerprint=(
                grant.provider_terms_fingerprint
            ),
            rights_holder_evidence_reference=(
                grant.rights_holder_evidence_reference
            ),
            rights_holder_evidence_fingerprint=(
                grant.rights_holder_evidence_fingerprint
            ),
            commercial_use_allowed=(
                grant.commercial_use_allowed
            ),
            publication_allowed=grant.publication_allowed,
            betting_platform_use_allowed=(
                grant.betting_platform_use_allowed
            ),
            redistribution_allowed=(
                grant.redistribution_allowed
            ),
            effective_from=grant.effective_from,
            expires_at=grant.expires_at,
            approved_by=grant.approved_by,
            approval_reference=grant.approval_reference,
            created_at=grant.created_at,
        )

        if rebuilt != grant:
            raise ValueError(
                "PROVIDER_RIGHTS_DERIVATION_MISMATCH"
            )

        payload_json = _json(grant.payload())
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO provider_rights_grant (
                    grant_id,
                    payload_json,
                    payload_sha256,
                    revoked_at
                )
                VALUES (?, ?, ?, NULL)
                """,
                (
                    grant.grant_id,
                    payload_json,
                    payload_sha,
                ),
            )
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM provider_rights_grant
                WHERE grant_id = ?
                """,
                (grant.grant_id,),
            ).fetchone()

        if row != (payload_json, payload_sha):
            raise ValueError(
                "PROVIDER_RIGHTS_MUTATION_VIOLATION"
            )

        return grant

    def revoke(
        self,
        grant_id: str,
        *,
        revoked_at: datetime,
    ) -> None:
        revoked_at = _aware(revoked_at).isoformat()

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT revoked_at
                FROM provider_rights_grant
                WHERE grant_id = ?
                """,
                (grant_id,),
            ).fetchone()

            if row is None:
                raise ValueError(
                    "PROVIDER_RIGHTS_GRANT_NOT_FOUND"
                )

            if row[0] is not None:
                if str(row[0]) != revoked_at:
                    raise ValueError(
                        "PROVIDER_RIGHTS_REVOCATION_MUTATION"
                    )
                return

            connection.execute(
                """
                UPDATE provider_rights_grant
                SET revoked_at = ?
                WHERE grant_id = ?
                """,
                (
                    revoked_at,
                    grant_id,
                ),
            )

    def get_verified(
        self,
        grant_id: str,
    ) -> tuple[
        ProviderRightsGrant,
        datetime | None,
    ] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    payload_json,
                    payload_sha256,
                    revoked_at
                FROM provider_rights_grant
                WHERE grant_id = ?
                """,
                (grant_id,),
            ).fetchone()

        if row is None:
            return None

        payload_json, payload_sha, revoked_at = row

        if (
            sha256(
                payload_json.encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "PROVIDER_RIGHTS_INTEGRITY_FAILURE"
            )

        payload = json.loads(payload_json)

        rebuilt = build_provider_rights_grant(
            provider_key=payload["provider_key"],
            sport=payload["sport"],
            use_case=payload["use_case"],
            environment=payload["environment"],
            status=payload["status"],
            provider_terms_reference=(
                payload["provider_terms_reference"]
            ),
            provider_terms_fingerprint=(
                payload["provider_terms_fingerprint"]
            ),
            rights_holder_evidence_reference=(
                payload[
                    "rights_holder_evidence_reference"
                ]
            ),
            rights_holder_evidence_fingerprint=(
                payload[
                    "rights_holder_evidence_fingerprint"
                ]
            ),
            commercial_use_allowed=bool(
                payload["commercial_use_allowed"]
            ),
            publication_allowed=bool(
                payload["publication_allowed"]
            ),
            betting_platform_use_allowed=bool(
                payload[
                    "betting_platform_use_allowed"
                ]
            ),
            redistribution_allowed=bool(
                payload["redistribution_allowed"]
            ),
            effective_from=datetime.fromisoformat(
                payload["effective_from"]
            ),
            expires_at=(
                datetime.fromisoformat(
                    payload["expires_at"]
                )
                if payload.get("expires_at")
                else None
            ),
            approved_by=payload["approved_by"],
            approval_reference=(
                payload["approval_reference"]
            ),
            created_at=datetime.fromisoformat(
                payload["created_at"]
            ),
        )

        if (
            rebuilt.grant_id != grant_id
            or rebuilt.payload() != payload
        ):
            raise ValueError(
                "PROVIDER_RIGHTS_REDERIVATION_FAILURE"
            )

        revoked = (
            datetime.fromisoformat(
                str(revoked_at)
            )
            if revoked_at is not None
            else None
        )

        return rebuilt, revoked

    def authorize(
        self,
        *,
        grant_id: str,
        provider_key: str,
        sport: str,
        use_case: str,
        environment: str,
        now: datetime,
        legal_evidence_store=None,
    ) -> ProviderRightsDecision:
        now = _aware(now)
        record = self.get_verified(grant_id)

        blockers: list[str] = []

        if record is None:
            blockers.append(
                "PROVIDER_RIGHTS_GRANT_NOT_FOUND"
            )
            return ProviderRightsDecision(
                authorized=False,
                grant_id=None,
                provider_key=provider_key,
                sport=sport,
                use_case=use_case,
                environment=environment,
                blockers=tuple(blockers),
            )

        grant, revoked_at = record

        if grant.provider_key != provider_key:
            blockers.append(
                "PROVIDER_RIGHTS_PROVIDER_MISMATCH"
            )
        if grant.sport != sport:
            blockers.append(
                "PROVIDER_RIGHTS_SPORT_MISMATCH"
            )
        if grant.use_case != use_case:
            blockers.append(
                "PROVIDER_RIGHTS_USE_CASE_MISMATCH"
            )
        if grant.environment != environment:
            blockers.append(
                "PROVIDER_RIGHTS_ENVIRONMENT_MISMATCH"
            )
        if grant.status != "APPROVED":
            blockers.append(
                "PROVIDER_RIGHTS_NOT_APPROVED"
            )
        if revoked_at is not None:
            blockers.append(
                "PROVIDER_RIGHTS_REVOKED"
            )
        if now < grant.effective_from:
            blockers.append(
                "PROVIDER_RIGHTS_NOT_ACTIVE"
            )
        if (
            grant.expires_at is not None
            and now >= grant.expires_at
        ):
            blockers.append(
                "PROVIDER_RIGHTS_EXPIRED"
            )

        if grant.status == "APPROVED":
            if legal_evidence_store is None:
                blockers.append(
                    "PROVIDER_LEGAL_EVIDENCE_STORE_REQUIRED"
                )
            else:
                terms = legal_evidence_store.find_verified(
                    evidence_kind="PROVIDER_TERMS",
                    content_fingerprint=(
                        grant.provider_terms_fingerprint
                    ),
                )
                if terms is None:
                    blockers.append(
                        "PROVIDER_TERMS_EVIDENCE_NOT_VERIFIED"
                    )

                if (
                    grant.rights_holder_evidence_fingerprint
                    is not None
                ):
                    rights = legal_evidence_store.find_verified(
                        evidence_kind=(
                            "RIGHTS_HOLDER_LICENSE"
                        ),
                        content_fingerprint=(
                            grant.rights_holder_evidence_fingerprint
                        ),
                    )
                    if rights is None:
                        blockers.append(
                            "RIGHTS_HOLDER_EVIDENCE_NOT_VERIFIED"
                        )

                if grant.approval_reference is not None:
                    approval = legal_evidence_store.find_verified(
                        evidence_kind="HUMAN_APPROVAL",
                        content_fingerprint=(
                            grant.approval_reference
                        ),
                    )
                    if approval is None:
                        blockers.append(
                            "HUMAN_APPROVAL_EVIDENCE_NOT_VERIFIED"
                        )

        if environment == "PRODUCTION":
            blockers.append(
                "PRODUCTION_RIGHTS_ACTIVATION_NOT_CONFIGURED"
            )

        return ProviderRightsDecision(
            authorized=not blockers,
            grant_id=grant.grant_id,
            provider_key=provider_key,
            sport=sport,
            use_case=use_case,
            environment=environment,
            blockers=tuple(blockers),
        )

    def audit_integrity(self) -> bool:
        with self._connect() as connection:
            grant_ids = [
                str(row[0])
                for row
                in connection.execute(
                    """
                    SELECT grant_id
                    FROM provider_rights_grant
                    ORDER BY grant_id
                    """
                ).fetchall()
            ]

        try:
            return all(
                self.get_verified(grant_id)
                is not None
                for grant_id
                in grant_ids
            )
        except ValueError:
            return False
