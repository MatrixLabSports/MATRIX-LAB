# MATRIX — Plan de activación de 42 mercados — 28-OCT-2026

## Regla de lectura
42/42 significa **representados y supervisados**. No significa 42 mercados autorizados para Telegram.

## Estado físico de corte
- Total: 42 lanes.
- Fútbol: 30.
- Tenis: 12.
- Supervisor: ACTIVE=2 / LAB=40.
- Registro prospectivo: 8.798 filas.
- Lanes con observación prospectiva válida: 16.
- Lanes con >=600: 13.
- Lanes en cero prospectivo: 26.
- Dinero real: BLOQUEADO.
- Apuestas automáticas: deshabilitadas.

## Prioridad 0 — Telegram gobernado hoy
### TOTAL_GOALS_OVER_UNDER
Solo **OVER_2_5** está autorizado.
Condiciones obligatorias:
P_MATRIX >=0.60, cuota decimal >1.50, EV revalidado >=0.05, freshness/riesgo PASS.

UNDER_2_5 está medido pero no promovido.

## Prioridad 1 — desbloqueo inmediato
### MATCH_WINNER — tenis
El supervisor lo mantiene ACTIVE, pero el mapeo exacto de cuota sigue requerido.
No publicar en Telegram hasta tener precio exacto de proveedor/casa y pasar los gates.

## Prioridad 2 — maduras, pero no promovidas
- MATCH_RESULT_1X2 — 727 prospectivas.
- DOUBLE_CHANCE_1X — 727.
- DOUBLE_CHANCE_X2 — 727.

Tienen medición/calibración, pero no autorización de señal.

### Goles por periodo — 634 cada una
- FIRST_HALF_TOTAL_GOALS_OVER_UNDER.
- SECOND_HALF_TOTAL_GOALS_OVER_UNDER.
- FIRST_HALF_TEAM_TOTAL_GOALS_HOME.
- FIRST_HALF_TEAM_TOTAL_GOALS_AWAY.
- SECOND_HALF_TEAM_TOTAL_GOALS_HOME.
- SECOND_HALF_TEAM_TOTAL_GOALS_AWAY.

Tienen walk-forward medido, pero siguen en research y además requieren familia de precio exacta.

## Prioridad 3 — calibración dedicada
- TEAM_TOTAL_GOALS_HOME — 627.
- TEAM_TOTAL_GOALS_AWAY — 627.

Ya superan 600 prospectivas, pero el cierre físico no encontró artefacto dedicado de outcome/calibración. No auto-promover.

## Prioridad 4 — colección incipiente
- TEAM_TOTAL_SHOTS_HOME — 3.
- TEAM_TOTAL_SHOTS_AWAY — 3.
- MATCH_WINNER — 99 en el registry prospectivo específico, aunque el supervisor lo mantiene ACTIVE por su calibración separada.

## Diagnóstico solamente
### DOUBLE_CHANCE_12
727 prospectivas, pero **NO PROMOVIBLE** con el challenger actual.
Bloqueador: `CHALLENGER_LOG_LOSS_WORSE_THAN_POISSON`.

## Lanes con 0 prospectivo
ACES, ASIAN_OR_EUROPEAN_HANDICAP, BOTH_PLAYERS_WIN_SET, BREAKS_OF_SERVE, BTTS, CARDS_OVER_UNDER, CORNERS_OVER_UNDER, DOUBLE_FAULTS, GAME_HANDICAP, GOALKEEPER_SAVES, PLAYER_ASSISTS, PLAYER_FOULS, PLAYER_PASSES, PLAYER_SHOTS, PLAYER_SHOTS_ON_TARGET, PLAYER_TACKLES, PLAYER_TOTAL_GAMES, SET_HANDICAP, SET_WINNER, TEAM_FOULS_AWAY, TEAM_FOULS_HOME, TEAM_SHOTS_ON_TARGET_AWAY, TEAM_SHOTS_ON_TARGET_HOME, TIEBREAK_YES_NO, TOTAL_GAMES, TOTAL_SETS.

Estas lanes deben seguir representadas en cada ciclo; ausencia de datos no puede convertirse en cero.

## Automatización nueva
- `config/MATRIX_42_MARKET_ACTIVATION_POLICY_20261028.json`
- `tools/matrix_42_market_activation_guard.py`
- `tests/test_matrix_42_market_activation_guard.py`
- `.github/workflows/matrix-42-market-activation-15m.yml`
- `evidence/governance/MATRIX_42_MARKET_ACTIVATION_LAST.json` se reconstruirá dinámicamente.

El guard impide que >=600 o ACTIVE por sí solos habiliten Telegram.

## Orden de fuentes
1. SofaScore.
2. Flashscore.
3. APIs/proveedores.

## Corte de APIs
Las APIs pagas de fútbol/tenis vencen el 28-OCT-2026 y no hay renovación autorizada. Después del corte, cualquier disponibilidad debe ser verificada físicamente; no se asume.
