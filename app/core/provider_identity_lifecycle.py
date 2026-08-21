
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from app.core.canonical_identity import SQLiteCanonicalIdentityRegistry


_ALLOWED_SPORTS = {"football", "tennis"}


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


def _nonempty(label: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}_REQUIRED")
    return value.strip()


def _aware_utc(label: str, value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{label}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _aware_utc(
        "TIMESTAMP",
        value,
    ).isoformat()


def _parse(value: str) -> datetime:
    return _aware_utc(
        "TIMESTAMP",
        datetime.fromisoformat(value),
    )


@dataclass(frozen=True)
class TemporalProviderIdentityBinding:
    binding_id: str
    sport: str
    entity_type: str
    provider_key: str
    provider_entity_id: str
    canonical_id: str
    valid_from: datetime
    valid_to: datetime | None
    known_at: datetime
    resolution_method: str
    reason_code: str
    human_reviewed: bool
    predecessor_binding_id: str | None = None
    corrects_binding_id: str | None = None
    name_join_allowed: bool = False
    automatic_model_promotion: bool = False
    automatic_provider_switch: bool = False
    automatic_wagering: bool = False

    def __post_init__(self) -> None:
        if self.name_join_allowed is not False:
            raise ValueError("NAME_JOIN_MUST_REMAIN_FORBIDDEN")
        if self.automatic_model_promotion is not False:
            raise ValueError("AUTOMATIC_MODEL_PROMOTION_MUST_REMAIN_DISABLED")
        if self.automatic_provider_switch is not False:
            raise ValueError("AUTOMATIC_PROVIDER_SWITCH_MUST_REMAIN_DISABLED")
        if self.automatic_wagering is not False:
            raise ValueError("AUTOMATIC_WAGERING_MUST_REMAIN_DISABLED")

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.temporal-provider-identity-binding/1",
            "binding_id": self.binding_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "provider_key": self.provider_key,
            "provider_entity_id": self.provider_entity_id,
            "canonical_id": self.canonical_id,
            "valid_from": _iso(self.valid_from),
            "valid_to": (
                _iso(self.valid_to)
                if self.valid_to is not None
                else None
            ),
            "known_at": _iso(self.known_at),
            "resolution_method": self.resolution_method,
            "reason_code": self.reason_code,
            "human_reviewed": self.human_reviewed,
            "predecessor_binding_id": self.predecessor_binding_id,
            "corrects_binding_id": self.corrects_binding_id,
            "name_join_allowed": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class TemporalProviderIdentityIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


def build_temporal_provider_identity_binding(
    *,
    sport: str,
    entity_type: str,
    provider_key: str,
    provider_entity_id: str,
    canonical_id: str,
    valid_from: datetime,
    valid_to: datetime | None,
    known_at: datetime,
    resolution_method: str,
    reason_code: str,
    human_reviewed: bool,
    predecessor_binding_id: str | None = None,
    corrects_binding_id: str | None = None,
) -> TemporalProviderIdentityBinding:
    sport = _nonempty(
        "SPORT",
        sport,
    ).lower()
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_SPORT")

    entity_type = _nonempty(
        "ENTITY_TYPE",
        entity_type,
    ).lower()
    provider_key = _nonempty(
        "PROVIDER_KEY",
        provider_key,
    )
    provider_entity_id = _nonempty(
        "PROVIDER_ENTITY_ID",
        provider_entity_id,
    )
    canonical_id = _nonempty(
        "CANONICAL_ID",
        canonical_id,
    )

    valid_from = _aware_utc(
        "VALID_FROM",
        valid_from,
    )
    known_at = _aware_utc(
        "KNOWN_AT",
        known_at,
    )

    if valid_from > known_at:
        raise ValueError(
            "PROVIDER_MAPPING_VALID_FROM_AFTER_KNOWN"
        )

    if valid_to is not None:
        valid_to = _aware_utc(
            "VALID_TO",
            valid_to,
        )
        if valid_to <= valid_from:
            raise ValueError(
                "PROVIDER_MAPPING_INVALID_VALIDITY_WINDOW"
            )
        if valid_to > known_at:
            raise ValueError(
                "PROVIDER_MAPPING_VALID_TO_AFTER_KNOWN"
            )

    resolution_method = _nonempty(
        "RESOLUTION_METHOD",
        resolution_method,
    )
    reason_code = _nonempty(
        "REASON_CODE",
        reason_code,
    )

    if not isinstance(
        human_reviewed,
        bool,
    ):
        raise TypeError(
            "HUMAN_REVIEWED_MUST_BE_BOOLEAN"
        )

    if (
        predecessor_binding_id is not None
        and corrects_binding_id is not None
    ):
        raise ValueError(
            "PROVIDER_MAPPING_RELATION_AMBIGUOUS"
        )

    if predecessor_binding_id is not None:
        predecessor_binding_id = _nonempty(
            "PREDECESSOR_BINDING_ID",
            predecessor_binding_id,
        )
        if human_reviewed is not True:
            raise ValueError(
                "PROVIDER_REMAP_REQUIRES_HUMAN_REVIEW"
            )

    if corrects_binding_id is not None:
        corrects_binding_id = _nonempty(
            "CORRECTS_BINDING_ID",
            corrects_binding_id,
        )
        if human_reviewed is not True:
            raise ValueError(
                "PROVIDER_MAPPING_CORRECTION_REQUIRES_HUMAN_REVIEW"
            )

    base = {
        "schema": "matrix.temporal-provider-identity-binding-id/1",
        "sport": sport,
        "entity_type": entity_type,
        "provider_key": provider_key,
        "provider_entity_id": provider_entity_id,
        "canonical_id": canonical_id,
        "valid_from": _iso(valid_from),
        "valid_to": (
            _iso(valid_to)
            if valid_to is not None
            else None
        ),
        "known_at": _iso(known_at),
        "resolution_method": resolution_method,
        "reason_code": reason_code,
        "human_reviewed": human_reviewed,
        "predecessor_binding_id": predecessor_binding_id,
        "corrects_binding_id": corrects_binding_id,
        "name_join_allowed": False,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return TemporalProviderIdentityBinding(
        binding_id=_sha(
            base
        ),
        sport=sport,
        entity_type=entity_type,
        provider_key=provider_key,
        provider_entity_id=provider_entity_id,
        canonical_id=canonical_id,
        valid_from=valid_from,
        valid_to=valid_to,
        known_at=known_at,
        resolution_method=resolution_method,
        reason_code=reason_code,
        human_reviewed=human_reviewed,
        predecessor_binding_id=predecessor_binding_id,
        corrects_binding_id=corrects_binding_id,
    )


def _binding_from_payload(
    payload: Mapping[str, Any],
) -> TemporalProviderIdentityBinding:
    return TemporalProviderIdentityBinding(
        binding_id=str(
            payload["binding_id"]
        ),
        sport=str(
            payload["sport"]
        ),
        entity_type=str(
            payload["entity_type"]
        ),
        provider_key=str(
            payload["provider_key"]
        ),
        provider_entity_id=str(
            payload["provider_entity_id"]
        ),
        canonical_id=str(
            payload["canonical_id"]
        ),
        valid_from=_parse(
            str(
                payload["valid_from"]
            )
        ),
        valid_to=(
            _parse(
                str(
                    payload["valid_to"]
                )
            )
            if payload.get("valid_to")
            is not None
            else None
        ),
        known_at=_parse(
            str(
                payload["known_at"]
            )
        ),
        resolution_method=str(
            payload["resolution_method"]
        ),
        reason_code=str(
            payload["reason_code"]
        ),
        human_reviewed=bool(
            payload["human_reviewed"]
        ),
        predecessor_binding_id=(
            payload.get(
                "predecessor_binding_id"
            )
        ),
        corrects_binding_id=(
            payload.get(
                "corrects_binding_id"
            )
        ),
        name_join_allowed=bool(
            payload.get(
                "name_join_allowed",
                False,
            )
        ),
        automatic_model_promotion=bool(
            payload.get(
                "automatic_model_promotion",
                False,
            )
        ),
        automatic_provider_switch=bool(
            payload.get(
                "automatic_provider_switch",
                False,
            )
        ),
        automatic_wagering=bool(
            payload.get(
                "automatic_wagering",
                False,
            )
        ),
    )


class SQLiteTemporalProviderIdentityLedger:
    def __init__(
        self,
        path: str | Path,
        *,
        identity_registry: SQLiteCanonicalIdentityRegistry,
    ) -> None:
        if not isinstance(
            identity_registry,
            SQLiteCanonicalIdentityRegistry,
        ):
            raise ValueError(
                "CANONICAL_IDENTITY_REGISTRY_REQUIRED"
            )

        self.path = Path(
            path
        )
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.identity_registry = (
            identity_registry
        )

        with closing(
            self._connect()
        ) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS temporal_provider_identity_binding ("
                "binding_id TEXT PRIMARY KEY,"
                "sport TEXT NOT NULL,"
                "entity_type TEXT NOT NULL,"
                "provider_key TEXT NOT NULL,"
                "provider_entity_id TEXT NOT NULL,"
                "canonical_id TEXT NOT NULL,"
                "valid_from TEXT NOT NULL,"
                "valid_to TEXT,"
                "known_at TEXT NOT NULL,"
                "payload_json TEXT NOT NULL,"
                "payload_sha256 TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_temporal_provider_identity_lookup "
                "ON temporal_provider_identity_binding "
                "(sport, entity_type, provider_key, provider_entity_id, "
                "known_at, valid_from, valid_to, binding_id)"
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

    def build_binding(
        self,
        **kwargs,
    ) -> TemporalProviderIdentityBinding:
        return build_temporal_provider_identity_binding(
            **kwargs
        )

    def _canonical_entity(
        self,
        canonical_id: str,
    ) -> Mapping[str, Any]:
        entity = (
            self.identity_registry.get_by_canonical_id(
                canonical_id
            )
        )

        if entity is None:
            raise ValueError(
                "CANONICAL_IDENTITY_NOT_FOUND"
            )

        return entity

    def _validate_canonical_binding(
        self,
        binding: TemporalProviderIdentityBinding,
    ) -> None:
        entity = self._canonical_entity(
            binding.canonical_id
        )

        if (
            entity["sport"]
            != binding.sport
            or entity["entity_type"]
            != binding.entity_type
        ):
            raise ValueError(
                "TEMPORAL_PROVIDER_MAPPING_CANONICAL_SCOPE_MISMATCH"
            )

    def _verified_row(
        self,
        row: tuple[Any, Any],
    ) -> TemporalProviderIdentityBinding:
        payload_json, payload_sha = row

        if (
            sha256(
                str(payload_json).encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "TEMPORAL_PROVIDER_MAPPING_PAYLOAD_HASH_MISMATCH"
            )

        payload = json.loads(
            payload_json
        )
        binding = _binding_from_payload(
            payload
        )

        rebuilt = build_temporal_provider_identity_binding(
            sport=binding.sport,
            entity_type=binding.entity_type,
            provider_key=binding.provider_key,
            provider_entity_id=(
                binding.provider_entity_id
            ),
            canonical_id=binding.canonical_id,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
            known_at=binding.known_at,
            resolution_method=(
                binding.resolution_method
            ),
            reason_code=binding.reason_code,
            human_reviewed=(
                binding.human_reviewed
            ),
            predecessor_binding_id=(
                binding.predecessor_binding_id
            ),
            corrects_binding_id=(
                binding.corrects_binding_id
            ),
        )

        if (
            rebuilt != binding
            or binding.payload() != payload
        ):
            raise ValueError(
                "TEMPORAL_PROVIDER_MAPPING_REDERIVATION_FAILURE"
            )

        return binding

    def _rows_for_key(
        self,
        connection,
        *,
        sport: str,
        entity_type: str,
        provider_key: str,
        provider_entity_id: str,
    ) -> tuple[TemporalProviderIdentityBinding, ...]:
        rows = connection.execute(
            "SELECT payload_json, payload_sha256 "
            "FROM temporal_provider_identity_binding "
            "WHERE sport = ? AND entity_type = ? "
            "AND provider_key = ? AND provider_entity_id = ? "
            "ORDER BY known_at, valid_from, binding_id",
            (
                sport,
                entity_type,
                provider_key,
                provider_entity_id,
            ),
        ).fetchall()

        return tuple(
            self._verified_row(
                row
            )
            for row in rows
        )

    def get_verified(
        self,
        binding_id: str,
    ) -> TemporalProviderIdentityBinding | None:
        with closing(
            self._connect()
        ) as connection:
            row = connection.execute(
                "SELECT payload_json, payload_sha256 "
                "FROM temporal_provider_identity_binding "
                "WHERE binding_id = ?",
                (
                    binding_id,
                ),
            ).fetchone()

        if row is None:
            return None

        binding = self._verified_row(
            row
        )

        if binding.binding_id != binding_id:
            raise ValueError(
                "TEMPORAL_PROVIDER_MAPPING_BINDING_ID_MISMATCH"
            )

        return binding

    @staticmethod
    def _same_key(
        left: TemporalProviderIdentityBinding,
        right: TemporalProviderIdentityBinding,
    ) -> bool:
        return (
            left.sport == right.sport
            and left.entity_type == right.entity_type
            and left.provider_key == right.provider_key
            and (
                left.provider_entity_id
                == right.provider_entity_id
            )
        )

    @staticmethod
    def _root_id(
        binding: TemporalProviderIdentityBinding,
        by_id: Mapping[
            str,
            TemporalProviderIdentityBinding,
        ],
    ) -> str:
        current = binding
        seen: set[str] = set()

        while (
            current.corrects_binding_id
            is not None
        ):
            if current.binding_id in seen:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_CYCLE"
                )
            seen.add(
                current.binding_id
            )

            parent = by_id.get(
                current.corrects_binding_id
            )
            if parent is None:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_TARGET_MISSING"
                )
            current = parent

        return current.binding_id

    @classmethod
    def _effective_heads_as_of(
        cls,
        rows: tuple[
            TemporalProviderIdentityBinding,
            ...,
        ],
        *,
        as_of: datetime,
    ) -> tuple[
        TemporalProviderIdentityBinding,
        ...,
    ]:
        visible = tuple(
            row
            for row in rows
            if row.known_at <= as_of
        )

        by_id = {
            row.binding_id: row
            for row in visible
        }

        heads: dict[
            str,
            TemporalProviderIdentityBinding,
        ] = {}

        for row in visible:
            root_id = cls._root_id(
                row,
                by_id,
            )
            previous = heads.get(
                root_id
            )

            if (
                previous is None
                or row.known_at
                > previous.known_at
                or (
                    row.known_at
                    == previous.known_at
                    and row.binding_id
                    > previous.binding_id
                )
            ):
                heads[
                    root_id
                ] = row

        return tuple(
            sorted(
                heads.values(),
                key=lambda item: (
                    item.valid_from,
                    item.binding_id,
                ),
            )
        )

    @classmethod
    def _resolve_from_rows(
        cls,
        rows: tuple[
            TemporalProviderIdentityBinding,
            ...,
        ],
        *,
        as_of: datetime,
        event_time: datetime,
    ) -> TemporalProviderIdentityBinding | None:
        matches = []

        for binding in cls._effective_heads_as_of(
            rows,
            as_of=as_of,
        ):
            if (
                binding.valid_from
                <= event_time
                and (
                    binding.valid_to
                    is None
                    or event_time
                    < binding.valid_to
                )
            ):
                matches.append(
                    binding
                )

        if len(matches) > 1:
            raise ValueError(
                "AMBIGUOUS_TEMPORAL_PROVIDER_IDENTITY_MAPPING"
            )

        return (
            matches[0]
            if matches
            else None
        )

    def resolve_as_of(
        self,
        *,
        sport: str,
        entity_type: str,
        provider_key: str,
        provider_entity_id: str,
        as_of: datetime,
        event_time: datetime,
    ) -> TemporalProviderIdentityBinding | None:
        as_of = _aware_utc(
            "AS_OF",
            as_of,
        )
        event_time = _aware_utc(
            "EVENT_TIME",
            event_time,
        )

        if event_time > as_of:
            raise ValueError(
                "PROVIDER_MAPPING_EVENT_TIME_AFTER_AS_OF"
            )

        with closing(
            self._connect()
        ) as connection:
            rows = self._rows_for_key(
                connection,
                sport=_nonempty(
                    "SPORT",
                    sport,
                ).lower(),
                entity_type=_nonempty(
                    "ENTITY_TYPE",
                    entity_type,
                ).lower(),
                provider_key=_nonempty(
                    "PROVIDER_KEY",
                    provider_key,
                ),
                provider_entity_id=_nonempty(
                    "PROVIDER_ENTITY_ID",
                    provider_entity_id,
                ),
            )

        return self._resolve_from_rows(
            rows,
            as_of=as_of,
            event_time=event_time,
        )

    def _validate_candidate(
        self,
        binding: TemporalProviderIdentityBinding,
        rows: tuple[
            TemporalProviderIdentityBinding,
            ...,
        ],
    ) -> None:
        self._validate_canonical_binding(
            binding
        )

        by_id = {
            row.binding_id: row
            for row in rows
        }

        if (
            binding.corrects_binding_id
            is not None
        ):
            corrected = by_id.get(
                binding.corrects_binding_id
            )

            if corrected is None:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_TARGET_MISSING"
                )

            if not self._same_key(
                binding,
                corrected,
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_SCOPE_MISMATCH"
                )

            if (
                binding.known_at
                <= corrected.known_at
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_KNOWLEDGE_REGRESSION"
                )

            if (
                binding.valid_from
                != corrected.valid_from
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_VALID_FROM_MUTATION"
                )

            if any(
                row.corrects_binding_id
                == corrected.binding_id
                for row in rows
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_CORRECTION_FORK"
                )

        elif (
            binding.predecessor_binding_id
            is not None
        ):
            predecessor = by_id.get(
                binding.predecessor_binding_id
            )

            if predecessor is None:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_PREDECESSOR_MISSING"
                )

            if not self._same_key(
                binding,
                predecessor,
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_PREDECESSOR_SCOPE_MISMATCH"
                )

            if (
                binding.known_at
                < predecessor.known_at
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_SUCCESSOR_KNOWN_BEFORE_PREDECESSOR"
                )

            if predecessor.valid_to is None:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_PREDECESSOR_MUST_BE_CLOSED"
                )

            if (
                predecessor.valid_to
                != binding.valid_from
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_SEGMENT_GAP_OR_OVERLAP"
                )

            if any(
                row.predecessor_binding_id
                == predecessor.binding_id
                for row in rows
            ):
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_SUCCESSOR_FORK"
                )

        else:
            roots = [
                row
                for row in rows
                if (
                    row.corrects_binding_id
                    is None
                    and row.predecessor_binding_id
                    is None
                )
            ]

            if roots:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_SECOND_INITIAL_FORBIDDEN"
                )

    def _insert(
        self,
        connection,
        binding: TemporalProviderIdentityBinding,
    ) -> None:
        payload_json = _canonical_json(
            binding.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        connection.execute(
            "INSERT INTO temporal_provider_identity_binding "
            "(binding_id, sport, entity_type, provider_key, provider_entity_id, "
            "canonical_id, valid_from, valid_to, known_at, payload_json, payload_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                binding.binding_id,
                binding.sport,
                binding.entity_type,
                binding.provider_key,
                binding.provider_entity_id,
                binding.canonical_id,
                _iso(
                    binding.valid_from
                ),
                (
                    _iso(
                        binding.valid_to
                    )
                    if binding.valid_to
                    is not None
                    else None
                ),
                _iso(
                    binding.known_at
                ),
                payload_json,
                payload_sha,
            ),
        )

    def append(
        self,
        binding: TemporalProviderIdentityBinding,
    ) -> TemporalProviderIdentityBinding:
        if type(binding) is not TemporalProviderIdentityBinding:
            raise ValueError(
                "TEMPORAL_PROVIDER_IDENTITY_BINDING_REQUIRED"
            )

        rebuilt = build_temporal_provider_identity_binding(
            sport=binding.sport,
            entity_type=binding.entity_type,
            provider_key=binding.provider_key,
            provider_entity_id=(
                binding.provider_entity_id
            ),
            canonical_id=binding.canonical_id,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
            known_at=binding.known_at,
            resolution_method=(
                binding.resolution_method
            ),
            reason_code=binding.reason_code,
            human_reviewed=(
                binding.human_reviewed
            ),
            predecessor_binding_id=(
                binding.predecessor_binding_id
            ),
            corrects_binding_id=(
                binding.corrects_binding_id
            ),
        )

        if rebuilt != binding:
            raise ValueError(
                "TEMPORAL_PROVIDER_MAPPING_DERIVATION_MISMATCH"
            )

        existing = self.get_verified(
            binding.binding_id
        )

        if existing is not None:
            if existing != binding:
                raise ValueError(
                    "TEMPORAL_PROVIDER_MAPPING_MUTATION_VIOLATION"
                )
            return existing

        with closing(
            self._connect()
        ) as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            try:
                rows = self._rows_for_key(
                    connection,
                    sport=binding.sport,
                    entity_type=(
                        binding.entity_type
                    ),
                    provider_key=(
                        binding.provider_key
                    ),
                    provider_entity_id=(
                        binding.provider_entity_id
                    ),
                )

                self._validate_candidate(
                    binding,
                    rows,
                )
                self._insert(
                    connection,
                    binding,
                )
                connection.commit()

            except Exception:
                connection.rollback()
                raise

        stored = self.get_verified(
            binding.binding_id
        )

        if stored is None:
            raise ValueError(
                "TEMPORAL_PROVIDER_MAPPING_DURABLE_APPEND_REQUIRED"
            )

        return stored

    def remap(
        self,
        *,
        sport: str,
        entity_type: str,
        provider_key: str,
        provider_entity_id: str,
        new_canonical_id: str,
        remap_at: datetime,
        known_at: datetime,
        resolution_method: str,
        reason_code: str,
        human_reviewed: bool,
    ) -> tuple[
        TemporalProviderIdentityBinding,
        TemporalProviderIdentityBinding,
    ]:
        remap_at = _aware_utc(
            "REMAP_AT",
            remap_at,
        )
        known_at = _aware_utc(
            "KNOWN_AT",
            known_at,
        )

        if remap_at > known_at:
            raise ValueError(
                "PROVIDER_REMAP_AFTER_KNOWN"
            )

        if human_reviewed is not True:
            raise ValueError(
                "PROVIDER_REMAP_REQUIRES_HUMAN_REVIEW"
            )

        sport = _nonempty(
            "SPORT",
            sport,
        ).lower()
        entity_type = _nonempty(
            "ENTITY_TYPE",
            entity_type,
        ).lower()
        provider_key = _nonempty(
            "PROVIDER_KEY",
            provider_key,
        )
        provider_entity_id = _nonempty(
            "PROVIDER_ENTITY_ID",
            provider_entity_id,
        )
        new_canonical_id = _nonempty(
            "NEW_CANONICAL_ID",
            new_canonical_id,
        )

        with closing(
            self._connect()
        ) as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            try:
                rows = self._rows_for_key(
                    connection,
                    sport=sport,
                    entity_type=(
                        entity_type
                    ),
                    provider_key=(
                        provider_key
                    ),
                    provider_entity_id=(
                        provider_entity_id
                    ),
                )

                current = self._resolve_from_rows(
                    rows,
                    as_of=known_at,
                    event_time=remap_at,
                )

                if current is None:
                    raise ValueError(
                        "PROVIDER_REMAP_CURRENT_BINDING_REQUIRED"
                    )

                if (
                    current.canonical_id
                    == new_canonical_id
                ):
                    raise ValueError(
                        "PROVIDER_REMAP_NOOP"
                    )

                closed = (
                    build_temporal_provider_identity_binding(
                        sport=sport,
                        entity_type=entity_type,
                        provider_key=provider_key,
                        provider_entity_id=(
                            provider_entity_id
                        ),
                        canonical_id=(
                            current.canonical_id
                        ),
                        valid_from=(
                            current.valid_from
                        ),
                        valid_to=remap_at,
                        known_at=known_at,
                        resolution_method=(
                            resolution_method
                        ),
                        reason_code=(
                            reason_code
                        ),
                        human_reviewed=True,
                        corrects_binding_id=(
                            current.binding_id
                        ),
                    )
                )

                self._validate_candidate(
                    closed,
                    rows,
                )
                self._insert(
                    connection,
                    closed,
                )

                rows_after_close = (
                    rows
                    + (
                        closed,
                    )
                )

                successor = (
                    build_temporal_provider_identity_binding(
                        sport=sport,
                        entity_type=entity_type,
                        provider_key=provider_key,
                        provider_entity_id=(
                            provider_entity_id
                        ),
                        canonical_id=(
                            new_canonical_id
                        ),
                        valid_from=remap_at,
                        valid_to=None,
                        known_at=known_at,
                        resolution_method=(
                            resolution_method
                        ),
                        reason_code=(
                            reason_code
                        ),
                        human_reviewed=True,
                        predecessor_binding_id=(
                            closed.binding_id
                        ),
                    )
                )

                self._validate_candidate(
                    successor,
                    rows_after_close,
                )
                self._insert(
                    connection,
                    successor,
                )
                connection.commit()

            except Exception:
                connection.rollback()
                raise

        return (
            self.get_verified(
                closed.binding_id
            ),
            self.get_verified(
                successor.binding_id
            ),
        )

    def history(
        self,
        *,
        sport: str,
        entity_type: str,
        provider_key: str,
        provider_entity_id: str,
    ) -> tuple[
        TemporalProviderIdentityBinding,
        ...,
    ]:
        with closing(
            self._connect()
        ) as connection:
            return self._rows_for_key(
                connection,
                sport=_nonempty(
                    "SPORT",
                    sport,
                ).lower(),
                entity_type=_nonempty(
                    "ENTITY_TYPE",
                    entity_type,
                ).lower(),
                provider_key=_nonempty(
                    "PROVIDER_KEY",
                    provider_key,
                ),
                provider_entity_id=_nonempty(
                    "PROVIDER_ENTITY_ID",
                    provider_entity_id,
                ),
            )

    def audit_integrity(
        self,
    ) -> TemporalProviderIdentityIntegrityReport:
        errors: list[str] = []

        with closing(
            self._connect()
        ) as connection:
            key_rows = connection.execute(
                "SELECT DISTINCT sport, entity_type, provider_key, provider_entity_id "
                "FROM temporal_provider_identity_binding "
                "ORDER BY sport, entity_type, provider_key, provider_entity_id"
            ).fetchall()

            total_records = 0

            for (
                sport,
                entity_type,
                provider_key,
                provider_entity_id,
            ) in key_rows:
                try:
                    rows = self._rows_for_key(
                        connection,
                        sport=str(sport),
                        entity_type=str(entity_type),
                        provider_key=str(provider_key),
                        provider_entity_id=str(
                            provider_entity_id
                        ),
                    )
                except Exception as error:
                    errors.append(
                        type(error).__name__
                        + ":"
                        + str(provider_key)
                        + ":"
                        + str(provider_entity_id)
                    )
                    continue

                accepted: tuple[
                    TemporalProviderIdentityBinding,
                    ...,
                ] = ()

                for binding in rows:
                    total_records += 1

                    try:
                        self._validate_candidate(
                            binding,
                            accepted,
                        )
                        accepted = (
                            accepted
                            + (
                                binding,
                            )
                        )
                    except Exception as error:
                        errors.append(
                            type(error).__name__
                            + ":"
                            + binding.binding_id
                        )

        return TemporalProviderIdentityIntegrityReport(
            ok=not errors,
            records=total_records,
            errors=tuple(
                errors
            ),
        )
