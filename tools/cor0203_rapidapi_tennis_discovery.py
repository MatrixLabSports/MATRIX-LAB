from __future__ import annotations

import hashlib
import json
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.provider_retry import ProviderRetryPolicy, retry_delay_seconds
from app.research.tennis.world_calendar_registry import (
    WorldCalendarEvent,
    build_world_calendar_registry,
)

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
RAPIDAPI_BASE_URL = "https://" + RAPIDAPI_HOST
PROVIDER_KEY = "rapidapi_tennis"
RANKING_CUT = date(2026, 9, 21)
MAX_RESPONSE_BYTES = 5_000_000
MAX_FIXTURE_PAGES = 4
MAX_RANKING_PAGES = 4
MAX_TOURNAMENT_INFO_REQUESTS = 12
PAGE_SIZE = 500


class RapidApiTennisDiscoveryError(RuntimeError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _safe_error(value: object, secret: str) -> str:
    text = str(value)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    return text[:500]


def _read_bounded(response, limit: int = MAX_RESPONSE_BYTES) -> bytes:
    body = response.read(limit + 1)
    if len(body) > limit:
        raise RapidApiTennisDiscoveryError("RAPIDAPI_TENNIS_RESPONSE_TOO_LARGE")
    return body


def _positive_id(value: object) -> str | None:
    token = str(value or "").strip()
    return token if token.isdigit() and int(token) > 0 else None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _data_rows(payload: Mapping[str, Any] | list[Any]) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        source = payload
    else:
        source = payload.get("data")
    if not isinstance(source, list):
        raise RapidApiTennisDiscoveryError("RAPIDAPI_TENNIS_DATA_NOT_LIST")
    return [row for row in source if isinstance(row, Mapping)]


def _provider_error(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    for key in ("error", "err"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


class RapidApiTennisClient:
    def __init__(
        self,
        api_key: str,
        *,
        opener: Callable[..., Any] = urlopen,
        timeout_seconds: float = 20.0,
        retry_attempts: int = 2,
        retry_base_delay_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("RAPIDAPI_TENNIS_KEY_REQUIRED")
        normalized_key = api_key.strip()
        try:
            normalized_key.encode("ascii")
        except UnicodeEncodeError as error:
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_KEY_MUST_BE_ASCII"
            ) from error
        if any(ord(ch) < 33 or ord(ch) > 126 for ch in normalized_key):
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_KEY_CONTAINS_INVALID_CHARACTERS"
            )
        self._api_key = normalized_key
        self._opener = opener
        self._timeout = float(timeout_seconds)
        self._retry_policy = ProviderRetryPolicy(
            provider_key=PROVIDER_KEY,
            max_attempts=retry_attempts,
            base_delay_seconds=float(retry_base_delay_seconds),
            max_delay_seconds=max(float(retry_base_delay_seconds), 1.0),
            jitter_ratio=0.0,
        )
        self._sleeper = sleeper
        self.request_attempt_count = 0
        self.request_count = 0

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        public = {
            str(k): str(v)
            for k, v in (params or {}).items()
            if v is not None
        }
        query = urlencode(public)
        url = RAPIDAPI_BASE_URL + path + (("?" + query) if query else "")
        request_fingerprint = _sha({"path": path, "params": public})
        last_transient: BaseException | None = None

        for attempt in range(1, self._retry_policy.max_attempts + 1):
            request = Request(
                url,
                headers={
                    "X-RapidAPI-Key": self._api_key,
                    "X-RapidAPI-Host": RAPIDAPI_HOST,
                    "User-Agent": "MATRIX-COR0203-RAPIDAPI-TENNIS/1.0",
                    "Accept": "application/json",
                },
                method="GET",
            )
            self.request_attempt_count += 1
            try:
                with self._opener(request, timeout=self._timeout) as response:
                    body = _read_bounded(response)
            except HTTPError as error:
                if error.code == 429 or 500 <= int(error.code) <= 599:
                    last_transient = error
                else:
                    raise RapidApiTennisDiscoveryError(
                        "RAPIDAPI_TENNIS_HTTP_ERROR:"
                        + str(error.code)
                        + ":"
                        + _safe_error(error, self._api_key)
                    ) from None
            except (URLError, TimeoutError, OSError) as error:
                last_transient = error
            else:
                if self._api_key.encode("utf-8") in body:
                    raise RapidApiTennisDiscoveryError(
                        "RAPIDAPI_TENNIS_SECRET_ECHO_DETECTED"
                    )
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise RapidApiTennisDiscoveryError(
                        "RAPIDAPI_TENNIS_INVALID_JSON"
                    ) from error
                provider_error = _provider_error(payload)
                if provider_error:
                    raise RapidApiTennisDiscoveryError(
                        "RAPIDAPI_TENNIS_PROVIDER_FAILURE:" + provider_error[:300]
                    )
                if not isinstance(payload, (Mapping, list)):
                    raise RapidApiTennisDiscoveryError(
                        "RAPIDAPI_TENNIS_RESPONSE_INVALID"
                    )
                self.request_count += 1
                return payload

            if attempt < self._retry_policy.max_attempts:
                self._sleeper(
                    retry_delay_seconds(
                        policy=self._retry_policy,
                        queue_item_fingerprint=request_fingerprint,
                        retry_number=attempt,
                    )
                )

        assert last_transient is not None
        raise RapidApiTennisDiscoveryError(
            "RAPIDAPI_TENNIS_RETRY_EXHAUSTED:"
            + type(last_transient).__name__
            + ":"
            + _safe_error(last_transient, self._api_key)
        ) from None

    def fixtures(self, start: date, stop: date) -> Mapping[str, Any]:
        if stop < start:
            raise ValueError("INVALID_DISCOVERY_DATE_RANGE")
        if (stop - start).days > 3:
            raise ValueError("DISCOVERY_RANGE_EXCEEDS_4_DAYS")
        if start == stop:
            path = f"/tennis/v2/atp/fixtures/{start.isoformat()}"
        else:
            path = (
                f"/tennis/v2/atp/fixtures/{start.isoformat()}/"
                f"{stop.isoformat()}"
            )

        rows: list[Mapping[str, Any]] = []
        page = 1
        for _ in range(MAX_FIXTURE_PAGES):
            payload = self._get(
                path,
                {
                    "include": "round,tournament,tournament.court",
                    "filter": "PlayerGroup:singles;TourRank:1",
                    "pageNo": page,
                    "pageSize": PAGE_SIZE,
                },
            )
            if not isinstance(payload, Mapping):
                raise RapidApiTennisDiscoveryError(
                    "RAPIDAPI_TENNIS_FIXTURE_ENVELOPE_INVALID"
                )
            rows.extend(_data_rows(payload))
            if not bool(payload.get("hasNextPage")):
                break
            page += 1
        else:
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_FIXTURE_PAGE_LIMIT_REACHED"
            )

        return {"data": rows, "pageNo": 1, "pageSize": len(rows), "hasNextPage": False}

    def tournament_info(self, tournament_id: str) -> Mapping[str, Any]:
        token = _positive_id(tournament_id)
        if token is None:
            raise ValueError("RAPIDAPI_TENNIS_TOURNAMENT_ID_INVALID")
        payload = self._get(f"/tennis/v2/atp/tournament/info/{token}")
        if not isinstance(payload, Mapping):
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_TOURNAMENT_INFO_INVALID"
            )
        data = payload.get("data")
        if isinstance(data, Mapping):
            return dict(data)
        if "id" in payload or "name" in payload:
            return dict(payload)
        raise RapidApiTennisDiscoveryError(
            "RAPIDAPI_TENNIS_TOURNAMENT_INFO_MISSING"
        )

    def ranking_snapshot(
        self,
        *,
        ranking_date: date,
        wanted_player_ids: Iterable[str],
    ) -> dict[str, Mapping[str, Any]]:
        wanted = {str(x) for x in wanted_player_ids if _positive_id(x)}
        found: dict[str, Mapping[str, Any]] = {}
        page = 1
        for _ in range(MAX_RANKING_PAGES):
            payload = self._get(
                "/tennis/v2/ranking/atp",
                {
                    "date": ranking_date.strftime("%d.%m.%Y"),
                    "group": "singles",
                    "page": page,
                    "limit": PAGE_SIZE,
                },
            )
            rows = _data_rows(payload)
            for row in rows:
                player = _mapping(row.get("player"))
                player_id = _positive_id(player.get("id"))
                if player_id is None:
                    continue
                if wanted and player_id not in wanted:
                    continue
                position = row.get("position")
                points = row.get("pts")
                if position is None or points is None:
                    continue
                found[player_id] = {
                    "place": str(position),
                    "points": str(points),
                    "player": str(player.get("name") or "").strip(),
                    "country": str(player.get("countryAcr") or "").strip(),
                    "snapshot_date": ranking_date.isoformat(),
                }
            if wanted and wanted.issubset(found):
                break
            if not rows or len(rows) < PAGE_SIZE:
                break
            page += 1
        return found

    def results_for_date(self, target_date: date) -> Mapping[str, Any]:
        rows: list[Mapping[str, Any]] = []
        page = 1
        for _ in range(MAX_FIXTURE_PAGES):
            payload = self._get(
                f"/tennis/v2/atp/results/{target_date.isoformat()}",
                {
                    "pageNo": page,
                    "pageSize": PAGE_SIZE,
                    "filter": "PlayerGroup:singles",
                },
            )
            if not isinstance(payload, Mapping):
                raise RapidApiTennisDiscoveryError(
                    "RAPIDAPI_TENNIS_RESULTS_ENVELOPE_INVALID"
                )
            rows.extend(_data_rows(payload))
            if not bool(payload.get("hasNextPage")):
                break
            page += 1
        else:
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_RESULTS_PAGE_LIMIT_REACHED"
            )
        return {
            "data": rows,
            "pageNo": 1,
            "pageSize": len(rows),
            "hasNextPage": False,
        }


def _parse_start(row: Mapping[str, Any]) -> datetime:
    token = str(row.get("startTime") or row.get("date") or "").strip()
    if not token:
        raise ValueError("RAPIDAPI_TENNIS_START_MISSING")
    parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("RAPIDAPI_TENNIS_START_NOT_AWARE")
    return parsed.astimezone(timezone.utc)


def _player(row: Mapping[str, Any], n: int) -> tuple[str | None, str]:
    obj = _mapping(row.get(f"player{n}"))
    player_id = _positive_id(row.get(f"player{n}Id") or obj.get("id"))
    name = str(obj.get("name") or row.get(f"player{n}Name") or "").strip()
    return player_id, name


def _tournament_tier(info: Mapping[str, Any]) -> str:
    return str(info.get("tier") or info.get("level") or "").strip()


def _rank_id(info: Mapping[str, Any]) -> str | None:
    rank = _mapping(info.get("rank"))
    return _positive_id(
        info.get("rankId")
        or info.get("rank_id")
        or rank.get("id")
        or rank.get("rank_id")
    )


def _court_name(info: Mapping[str, Any]) -> str:
    court = _mapping(info.get("court"))
    return str(
        court.get("name")
        or court.get("court_name")
        or info.get("courtName")
        or info.get("surface")
        or ""
    ).strip()


def _round_name(row: Mapping[str, Any]) -> str:
    round_obj = _mapping(row.get("round"))
    return str(
        round_obj.get("name")
        or round_obj.get("round_name")
        or row.get("roundName")
        or ("ROUND_ID_" + str(row.get("roundId")))
    ).strip()


def build_discovery_registry(
    *,
    fixture_payload: Mapping[str, Any],
    tournament_info: Mapping[str, Mapping[str, Any]],
    ranking_by_player: Mapping[str, Mapping[str, Any]],
    as_of_utc: str,
) -> dict[str, Any]:
    as_of = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )
    events: list[WorldCalendarEvent] = []
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in _data_rows(fixture_payload):
        match_id = _positive_id(row.get("matchId") or row.get("id"))
        tournament_id = _positive_id(row.get("tournamentId"))
        p1_id, p1_name = _player(row, 1)
        p2_id, p2_name = _player(row, 2)
        blockers: list[str] = []

        if match_id is None:
            blockers.append("MATCH_ID_INVALID")
        if tournament_id is None:
            blockers.append("TOURNAMENT_ID_INVALID")
        if p1_id is None or p2_id is None or p1_id == p2_id:
            blockers.append("PLAYER_IDS_NOT_FIXED")
        if not p1_name or not p2_name or p1_name == p2_name:
            blockers.append("PLAYER_NAMES_NOT_FIXED")

        try:
            start = _parse_start(row)
            if start <= as_of:
                blockers.append("EVENT_NOT_FUTURE")
        except (TypeError, ValueError):
            start = None
            blockers.append("START_AUTHORITY_INVALID")

        info = tournament_info.get(tournament_id or "", {})
        tier = _tournament_tier(info)
        rank_id = _rank_id(info)
        court = _court_name(info)

        if rank_id != "1":
            blockers.append("TOURNAMENT_RANK_NOT_CHALLENGER_ITF")
        if "challenger" not in tier.casefold():
            blockers.append("TOURNAMENT_NOT_PROVEN_CHALLENGER")
        if court.casefold() != "hard":
            blockers.append("SURFACE_OUT_OF_DOMAIN")

        p1_ranking = ranking_by_player.get(p1_id or "")
        p2_ranking = ranking_by_player.get(p2_id or "")
        if not isinstance(p1_ranking, Mapping):
            blockers.append("RANKING_CUT_MISSING_PLAYER1")
        if not isinstance(p2_ranking, Mapping):
            blockers.append("RANKING_CUT_MISSING_PLAYER2")

        if blockers:
            rejected.append(
                {
                    "match_id": match_id,
                    "tournament_id": tournament_id,
                    "blockers": sorted(set(blockers)),
                }
            )
            continue

        tournament_name = str(info.get("name") or f"rapidapi-tournament:{tournament_id}")
        round_name = _round_name(row) or "UNKNOWN_ROUND"
        snapshot = {
            "fixture": row,
            "tournament_info": info,
            "ranking_player1": p1_ranking,
            "ranking_player2": p2_ranking,
        }
        source_sha = _sha(snapshot)
        event_id = f"rapidapi-tennis:match:{match_id}"
        source_reference = (
            f"fixtures:matchId={match_id};"
            f"tournament_info={tournament_id};"
            f"ranking_cut={RANKING_CUT.isoformat()}"
        )

        events.append(
            WorldCalendarEvent(
                event_id=event_id,
                sport="TENNIS",
                competition_id=f"rapidapi-tennis:tournament:{tournament_id}",
                competition_name=tournament_name,
                tour_level="ATP_CHALLENGER",
                surface="Hard",
                environment="UNKNOWN",
                round=round_name,
                event_start_utc=start.isoformat(),
                player1_id=f"rapidapi-tennis:player:{p1_id}",
                player2_id=f"rapidapi-tennis:player:{p2_id}",
                source_provider=PROVIDER_KEY,
                source_reference=source_reference,
                source_snapshot_sha256=source_sha,
            )
        )
        candidates.append(
            {
                "event_id": event_id,
                "canonical_source_event_id": event_id,
                "competition_id": f"rapidapi-tennis:tournament:{tournament_id}",
                "competition": tournament_name,
                "round": round_name,
                "surface": "Hard",
                "tour_level": "C",
                "event_start_utc": start.isoformat(),
                "target_period": 20260921,
                "source_provider": PROVIDER_KEY,
                "source_reference": source_reference,
                "source_snapshot_sha256": source_sha,
                "players": [
                    {
                        "name": p1_name,
                        "provider_player_id": f"rapidapi-tennis:player:{p1_id}",
                        "provider_ranking": dict(p1_ranking),
                    },
                    {
                        "name": p2_name,
                        "provider_player_id": f"rapidapi-tennis:player:{p2_id}",
                        "provider_ranking": dict(p2_ranking),
                    },
                ],
                "historical_identity_crosswalk_status": "PENDING",
            }
        )

    registry = build_world_calendar_registry(events=events, as_of_utc=as_of_utc)
    return {
        "schema": "MATRIX_COR0203_RAPIDAPI_TENNIS_DISCOVERY_V1",
        "provider": PROVIDER_KEY,
        "as_of_utc": as_of.isoformat(),
        "fixture_rows": len(_data_rows(fixture_payload)),
        "eligible_input_events": len(events),
        "eligible_candidates": candidates,
        "provider_rejected": rejected,
        "world_registry": registry,
        "ranking_cut": RANKING_CUT.isoformat(),
        "automatic_model_promotion": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def fetch_discovery(
    *,
    client: RapidApiTennisClient,
    start: date,
    stop: date,
    as_of_utc: str,
) -> dict[str, Any]:
    fixtures = client.fixtures(start, stop)
    rows = _data_rows(fixtures)
    tournament_ids = sorted(
        {
            token
            for row in rows
            for token in [_positive_id(row.get("tournamentId"))]
            if token is not None
        }
    )
    if len(tournament_ids) > MAX_TOURNAMENT_INFO_REQUESTS:
        tournament_ids = tournament_ids[:MAX_TOURNAMENT_INFO_REQUESTS]

    info = {
        tournament_id: client.tournament_info(tournament_id)
        for tournament_id in tournament_ids
    }
    wanted_player_ids = {
        token
        for row in rows
        for token in (
            _player(row, 1)[0],
            _player(row, 2)[0],
        )
        if token is not None
    }
    rankings = client.ranking_snapshot(
        ranking_date=RANKING_CUT,
        wanted_player_ids=wanted_player_ids,
    )
    result = build_discovery_registry(
        fixture_payload=fixtures,
        tournament_info=info,
        ranking_by_player=rankings,
        as_of_utc=as_of_utc,
    )
    result["request_count"] = client.request_count
    result["network_calls"] = client.request_count
    result["tournaments_queried"] = len(info)
    result["ranking_players_found"] = len(rankings)
    return result
