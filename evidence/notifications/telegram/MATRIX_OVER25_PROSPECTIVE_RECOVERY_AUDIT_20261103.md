# MATRIX — Auditoría de recuperación prospectiva auténtica Over 2.5
Corte físico 2026-11-03, rama operativa `repair/cor09-world-pipeline`.

## Objetivo y roles de revisión
Revisión funcional de datos, integridad temporal, motor matemático, cuota exacta, sharp, CI y gobernanza. No se afirma que especialistas humanos externos participaran.

## Hechos verificados con ejecuciones reales

1. Productor alternativo autenticado `football-data.org`, calendario originado/comparado con SofaScore y Flashscore:
   - 19 futuros capturados en 2026-11-03 Bogotá.
   - Siete partidos con triple verificación de calendario entre las tres fuentes (seis Championship y uno Brasil).
   - 10 evaluaciones de investigación por históricos de grupo.
   - 0 señales autorizadas, `REAL_MONEY=BLOCKED`.
2. Archivo nuevo físicamente persistido:
   `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json`
   Blob Git SHA `0a834b289116be7e78a4f587a7a90d26880507ed`, ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41620496062.
   - **9 Championship examinados, 6 con `PASS_PROSPECTIVE_RESEARCH_HISTORY_ONLY`, 3 bloqueados por identidad/datos.**
   - Todos los 6 aprobados tienen 13 filas históricas individuales auténticas por equipo, con IDs de partido/equipo, resultado final, kickoff anterior al análisis, hora real de captura `2026-11-03T10:31:56Z`, SHA del response histórico `28b7cfe540394b5bf1b4fec83841ce049dbf32f72d8662e4fd3811bdaf85ceff`.
   - Motor congelado `calibrated_log_pool_v1`, parámetros Over 2.5 `a=0.6,b=0,c=0.4`; probabilidad de investigación reproducida, no `p_matrix` de producción.
   - Seis probabilidades `p_over25_research` (solo investigación): 561917=0.6024946159, 561918=0.5146414249, 561921=0.6172471641, 561922=0.5767728178, 561924=0.5606183366, 561928=0.5820348324.
   - Tres bloqueados: 561919, 561920, 561923. No inventar cobertura faltante.
   - Runner Windows `13 passed`, `PROSPECTIVE_PIT_REPORT_PERSISTED`, trabajo completed/success.
3. Workflow independiente real https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41620147493:
   - 63 pruebas aprobadas, 19 fixtures autenticados, 7 crosschecks, 10 scores de investigación, 6 historiales prospectivos aprobados.
   - Persistencia completada. Cuotas: 0, `network_calls=0`, `SKIPPED_NO_PREMATCH_WINDOW`.
4. Históricos anteriores de referencia no modificados:
   - Championship raw vs fuente independiente 57/57, Brasil 237/237, Italia Serie A 30/30 concordancias en sus subconjuntos de grupo.
   - Championship `CANONICAL_ENRICHED_PIT` contra `RAW_GROUP_PIT` en once eventos originales: 11/11 probabilidades iguales, sin diferencia. Esta comparación no equivale a certificación prospectiva completa del nuevo proveedor.

## Código guardado
- `tools/matrix_football_independent_over25_shadow.py`: incorpora fuente, nombre real del adversario, observación temporal de cada historial y su SHA sin recalibrar; commits `547211f2`, `22fb2339`.
- `tools/matrix_championship_prospective_pit_attestation.py` y pruebas: construye/valida objetos de `FootballMatchAnalysisInput` y `FootballHistoryObservation` en cuarentena, controla no fuga después del kickoff, identidad de las tres fuentes y cálculo congelado; commits `9f2aeba8`, `11ba0d9c`, `0ef28acb`, `2cb4c8ec`.
- Trabajo físico Windows `.github/workflows/matrix-championship-prospective-pit-windows.yml`: `0aa2f277`; persistencia por Python `5a008011`.
- `.github/workflows/matrix-football-independent-fixture-recovery.yml`: nuevo paso real de PIT `3de01a33`; descarta sondeo de cuota en push fuera de ventana y usa `--previous`: `5af43dc4`.
- `tools/matrix_independent_over25_quote_audit.py` preserva expiración **absoluta** del bloqueo HTTP 429 y no contacta proveedor fuera de los 120 minutos: `3e9deca0`, pruebas `814edd5c`.
- `tools/matrix_championship_quote_window_scope.py` con filtro estricto solo para los 6 partidos certificados y antes del kickoff `14c1ad37`, pruebas `c84048e4`. Lee evidencias con IDs/observación/mercado y niega probabilidad de producción. Soporte de informes únicos `959c8196`.
- Workflow de **investigación** con cron `*/15 * * * *` en rama predeterminada `main`: `.github/workflows/matrix-championship-quote-research-15m.yml`, commits `91b1c2ec`, `fb7f93c9`. Consulta `odds-api.net` únicamente si existen partidos certificados en una ventana prematch de 120 minutos; usa 429 y límites de cuota, exige precio exacto Over 2.5 full time, casas colombianas y referencia Pinnacle <=120s. Nunca emite señales ni órdenes.
- CI primera ejecución del programador: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41621182602, **20 pruebas aprobadas**, `NO_VERIFIED_PREMATCH_SCOPE`, consulta externa omitida correctamente; artefacto de ventana subido.
- CI nueva tras código versionado: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41621776476, estado pendiente de verificar al corte.
- Corrección de colisiones de Git entre dos jobs simultáneos para no perder PIT: `90e6566c`, evidencia única `MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_<run_id>.json` en lugar de sobrescribir el mismo archivo; ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41621485245 pendiente de conclusión al corte.
- La falla previa en https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41619919697 se produjo por colisión Git add/add al intentar guardar el mismo JSON desde Windows y Linux. Sus cálculos y pruebas anteriores al commit sí aprobaron.

## Gates aún BLOQUEADOS
- 0 `p_matrix` de producción; sigue sin verificarse la equivalencia prospectiva **completa** del proveedor alternativo a las características calibradas originales y el crosswalk API-Football.
- 0 cuotas Over 2.5 ejecutables exactas y 0 referencias sharp frescas. Proveedor odds-api.net devolvió 429 en una consulta fuera de ventana de una corrida antigua; nuevas consultas fuera de ventana están prohibidas y existe enfriamiento absoluto de una hora. Su disponibilidad en la ventana futura no está confirmada.
- 0 envíos verdes de Telegram certificados. `0 BET` es el resultado correcto mientras falte evidencia.
- Sin refit, sin cambio de parámetros, sin alteración de cohortes, sin reusar resultados postkickoff, sin dinero real.

## Próximo criterio de aprobación
Solo si un evento auténtico (futuro al instante de observación) mantiene identidad crosscheck, histórica PIT válida, paridad de características calibradas verificada y una cuota exacta fresca con sharp y EV/gates completos, podría evaluar el supervisor su autorización ordinaria. Este informe no concede autorizaciones.
