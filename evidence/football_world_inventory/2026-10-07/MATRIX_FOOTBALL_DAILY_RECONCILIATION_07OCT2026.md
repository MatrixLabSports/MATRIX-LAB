# MATRIX-LAB-SPORTS — Dictamen diario fútbol 07-OCT-2026

## Secuencia ejecutada
SofaScore + Flashscore se intentaron primero. SofaScore fue accesible por web pública pero no expuso el total/IDs completos; Flashscore no fue accesible por la herramienta web y Opera Browser Connector está desconectado. Por gobernanza no se inventó ningún conteo browser ni se declaró un union mundial exacto.

Después se ejecutaron las fuentes estructuradas. football-data.org respondió HTTP 200 autenticado con 0 partidos accesibles para 07-OCT y `world_complete=false`. API-Football ejecutó un ciclo fresco y cerró PASS.

## API-Football 07-OCT fresco
**233 recibidos → 207 futuros → 107 PIT-ready → 88 candidatos de freeze → 77 ya existentes + 11 nuevos → 0 colisiones físicas.**

El ciclo usó 161 llamadas. El estado global posterior quedó en **1450 freezes / 1450 fixture IDs únicos**, 0 grupos de fixture duplicados, 0 duplicados físicos exactos y 0 pares sospechosos en 36 horas. La calibración registra 1024 filas / 1024 fixture IDs únicos.

## Corrección 429
El primer rerun falló por `API_FOOTBALL_TEAM_LAST_HTTP_STATUS_429:1628`. Se corrigió el fallback para registrar 429, respetar backoff/retry y, si persiste, bloquear como dato faltante sin derribar el lote ni imputar cero. Se añadieron pruebas 429→200 y 429 persistente.

CI del parche: run `37606033708` = SUCCESS. Verificación de producción: run `37606526278` = SUCCESS. En el ciclo fresco no reapareció 429 (`rate_limit_event_count=0`); terminó con `daily_remaining=6522` y `minute_remaining=139`.

## Mercados
- Over 2.5: ACTIVE_V2 / STRONG; 622 freezes, 227 settlements, 395 pendientes; métricas cerradas.
- 1X2: ACTIVE_V2 / DEVELOPING; 622 freezes, 227 settlements, 395 pendientes; métricas cerradas.
- Player Shots v3: DEVELOPING; 0 freezes / 0 calibraciones.
- Team Total Shots Home: DEVELOPING; 0 / 0.
- Team Total Shots Away: DEVELOPING; 0 / 0.
- Team Fouls Total: DEVELOPING; 1 freeze / 1 calibración; faltan 29 para gate 30.

## Veredicto
`STRUCTURED_PIPELINE_PASS_BROWSER_EXACT_UNION_PENDING`.

El pipeline estructurado del 07-OCT está físicamente ejecutado y deduplicado. Lo único pendiente es cerrar la enumeración exacta browser de SofaScore/Flashscore cuando Opera vuelva a estar conectado; ese faltante no autoriza joins por nombre ni backfill.

Protecciones intactas: no backfill, Missing≠0, sin imputación silenciosa, sin name-only join, dedupe físico antes del contador, no odds→P_MATRIX, métricas selladas, automatic_wagering=false, REAL_MONEY=BLOCKED.
