from __future__ import annotations

import hashlib
import json
import time
import unicodedata
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
from tools.cor0203_physical_identity import physical_event_key

RAPIDAPI_HOST = "tennis-api-atp-wta-itf.p.rapidapi.com"
RAPIDAPI_BASE_URL = "https://" + RAPIDAPI_HOST
PROVIDER_KEY = "rapidapi_tennis"
RANKING_CUT = date(2026, 9, 21)
MAX_RESPONSE_BYTES = 5_000_000
MAX_FIXTURE_PAGES = 4
MAX_WORLD_FIXTURE_PAGES = 12
MAX_RESULT_PAGES = 12
MAX_RANKING_PAGES = 4
MAX_RANK_HISTORY_FALLBACK_REQUESTS = 32
MAX_RANK_ALIAS_PROFILE_REQUESTS = 32
MAX_TOURNAMENT_INFO_REQUESTS = 12
PAGE_SIZE = 500
MODEL_HARD_SURFACES = {"hard", "i.hard", "indoor hard", "indoor_hard"}


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

    def fixtures_for_tour(
        self,
        tour: str,
        start: date,
        stop: date,
        *,
        filter_value: str | None = None,
        max_pages: int = MAX_WORLD_FIXTURE_PAGES,
    ) -> Mapping[str, Any]:
        normalized_tour = str(tour or "").strip().casefold()
        if normalized_tour not in {"atp", "wta", "itf"}:
            raise ValueError("RAPIDAPI_TENNIS_TOUR_UNSUPPORTED")
        if stop < start:
            raise ValueError("INVALID_DISCOVERY_DATE_RANGE")
        if (stop - start).days > 3:
            raise ValueError("DISCOVERY_RANGE_EXCEEDS_4_DAYS")
        if start == stop:
            path = (
                f"/tennis/v2/{normalized_tour}/fixtures/"
                f"{start.isoformat()}"
            )
        else:
            path = (
                f"/tennis/v2/{normalized_tour}/fixtures/"
                f"{start.isoformat()}/{stop.isoformat()}"
            )

        rows: list[Mapping[str, Any]] = []
        page = 1
        page_limit = max(1, int(max_pages))
        for _ in range(page_limit):
            params: dict[str, Any] = {
                "include": "round,tournament,tournament.court",
                "pageNo": page,
                "pageSize": PAGE_SIZE,
            }
            if filter_value:
                params["filter"] = filter_value
            payload = self._get(path, params)
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
                "RAPIDAPI_TENNIS_FIXTURE_PAGE_LIMIT_REACHED:"
                + normalized_tour.upper()
            )

        return {
            "data": rows,
            "pageNo": 1,
            "pageSize": len(rows),
            "hasNextPage": False,
        }

    def fixtures(self, start: date, stop: date) -> Mapping[str, Any]:
        return self.fixtures_for_tour(
            "atp",
            start,
            stop,
            filter_value="PlayerGroup:singles;TourRank:1",
            max_pages=MAX_FIXTURE_PAGES,
        )

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

    def ranking_snapshot_rows(
        self,
        *,
        ranking_date: date,
    ) -> list[Mapping[str, Any]]:
        rows_out: list[Mapping[str, Any]] = []
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
            rows_out.extend(rows)
            if not rows or len(rows) < PAGE_SIZE:
                break
            page += 1
        return rows_out

    def player_profile(
        self,
        *,
        player_id: str,
    ) -> Mapping[str, Any]:
        token = _positive_id(player_id)
        if token is None:
            raise ValueError("RAPIDAPI_TENNIS_PLAYER_ID_INVALID")
        payload = self._get(f"/tennis/v2/atp/player/profile/{token}")
        if not isinstance(payload, Mapping):
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_PLAYER_PROFILE_INVALID"
            )
        return payload

    def ranking_history(
        self,
        *,
        player_id: str,
        months: int = 3,
    ) -> Mapping[str, Any]:
        token = _positive_id(player_id)
        if token is None:
            raise ValueError("RAPIDAPI_TENNIS_PLAYER_ID_INVALID")
        payload = self._get(
            f"/tennis/v2/ranking/atp/player/{token}/history",
            {"months": max(1, min(int(months), 12))},
        )
        if not isinstance(payload, Mapping):
            raise RapidApiTennisDiscoveryError(
                "RAPIDAPI_TENNIS_RANKING_HISTORY_INVALID"
            )
        return payload

    def _results_path(
        self,
        path: str,
    ) -> Mapping[str, Any]:
        rows: list[Mapping[str, Any]] = []
        page = 1
        for _ in range(MAX_RESULT_PAGES):
            payload = self._get(
                path,
                {
                    "pageNo": page,
                    "pageSize": PAGE_SIZE,
                    "filter": "PlayerGroup:singles;TourRank:1",
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

    def results_for_date(self, target_date: date) -> Mapping[str, Any]:
        return self._results_path(
            f"/tennis/v2/atp/results/{target_date.isoformat()}"
        )

    def results_for_range(
        self,
        start: date,
        stop: date,
    ) -> Mapping[str, Any]:
        if stop < start:
            raise ValueError("INVALID_RESULTS_DATE_RANGE")
        if (stop - start).days > 13:
            raise ValueError("RESULTS_RANGE_EXCEEDS_14_DAYS")
        if start == stop:
            return self.results_for_date(start)
        return self._results_path(
            f"/tennis/v2/atp/results/{start.isoformat()}/{stop.isoformat()}"
        )


COUNTRY_ALIASES = {
    "POR": "PRT",
}


def _norm_identity_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _canonical_ioc(value: object) -> str:
    token = str(value or "").strip().upper()
    return COUNTRY_ALIASES.get(token, token)


def _profile_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        data = payload
    info = data.get("information")
    if not isinstance(info, Mapping):
        info = {}
    plays = str(info.get("plays") or info.get("hand") or "").strip().casefold()
    hand = "L" if plays.startswith("left") else "R" if plays.startswith("right") else ""
    birthday = str(data.get("birthday") or "").strip()[:10]
    return {
        "id": str(data.get("id") or "").strip(),
        "name": str(data.get("name") or "").strip(),
        "ioc": _canonical_ioc(data.get("countryAcr")),
        "dob": birthday,
        "hand": hand,
    }


def recover_exact_rankings_via_profile_alias(
    *,
    client: RapidApiTennisClient,
    ranking_date: date,
    wanted_player_ids: Iterable[str],
    existing_rankings: Mapping[str, Mapping[str, Any]],
    fixture_identity_by_player: Mapping[str, Mapping[str, Any]],
    max_profile_requests: int = MAX_RANK_ALIAS_PROFILE_REQUESTS,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    merged = {
        str(player_id): dict(row)
        for player_id, row in existing_rankings.items()
        if isinstance(row, Mapping)
    }
    missing = sorted({
        str(player_id)
        for player_id in wanted_player_ids
        if _positive_id(player_id) and str(player_id) not in merged
    })
    if not missing:
        return merged, {
            "schema": "MATRIX_COR0203_EXACT_CUT_RANK_PROFILE_ALIAS_V1",
            "ranking_cut": ranking_date.isoformat(),
            "missing_player_ids": [],
            "ranking_snapshot_rows_scanned": 0,
            "profile_requests": 0,
            "recovered_count": 0,
            "recovered": [],
            "blocked_count": 0,
            "blocked": [],
            "join_by_name_only": False,
            "current_rank_used": False,
            "post_cut_competitive_data_used": False,
            "outcomes_used": False,
            "odds_used": False,
            "real_money": "BLOCKED",
        }

    ranking_rows_fetcher = getattr(client, "ranking_snapshot_rows", None)
    if not callable(ranking_rows_fetcher):
        return merged, {
            "schema": "MATRIX_COR0203_EXACT_CUT_RANK_PROFILE_ALIAS_V1",
            "ranking_cut": ranking_date.isoformat(),
            "missing_player_ids": missing,
            "ranking_snapshot_rows_scanned": 0,
            "profile_requests": 0,
            "recovered_count": 0,
            "recovered": [],
            "blocked_count": len(missing),
            "blocked": [
                {
                    "player_id": player_id,
                    "reason": "RANKING_PROFILE_ALIAS_CAPABILITY_UNAVAILABLE",
                }
                for player_id in missing
            ],
            "join_by_name_only": False,
            "current_rank_used": False,
            "post_cut_competitive_data_used": False,
            "outcomes_used": False,
            "odds_used": False,
            "real_money": "BLOCKED",
        }
    try:
        ranking_rows = ranking_rows_fetcher(ranking_date=ranking_date)
    except (RapidApiTennisDiscoveryError, ValueError, AttributeError) as error:
        return merged, {
            "schema": "MATRIX_COR0203_EXACT_CUT_RANK_PROFILE_ALIAS_V1",
            "ranking_cut": ranking_date.isoformat(),
            "missing_player_ids": missing,
            "ranking_snapshot_rows_scanned": 0,
            "profile_requests": 0,
            "recovered_count": 0,
            "recovered": [],
            "blocked_count": len(missing),
            "blocked": [
                {
                    "player_id": player_id,
                    "reason": (
                        "RANKING_ALIAS_SNAPSHOT_FAILED:"
                        + type(error).__name__
                        + ":"
                        + str(error)[:250]
                    ),
                }
                for player_id in missing
            ],
            "join_by_name_only": False,
            "current_rank_used": False,
            "post_cut_competitive_data_used": False,
            "outcomes_used": False,
            "odds_used": False,
            "real_money": "BLOCKED",
        }

    rows_by_name: dict[str, list[Mapping[str, Any]]] = {}
    for row in ranking_rows:
        player = _mapping(row.get("player"))
        ranking_player_id = _positive_id(player.get("id"))
        name = str(player.get("name") or "").strip()
        position = str(row.get("position") or "").strip()
        points = str(
            row.get("pts")
            if row.get("pts") is not None
            else row.get("point")
            if row.get("point") is not None
            else row.get("points")
            if row.get("points") is not None
            else ""
        ).strip()
        if (
            ranking_player_id is None
            or not name
            or not position.isdigit()
            or int(position) <= 0
            or not points.isdigit()
            or int(points) < 0
        ):
            continue
        payload = dict(row)
        payload["_ranking_player_id"] = ranking_player_id
        rows_by_name.setdefault(_norm_identity_name(name), []).append(payload)

    recovered: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    profile_requests = 0
    profile_cache: dict[str, dict[str, str] | None] = {}

    def profile_identity(player_id: str) -> dict[str, str] | None:
        nonlocal profile_requests
        if player_id in profile_cache:
            return profile_cache[player_id]
        if profile_requests >= max(0, int(max_profile_requests)):
            profile_cache[player_id] = None
            return None
        try:
            payload = client.player_profile(player_id=player_id)
            profile_requests += 1
        except (RapidApiTennisDiscoveryError, ValueError):
            profile_cache[player_id] = None
            return None
        identity = _profile_identity(payload)
        profile_cache[player_id] = identity
        return identity

    for fixture_player_id in missing:
        fixture_identity = fixture_identity_by_player.get(fixture_player_id, {})
        fixture_name = str(fixture_identity.get("name") or "").strip()
        if not fixture_name:
            blocked.append({
                "player_id": fixture_player_id,
                "reason": "FIXTURE_IDENTITY_NAME_MISSING",
            })
            continue

        fixture_profile = profile_identity(fixture_player_id)
        if not isinstance(fixture_profile, Mapping):
            blocked.append({
                "player_id": fixture_player_id,
                "player": fixture_name,
                "reason": "FIXTURE_PROFILE_UNAVAILABLE_OR_PROFILE_BUDGET_REACHED",
            })
            continue
        if (
            _positive_id(fixture_profile.get("id")) != fixture_player_id
            or _norm_identity_name(fixture_profile.get("name"))
            != _norm_identity_name(fixture_name)
            or not str(fixture_profile.get("dob") or "")
        ):
            blocked.append({
                "player_id": fixture_player_id,
                "player": fixture_name,
                "reason": "FIXTURE_PROFILE_IDENTITY_INCOMPLETE",
            })
            continue

        candidates = rows_by_name.get(_norm_identity_name(fixture_name), [])
        validated: list[dict[str, Any]] = []
        for row in candidates:
            ranking_player_id = str(row.get("_ranking_player_id") or "")
            if not ranking_player_id:
                continue
            candidate_profile = profile_identity(ranking_player_id)
            if not isinstance(candidate_profile, Mapping):
                continue
            if (
                _positive_id(candidate_profile.get("id")) != ranking_player_id
                or _norm_identity_name(candidate_profile.get("name"))
                != _norm_identity_name(fixture_profile.get("name"))
                or str(candidate_profile.get("dob") or "")
                != str(fixture_profile.get("dob") or "")
            ):
                continue
            fixture_hand = str(fixture_profile.get("hand") or "")
            candidate_hand = str(candidate_profile.get("hand") or "")
            if (
                fixture_hand
                and candidate_hand
                and fixture_hand != candidate_hand
            ):
                continue
            fixture_ioc = str(fixture_profile.get("ioc") or "")
            candidate_ioc = str(candidate_profile.get("ioc") or "")
            if fixture_ioc and candidate_ioc and fixture_ioc != candidate_ioc:
                continue
            validated.append({
                "ranking_player_id": ranking_player_id,
                "row": row,
                "profile": dict(candidate_profile),
            })

        unique_ids = sorted({
            row["ranking_player_id"]
            for row in validated
        })
        if len(unique_ids) != 1:
            blocked.append({
                "player_id": fixture_player_id,
                "player": fixture_name,
                "reason": (
                    "RANKING_PROFILE_ALIAS_NONUNIQUE"
                    if unique_ids
                    else "RANKING_PROFILE_ALIAS_NOT_FOUND"
                ),
                "validated_ranking_player_ids": unique_ids,
            })
            continue

        selected = next(
            row
            for row in validated
            if row["ranking_player_id"] == unique_ids[0]
        )
        rank_row = selected["row"]
        rank_player = _mapping(rank_row.get("player"))
        place = str(rank_row.get("position"))
        points = str(
            rank_row.get("pts")
            if rank_row.get("pts") is not None
            else rank_row.get("point")
            if rank_row.get("point") is not None
            else rank_row.get("points")
        )
        ranking = {
            "place": place,
            "points": points,
            "player": fixture_name,
            "country": str(
                fixture_identity.get("country")
                or fixture_profile.get("ioc")
                or rank_player.get("countryAcr")
                or ""
            ).strip(),
            "snapshot_date": ranking_date.isoformat(),
            "ranking_source": "EXACT_CUT_RANKING_PROFILE_ALIAS",
            "ranking_identity_alias": {
                "fixture_player_id": fixture_player_id,
                "ranking_player_id": unique_ids[0],
                "basis": (
                    "EXACT_NAME_PLUS_PROFILE_DOB_PLUS_HAND_IOC_CONSISTENCY_"
                    "AND_UNIQUE_EXACT_CUT_RANKING_ID"
                ),
            },
        }
        merged[fixture_player_id] = ranking
        recovered.append({
            "fixture_player_id": fixture_player_id,
            "ranking_player_id": unique_ids[0],
            "player": fixture_name,
            "place": place,
            "points": points,
            "ranking_date": ranking_date.isoformat(),
        })

    return merged, {
        "schema": "MATRIX_COR0203_EXACT_CUT_RANK_PROFILE_ALIAS_V1",
        "ranking_cut": ranking_date.isoformat(),
        "missing_player_ids": missing,
        "ranking_snapshot_rows_scanned": len(ranking_rows),
        "profile_requests": profile_requests,
        "recovered_count": len(recovered),
        "recovered": recovered,
        "blocked_count": len(blocked),
        "blocked": blocked,
        "join_by_name_only": False,
        "current_rank_used": False,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "real_money": "BLOCKED",
    }


def _ranking_history_rows(
    payload: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    rows = payload.get("history")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, Mapping)]
    data = payload.get("data")
    if isinstance(data, Mapping):
        rows = data.get("history")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def recover_exact_rankings_from_history(
    *,
    client: RapidApiTennisClient,
    ranking_date: date,
    wanted_player_ids: Iterable[str],
    existing_rankings: Mapping[str, Mapping[str, Any]],
    fixture_identity_by_player: Mapping[str, Mapping[str, Any]],
    max_requests: int = MAX_RANK_HISTORY_FALLBACK_REQUESTS,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    merged = {
        str(player_id): dict(row)
        for player_id, row in existing_rankings.items()
        if isinstance(row, Mapping)
    }
    missing = sorted({
        str(player_id)
        for player_id in wanted_player_ids
        if _positive_id(player_id) and str(player_id) not in merged
    })
    recovered: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    requests = 0

    for player_id in missing:
        if requests >= max(0, int(max_requests)):
            blocked.append({
                "player_id": player_id,
                "reason": "RANK_HISTORY_FALLBACK_BUDGET_REACHED",
            })
            continue
        try:
            payload = client.ranking_history(
                player_id=player_id,
                months=3,
            )
            requests += 1
        except (RapidApiTennisDiscoveryError, ValueError) as error:
            blocked.append({
                "player_id": player_id,
                "reason": (
                    "RANK_HISTORY_LOOKUP_FAILED:"
                    + type(error).__name__
                    + ":"
                    + str(error)[:250]
                ),
            })
            continue

        matches: list[tuple[str, str]] = []
        for row in _ranking_history_rows(payload):
            day = str(row.get("date") or "").strip()[:10]
            if day != ranking_date.isoformat():
                continue
            position = str(row.get("position") or "").strip()
            points = str(
                row.get("pts")
                if row.get("pts") is not None
                else row.get("point")
                if row.get("point") is not None
                else row.get("points")
                if row.get("points") is not None
                else ""
            ).strip()
            if (
                position.isdigit()
                and int(position) > 0
                and points.isdigit()
                and int(points) >= 0
            ):
                matches.append((position, points))

        unique = sorted(set(matches))
        if len(unique) != 1:
            blocked.append({
                "player_id": player_id,
                "reason": (
                    "EXACT_RANKING_CUT_NOT_UNIQUE"
                    if unique
                    else "EXACT_RANKING_CUT_NOT_FOUND"
                ),
                "matches": [
                    {"place": place, "points": points}
                    for place, points in unique
                ],
            })
            continue

        identity = fixture_identity_by_player.get(player_id, {})
        place, points = unique[0]
        ranking = {
            "place": place,
            "points": points,
            "player": str(identity.get("name") or "").strip(),
            "country": str(identity.get("country") or "").strip(),
            "snapshot_date": ranking_date.isoformat(),
            "ranking_source": "PLAYER_RANKING_HISTORY_EXACT_CUT",
        }
        merged[player_id] = ranking
        recovered.append({
            "player_id": player_id,
            "player": ranking["player"],
            "place": place,
            "points": points,
            "ranking_date": ranking_date.isoformat(),
        })

    return merged, {
        "schema": "MATRIX_COR0203_EXACT_CUT_RANK_HISTORY_RECOVERY_V1",
        "ranking_cut": ranking_date.isoformat(),
        "requested_missing_player_ids": missing,
        "history_requests": requests,
        "recovered_count": len(recovered),
        "recovered": recovered,
        "blocked_count": len(blocked),
        "blocked": blocked,
        "current_rank_used": False,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "real_money": "BLOCKED",
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
        if court.casefold() not in MODEL_HARD_SURFACES:
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
                    "players": [
                        {
                            "provider_player_id": (
                                f"rapidapi-tennis:player:{p1_id}"
                                if p1_id is not None
                                else None
                            ),
                            "name": p1_name,
                            "ranking_found": isinstance(p1_ranking, Mapping),
                        },
                        {
                            "provider_player_id": (
                                f"rapidapi-tennis:player:{p2_id}"
                                if p2_id is not None
                                else None
                            ),
                            "name": p2_name,
                            "ranking_found": isinstance(p2_ranking, Mapping),
                        },
                    ],
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
        candidate = {
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
            "player_identities": [
                {
                    "display_name": p1_name,
                    "provider_player_id": f"rapidapi-tennis:player:{p1_id}",
                    "provider": PROVIDER_KEY,
                },
                {
                    "display_name": p2_name,
                    "provider_player_id": f"rapidapi-tennis:player:{p2_id}",
                    "provider": PROVIDER_KEY,
                },
            ],
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
        candidate["physical_event_key"] = physical_event_key(candidate)
        candidates.append(candidate)

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

    # The fixtures request explicitly asks the provider to include tournament
    # and tournament.court. Reuse that governed response first instead of
    # spending one extra API request per tournament. Only unresolved
    # tournaments consume the bounded tournament-info fallback budget.
    embedded_info: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        tournament_id = _positive_id(row.get("tournamentId"))
        embedded = _mapping(row.get("tournament"))
        if tournament_id is None or not embedded:
            continue
        if (
            _tournament_tier(embedded)
            and _rank_id(embedded) is not None
            and _court_name(embedded)
        ):
            embedded_info.setdefault(tournament_id, dict(embedded))

    unresolved_ids = [
        tournament_id
        for tournament_id in tournament_ids
        if tournament_id not in embedded_info
    ]
    fallback_ids = unresolved_ids[:MAX_TOURNAMENT_INFO_REQUESTS]
    network_info = {
        tournament_id: client.tournament_info(tournament_id)
        for tournament_id in fallback_ids
    }
    info = {**embedded_info, **network_info}
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
    fixture_identity_by_player = {}
    for row in rows:
        for side in (1, 2):
            player_id, player_name = _player(row, side)
            if player_id is None:
                continue
            player_obj = _mapping(row.get(f"player{side}"))
            fixture_identity_by_player[player_id] = {
                "name": player_name,
                "country": str(
                    player_obj.get("countryAcr")
                    or row.get(f"player{side}Country")
                    or ""
                ).strip(),
            }
    rankings, ranking_history_recovery = recover_exact_rankings_from_history(
        client=client,
        ranking_date=RANKING_CUT,
        wanted_player_ids=wanted_player_ids,
        existing_rankings=rankings,
        fixture_identity_by_player=fixture_identity_by_player,
    )
    rankings, ranking_profile_alias_recovery = recover_exact_rankings_via_profile_alias(
        client=client,
        ranking_date=RANKING_CUT,
        wanted_player_ids=wanted_player_ids,
        existing_rankings=rankings,
        fixture_identity_by_player=fixture_identity_by_player,
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
    result["tournaments_embedded"] = len(embedded_info)
    result["tournaments_network_queried"] = len(network_info)
    result["tournaments_unresolved"] = max(
        0,
        len(unresolved_ids) - len(fallback_ids),
    )
    result["ranking_players_found"] = len(rankings)
    result["ranking_history_recovery"] = ranking_history_recovery
    result["ranking_history_recovered_count"] = int(
        ranking_history_recovery.get("recovered_count", 0)
    )
    result["ranking_profile_alias_recovery"] = ranking_profile_alias_recovery
    result["ranking_profile_alias_recovered_count"] = int(
        ranking_profile_alias_recovery.get("recovered_count", 0)
    )
    return result
