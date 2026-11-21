# MATRIX — Recuperación certificada del componente histórico Over 2.5

Corte comprobado: 2026-11-03 UTC. Repo: `MatrixLabSports/MATRIX-LAB`. Rama operativa `repair/cor09-world-pipeline`.

## Comité de revisión por funciones
Ingeniería de fuentes y trazabilidad, auditoría matemática, calidad de histórico PIT, cotejo de identidades SofaScore/Flashscore, CI/operación, integridad de cuotas/CLV y supervisor de seguridad. Se trata de funciones analíticas, no de personal humano externo.

## Certificación física 1 — seis partidos futuros

Ejecución Windows: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41627759153 `completed/success`, 26 pruebas aprobadas, `REAL_AUTHENTIC_BASELINE_VERIFIED=6`, `BASELINE_EVIDENCE_PERSISTED`.

Artefacto inmutable persistido:
`evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_OVER25_BASELINE_WINDOWS_41627759153.json`
SHA blob `dfc6080c54a4064d77bab0b10cc8a204d4088d41`.

El auditor decodificó y verificó el SHA de la respuesta HTTP autenticada de football-data.org:
`28b7cfe540394b5bf1b4fec83841ce049dbf32f72d8662e4fd3811bdaf85ceff`.
Reconstruyó 156 finales históricos de Championship anteriores al corte de la captura y, usando `_inputs_for_target` y `_pool_over25` originales, comparó componente histórico, componente Poisson, recuentos y probabilidades con los valores de investigación guardados.

Resultados por ID de football-data.org:

| ID | Baseline Over 2.5 original | Poisson | Probabilidad de investigación |
|---|---:|---:|---:|
| 561917 | 0.615384615385 | 0.593820361572 | 0.6024946159 |
| 561918 | 0.615384615385 | 0.446283520549 | 0.5146414249 |
| 561921 | 0.615384615385 | 0.618486956788 | 0.6172471641 |
| 561922 | 0.615384615385 | 0.550468341570 | 0.5767728178 |
| 561924 | 0.615384615385 | 0.523179401363 | 0.5606183366 |
| 561928 | 0.615384615385 | 0.559356594995 | 0.5820348324 |

Todos los valores son de investigación. No son `p_matrix` gobernados.

## Certificación física 2 — dos proveedores y el mismo histórico

En la misma ejecución Windows:
`evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_CROSS_PROVIDER_WINDOWS_41627759153.json`
Blob SHA `3397d6e8679d497ad29b2797aaa6818a136fe822`.

Cotejo contra el archivo original congelado API-Football del ciclo 2026-10-24:
- 133 partidos de cada proveedor en el alcance histórico previo al corte.
- **102 resultados emparejados, 0 desacuerdos de marcador**.
- **57 partidos con características de grupo computables en ambos proveedores; 57/57 idénticos, 0 distintos, 0 bloqueados unilateralmente**.
- `historical_raw_group_model_feature_parity_verified=true` en **este subconjunto histórico**.
- `canonical_enriched_pit_equivalence_verified=false`; `full_original_calibrated_model_equivalence_verified=false`, porque la coincidencia de grupos históricos NO prueba aún todos los campos enriquecidos del productor de producción ni el mapeo original para partidos nuevos.
- Ninguna consulta adicional al proveedor para esta comparación: `network_calls=0`.

## Código y pruebas de la solución
- `tools/matrix_football_independent_over25_shadow.py`, commit `15552cdc`: conserva exactamente el HTTP autenticado codificado en base64, SHA, hora observada y liga por cada grupo.
- `tools/matrix_championship_baseline_pit_replay.py`, commit inicial `7fa841e3` y corrección `27dca396`: valida HTTP contra SHA y vuelve a ejecutar el modelo original. Selecciona estrictamente la certificación que coincida con los cuatro archivos de fuente del mismo ciclo, incluidos los informes inmutables por ejecución; no empareja snapshots de fechas distintas.
- `tools/matrix_championship_cross_provider_archived_replay.py`, commit `458de073`: coteja evidencia auténtica de fuente independiente con archivo físico API-Football, sin red ni apuesta.
- Tests negativos en `tests/test_matrix_championship_baseline_pit_replay.py` y `tests/test_matrix_championship_cross_provider_archived_replay.py`: alteración del HTTP, cambio de componente, fuente incorrecta, análisis postkickoff y hashes no coincidentes.
- Workflows `.github/workflows/matrix-football-independent-fixture-recovery.yml` y `.github/workflows/matrix-over25-authentic-baseline-windows.yml` integran pruebas, auditorías y conservación inmutable del reporte.
- Corrigió interferencia entre procesos Windows/Linux: los archivos de evidencia se guardan con ID de corrida GitHub; el auditor no escoge la certificación más reciente sin comprobar primero todos los hashes.
- `tools/matrix_championship_quote_window_scope.py`, commit `e649fe38`: escoge para cuotas solo una certificación que coincida con cuatro hashes actuales, no una versión posterior de otra captura. Test `37bd681b` comprueba dos versiones del mismo día y rechazo de todas las versiones incompatibles.
- Runner Windows https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41628106845: `completed/success`, **32 pruebas aprobadas** y `AUTHENTIC_PROSPECTIVE_RESEARCH_FIXTURES=6`, evidencia persistida.
- El cron Linux `*/15 * * * *` en main, `.github/workflows/matrix-championship-quote-research-15m.yml`, commit `150cc981`: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41628142354, **completed/success, 24 pruebas aprobadas**. El filtro devolvió `NO_VERIFIED_PREMATCH_SCOPE`, cero partidos en la ventana de 120 minutos, cero solicitudes de cuota, cero señales. Esto certifica funcionamiento y seguridad del filtro, **no precios disponibles**.

## Controles de producción pendientes

1. Paridad prospectiva completa de características `CANONICAL_ENRICHED_PIT` contra la fuente alternativa, con crosswalk auténtico de IDs originales para el mismo partido; no confundir 57/57 de grupo con un GO total de producción.
2. Cuotas exactas full-time Over 2.5 de casa colombiana >1.50, timestamp proveedor <=120 segundos, referencia sharp Pinnacle <=120 segundos, EV+, kickoff, controles de sizing. Los últimos archivos de cuota mostraron 0 cuotas y 0 sharp: `SKIPPED_NO_PREMATCH_WINDOW`. Históricamente el proveedor de cuotas devolvió HTTP 429; se conserva enfriamiento y no sondeo fuera de ventana.
3. Telegram green/supervisor sigue `NO-GO`, `0 BET`; no enviar publicaciones prematuras.

**Protecciones permanentes:** `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, parámetros congelados `a=0.6,b=0,c=0.4`, sin recalibración, sin alteración de cohortes, sin backfill de resultados de partidos futuros.
