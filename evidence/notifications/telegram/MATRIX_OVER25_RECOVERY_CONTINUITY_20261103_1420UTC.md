# MATRIX — Comité técnico de recuperación Over 2.5 — corte físico 2026-11-03 14:20 UTC

Repositorio `MatrixLabSports/MATRIX-LAB`, rama `repair/cor09-world-pipeline`. Esta revisión agrupa funciones de ingeniería de datos, integridad de fuentes y del tiempo, modelado, cuotas y sharp, DevOps/Windows, riesgo y Telegram. No implica personal humano adicional.

## Prioridad y regla de continuidad
Recuperar evidencia prospectiva compatible, asegurar una entrada de cuotas autorizada y distinguir señales gobernadas de investigación. No reiterar auditorías de calibración ya concluidas; jamás producir `p_matrix` desde un experimento. `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, dinero real no autorizado, `0 BET` legítimo.

## 1. Evidencia prospectiva — se resolvió la mezcla entre ciclos

- La captura de `football-data.org` de 2026-11-03 14:04 UTC continuó generando 19 partidos futuros, 7 identidades de calendario confirmadas por SofaScore+Flashscore y 6 historiales individuales de Championship válidos para investigación. [Ejecución 41649771130](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41649771130) `completed/success`.
- Antes, un fichero diario del proveedor podía actualizarse mientras la certificación era de otra captura. Se preserva el bloqueo por hash, pero ahora se guarda un **paquete atómico de cinco documentos por ID de ejecución**:
  `tools/matrix_championship_atomic_pit_cycle.py` (commits `7e37555b`, `36331081`);
  `tools/matrix_championship_quote_window_scope.py` (commit `78904776`);
  `tests/test_matrix_championship_atomic_pit_cycle.py`, pruebas contra cambios de evento, fuente y uso de certificaciones obsoletas; `tests/test_matrix_championship_quote_window_scope.py` comprueba que una captura diaria incompatible NO sustituye a un paquete válido.
- El paquete incluye íntegros `intake`, `shadow`, `sofa`, `flash`, `attestation`, hashes SHA-256 canónicos y marcas de tiempo. Todos se toman del **mismo ciclo auténtico**; ninguna diferencia de hash se corrige mediante imputación.
- Verificación real [Windows #41652244354](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41652244354): `completed/success`, **33 pruebas aprobadas**, `AUTHENTIC_ATOMIC_PROSPECTIVE_HISTORY=6`, `ATOMIC_PIT_EVIDENCE_PERSISTED`.
- Artefacto físico persistido `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_41652244354.json`, Git blob `9961489ff5963780e5990983025ef7f9bdba6687`. Registro del 3-Nov-2026 a las `14:09:20.696634+00:00`. SHA de capturas: intake `4675b441d6bd788706767631365bdab4e350fca59a9b4ba9261a4e79aea4593c`, shadow `c2d47d1acd2c280bb5d74026e4f3c10a3353bebeecec5769c7bf3823ea706589`, SofaScore `968d4639e4a576c03301a15f3eccf958753ad4a02e278fb1a57765fd5af78137`, Flashscore `9a60ba455c385b3bb5e27c35da1af5eff5cac336c4744ebd2ff11fa581f61ec0`. No `p_matrix`, no Telegram.
- La prueba de regresión de los tres proveedores y las capturas dio **51 pruebas aprobadas en Windows** [#41652604235](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41652604235), `completed/success`; sigue 6 historiales válidos, 102 marcadores concordantes, 57/57 características de grupo idénticas, 8/11 comparaciones enriquecidas idénticas y 3 equipos/casos sin mapeo original prospectivo suficiente.

## 2. Proveedor de cuotas — HTTP 429 bloqueado en ambos flujos

- `evidence/notifications/telegram/MATRIX_ODDS_API_QUOTA_GUARD_LAST.json`: respuesta real `HTTP 429`, `BLOCKED_EXHAUSTED`, `api_calls_allowed=false`; no puede declararse que `odds-api.net` dispone de créditos.
- `tools/matrix_independent_over25_quote_audit.py` commit `2e1424f7`: incorpora `--global-quota-guard` para rechazar *antes de consultar siquiera /usage* las ejecuciones en ventana cuando se mantiene la decisión global de cuota agotada. Sin fichero de cuota global también se bloquea. No evita ni altera el veto del proveedor; la cuota debe acreditarse nuevamente.
- Nuevas pruebas en `tests/test_matrix_independent_over25_quote_audit.py` commit `78128574`: dentro de ventana con `BLOCKED_EXHAUSTED` produce `network_calls=0`, no se permite consulta de evento ni snapshot, dinero real y mensajes permanecen bloqueados.
- Workflows actualizados: `.github/workflows/matrix-football-independent-fixture-recovery.yml` y `.github/workflows/matrix-championship-quote-research-15m.yml` pasan el guard real; no ejecutan consultas innecesarias; no generan señales.
- La definición de la tarea diaria independiente en `main` fue alineada con la rama operativa, commit `8929fea8`; el programador de 15 minutos, commit de `main` `60c10c6e`; el recolector de navegador de 5 minutos se alineó en `main`, commit `a7f8f515`.
- Última ejecución específica del programador 15m iniciada por cambio: [#41652636543](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41652636543), **en cola al corte**. No afirmar que su corrida nueva aprobó hasta verla finalizar.

## 3. Captura real de navegador, sin cuota pagada

- Recolector de navegador Windows [#41651445893](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41651445893) `completed/success`: **61 + 23 pruebas aprobadas**, CDP `PASS_CDP_REACHABLE`, Chrome `156.0.8078.79`, 14 páginas autorizadas, resultado `PASS_CAPTURED`, `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- Segunda verificación [#41651743642](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41651743642) también `completed/success` con los mismos controles; a las 14:15 UTC había `betano_exact_quote_count=0`, `research_only_quote_target_count=0`, `candidates=0`. El navegador no sustituyó la referencia Pinnacle.
- Los partidos Championship de interés, con kickoff de alrededor de las 20:00 UTC, todavía no habían abierto la ventana autorizada de 120 minutos a las 14:15. Cero cuotas era el resultado correcto, no una falla del Runner.

## 4. Equivalencia original y Telegram — sin elevar resultados retrospectivos

- 57/57 igualdad de características de grupo de fuentes independientes en el subconjunto retrospectivo; 8/11 en tres vías (`CANONICAL_ENRICHED_PIT` original, grupo original, fuente nueva), 3 casos bloqueados por identidad histórica.
- Los seis partidos de investigación **no** están certificados como equivalentes completamente al universo enriquecido original del proveedor API-Football. Sus probabilidades son `p_over25_research`, no `p_matrix` gobernada.
- Supervisor Telegram [#41627244910](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41627244910) termina `success` pero tenía **0 archivos canónicos nuevos**, **0 candidatos** y **0 mensajes emitidos**. La ejecución técnica NO equivale a recuperación de señales.
- El control final [#41630466905](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41630466905) completó 17 pruebas y persistió `MATRIX_OVER25_RECOVERY_TRUTH_41630466905.json`: `NO_GO_FAIL_CLOSED`.
- Quedan sin prueba suficiente en este corte: paridad prospectiva enriquecida completa, crosswalk de identificación original del partido futuro, exportación de nueva probabilidad canónica gobernada, cuota ejecutable auténtica >1.50 y fresca <=120 s, sharp Pinnacle <=120 s, EV positivo y entrada válida de Telegram. **No promover a Telegram ni apostar**.

## Próximo criterio verificable sin inventar datos
Continuar desde el paquete atómico real de seis eventos, filtrarlos solamente durante su ventana prematch, leer precios autorizados y referencias sharp de proveedores con disponibilidad acreditada (nunca eludir HTTP 429), verificar en conjunto las características calibradas originales, y solo entonces permitir al supervisor ordinario decidir en modo papel, con 1 unidad máxima. Si falta cualquier componente: NO BET.

No se cambió la calibración, la búsqueda de parámetros, cohortes, capacidad de apuesta, seguridad de Windows ni la autorización de dinero real.

## Adenda física de certificación a 14:24 UTC

- El flujo automático independiente [#41651322786](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41651322786) concluyó **completed/success**. Generó de forma real `MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_41651322786.json` a partir del mismo ciclo de cinco documentos, seis históricos prospectivos válidos y lo persistió mediante GitHub `git push`. Registró cero consultas de precios por estar fuera de ventana.
- El filtro de 15 minutos [#41652636543](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41652636543) terminó **completed/success, 35 passed**. Ejecutó filtro real `NO_VERIFIED_PREMATCH_SCOPE`, `research_only_eligible_count=0` sin consultas ni señal.
- El Runner Windows [#41653234038](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41653234038) terminó **completed/success**, `35 passed`, `AUTHENTIC_ATOMIC_PROSPECTIVE_HISTORY=6` y `AUTHENTIC_ATOMIC_QUOTE_WINDOW_RESEARCH_ONLY=NO_VERIFIED_PREMATCH_SCOPE`; persistencia `ATOMIC_PIT_EVIDENCE_PERSISTED`.
- Evidencia adicional del filtro: `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_QUOTE_WINDOW_SCOPE_WINDOWS_41653234038.json` y paquete `MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_41653234038.json`.
- Para no prometer recuperaciones no logradas: **sigue faltando** paridad prospectiva enriquecida completa para el nuevo proveedor, una probabilidad de producción gobernada, precios exactos actuales y una referencia Pinnacle fresca. `odds-api.net` continúa con decisión `BLOCKED_EXHAUSTED` por HTTP 429. **NO BET**, `REAL_MONEY=BLOCKED`.
