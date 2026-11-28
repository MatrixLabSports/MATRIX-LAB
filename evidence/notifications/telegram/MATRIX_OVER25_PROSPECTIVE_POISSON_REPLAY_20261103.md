# MATRIX — Comité técnico: recomputación prospectiva de Over 2.5

Corte: 2026-11-03 UTC. Repositorio `MatrixLabSports/MATRIX-LAB`, rama `repair/cor09-world-pipeline`.

## Alcance
Revisión funcional de ingeniería del dato, series temporales, auditoría estadística, calibración, CI, cuotas y gobierno de señales. No se afirma participación de especialistas humanos externos.

## Evidencia previa preservada
- 6 partidos Championship de 9 examinados con 13 históricos individuales por equipo observados antes del kickoff, triple cruce de identidad, SHA del proveedor y cálculo original `calibrated_log_pool_v1`; otros 3 bloqueados. Prueba original Windows `41620496062`.
- 11/11 coincidencias retrospectivas `CANONICAL_ENRICHED_PIT` vs `RAW_GROUP_PIT` del productor original; no extrapolables a otros partidos o calibración de otro proveedor.
- Enlace exacto a cuatro SHA canónicos de intake, shadow, SofaScore y Flashscore; certificado Windows `41624462039`, 22 pruebas.

## Nueva verificación matemática
- Código `tools/matrix_championship_prospective_pit_attestation.py`, commit `99ca6408`: reconstruye tasas de gol esperadas y componente Poisson Over 2.5 mediante los goles históricos de las observaciones originales que ya se habían validado. Las compara con la probabilidad Poisson guardada, con tolerancia estricta de 1e-9.
- Los parámetros congelados `a=0.6,b=0,c=0.4` continúan sin cambiar. Después de Poisson, se vuelve a ejecutar `_pool_over25` y se compara con el `p_over25_research` original. Sin resultados posteriores al comienzo del encuentro, sin inventar IDs de API-Football.
- `tests/test_matrix_championship_prospective_pit_attestation.py`, commit `4c36074c`: pruebas positivas y negativas que alteran deliberadamente goles históricos o la probabilidad Poisson; deben obtener `BLOCKED_AUTHENTIC_HISTORY_POISSON_MISMATCH`, no un `PASS`.
- La primera ejecución tras modificación `41625002959` falló por pruebas de transición en el paquete. La posterior ejecución con los cambios completos `41625045528` pasó la suite sin relajar el gate.

## Certificación física
- https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41625045528: **completed/success** en el Runner Windows; `24 passed in 0.66s`, `AUTHENTIC_PROSPECTIVE_RESEARCH_FIXTURES=6`, `PROSPECTIVE_PIT_REPORT_PERSISTED`. Sin alteración del productor canónico ni del dinero real.
- https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41624051642: **completed/success** programador Linux de investigación; filtro fuera de ventana, sin consultas de precios.
- Se preservan los informes prospectivos y hashes de ciclos previos y nuevos, sin afirmar `p_matrix` de producción.

## Diferencia entre lo demostrado y lo pendiente
- DEMOSTRADO: observaciones individuales auténticas PIT, recomputación independiente del componente Poisson para 6 partidos, ejecución de la fórmula congelada y contratos de seguridad que bloquean alteraciones.
- NO DEMOSTRADO: paridad de todos los componentes/calibración original entre **proveedores** para partidos prospectivos; validez fuera de muestra del sustituto; cuota exacta full-time Over 2.5 en casa colombiana y referencia sharp <=120 segundos; EV positivo y controles económicos finales; envío verde de Telegram.
- La probabilidad alternativa sigue siendo `p_over25_research`, **no** `p_matrix` gobernada.
- `0 BET`, `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, cohortes/holdouts originales intactos.

## Próximo control no sustituible
Capturar de forma verificable la serie de grupo completa de la fuente independiente y comparar también el componente base de goles con las observaciones archivadas del proveedor original, en ventanas PIT equivalentes; cualquier no-paridad se bloquea y se mide. No liberar Telegram por el simple hecho de haber certificado Poisson. El proveedor de cuotas reportó HTTP 429 en sondeo anterior: respetar control de cuota y no solicitar fuera de ventana.
