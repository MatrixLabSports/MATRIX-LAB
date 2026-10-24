from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class MarketLane:
    sport: str
    key: str
    display_name: str
    family: str
    required: bool
    lifecycle: str


FOOTBALL_MARKETS: tuple[MarketLane, ...] = (
    MarketLane("football","MATCH_RESULT_1X2","1X2","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","DOUBLE_CHANCE_1X","Doble oportunidad 1X","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","DOUBLE_CHANCE_X2","Doble oportunidad X2","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","DOUBLE_CHANCE_12","Doble oportunidad 12","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","TOTAL_GOALS_OVER_UNDER","Over/Under goles","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","BTTS","Ambos equipos marcan","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","ASIAN_OR_EUROPEAN_HANDICAP","Hándicap","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("football","CORNERS_OVER_UNDER","Corners O/U","team",True,"LAB_REQUIRED"),
    MarketLane("football","CARDS_OVER_UNDER","Tarjetas O/U","team",True,"LAB_REQUIRED"),
    MarketLane("football","TEAM_TOTAL_SHOTS_HOME","Tiros totales equipo local","team",True,"LAB_REQUIRED"),
    MarketLane("football","TEAM_TOTAL_SHOTS_AWAY","Tiros totales equipo visitante","team",True,"LAB_REQUIRED"),
    MarketLane("football","TEAM_SHOTS_ON_TARGET_HOME","Tiros a puerta equipo local","team",True,"LAB_REQUIRED"),
    MarketLane("football","TEAM_SHOTS_ON_TARGET_AWAY","Tiros a puerta equipo visitante","team",True,"LAB_REQUIRED"),
    MarketLane("football","TEAM_FOULS_HOME","Faltas equipo local","team",True,"LAB_REQUIRED"),
    MarketLane("football","TEAM_FOULS_AWAY","Faltas equipo visitante","team",True,"LAB_REQUIRED"),
    MarketLane("football","GOALKEEPER_SAVES","Atajadas de portero","player",True,"LAB_REQUIRED"),
    MarketLane("football","PLAYER_SHOTS","Remates de jugador","player",True,"LAB_REQUIRED"),
    MarketLane("football","PLAYER_SHOTS_ON_TARGET","Remates a puerta de jugador","player",True,"LAB_REQUIRED"),
    MarketLane("football","PLAYER_ASSISTS","Asistencias de jugador","player",True,"LAB_REQUIRED"),
    MarketLane("football","PLAYER_PASSES","Pases de jugador","player",True,"LAB_REQUIRED"),
    MarketLane("football","PLAYER_TACKLES","Tackles de jugador","player",True,"LAB_REQUIRED"),
    MarketLane("football","PLAYER_FOULS","Faltas de jugador","player",True,"LAB_REQUIRED"),
)

TENNIS_MARKETS: tuple[MarketLane, ...] = (
    MarketLane("tennis","MATCH_WINNER","Ganador del partido","core",True,"ACTIVE_OR_PROSPECTIVE_REQUIRED"),
    MarketLane("tennis","SET_WINNER","Ganador de set","sets",True,"LAB_REQUIRED"),
    MarketLane("tennis","SET_HANDICAP","Hándicap de sets","sets",True,"LAB_REQUIRED"),
    MarketLane("tennis","TOTAL_SETS","Total de sets","sets",True,"LAB_REQUIRED"),
    MarketLane("tennis","BOTH_PLAYERS_WIN_SET","Ambos jugadores ganan un set","sets",True,"LAB_REQUIRED"),
    MarketLane("tennis","GAME_HANDICAP","Hándicap de juegos","games",True,"LAB_REQUIRED"),
    MarketLane("tennis","TOTAL_GAMES","Total de juegos","games",True,"LAB_REQUIRED"),
    MarketLane("tennis","PLAYER_TOTAL_GAMES","Total de juegos por jugador","games",True,"LAB_REQUIRED"),
    MarketLane("tennis","TIEBREAK_YES_NO","Tie-break sí/no","serve",True,"LAB_REQUIRED"),
    MarketLane("tennis","ACES","Aces","serve",True,"LAB_REQUIRED"),
    MarketLane("tennis","DOUBLE_FAULTS","Dobles faltas","serve",True,"LAB_REQUIRED"),
    MarketLane("tennis","BREAKS_OF_SERVE","Breaks de servicio","serve",True,"LAB_REQUIRED"),
)

ALL_MARKETS: tuple[MarketLane, ...] = FOOTBALL_MARKETS + TENNIS_MARKETS

EXPECTED_FOOTBALL_KEYS = frozenset(x.key for x in FOOTBALL_MARKETS)
EXPECTED_TENNIS_KEYS = frozenset(x.key for x in TENNIS_MARKETS)


def portfolio_by_sport() -> Mapping[str, tuple[MarketLane, ...]]:
    return {"football": FOOTBALL_MARKETS, "tennis": TENNIS_MARKETS}


def required_market_keys(sport: str) -> frozenset[str]:
    lanes = portfolio_by_sport().get(str(sport).strip().lower())
    if lanes is None:
        raise ValueError("UNKNOWN_SPORT")
    return frozenset(x.key for x in lanes if x.required)
