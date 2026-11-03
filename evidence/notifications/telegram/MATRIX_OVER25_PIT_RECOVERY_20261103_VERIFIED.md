# MATRIX — Auditoría de recuperación del productor Over 2.5

Fecha de prueba física: 2026-11-03 UTC. Rama: `repair/cor09-world-pipeline`.

## Pregunta técnica resuelta

¿Sustituir las observaciones enriquecidas `CANONICAL_ENRICHED_PIT` del productor original por observaciones de grupo `RAW_GROUP_PIT` cambia las probabilidades congeladas de Over 2.5?

### Resultado físico — Championship, ciclo original 2026-10-24

- Ciclo fuente inmutable: `evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z`.
- Fuente del modelo: `app/research/football/match_analysis_input.py` + `tools/api_football_market_shadow_p_matrix.py`; mismos parámetros congelados de Over 2.5, `a=0.6, b=0.0, c=0.4`.
- 11 entradas históricas canónicas originales de Championship, con observaciones `CANONICAL_ENRICHED_PIT` de ambos equipos.
- **11/11** comparables con la alternativa de grupo: **11 probabilidades idénticas**, **0 probabilidades distintas**, **0 bloqueadas**, máxima desviación absoluta **0.0**.
- Cada pareja contiene 11 observaciones por equipo tanto en fuente canónica como en fuente de grupo. Las identidades y referencias pertenecen a un corte anterior al comienzo del partido, según el manifiesto original.
- Reporte JSON persistido: `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ENRICHED_RAW_PIT_REPLAY.json`. Blob SHA `4da9a59c8c78cd26429a024f3dce9c9013d9ac14`.
- Ejecución CI Windows real: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41618327729, trabajo `archived-parity`, **completed/success**. Tres pruebas de seguridad aprobadas; reporte subido como artefacto y persistido con `PIT_PARITY_EVIDENCE_PERSISTED`.
- En las primeras dos ejecuciones se confirmó cálculo + artefacto, pero la persistencia falló por PowerShell bloqueado. Corrección codificada sin cambiar Windows: `tools/matrix_persist_over25_pit_parity.py` y `.github/workflows/matrix-over25-enriched-raw-pit-replay.yml`, que usa Python local.

### Evidencia histórica complementaria YA VERIFICADA (sin repetir)

- Comparaciones de grupo API-Football vs football-data.org: Championship 57/57, Brasil 237/237 e Italia 30/30 en subconjuntos históricos evaluables. La concordancia del cálculo de grupo en estas ligas no demuestra equivalencia de características enriquecidas para todos los partidos.
- La nueva prueba 11/11 y las comparaciones 57/57 **no son un mismo conjunto de partidos**: no asumir una equivalencia transitiva prospectiva a partir de esos agregados. Aún faltan comprobaciones de identidad de equipos/ligas, histórico puntual, captura PIT autenticada y estabilidad prospectiva.

## Estado del productor y Telegram

- **RESUELTO:** cuantificación histórica auténtica de la diferencia entre entradas enriquecidas y de grupo en el subconjunto Championship 11/11; código, tests, workflow y evidencia física.
- **PENDIENTE:** fuente alternativa que produzca entradas canónicas actuales con ID estable, fixture/historial SHA, hora observada anterior al análisis, IDs de liga/temporada y al menos cinco resultados autenticados por equipo; paridad prospectiva por partido. El archivo histórico de congelación anterior tiene 5243 filas, cero `p_matrix` en el campo de producción y cero partidos para 2026-11-03.
- **PENDIENTE:** probabilidad gobernada actual de Over 2.5, cuota exacta de casa autorizada >1.50, referencia sharp actual, EV positivo, kickoff y controles completos, y envío certificado por Telegram. No se autoriza fabricar nueva `p_matrix`.
- Las pruebas NO prueban rentabilidad ni validación fuera de muestra en el nuevo proveedor.
- Se mantienen `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `0 BET`, holdouts, calibraciones y cohortes originales intactas.

## Próxima acción del productor

En un **partido futuro real** de Championship autenticado en SofaScore, Flashscore y football-data.org, capturar prospectivamente las observaciones individuales del proveedor alternativo con timestamp, hash y estado final ya conocido, construir un objeto experimental conforme a `FootballMatchAnalysisInput`, ejecutar el mismo motor congelado en modo shadow, y certificar identidad y paridad con el histórico original, sin saltarse gates ni publicar `p_matrix` de producción. Solo tras esa evidencia revisar una promoción gobernada de Over 2.5, antes de cuotas y Telegram.
