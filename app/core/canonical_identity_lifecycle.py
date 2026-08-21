
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
_ALLOWED_EVENT_TYPES = {
    "ALIAS_ADDED",
    "DISPLAY_NAME_CHANGED",
    "SUPERSEDED",
}


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
class CanonicalIdentityLifecycleEvent:
    event_id: str
    sport: str
    entity_type: str
    canonical_id: str
    event_type: str
    effective_at: datetime
    known_at: datetime
    reason_code: str
    human_reviewed: bool
    previous_event_id: str | None = None
    alias: str | None = None
    display_name: str | None = None
    superseded_by_canonical_id: str | None = None
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
            "schema": "matrix.canonical-identity-lifecycle-event/1",
            "event_id": self.event_id,
            "sport": self.sport,
            "entity_type": self.entity_type,
            "canonical_id": self.canonical_id,
            "event_type": self.event_type,
            "effective_at": _iso(self.effective_at),
            "known_at": _iso(self.known_at),
            "reason_code": self.reason_code,
            "human_reviewed": self.human_reviewed,
            "previous_event_id": self.previous_event_id,
            "alias": self.alias,
            "display_name": self.display_name,
            "superseded_by_canonical_id": self.superseded_by_canonical_id,
            "name_join_allowed": False,
            "automatic_model_promotion": False,
            "automatic_provider_switch": False,
            "automatic_wagering": False,
        }


@dataclass(frozen=True)
class CanonicalIdentityState:
    sport: str
    entity_type: str
    canonical_id: str
    display_name: str
    aliases: tuple[str, ...]
    superseded_by_canonical_id: str | None
    event_ids: tuple[str, ...]
    as_of: datetime
    event_time: datetime
    name_join_allowed: bool = False

    def __post_init__(self) -> None:
        if self.name_join_allowed is not False:
            raise ValueError("NAME_JOIN_MUST_REMAIN_FORBIDDEN")


@dataclass(frozen=True)
class CanonicalIdentityLifecycleIntegrityReport:
    ok: bool
    records: int
    errors: tuple[str, ...]


def build_canonical_identity_lifecycle_event(
    *,
    sport: str,
    entity_type: str,
    canonical_id: str,
    event_type: str,
    effective_at: datetime,
    known_at: datetime,
    reason_code: str,
    human_reviewed: bool,
    previous_event_id: str | None = None,
    alias: str | None = None,
    display_name: str | None = None,
    superseded_by_canonical_id: str | None = None,
) -> CanonicalIdentityLifecycleEvent:
    sport = _nonempty("SPORT", sport).lower()
    if sport not in _ALLOWED_SPORTS:
        raise ValueError("INVALID_SPORT")

    entity_type = _nonempty(
        "ENTITY_TYPE",
        entity_type,
    ).lower()
    canonical_id = _nonempty(
        "CANONICAL_ID",
        canonical_id,
    )
    event_type = _nonempty(
        "EVENT_TYPE",
        event_type,
    ).upper()

    if event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError("INVALID_IDENTITY_LIFECYCLE_EVENT_TYPE")

    effective_at = _aware_utc(
        "EFFECTIVE_AT",
        effective_at,
    )
    known_at = _aware_utc(
        "KNOWN_AT",
        known_at,
    )

    if effective_at > known_at:
        raise ValueError("IDENTITY_EVENT_EFFECTIVE_AFTER_KNOWN")

    reason_code = _nonempty(
        "REASON_CODE",
        reason_code,
    )

    if not isinstance(human_reviewed, bool):
        raise TypeError("HUMAN_REVIEWED_MUST_BE_BOOLEAN")

    if previous_event_id is not None:
        previous_event_id = _nonempty(
            "PREVIOUS_EVENT_ID",
            previous_event_id,
        )

    if event_type == "ALIAS_ADDED":
        alias = _nonempty(
            "ALIAS",
            alias,
        )
        if display_name is not None or superseded_by_canonical_id is not None:
            raise ValueError("ALIAS_EVENT_SCOPE_INVALID")

    elif event_type == "DISPLAY_NAME_CHANGED":
        display_name = _nonempty(
            "DISPLAY_NAME",
            display_name,
        )
        if alias is not None or superseded_by_canonical_id is not None:
            raise ValueError("DISPLAY_NAME_EVENT_SCOPE_INVALID")
        if human_reviewed is not True:
            raise ValueError("DISPLAY_NAME_CHANGE_REQUIRES_HUMAN_REVIEW")

    elif event_type == "SUPERSEDED":
        superseded_by_canonical_id = _nonempty(
            "SUPERSEDED_BY_CANONICAL_ID",
            superseded_by_canonical_id,
        )
        if alias is not None or display_name is not None:
            raise ValueError("SUPERSESSION_EVENT_SCOPE_INVALID")
        if superseded_by_canonical_id == canonical_id:
            raise ValueError("IDENTITY_CANNOT_SUPERSEDE_ITSELF")
        if human_reviewed is not True:
            raise ValueError("IDENTITY_SUPERSESSION_REQUIRES_HUMAN_REVIEW")

    base = {
        "schema": "matrix.canonical-identity-lifecycle-event-id/1",
        "sport": sport,
        "entity_type": entity_type,
        "canonical_id": canonical_id,
        "event_type": event_type,
        "effective_at": _iso(effective_at),
        "known_at": _iso(known_at),
        "reason_code": reason_code,
        "human_reviewed": human_reviewed,
        "previous_event_id": previous_event_id,
        "alias": alias,
        "display_name": display_name,
        "superseded_by_canonical_id": superseded_by_canonical_id,
        "name_join_allowed": False,
        "automatic_model_promotion": False,
        "automatic_provider_switch": False,
        "automatic_wagering": False,
    }

    return CanonicalIdentityLifecycleEvent(
        event_id=_sha(base),
        sport=sport,
        entity_type=entity_type,
        canonical_id=canonical_id,
        event_type=event_type,
        effective_at=effective_at,
        known_at=known_at,
        reason_code=reason_code,
        human_reviewed=human_reviewed,
        previous_event_id=previous_event_id,
        alias=alias,
        display_name=display_name,
        superseded_by_canonical_id=superseded_by_canonical_id,
    )


def _event_from_payload(
    payload: Mapping[str, Any],
) -> CanonicalIdentityLifecycleEvent:
    return CanonicalIdentityLifecycleEvent(
        event_id=str(payload["event_id"]),
        sport=str(payload["sport"]),
        entity_type=str(payload["entity_type"]),
        canonical_id=str(payload["canonical_id"]),
        event_type=str(payload["event_type"]),
        effective_at=_parse(str(payload["effective_at"])),
        known_at=_parse(str(payload["known_at"])),
        reason_code=str(payload["reason_code"]),
        human_reviewed=bool(payload["human_reviewed"]),
        previous_event_id=payload.get("previous_event_id"),
        alias=payload.get("alias"),
        display_name=payload.get("display_name"),
        superseded_by_canonical_id=payload.get(
            "superseded_by_canonical_id"
        ),
        name_join_allowed=bool(
            payload.get("name_join_allowed", False)
        ),
        automatic_model_promotion=bool(
            payload.get("automatic_model_promotion", False)
        ),
        automatic_provider_switch=bool(
            payload.get("automatic_provider_switch", False)
        ),
        automatic_wagering=bool(
            payload.get("automatic_wagering", False)
        ),
    )


class SQLiteCanonicalIdentityLifecycleLedger:
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
            raise ValueError("CANONICAL_IDENTITY_REGISTRY_REQUIRED")

        self.path = Path(path)
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.identity_registry = identity_registry

        with closing(
            self._connect()
        ) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS canonical_identity_lifecycle ("
                "event_id TEXT PRIMARY KEY,"
                "canonical_id TEXT NOT NULL,"
                "sport TEXT NOT NULL,"
                "entity_type TEXT NOT NULL,"
                "event_type TEXT NOT NULL,"
                "effective_at TEXT NOT NULL,"
                "known_at TEXT NOT NULL,"
                "payload_json TEXT NOT NULL,"
                "payload_sha256 TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS "
                "idx_canonical_identity_lifecycle_lookup "
                "ON canonical_identity_lifecycle "
                "(canonical_id, known_at, effective_at, event_id)"
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

    def build_event(self, **kwargs) -> CanonicalIdentityLifecycleEvent:
        return build_canonical_identity_lifecycle_event(
            **kwargs
        )

    def _canonical_entity(
        self,
        canonical_id: str,
    ) -> Mapping[str, Any]:
        entity = self.identity_registry.get_by_canonical_id(
            canonical_id
        )
        if entity is None:
            raise ValueError("CANONICAL_IDENTITY_NOT_FOUND")
        return entity

    def _validate_binding(
        self,
        event: CanonicalIdentityLifecycleEvent,
    ) -> None:
        entity = self._canonical_entity(
            event.canonical_id
        )

        if (
            entity["sport"] != event.sport
            or entity["entity_type"] != event.entity_type
        ):
            raise ValueError(
                "IDENTITY_LIFECYCLE_CANONICAL_BINDING_MISMATCH"
            )

        if event.superseded_by_canonical_id is not None:
            target = self._canonical_entity(
                event.superseded_by_canonical_id
            )

            if (
                target["sport"] != event.sport
                or target["entity_type"] != event.entity_type
            ):
                raise ValueError(
                    "IDENTITY_SUPERSESSION_SCOPE_MISMATCH"
                )

    def _verified_row(
        self,
        row: tuple[Any, Any],
    ) -> CanonicalIdentityLifecycleEvent:
        payload_json, payload_sha = row

        if (
            sha256(
                str(payload_json).encode("utf-8")
            ).hexdigest()
            != payload_sha
        ):
            raise ValueError(
                "IDENTITY_LIFECYCLE_PAYLOAD_HASH_MISMATCH"
            )

        payload = json.loads(
            payload_json
        )
        event = _event_from_payload(
            payload
        )

        rebuilt = build_canonical_identity_lifecycle_event(
            sport=event.sport,
            entity_type=event.entity_type,
            canonical_id=event.canonical_id,
            event_type=event.event_type,
            effective_at=event.effective_at,
            known_at=event.known_at,
            reason_code=event.reason_code,
            human_reviewed=event.human_reviewed,
            previous_event_id=event.previous_event_id,
            alias=event.alias,
            display_name=event.display_name,
            superseded_by_canonical_id=(
                event.superseded_by_canonical_id
            ),
        )

        if (
            rebuilt != event
            or event.payload() != payload
        ):
            raise ValueError(
                "IDENTITY_LIFECYCLE_REDERIVATION_FAILURE"
            )

        return event

    def _events_for(
        self,
        canonical_id: str,
    ) -> tuple[CanonicalIdentityLifecycleEvent, ...]:
        with closing(
            self._connect()
        ) as connection:
            rows = connection.execute(
                "SELECT payload_json, payload_sha256 "
                "FROM canonical_identity_lifecycle "
                "WHERE canonical_id = ? "
                "ORDER BY known_at, event_id",
                (
                    canonical_id,
                ),
            ).fetchall()

        return tuple(
            self._verified_row(row)
            for row in rows
        )

    def get_verified(
        self,
        event_id: str,
    ) -> CanonicalIdentityLifecycleEvent | None:
        with closing(
            self._connect()
        ) as connection:
            row = connection.execute(
                "SELECT payload_json, payload_sha256 "
                "FROM canonical_identity_lifecycle "
                "WHERE event_id = ?",
                (
                    event_id,
                ),
            ).fetchone()

        if row is None:
            return None

        event = self._verified_row(
            row
        )

        if event.event_id != event_id:
            raise ValueError(
                "IDENTITY_LIFECYCLE_EVENT_ID_MISMATCH"
            )

        return event

    def append(
        self,
        event: CanonicalIdentityLifecycleEvent,
    ) -> CanonicalIdentityLifecycleEvent:
        if type(event) is not CanonicalIdentityLifecycleEvent:
            raise ValueError(
                "CANONICAL_IDENTITY_LIFECYCLE_EVENT_REQUIRED"
            )

        rebuilt = build_canonical_identity_lifecycle_event(
            sport=event.sport,
            entity_type=event.entity_type,
            canonical_id=event.canonical_id,
            event_type=event.event_type,
            effective_at=event.effective_at,
            known_at=event.known_at,
            reason_code=event.reason_code,
            human_reviewed=event.human_reviewed,
            previous_event_id=event.previous_event_id,
            alias=event.alias,
            display_name=event.display_name,
            superseded_by_canonical_id=(
                event.superseded_by_canonical_id
            ),
        )

        if rebuilt != event:
            raise ValueError(
                "IDENTITY_LIFECYCLE_EVENT_DERIVATION_MISMATCH"
            )

        self._validate_binding(
            event
        )

        existing = self.get_verified(
            event.event_id
        )

        if existing is not None:
            if existing != event:
                raise ValueError(
                    "IDENTITY_LIFECYCLE_EVENT_MUTATION_VIOLATION"
                )
            return existing

        events = self._events_for(
            event.canonical_id
        )

        expected_previous = (
            events[-1].event_id
            if events
            else None
        )

        if event.previous_event_id != expected_previous:
            raise ValueError(
                "IDENTITY_LIFECYCLE_NON_LINEAR_CHAIN"
            )

        if (
            events
            and event.known_at
            <= events[-1].known_at
        ):
            raise ValueError(
                "IDENTITY_LIFECYCLE_KNOWLEDGE_TIME_REGRESSION"
            )

        if any(
            item.event_type == "SUPERSEDED"
            for item in events
        ):
            raise ValueError(
                "SUPERSEDED_IDENTITY_IS_TERMINAL"
            )

        if event.event_type == "ALIAS_ADDED":
            aliases = {
                item.alias.casefold()
                for item in events
                if (
                    item.event_type == "ALIAS_ADDED"
                    and item.alias is not None
                )
            }
            if event.alias.casefold() in aliases:
                raise ValueError(
                    "DUPLICATE_IDENTITY_ALIAS"
                )

        if event.event_type == "DISPLAY_NAME_CHANGED":
            state = self.state_as_of(
                canonical_id=event.canonical_id,
                as_of=event.known_at,
                event_time=event.effective_at,
            )
            if (
                state.display_name.casefold()
                == event.display_name.casefold()
            ):
                raise ValueError(
                    "IDENTITY_DISPLAY_NAME_NOOP"
                )

        if event.event_type == "SUPERSEDED":
            terminal = self.resolve_terminal_canonical_id_as_of(
                canonical_id=(
                    event.superseded_by_canonical_id
                ),
                as_of=event.known_at,
                event_time=event.effective_at,
            )

            if terminal == event.canonical_id:
                raise ValueError(
                    "IDENTITY_SUPERSESSION_CYCLE"
                )

        payload_json = _canonical_json(
            event.payload()
        )
        payload_sha = sha256(
            payload_json.encode("utf-8")
        ).hexdigest()

        with closing(
            self._connect()
        ) as connection:
            connection.execute(
                "BEGIN IMMEDIATE"
            )
            try:
                connection.execute(
                    "INSERT INTO canonical_identity_lifecycle "
                    "(event_id, canonical_id, sport, entity_type, "
                    "event_type, effective_at, known_at, payload_json, payload_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.canonical_id,
                        event.sport,
                        event.entity_type,
                        event.event_type,
                        _iso(event.effective_at),
                        _iso(event.known_at),
                        payload_json,
                        payload_sha,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        stored = self.get_verified(
            event.event_id
        )

        if stored is None:
            raise ValueError(
                "IDENTITY_LIFECYCLE_DURABLE_APPEND_REQUIRED"
            )

        return stored

    def state_as_of(
        self,
        *,
        canonical_id: str,
        as_of: datetime,
        event_time: datetime | None = None,
    ) -> CanonicalIdentityState:
        as_of = _aware_utc(
            "AS_OF",
            as_of,
        )
        event_time = _aware_utc(
            "EVENT_TIME",
            as_of if event_time is None else event_time,
        )

        if event_time > as_of:
            raise ValueError(
                "IDENTITY_EVENT_TIME_AFTER_AS_OF"
            )

        entity = self._canonical_entity(
            canonical_id
        )

        display_name = str(
            entity["display_name"]
        )
        aliases: list[str] = []
        superseded_by: str | None = None
        selected_ids: list[str] = []

        for event in self._events_for(
            canonical_id
        ):
            if (
                event.known_at > as_of
                or event.effective_at > event_time
            ):
                continue

            selected_ids.append(
                event.event_id
            )

            if event.event_type == "ALIAS_ADDED":
                aliases.append(
                    event.alias
                )
            elif event.event_type == "DISPLAY_NAME_CHANGED":
                display_name = event.display_name
            elif event.event_type == "SUPERSEDED":
                superseded_by = (
                    event.superseded_by_canonical_id
                )

        return CanonicalIdentityState(
            sport=str(
                entity["sport"]
            ),
            entity_type=str(
                entity["entity_type"]
            ),
            canonical_id=canonical_id,
            display_name=display_name,
            aliases=tuple(
                aliases
            ),
            superseded_by_canonical_id=(
                superseded_by
            ),
            event_ids=tuple(
                selected_ids
            ),
            as_of=as_of,
            event_time=event_time,
        )

    def resolve_terminal_canonical_id_as_of(
        self,
        *,
        canonical_id: str,
        as_of: datetime,
        event_time: datetime | None = None,
    ) -> str:
        as_of = _aware_utc(
            "AS_OF",
            as_of,
        )
        event_time = _aware_utc(
            "EVENT_TIME",
            as_of if event_time is None else event_time,
        )

        current = canonical_id
        seen: set[str] = set()

        while True:
            if current in seen:
                raise ValueError(
                    "IDENTITY_SUPERSESSION_CYCLE"
                )
            seen.add(
                current
            )

            state = self.state_as_of(
                canonical_id=current,
                as_of=as_of,
                event_time=event_time,
            )

            if (
                state.superseded_by_canonical_id
                is None
            ):
                return current

            current = (
                state.superseded_by_canonical_id
            )

    def audit_integrity(
        self,
    ) -> CanonicalIdentityLifecycleIntegrityReport:
        errors: list[str] = []

        with closing(
            self._connect()
        ) as connection:
            ids = [
                str(row[0])
                for row in connection.execute(
                    "SELECT event_id "
                    "FROM canonical_identity_lifecycle "
                    "ORDER BY known_at, event_id"
                ).fetchall()
            ]

        previous_by_identity: dict[str, str | None] = {}
        known_by_identity: dict[str, datetime] = {}

        for event_id in ids:
            try:
                event = self.get_verified(
                    event_id
                )
                if event is None:
                    errors.append(
                        "MISSING_EVENT:"
                        + event_id
                    )
                    continue

                self._validate_binding(
                    event
                )

                expected_previous = (
                    previous_by_identity.get(
                        event.canonical_id
                    )
                )

                if (
                    event.previous_event_id
                    != expected_previous
                ):
                    errors.append(
                        "NON_LINEAR_CHAIN:"
                        + event.event_id
                    )

                previous_known = (
                    known_by_identity.get(
                        event.canonical_id
                    )
                )
                if (
                    previous_known is not None
                    and event.known_at
                    <= previous_known
                ):
                    errors.append(
                        "KNOWLEDGE_TIME_REGRESSION:"
                        + event.event_id
                    )

                previous_by_identity[
                    event.canonical_id
                ] = event.event_id
                known_by_identity[
                    event.canonical_id
                ] = event.known_at

            except Exception as error:
                errors.append(
                    type(error).__name__
                    + ":"
                    + event_id
                )

        return CanonicalIdentityLifecycleIntegrityReport(
            ok=not errors,
            records=len(
                ids
            ),
            errors=tuple(
                errors
            ),
        )
