from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _round_token(value: object) -> str:
    token = _norm(value).replace("_", " ").replace("-", " ")
    token = " ".join(token.split())
    aliases = {
        "1/4": "QF",
        "quarter final": "QF",
        "quarter finals": "QF",
        "quarterfinal": "QF",
        "quarterfinals": "QF",
        "qf": "QF",
        "1/2": "SF",
        "semi final": "SF",
        "semi finals": "SF",
        "semifinal": "SF",
        "semifinals": "SF",
        "sf": "SF",
        "final": "F",
        "finals": "F",
        "f": "F",
        "first": "R1",
        "first round": "R1",
        "round 1": "R1",
        "r1": "R1",
        "second": "R2",
        "second round": "R2",
        "round 2": "R2",
        "r2": "R2",
        "q1": "Q1",
        "qualifying 1": "Q1",
        "q2": "Q2",
        "qualifying 2": "Q2",
        "q3": "Q3",
        "qualifying 3": "Q3",
    }
    return aliases.get(token, token.upper())


def _provider_player_ids(row: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for item in row.get("player_identities", []) or []:
        if not isinstance(item, Mapping):
            continue
        token = str(item.get("provider_player_id") or "").strip()
        if token:
            values.append(token)
    return sorted(set(values))


def _plain_player_names(row: Mapping[str, Any]) -> list[str]:
    players = row.get("players") or []
    values: list[str] = []
    if isinstance(players, list):
        for player in players:
            if isinstance(player, Mapping):
                name = player.get("name") or player.get("display_name")
            else:
                name = player
            token = _norm(name)
            if token:
                values.append(token)
    for key in ("alphabetical_player_a", "alphabetical_player_b"):
        token = _norm(row.get(key))
        if token:
            values.append(token)
    return sorted(set(values))


def physical_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    competition_id = str(row.get("competition_id") or "").strip()
    competition = _norm(row.get("competition"))
    round_name = _round_token(row.get("round"))

    provider_ids = _provider_player_ids(row)
    if len(provider_ids) == 2 and competition_id:
        authority = "PROVIDER_TOURNAMENT_PLAYER_IDS_ROUND"
        components = {
            "competition_id": competition_id,
            "round": round_name,
            "players": provider_ids,
        }
    else:
        names = _plain_player_names(row)
        if len(names) != 2:
            return {
                "physical_event_key": None,
                "authority": "INSUFFICIENT_IDENTITY",
                "components": {},
            }
        authority = "CANONICAL_NAMES_COMPETITION_ROUND_FALLBACK"
        components = {
            "competition": competition or competition_id.casefold(),
            "round": round_name,
            "players": names,
        }

    body = json.dumps(
        components,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return {
        "physical_event_key": hashlib.sha256(body).hexdigest(),
        "authority": authority,
        "components": components,
    }


def physical_event_key(row: Mapping[str, Any]) -> str | None:
    explicit = str(row.get("physical_event_key") or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", explicit):
        return explicit
    value = physical_identity(row).get("physical_event_key")
    return str(value) if value else None
