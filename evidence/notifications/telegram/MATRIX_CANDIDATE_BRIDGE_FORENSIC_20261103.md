# MATRIX — Auditoría física del puente de candidatos (2026-11-03 UTC)

## Alcance y origen

Repositorio: `MatrixLabSports/MATRIX-LAB`; rama `repair/cor09-world-pipeline`.
No se ha alterado ninguna calibración, parámetro `p_matrix`, selección de cuotas, envío de Telegram ni política de dinero real.

## Evidencia independiente

1. Supervisor: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41575178645 (trabajo `notify`). A las 03:58 UTC de 2026-11-03 reportó `FAIL_CLOSED_NO_CANONICAL_INPUTS`. Para 2026-11-02 y 2026-11-03 (Bogotá) observó cero archivos de fútbol en `browser_physical_verification`, `shadow_quote_freeze` y `over25_shadow_ev`, y cero archivos canónicos de tenis. `FOOTBALL_DISCOVERY_DONE=0`, `TENNIS_DISCOVERY_DONE=0`, `sent_now=0`.
2. El mismo diagnóstico reportó para 2026-11-03 diecinueve fixtures de fútbol en investigación independiente y diez con puntuación de investigación; `historical_feature_equivalence_verified=false`, `exact_bookmaker_quotes_verified=0`, `independent_source_promotes_telegram=false`. **Estas filas NO son entradas canónicas ni señales autorizadas.**
3. Recolector previo: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41574129977; `collect=success`, 14 páginas observadas, cero candidatos, cero coincidencias y cero cuotas exactas Betano.
4. Recolector con primer diagnóstico: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41577647086, trabajo `125724783459`; 23 pruebas aprobadas, CDP alcanzable, 14 páginas, cero candidatos, entradas canónicas locales ausentes para ambas fechas.

## Reparación del enlace (código)

- `6302de16`: inventario y antigüedad de origen en el recolector, solo diagnóstico.
- `4bf7daab`: pruebas de fallo cerrado y origen.
- `38a32e11`: pruebas integradas al flujo de Windows.
- `e332bbf9`: `build_blocker_recovery_audit` exporta `browser_prematch_candidate_rows` a partir de los candidatos canónicos descubiertos, incluso sin `pre_send_gate`; excluye ya enviados y partidos iniciados.
- `320f0eed`: el recolector prefiere esa lista y rechaza entradas nuevas con auditoría antigua o no verificable; mantiene lectura de formato legado solo cuando la lista nueva no existe.
- `3aca234b`, `e6b83769`: pruebas de filtrado, frescura, inicio y puente productor/recolector.

El puente es de **descubrimiento de posibles partidos para buscar cuotas**; no concede autorización de señal ni altera las puertas de seguridad existentes.

## Bloqueador restante — NO RESUELTO

La fuente canónica de fútbol y tenis permanece ausente en el ciclo observado. La recuperación operativa exige demostrar equivalencia de identidad, histórico y características de los proveedores independientes antes de producir archivos `over25_shadow_ev` autorizados. No se permiten sustituciones sintéticas de `p_matrix`, relleno posterior al inicio, cuotas aproximadas, evasión antiautomatización ni señales sin referencia sharp y controles completos.

## Criterios para certificar recuperación

- Ejecución efectiva del supervisor con nueva evidencia canónica vigente, no solo calendarios.
- Al menos un candidato auténtico en `browser_prematch_candidate_rows`, con fuente, probabilidades originales y horario verificables.
- Ejecución de `collect` con identidad de evento, mercado y selección exactos, y evidencia física del precio fresco.
- Gating completo de Telegram (cuota > 1.50, EV y validación, referencia sharp fresca, kickoff, correlación, gobierno, límites, bloqueos).
- Hasta entonces: `0 BET`, `REAL_MONEY=BLOCKED`, `automatic_wagering=false`.

No considerar el número de páginas capturadas como número de cuotas certificadas.

## Certificación física del puente mediante Runner Windows

- Ejecución: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41577892108
- Trabajo: `collect` (`125725560567`), **completed / success**, terminado alrededor de 2026-11-03T04:24:46Z.
- Pruebas reales: **28 passed in 1.19s**, incluyendo puente de supervisor sin `pre_send_gate`, exclusión de encuentros enviados/iniciados, auditoría obsoleta, umbral de probabilidad y bloqueo por kickoff.
- CDP: `PASS_CDP_REACHABLE`, puerto 9222, Chrome 156.0.8078.79.
- Captura: `PASS_CAPTURED`, 14 páginas, cero candidatos y cero cuotas exactas Betano. Persistencia: `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- El fichero de auditoría observado era el anterior (03:58:32 UTC) y todavía no contenía el campo `browser_prematch_candidate_rows`. Eso es **ausencia de un nuevo ciclo del supervisor**, no un fallo de las pruebas del puente.
- Directorios canónicos de fútbol para los días 2026-11-02 y 2026-11-03: ausentes en la sesión operativa verificada.

**Estado final de esta intervención:** puente de código y pruebas RESUELTO; recuperación de datos canónicos y producción certificada de señales verdes PENDIENTE. No alterar calibraciones ni fabricar datos.
