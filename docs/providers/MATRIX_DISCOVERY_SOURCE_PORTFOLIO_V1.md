# MATRIX DISCOVERY SOURCE PORTFOLIO V1

Fecha efectiva: 2026-10-04
Zona horaria canónica: America/Bogota

## Regla

Ninguna fuente individual puede declarar por sí sola que el calendario mundial de fútbol o tenis está completo.

La cobertura mundial se determina por reconciliación de múltiples fuentes y por normalización física de identidad + fecha/hora a America/Bogota.

## Tenis

### Fuentes operativas

1. RapidAPI Tennis
   - Rol: PRIMARY_PAID_DISCOVERY_AND_HISTORY
   - Uso: calendario, identidad proveedor, ranking/histórico y features permitidas.
   - Restricción: su flag interno de completitud NO equivale a cobertura mundial total.

2. API-Tennis
   - Rol: SECONDARY_PAID_DISCOVERY_AND_STATS_RICH_VALIDATION
   - Uso: calendario, contraste, stats-rich e identidad secundaria.

3. SofaScore
   - Rol: WORLD_COVERAGE_AND_ENTITY_METADATA_SIDECAR
   - API automatizada CI: BLOCKED por WAF/HTTP 403 al 2026-10-04.
   - Browser/web: VERIFIED.
   - Uso permitido: torneos, calendario, superficie, jugadores, ranking visible, próximos/últimos partidos, evento y metadata.
   - feeds_model_automatically=false.

4. Flashscore
   - Rol: WORLD_CALENDAR_COVERAGE_CROSSCHECK
   - Uso: auditoría de calendario, torneo, superficie, singles/dobles y frontera horaria.
   - feeds_model_automatically=false.

5. ATP / WTA / ITF oficiales
   - Rol: OFFICIAL_COMPETITION_DATE_SURFACE_AUTHORITY.
   - Uso: existencia de torneo, categoría, semana/fecha y superficie cuando haya discrepancia.

## Fútbol

1. API-Football
   - Rol: PRIMARY_PAID_WORLD_DISCOVERY_AND_STATS.

2. SofaScore
   - Rol: WORLD_COVERAGE_TEAM_PLAYER_METADATA_SIDECAR.
   - API automatizada CI: BLOCKED por WAF/HTTP 403 al 2026-10-04.
   - Browser/web: VERIFIED capability.
   - Uso permitido: calendario diario, event IDs, equipos, plantillas, jugadores, lineups, estadísticas, incidentes, standings y metadata.
   - feeds_model_automatically=false hasta reconciliación física con API-Football.

3. Flashscore y calendarios oficiales de competición
   - Rol: cobertura y control de omisiones.

## Gate WORLD_COMPLETE

WORLD_COMPLETE=true solo se permite cuando:

- la ventana se normalizó a 00:00:00–23:59:59 America/Bogota;
- se reconciliaron al menos dos fuentes independientes;
- discrepancias de torneo/evento están listadas explícitamente;
- el inventario conserva identidad física y fuente de procedencia;
- ningún proveedor individual impone por sí solo la completitud;
- eventos no reconciliados quedan DISCOVERY_ONLY o BLOCKED, nunca se inventan;
- SofaScore/Flashscore no generan P_MATRIX por sí solos.

## Gobernanza de modelos

Todas estas fuentes pueden ampliar discovery e identidad. Ninguna puede:
- abrir métricas selladas;
- usar cuotas para P_MATRIX;
- introducir outcomes post-cut;
- hacer backfill sintético;
- saltarse PIT/identidad/histórico/freeze;
- alterar automáticamente R218/R223 o modelos de fútbol.

REAL_MONEY=BLOCKED.
