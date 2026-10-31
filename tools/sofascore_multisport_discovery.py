from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

try:
    from curl_cffi import requests as http_requests  # type: ignore
    HTTP_BACKEND = "curl_cffi_chrome"
except Exception:  # pragma: no cover - fallback is exercised in CI only if needed
    import requests as http_requests  # type: ignore
    HTTP_BACKEND = "requests"

BASE_URLS = (
    "https://api.sofascore.com/api/v1",
    "https://www.sofascore.com/api/v1",
)
BOGOTA = ZoneInfo("America/Bogota")
TIMEOUT_SECONDS = 25.0
MAX_TENNIS_PAGES = 20
MAX_RESPONSE_BYTES = 20_000_000


class SofaScoreDiscoveryError(RuntimeError):
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


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _event_start_utc(row: Mapping[str, Any]) -> datetime | None:
    stamp = row.get("startTimestamp")
    try:
        stamp_int = int(stamp)
    except (TypeError, ValueError):
        return None
    if stamp_int <= 0:
        return None
    return datetime.fromtimestamp(stamp_int, tz=timezone.utc)


def _extract_events(value: object) -> list[Mapping[str, Any]]:
    found: dict[int, Mapping[str, Any]] = {}

    def walk(node: object) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child)
            return
        if not isinstance(node, Mapping):
            return
        event_id = _positive_int(node.get("id"))
        if (
            event_id is not None
            and _event_start_utc(node) is not None
            and isinstance(node.get("homeTeam"), Mapping)
            and isinstance(node.get("awayTeam"), Mapping)
            and isinstance(node.get("tournament"), Mapping)
        ):
            found[event_id] = node
        for child in node.values():
            if isinstance(child, (list, Mapping)):
                walk(child)

    walk(value)
    return list(found.values())


def _surface(row: Mapping[str, Any]) -> str:
    tournament = _mapping(row.get("tournament"))
    unique = _mapping(tournament.get("uniqueTournament"))
    for value in (
        row.get("groundType"),
        tournament.get("groundType"),
        tournament.get("surface"),
        unique.get("groundType"),
        unique.get("surface"),
    ):
        if value is None:
            continue
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("slug") or ""
        token = str(value or "").strip()
        if token:
            return token
    return ""


def _entity(row: Mapping[str, Any], side: str) -> dict[str, Any]:
    obj = _mapping(row.get(side + "Team"))
    country = _mapping(obj.get("country"))
    gender = str(obj.get("gender") or "").strip()
    return {
        "sofascore_id": _positive_int(obj.get("id")),
        "name": str(obj.get("name") or "").strip(),
        "slug": str(obj.get("slug") or "").strip(),
        "gender": gender or None,
        "country": str(country.get("name") or obj.get("countryName") or "").strip() or None,
        "country_alpha2": str(country.get("alpha2") or "").strip() or None,
    }


def _normalize_event(row: Mapping[str, Any], *, sport: str) -> dict[str, Any]:
    event_id = _positive_int(row.get("id"))
    start_utc = _event_start_utc(row)
    if event_id is None or start_utc is None:
        raise SofaScoreDiscoveryError("SOFASCORE_EVENT_CORE_ID_OR_START_MISSING")
    tournament = _mapping(row.get("tournament"))
    unique = _mapping(tournament.get("uniqueTournament"))
    category = _mapping(tournament.get("category"))
    status = _mapping(row.get("status"))
    home = _entity(row, "home")
    away = _entity(row, "away")
    if not home["name"] or not away["name"]:
        raise SofaScoreDiscoveryError("SOFASCORE_EVENT_ENTITY_NAME_MISSING")
    physical = {
        "sport": sport,
        "home_name": home["name"].casefold(),
        "away_name": away["name"].casefold(),
        "start_utc": start_utc.isoformat(),
        "tournament": str(
            unique.get("name")
            or tournament.get("name")
            or ""
        ).strip().casefold(),
    }
    return {
        "source_provider": "sofascore",
        "sport": sport,
        "source_event_id": f"sofascore:{sport}:event:{event_id}",
        "sofascore_event_id": event_id,
        "event_start_utc": start_utc.isoformat(),
        "event_start_bogota": start_utc.astimezone(BOGOTA).isoformat(),
        "status_type": str(status.get("type") or "").strip() or None,
        "status_description": str(status.get("description") or "").strip() or None,
        "tournament_id": _positive_int(tournament.get("id")),
        "tournament_name": str(tournament.get("name") or "").strip(),
        "unique_tournament_id": _positive_int(unique.get("id")),
        "unique_tournament_name": str(unique.get("name") or "").strip(),
        "category_id": _positive_int(category.get("id")),
        "category_name": str(category.get("name") or "").strip(),
        "surface": _surface(row),
        "round_info": row.get("roundInfo"),
        "home": home,
        "away": away,
        "physical_event_key": _sha(physical),
        "source_snapshot_sha256": _sha(row),
    }


class SofaScoreClient:
    def __init__(self, *, session: Any | None = None, timeout_seconds: float = TIMEOUT_SECONDS) -> None:
        if session is not None:
            self._session = session
        elif HTTP_BACKEND == "curl_cffi_chrome":
            self._session = http_requests.Session(impersonate="chrome")
        else:
            self._session = http_requests.Session()
        self._timeout = float(timeout_seconds)
        self.request_count = 0
        self.request_log: list[dict[str, Any]] = []

    def _get(self, path: str) -> Mapping[str, Any]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/154.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.sofascore.com/",
            "Origin": "https://www.sofascore.com",
        }
        failures: list[str] = []
        for base_url in BASE_URLS:
            url = base_url + path
            try:
                response = self._session.get(
                    url,
                    headers=headers,
                    timeout=self._timeout,
                )
            except Exception as error:
                self.request_count += 1
                failure = (
                    "NETWORK:"
                    + type(error).__name__
                    + ":"
                    + str(error)[:220]
                )
                failures.append(base_url + "=" + failure)
                self.request_log.append({
                    "base_url": base_url,
                    "path": path,
                    "http_status": None,
                    "error": failure,
                })
                continue
            status = int(getattr(response, "status_code", 0) or 0)
            body = bytes(getattr(response, "content", b""))
            self.request_count += 1
            self.request_log.append({
                "base_url": base_url,
                "path": path,
                "http_status": status,
                "response_bytes": len(body),
                "response_sha256": hashlib.sha256(body).hexdigest(),
            })
            if len(body) > MAX_RESPONSE_BYTES:
                failures.append(base_url + "=RESPONSE_TOO_LARGE")
                continue
            if not (200 <= status < 300):
                failures.append(base_url + f"=HTTP_{status}")
                continue
            try:
                payload = response.json()
            except Exception:
                try:
                    payload = json.loads(body.decode("utf-8"))
                except Exception as error:
                    failures.append(
                        base_url
                        + "=INVALID_JSON:"
                        + type(error).__name__
                    )
                    continue
            if not isinstance(payload, Mapping):
                failures.append(base_url + "=RESPONSE_NOT_OBJECT")
                continue
            return payload
        raise SofaScoreDiscoveryError(
            "SOFASCORE_ALL_BASE_URLS_FAILED:"
            + "|".join(failures)[:1000]
            + ":"
            + path
        )

    def football_schedule(self, target: date) -> Mapping[str, Any]:
        return self._get(f"/sport/football/scheduled-events/{target.isoformat()}")

    def tennis_schedule_page(self, target: date, page: int) -> Mapping[str, Any]:
        return self._get(
            f"/sport/tennis/scheduled-tournaments/{target.isoformat()}/page/{int(page)}"
        )

    def event(self, event_id: int) -> Mapping[str, Any]:
        return self._get(f"/event/{int(event_id)}")

    def player(self, player_id: int) -> Mapping[str, Any]:
        return self._get(f"/player/{int(player_id)}")

    def team(self, team_id: int) -> Mapping[str, Any]:
        return self._get(f"/team/{int(team_id)}")

    def team_players(self, team_id: int) -> Mapping[str, Any]:
        return self._get(f"/team/{int(team_id)}/players")


def _candidate_source_dates(target: date) -> list[date]:
    return [target - timedelta(days=1), target, target + timedelta(days=1)]


def _football_events(client: SofaScoreClient, target: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: dict[int, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    for source_date in _candidate_source_dates(target):
        payload = client.football_schedule(source_date)
        events = _extract_events(payload)
        audits.append({
            "source_date": source_date.isoformat(),
            "payload_sha256": _sha(payload),
            "events_extracted": len(events),
        })
        for raw in events:
            normalized = _normalize_event(raw, sport="football")
            local_date = datetime.fromisoformat(normalized["event_start_bogota"]).date()
            if local_date == target:
                rows[normalized["sofascore_event_id"]] = normalized
    return sorted(
        rows.values(),
        key=lambda row: (row["event_start_utc"], row["sofascore_event_id"]),
    ), audits


def _tennis_events(client: SofaScoreClient, target: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: dict[int, dict[str, Any]] = {}
    audits: list[dict[str, Any]] = []
    for source_date in _candidate_source_dates(target):
        date_total = 0
        pages: list[dict[str, Any]] = []
        for page in range(1, MAX_TENNIS_PAGES + 1):
            payload = client.tennis_schedule_page(source_date, page)
            events = _extract_events(payload)
            date_total += len(events)
            pages.append({
                "page": page,
                "payload_sha256": _sha(payload),
                "events_extracted": len(events),
                "has_next_page": bool(payload.get("hasNextPage")),
            })
            for raw in events:
                normalized = _normalize_event(raw, sport="tennis")
                local_date = datetime.fromisoformat(normalized["event_start_bogota"]).date()
                if local_date == target:
                    rows[normalized["sofascore_event_id"]] = normalized
            if not bool(payload.get("hasNextPage")):
                break
        else:
            raise SofaScoreDiscoveryError(
                "SOFASCORE_TENNIS_PAGE_LIMIT_REACHED:" + source_date.isoformat()
            )
        audits.append({
            "source_date": source_date.isoformat(),
            "events_extracted_across_pages": date_total,
            "pages": pages,
        })
    return sorted(
        rows.values(),
        key=lambda row: (row["event_start_utc"], row["sofascore_event_id"]),
    ), audits


def _sample_enrichment(
    client: SofaScoreClient,
    *,
    football_events: list[dict[str, Any]],
    tennis_events: list[dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "football": None,
        "tennis": None,
    }
    if football_events:
        event = football_events[0]
        team_id = _positive_int(event["home"].get("sofascore_id"))
        event_id = int(event["sofascore_event_id"])
        detail = client.event(event_id)
        team_payload = client.team(team_id) if team_id else {}
        roster_payload = client.team_players(team_id) if team_id else {}
        roster = roster_payload.get("players") if isinstance(roster_payload, Mapping) else None
        result["football"] = {
            "event_id": event_id,
            "team_id": team_id,
            "event_detail_sha256": _sha(detail),
            "team_profile_sha256": _sha(team_payload) if team_payload else None,
            "roster_sha256": _sha(roster_payload) if roster_payload else None,
            "roster_items": len(roster) if isinstance(roster, list) else None,
            "status": "PASS",
        }
    if tennis_events:
        event = tennis_events[0]
        player_id = _positive_int(event["home"].get("sofascore_id"))
        event_id = int(event["sofascore_event_id"])
        detail = client.event(event_id)
        player_payload = client.player(player_id) if player_id else {}
        result["tennis"] = {
            "event_id": event_id,
            "player_id": player_id,
            "event_detail_sha256": _sha(detail),
            "player_profile_sha256": _sha(player_payload) if player_payload else None,
            "status": "PASS",
        }
    return result


def build_multisport_discovery(
    *,
    client: SofaScoreClient,
    target_date_bogota: date,
    verify_entity_enrichment: bool = False,
) -> dict[str, Any]:
    football, football_audit = _football_events(client, target_date_bogota)
    tennis, tennis_audit = _tennis_events(client, target_date_bogota)
    enrichment = (
        _sample_enrichment(
            client,
            football_events=football,
            tennis_events=tennis,
        )
        if verify_entity_enrichment
        else {"football": None, "tennis": None}
    )
    tennis_tournaments = sorted({
        (
            row.get("unique_tournament_name")
            or row.get("tournament_name")
            or "UNKNOWN"
        )
        for row in tennis
    })
    football_competitions = sorted({
        (
            row.get("unique_tournament_name")
            or row.get("tournament_name")
            or "UNKNOWN"
        )
        for row in football
    })
    return {
        "schema": "MATRIX_SOFASCORE_MULTISPORT_DISCOVERY_V1",
        "provider": "sofascore",
        "provider_role": "WORLD_DISCOVERY_AND_ENTITY_METADATA_SIDECAR",
        "http_backend": HTTP_BACKEND,
        "target_date_bogota": target_date_bogota.isoformat(),
        "timezone": "America/Bogota",
        "football": {
            "event_count": len(football),
            "competition_count": len(football_competitions),
            "competitions": football_competitions,
            "source_date_audit": football_audit,
            "events": football,
        },
        "tennis": {
            "event_count": len(tennis),
            "tournament_count": len(tennis_tournaments),
            "tournaments": tennis_tournaments,
            "source_date_audit": tennis_audit,
            "events": tennis,
        },
        "entity_enrichment_probe": enrichment,
        "provider_network_calls": client.request_count,
        "request_log": client.request_log,
        "protections": {
            "feeds_model_automatically": False,
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "metrics_opened": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date-bogota", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--verify-entity-enrichment", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    target = date.fromisoformat(args.target_date_bogota)
    client = SofaScoreClient()
    try:
        report = build_multisport_discovery(
            client=client,
            target_date_bogota=target,
            verify_entity_enrichment=args.verify_entity_enrichment,
        )
    except Exception as error:
        report = {
            "schema": "MATRIX_SOFASCORE_MULTISPORT_DISCOVERY_V1",
            "provider": "sofascore",
            "provider_role": "WORLD_DISCOVERY_AND_ENTITY_METADATA_SIDECAR",
            "http_backend": HTTP_BACKEND,
            "target_date_bogota": target.isoformat(),
            "status": "BLOCKED",
            "error": type(error).__name__ + ":" + str(error)[:800],
            "provider_network_calls": client.request_count,
            "request_log": client.request_log,
            "protections": {
                "feeds_model_automatically": False,
                "odds_used_to_generate_probability": False,
                "outcomes_used_to_generate_probability": False,
                "metrics_opened": False,
                "automatic_wagering": False,
                "real_money": "BLOCKED",
            },
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": report.get("status"),
        "target_date_bogota": report.get("target_date_bogota"),
        "football_event_count": _mapping(report.get("football")).get("event_count"),
        "tennis_event_count": _mapping(report.get("tennis")).get("event_count"),
        "provider_network_calls": report.get("provider_network_calls"),
        "real_money": _mapping(report.get("protections")).get("real_money"),
    }, sort_keys=True))
    if report.get("status") != "PASS" and args.fail_on_blocked:
        raise SystemExit("SOFASCORE_MULTISPORT_DISCOVERY_BLOCKED")


if __name__ == "__main__":
    main()
