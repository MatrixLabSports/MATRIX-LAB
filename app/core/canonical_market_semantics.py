from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Iterable


class LineSemantics(str, Enum):
    NONE = "NONE"
    TOTAL = "TOTAL"
    HANDICAP = "HANDICAP"
    PLAYER_THRESHOLD = "PLAYER_THRESHOLD"


class VoidabilityClass(str, Enum):
    STANDARD_EVENT = "STANDARD_EVENT"
    PLAYER_PARTICIPATION = "PLAYER_PARTICIPATION"
    PROVIDER_METRIC = "PROVIDER_METRIC"


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name.upper()}_REQUIRED")
    return value


def _canonical_sha(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExecutableMarketDefinition:
    version: str
    sport: str
    market_family: str
    market_variant: str
    period: str
    subject_scope: str
    selection_schema: tuple[str, ...]
    line_semantics: LineSemantics
    line_unit: str | None
    metric_key: str | None
    participant_identity_kind: str
    provider_definition_required: bool
    voidability_class: VoidabilityClass

    def __post_init__(self) -> None:
        _required(self.version, "version")
        if not self.version.startswith("MATRIX-MARKET-R2/"):
            raise ValueError("MARKET_VERSION_INVALID")
        if self.sport not in {"football", "tennis"}:
            raise ValueError("SPORT_INVALID")
        for name in ("market_family", "market_variant", "period", "subject_scope", "metric_key", "participant_identity_kind"):
            _required(getattr(self, name), name)
        if self.sport == "football" and self.market_family not in FOOTBALL_CANDIDATE_FAMILIES:
            raise ValueError("MARKET_FAMILY_SPORT_MISMATCH")
        if self.sport == "tennis" and self.market_family not in TENNIS_CANDIDATE_FAMILIES:
            raise ValueError("MARKET_FAMILY_SPORT_MISMATCH")
        if not self.selection_schema or any(not isinstance(x, str) or not x.strip() for x in self.selection_schema):
            raise ValueError("SELECTION_SCHEMA_REQUIRED")
        if len(set(self.selection_schema)) != len(self.selection_schema):
            raise ValueError("SELECTION_SCHEMA_DUPLICATE")
        line_required = self.line_semantics is not LineSemantics.NONE
        if line_required and ("LINE" not in self.selection_schema or not self.line_unit):
            raise ValueError("LINE_SEMANTICS_REQUIRE_LINE_AND_UNIT")
        if not line_required and self.line_unit is not None:
            raise ValueError("LINE_UNIT_FORBIDDEN_WITHOUT_LINE")
        if self.provider_definition_required and not self.metric_key:
            raise ValueError("PROVIDER_DEFINITION_REQUIRES_METRIC_KEY")
        if self.voidability_class is VoidabilityClass.PROVIDER_METRIC and not self.provider_definition_required:
            raise ValueError("PROVIDER_METRIC_MUST_REQUIRE_PROVIDER_DEFINITION")
        expected = f"MATRIX-MARKET-R2/{self.sport}/{self.market_family}/{self.market_variant}"
        if self.version != expected:
            raise ValueError("MARKET_VERSION_IDENTITY_MISMATCH")

    @property
    def key(self) -> tuple[str, str, str, str, str]:
        return (self.sport, self.market_family, self.market_variant, self.period, self.subject_scope)

    def payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "sport": self.sport,
            "market_family": self.market_family,
            "market_variant": self.market_variant,
            "period": self.period,
            "subject_scope": self.subject_scope,
            "selection_schema": list(self.selection_schema),
            "line_semantics": self.line_semantics.value,
            "line_unit": self.line_unit,
            "metric_key": self.metric_key,
            "participant_identity_kind": self.participant_identity_kind,
            "provider_definition_required": self.provider_definition_required,
            "voidability_class": self.voidability_class.value,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_sha(self.payload())


FOOTBALL_CANDIDATE_FAMILIES = (
    "BOTH_TEAMS_TO_SCORE", "CARDS", "CORNERS", "GOAL_TOTALS_OR_TEAM_TOTALS",
    "PLAYER_ASSISTS_OR_PASSES", "PLAYER_SHOTS_OR_SHOTS_ON_TARGET", "RESULT_OR_DOUBLE_CHANCE",
)
TENNIS_CANDIDATE_FAMILIES = (
    "GAME_HANDICAP", "GAME_OR_SET_TOTALS", "MATCH_WINNER", "PLAYER_PROPS", "SET_WINNER",
)


def canonical_candidate_market_definitions() -> tuple[ExecutableMarketDefinition, ...]:
    m = ExecutableMarketDefinition
    L = LineSemantics
    V = VoidabilityClass
    rows = (
        m("MATRIX-MARKET-R2/football/BOTH_TEAMS_TO_SCORE/yes-no", "football", "BOTH_TEAMS_TO_SCORE", "yes-no", "FULL_TIME", "MATCH", ("YES", "NO"), L.NONE, None, "BOTH_TEAMS_SCORE", "TEAM", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/football/CARDS/total-cards", "football", "CARDS", "total-cards", "FULL_TIME", "MATCH_OR_TEAM", ("OVER", "UNDER", "LINE"), L.TOTAL, "CARD_COUNT", "PROVIDER_CARD_DEFINITION", "MATCH_OR_TEAM", True, V.PROVIDER_METRIC),
        m("MATRIX-MARKET-R2/football/CORNERS/total-corners", "football", "CORNERS", "total-corners", "FULL_TIME", "MATCH_OR_TEAM", ("OVER", "UNDER", "LINE"), L.TOTAL, "CORNER_COUNT", "CORNER_COUNT", "MATCH_OR_TEAM", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/football/GOAL_TOTALS_OR_TEAM_TOTALS/goal-total", "football", "GOAL_TOTALS_OR_TEAM_TOTALS", "goal-total", "FULL_TIME", "MATCH_OR_TEAM", ("OVER", "UNDER", "LINE"), L.TOTAL, "GOAL_COUNT", "GOAL_COUNT", "MATCH_OR_TEAM", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/football/PLAYER_ASSISTS_OR_PASSES/player-threshold", "football", "PLAYER_ASSISTS_OR_PASSES", "player-threshold", "FULL_TIME", "PLAYER", ("OVER", "UNDER", "LINE"), L.PLAYER_THRESHOLD, "PROVIDER_METRIC_UNIT", "PLAYER_ASSISTS_OR_PASSES_METRIC", "PLAYER", True, V.PROVIDER_METRIC),
        m("MATRIX-MARKET-R2/football/PLAYER_SHOTS_OR_SHOTS_ON_TARGET/player-threshold", "football", "PLAYER_SHOTS_OR_SHOTS_ON_TARGET", "player-threshold", "FULL_TIME", "PLAYER", ("OVER", "UNDER", "LINE"), L.PLAYER_THRESHOLD, "PROVIDER_METRIC_UNIT", "PLAYER_SHOTS_OR_SOT_METRIC", "PLAYER", True, V.PROVIDER_METRIC),
        m("MATRIX-MARKET-R2/football/RESULT_OR_DOUBLE_CHANCE/result-or-double-chance", "football", "RESULT_OR_DOUBLE_CHANCE", "result-or-double-chance", "FULL_TIME", "MATCH", ("HOME", "DRAW", "AWAY", "HOME_OR_DRAW", "AWAY_OR_DRAW", "HOME_OR_AWAY"), L.NONE, None, "MATCH_RESULT_OR_DOUBLE_CHANCE", "TEAM", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/tennis/GAME_HANDICAP/game-handicap", "tennis", "GAME_HANDICAP", "game-handicap", "MATCH", "PLAYER", ("PLAYER_A", "PLAYER_B", "LINE"), L.HANDICAP, "GAME_COUNT", "GAME_HANDICAP", "PLAYER", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/tennis/GAME_OR_SET_TOTALS/game-or-set-total", "tennis", "GAME_OR_SET_TOTALS", "game-or-set-total", "MATCH_OR_SET", "MATCH_OR_SET", ("OVER", "UNDER", "LINE"), L.TOTAL, "GAME_OR_SET_COUNT", "GAME_OR_SET_TOTAL", "MATCH_OR_SET", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/tennis/MATCH_WINNER/match-winner", "tennis", "MATCH_WINNER", "match-winner", "MATCH", "MATCH", ("PLAYER_A", "PLAYER_B"), L.NONE, None, "MATCH_WINNER", "PLAYER", False, V.STANDARD_EVENT),
        m("MATRIX-MARKET-R2/tennis/PLAYER_PROPS/player-threshold", "tennis", "PLAYER_PROPS", "player-threshold", "MATCH", "PLAYER", ("OVER", "UNDER", "LINE"), L.PLAYER_THRESHOLD, "PROVIDER_METRIC_UNIT", "TENNIS_PLAYER_PROP_METRIC", "PLAYER", True, V.PROVIDER_METRIC),
        m("MATRIX-MARKET-R2/tennis/SET_WINNER/set-winner", "tennis", "SET_WINNER", "set-winner", "SET", "SET", ("PLAYER_A", "PLAYER_B"), L.NONE, None, "SET_WINNER", "PLAYER", False, V.STANDARD_EVENT),
    )
    validate_market_registry(rows)
    return rows


def validate_market_registry(definitions: Iterable[ExecutableMarketDefinition]) -> None:
    rows = tuple(definitions)
    keys = [row.key for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_EXECUTABLE_MARKET_IDENTITY")
    expected = {("football", x) for x in FOOTBALL_CANDIDATE_FAMILIES} | {("tennis", x) for x in TENNIS_CANDIDATE_FAMILIES}
    actual = {(row.sport, row.market_family) for row in rows}
    if actual != expected:
        raise ValueError("CANDIDATE_MARKET_FAMILY_COVERAGE_MISMATCH")
