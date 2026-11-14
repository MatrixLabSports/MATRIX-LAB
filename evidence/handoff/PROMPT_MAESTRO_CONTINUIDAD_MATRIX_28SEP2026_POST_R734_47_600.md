# PROMPT MAESTRO DE CONTINUIDAD TOTAL — MATRIX-LAB-SPORTS
## HANDOFF 28-SEP-2026 — POST-R734 IDENTITY + TENIS 47/600 + COR10 RESUELTO + FÚTBOL FREEZE PROSPECTIVO 67 + CI 3158 PASS

IDIOMA OBLIGATORIO: **ESPAÑOL**

PROYECTO: **MATRIX-LAB-SPORTS**

REPOSITORIO: **MatrixLabSports/MATRIX-LAB**

RAMA OPERATIVA: **repair/cor09-world-pipeline**

RAMA POR DEFECTO / WORKFLOWS: **main**

ZONA HORARIA CANÓNICA: **America/Bogota**

FECHA DE HANDOFF: **28-SEP-2026**

ESTADO GLOBAL: **RESEARCH_VALIDATION_NOT_PRODUCTION_READY**

EXTERNAL_AUDIT: **NOT_CLOSED**

REAL_MONEY: **BLOCKED**

AUTOMATIC_WAGERING: **FALSE**

---

# 0. REGLA SUPREMA DE CONTINUIDAD Y VERACIDAD

Continúa EXACTAMENTE desde el último estado físico y canónico existente.

NO empieces desde cero.

NO reconstruyas por memoria algo que ya exista físicamente.

NO inventes avances, uso de APIs, llamadas, PASS, cobertura, cuotas, probabilidades, ejecución, settlement, CI, hashes, archivos, conteos ni cierres.

NO llames “usada” a una API porque exista código, adaptador, secreto, suscripción o workflow. Solo puede afirmarse uso cuando exista llamada física verificable y evidencia persistida.

La autoridad, de mayor a menor, es:

1. repositorio/runtime físico y evidencia de proveedor;
2. ledgers, SHA-256, manifests, workflows terminales y artefactos persistidos;
3. auditoría reconciliada;
4. este handoff y resúmenes anteriores;
5. memoria/chat.

Si este prompt contradice evidencia física posterior, MANDA LA EVIDENCIA FÍSICA POSTERIOR.

Antes de afirmar PASS, ejecución, uso de API, avance de conteo o cierre de COR, verifica físicamente archivos + commit + workflow/log correspondiente.

PROHIBIDO volver a afirmar como hecho algo que no se haya comprobado físicamente.

---

# 1. CABEZAS FÍSICAS Y CI AL CREAR ESTE HANDOFF

Cabeza operativa inmediatamente ANTES de persistir este nuevo handoff:

`02ed415ea37000bc3a53270257e280c9d5c47635`

Mensaje:
`test(cor02-03): define JSON fixture loader for identity authority tests`

MATRIX CI:
- run: `36424149666`
- job: `108933852129`
- resultado: **SUCCESS**
- pruebas: **3158 passed**
- mensaje final: **MATRIX CI QUALITY GATE: PASS**

Cabeza `main` inmediatamente antes del handoff:

`c75e12f9dd02ebf926578d1a8affbc07895d0055`

Mensaje:
`ci(cor02-03): probe Ultra days 5-8 inventory`

IMPORTANTE:
al abrir la nueva conversación, vuelve a consultar físicamente las dos ramas. Pueden existir commits posteriores al handoff.

---

# 2. ORDEN OBLIGATORIO DE LECTURA EN LA NUEVA CONVERSACIÓN

## A. Autoridad reconciliada y veracidad
- `docs/governance/MATRIX_RECONCILED_BASELINE_SUPREMACY_V1.md`
- `evidence/audit/MATRIX_TOTAL_RECONCILIATION_AUDIT_20260926.md`
- `evidence/audit/MATRIX_RECONCILED_TRUTH_STATE_20260926.json`
- `docs/governance/MATRIX_TRUTHFULNESS_AND_PHYSICAL_EVIDENCE_CONSTITUTION_V1.md`
- `evidence/audit/MATRIX_API_USAGE_CLAIM_GATE_V1.md`

## B. Handoff actual
- `evidence/handoff/PROMPT_MAESTRO_CONTINUIDAD_MATRIX_28SEP2026_POST_R734_47_600.md`
- `evidence/handoff/MATRIX_HANDOFF_RESUMEN_POST_R734_28SEP2026.md`
- `evidence/handoff/MATRIX_HANDOFF_MANIFEST_POST_R734_28SEP2026.json`

Los handoffs anteriores siguen siendo historia útil, pero este handoff manda donde existe evidencia posterior.

## C. Estado COR actual
- `evidence/audit/MATRIX_OPEN_COR_STATUS_20260928.json`
- `evidence/cor10/MATRIX_COR10_ADJUDICATION.json`
- `evidence/cor10/MATRIX_COR10_GENUINE_FUTURE_EXECUTION.json`
- `evidence/cor10/COR10_CLOSURE_MANIFEST.json`
- `evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_R727.json` o revisión física posterior.

## D. Tenis COR02/COR03
- `evidence/cor0203/runtime/MATRIX_COR0203_PRODUCTION_OBSERVABILITY_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_CROSSWALK_R730.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_RESTAGE_DELTA_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R731.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_PREFEATURE_REGISTRY_R732.json`
- `evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R731.json`
- `evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R732.json`
- `evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R734.json`
- `evidence/cor0203/identity/MATRIX_COR0203_RAPIDAPI_PROFILE_IDENTITY_R732.json`
- `tools/cor0203_identity_authority.py`
- `tools/cor0203_identity_restage_delta.py`
- `tools/cor0203_build_identity_crosswalk.py`
- `scripts/cor0203_production_cycle.sh`

## E. Fútbol — canonical, challenger y freeze prospectivo
- `evidence/api_football/canonical_analysis/manifest.json`
- `evidence/api_football/engine_registry/physical_adjudication.json`
- `evidence/api_football/challenger/challenger_manifest.json`
- `evidence/api_football/challenger/final_holdout_adjudication.json`
- `evidence/api_football/market_governance/market_governance.json`
- `evidence/api_football/btts_challenger_v2/manifest.json`
- `evidence/api_football/btts_challenger_v2/exclusion_registry.json`
- `evidence/api_football/prospective_market_freeze/manifest.json`
- `evidence/api_football/prospective_market_freeze/freeze.json`
- `evidence/api_football/prospective_market_freeze/settlement_sync_last.json`
- `tools/api_football_prospective_market_freeze.py`
- `tools/api_football_prospective_api_settlement.py`

## F. Pinnacle / casas / RushBet
- `evidence/api_football/bookmakers/manifest.json`
- `evidence/api_football/pinnacle_coverage/manifest.json`
- `evidence/api_football/pinnacle_reference/manifest.json`
- `evidence/api_football/pinnacle_reference/pinnacle_reference_odds.jsonl`
- `evidence/audit/MATRIX_RUSHBET_SOURCE_SELECTION_20260928.md`
- `tools/odds_api_net_colombia_catalog_probe.py`
- `tests/test_odds_api_net_colombia_catalog_probe.py`

---

# 3. CORRECCIONES EXTERNAS — ESTADO ACTUAL

La auditoría externa global todavía NO está cerrada.

## RESUELTAS FÍSICAMENTE
- COR01
- COR04
- COR05
- COR06
- COR07
- COR08
- COR09
- COR10
- COR12

Total resueltas: **9/12**.

## ABIERTAS
- COR02
- COR03
- COR11

Total abiertas: **3/12**.

No declarar cierre global hasta que los criterios literales restantes estén satisfechos y exista evidencia física.

---

# 4. COR10 — YA RESUELTO, NO REABRIR SIN EVIDENCIA CONTRARIA

Archivos:
- `evidence/cor10/MATRIX_COR10_ADJUDICATION.json`
- `evidence/cor10/MATRIX_COR10_GENUINE_FUTURE_EXECUTION.json`
- `evidence/cor10/COR10_CLOSURE_MANIFEST.json`

Estado físico:
- `status = RESOLVED`
- `pass = true`
- execution_count = 1
- future_execution_count = 1
- future_execution_rate = 1.0

Ejecución:
- id: `COR10-FOOTBALL-1528902-OVER25-PINNACLE`
- fixture: Georgia vs Ukraine
- mercado: Over 2.5
- bookmaker: Pinnacle
- cuota decimal: 2.2
- stake nominal shadow: 1000 COP
- fondos transferidos: false
- freeze: 2026-09-28T10:02:50Z
- execution: 2026-09-28T10:17:34Z
- kickoff: 2026-09-28T16:00:00Z
- quote transport: API-Football /odds
- odds_used_to_generate_probability = false
- real_money = BLOCKED
- settlement al registrar: PENDING_FINAL

Cierre COR10 significa que la aceptación literal de evidencia futura fue satisfecha por una ejecución SHADOW genuina, NO que exista autorización de dinero real.

---

# 5. COR11 — SIGUE ABIERTO

Criterio:
cadencia documentada y respetada por >=14 días calendario reales consecutivos de Bogotá.

Estado físico reflejado en el status de 28-SEP:
- **8/14 días reales**
- fechas: 21–28 SEP 2026
- synthetic_days = false
- backfill = false
- closure_allowed_now = false

NO agregar días sintéticos.
NO backfill.
NO usar cambio de fecha UTC para inventar día Bogotá.
El updater es fail-closed.

Al reanudar, verificar si el ledger avanzó físicamente antes de repetir 8/14.

---

# 6. TENIS COR02/COR03 — ESTADO FÍSICO ACTUAL

Proveedor real:
`rapidapi_tennis`

Host:
`tennis-api-atp-wta-itf.p.rapidapi.com`

Plan físicamente usado:
**Ultra**.

Secret:
`RAPIDAPI_TENNIS_KEY`
Nunca mostrarlo ni pedirlo en chat.

## Holdout

`holdout_id = A22_POST_AUDIT_VIRGIN_HOLDOUT_V1`

Estado físico más reciente al handoff:
- **47/600 observaciones admisibles**
- Window 1: **47/200**
- restantes total: 553
- restantes Window 1: 153
- **47/47 PASS**
- failed_observations = 0
- metrics_opened = false
- outcomes_read = 0
- metrics = `SEALED_UNTIL_600`
- silent_imputation_detected = false
- integrity = PASS
- REAL_MONEY = BLOCKED

Binding:
`MATRIX_COR0203_MODEL_BINDING_R707_V1`

Modelos congelados:
- ELO: `R218_ELO_BOTH`
- Glicko: `R223_BATCH_GLICKO_RATING_BOTH`

NO cambiar estos modelos dentro del holdout.
NO backfill histórico al holdout.
NO abrir métricas antes del contrato de 600.
NO leer outcomes para performance antes del gate.
NO odds -> P.
Missing != 0.
No imputación silenciosa.
Freeze siempre antes del inicio del evento.

---

# 7. TENIS — MEJORAS DE IDENTIDAD R731/R732/R733/R734

El cuello R730 era identidad canónica.

## R730
17 eventos.
Con la autoridad nueva:
- 15 eventos PASS
- 2 eventos BLOCKED

Bloqueados:
1. `COR0203-RAPIDAPI-TENNIS-1471`
   - jugador bloqueante: `rapidapi-tennis:player:76126`
   - Keisuke Saitoh
2. `COR0203-RAPIDAPI-TENNIS-1466`
   - jugador bloqueante: `rapidapi-tennis:player:73055`
   - Alexandr Binda

Razón:
no existe en las fuentes actuales un ID canónico histórico pre-corte único suficiente para aprobar el crosswalk.
Aunque Ultra devuelve perfil biográfico exacto para ambos, NO forzar el join por nombre.
Además, sin historia gobernada ELO/Glicko no deben contaminar el holdout.

## R731
Se amplió autoridad con historia estrictamente pre-corte y biografía Sackmann.

## R732
Se creó colector Ultra por ID numérico exacto para seis perfiles bloqueados.
Protección:
solo identidad/biografía; ranking/puntos actuales competitivos se descartan.
Se persistió:
`MATRIX_COR0203_RAPIDAPI_PROFILE_IDENTITY_R732.json`

## R733
Cuatro identidades adicionales quedaron legítimamente resolubles mediante:
- provider ID exacto;
- perfil Ultra;
- ID histórico pre-corte único;
- IOC;
- DOB/hand.

## R734
Se corrigió el caso:
`Marat Sharipov (RUS)` proveedor
→ `Marat Sharipov` canónico

La unión está respaldada por:
- canonical source id `S0MN`
- 27 filas históricas pre-corte
- latest row 20260914
- país/hand coherentes.

NO generalizar esta corrección a un join por nombre. Solo está permitida cuando el archivo de autoridad contiene evidencia física equivalente.

Autoridad activa:
`MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R734`

---

# 8. TENIS — RESTAGING APPEND-ONLY YA SOLUCIONADO

Problema encontrado:
cuando R730 ya tenía staging físico, una mejora posterior del crosswalk devolvía `ALREADY_STAGED` y los eventos recién liberados no podían entrar.

Solución permanente:
`tools/cor0203_identity_restage_delta.py`

Regla:
- NO sobrescribir staging previo;
- crear una revisión delta append-only;
- preservar preregistro original;
- no seleccionar de nuevo por resultado/modelo;
- excluir duplicados ya congelados;
- permitir restage adicional únicamente si cambia una identidad canónica con evidencia.

Integración en:
`scripts/cor0203_production_cycle.sh`

Orden:
crosswalk → identity restage delta → reconstruir crosswalk del delta → staging → preflight → freeze.

## Delta R731
Eventos:
- 1415 Otto Virtanen vs Tiago Pereira
- 1469 Terence Atmane vs Enzo Aguiard
- 1475 Marat Sharipov/Mitsuki Wei Kang Leong

Resultado inicial:
- 2 freezes válidos
- 1475 bloqueado por diferencia de etiqueta `Marat Sharipov (RUS)` vs nombre histórico canónico.

## Delta R732
Después de R734:
- restage solo de 1475 por `CANONICAL_IDENTITY_MAPPING_CHANGED`
- 1 freeze válido
- holdout 46 → **47**

La corrección de conteo físico también quedó resuelta:
el restage usa el máximo `ending_observation_count` físico, no el número bruto de IDs contenidos en archivos quarantined.

---

# 9. TENIS — HORIZONTE ULTRA

Ventana gobernada actual:
**4 días**.

Prueba días 5–8:
workflow:
`COR02-03 Ultra days5-8 inventory probe`

Resultado físico:
- PASS técnico
- 3 network calls
- ranking players found = 900
- start = 2026-10-02
- stop = 2026-10-05
- fixture_rows = 0
- eligible_input_events = 0
- sin 429

Conclusión operativa:
NO promover a 8 días ahora porque la segunda ventana no aporta inventario y solo consume llamadas.
Mantener 4 días hasta que exista evidencia de utilidad.

---

# 10. TENIS — CI ACTUAL

Se corrigió el único fallo pendiente de tests:
tres tests nuevos llamaban `_load` sin definirlo.

Commit:
`02ed415ea37000bc3a53270257e280c9d5c47635`

Run:
`36424149666`

Resultado:
**3158 passed in 32.13s**
**MATRIX CI QUALITY GATE: PASS**

No declarar una futura cabeza verde sin volver a verificar CI.

---

# 11. FÚTBOL — CANONICAL INPUT ACTUAL

Archivo:
`evidence/api_football/canonical_analysis/manifest.json`

Estado:
- total_fixture_count = 83
- builder_output_count = 82
- ready_input_count = 81
- blocked_future_input_count = 1
- not_future_at_analysis_count = 1
- rejected_target_count = 2
- chunk_count = 11
- canonical bundle SHA:
  `7546f8f43228e6af9205e8db79a78a0a92993046a0e7a2c514be854eb485e76d`
- analysis_as_of source = RUNTIME_UTC_NOW
- baseline Poisson = EXPERIMENTAL_NOT_PROMOTED
- model_probability_generated = false
- P_MATRIX = NOT_GENERATED
- odds_used_to_generate_model_probability = false
- status = PASS
- REAL_MONEY = BLOCKED

La adjudicación física del engine registry concluyó:
- governed P_MATRIX engine available = false
- engine executable count = 0
- R315/R442/R316/R318/R320/R322 no están físicamente promovidos solo por existir identificadores.
- Poisson transparente es baseline experimental, no P_MATRIX.

---

# 12. FÚTBOL — RETROSPECTIVO, CHALLENGER V1 Y GOBIERNO POR MERCADO

Dataset retrospectivo:
- 2379 observaciones elegibles.
- split cronológico:
  - desarrollo 1665
  - validación 357
  - final holdout 357

Challenger V1:
`calibrated_log_pool_v1`

Final holdout:
- 1X2: challenger supera Poisson en Brier y log-loss → PASS de mercado.
- Over 2.5: challenger supera Poisson en Brier y log-loss → PASS de mercado.
- BTTS: challenger NO supera Poisson → FAIL de mercado.
- overall all-three = FAIL.

NO usar el FAIL global para borrar los mercados que sí pasaron.
NO usar los mercados aprobados como P_MATRIX todavía.

Market governance:
- approved_markets = [`1x2`, `over_2_5`]
- rejected_markets = [`btts`]
- estado de 1X2/Over = `MARKET_CHALLENGER_FROZEN_APPROVED_FOR_NEXT_GATES`
- engine_executable_for_p_matrix = false
- governed_engine_promoted = false
- REAL_MONEY = BLOCKED

---

# 13. FÚTBOL — BTTS V2

BTTS V1 quedó rechazado.

Se creó:
`btts_logistic_challenger_v2`

Estado:
`FROZEN_BTTS_V2_AWAITING_NEW_PROSPECTIVE_HOLDOUT`

Desarrollo:
1665

Validación:
357

Validación BTTS V2:
- Brier = 0.243321891055229
- log-loss = 0.67971084225647
- Poisson Brier = 0.24374956213603283
- Poisson log-loss = 0.681131970166502
- validation_superiority = true

Protección crítica:
los 357 del final holdout original están PERMANENTEMENTE EXCLUIDOS del desarrollo/validación/tuning de BTTS V2.

Exclusion registry:
- forbidden_fixture_count = 357
- overlap training-validation = 0
- source holdout seal:
  `b9a84e388c0cf2eec0b74705d04a0a8ba7321867754257bc5465ba436543eccf`

NO volver a usar esos 357 outcomes para “validar” BTTS V2.

---

# 14. FÚTBOL — FREEZE PROSPECTIVO REAL

Archivo:
`evidence/api_football/prospective_market_freeze/manifest.json`

Primer freeze prospectivo genuino:
- created_at = 2026-09-28T10:02:50Z
- frozen_event_count = **67**
- excluded_event_count = 14
- historical_seen_fixture_count = 2379
- original holdout forbidden count = 357
- freeze SHA:
  `692bf57783664baffe2b9fb3af8cc85153557ee7086a8e09fc870e292e95abe3`

Protecciones:
- future_only = true
- unseen_events_only = true
- freeze_strictly_before_kickoff = true
- original 357 excluded = true
- missing feature imputation = false
- outcomes read at freeze = false
- settlement FINAL-only = true
- odds_used_to_generate_probability = false
- p_matrix_generated = false
- automatic_wagering = false
- real_money = BLOCKED

Mercados congelados:
- 1X2 challenger aprobado
- Over 2.5 challenger aprobado
- BTTS V2 congelado de investigación

Esto NO equivale a P_MATRIX ni a autorización de apuesta.

---

# 15. FÚTBOL — SETTLEMENT FINAL-ONLY

Herramienta principal:
`tools/api_football_prospective_api_settlement.py`

Política:
- consultar por fixture ID exacto;
- validar identidad home/away;
- ejecutar lookup solo tras kickoff + 120 minutos;
- autoaceptar solo `FT`;
- AET/PEN/PST/CANC/ABD/AWD/WO/SUSP/INT quedan bloqueados para adjudicación;
- score full-time obligatorio;
- derive outcome 1X2 / Over2.5 / BTTS;
- metrics_opened = false;
- used_for_metrics = false;
- P_MATRIX = NOT_GENERATED;
- REAL_MONEY = BLOCKED.

Último sync físico leído al crear el handoff:
- run_at = 2026-09-28T10:03:42Z
- frozen = 67
- ledger_final_count = 0
- new settlements = 0
- pending = 67
- network_calls = 0
- metrics_opened = false
- settlement_final_only = true
- status = PASS

Este sync puede quedar obsoleto por cron. RECONSULTAR antes de afirmar el conteo actual.

No abrir métricas prospectivas sin preregistro explícito del gate correspondiente.
No reentrenar y luego llamar “unseen” a los mismos outcomes.

---

# 16. PINNACLE

Pinnacle está físicamente disponible como referencia mediante API-Football, NO mediante una conexión directa oficial Pinnacle.

Bookmaker id:
**4**

Cobertura auditada anterior:
- 47/83 fixtures con referencia Pinnacle
- 17 mercados
- 4021 reference quotes
- quote_role = REFERENCE
- probability_source = MODEL_ONLY
- odds_used_to_generate_model_probability = false

Pinnacle sirve para:
- precio de referencia;
- vig/overround;
- dispersión;
- closing line value;
- evaluación de edge contra modelo.

Pinnacle NO genera P_MODEL/P_MATRIX.

---

# 17. RUSHBET / BETPLAY / BETANO / BWIN

RushBet NO aparece en el catálogo de bookmakers de API-Football.

Ruta candidata:
`odds-api.net`

Código preparado:
- `tools/odds_api_net_colombia_catalog_probe.py`
- `tests/test_odds_api_net_colombia_catalog_probe.py`

Workflow en main:
`.github/workflows/odds-api-net-colombia-catalog.yml`

Estado actual a este handoff:
**PREACTIVATION / CREDENTIAL_REQUIRED / NOT VERIFIED USED**

Secret esperado:
`ODDS_API_NET_KEY`

Nunca pedir al usuario que pegue la key en el chat.

Solo declarar RushBet VERIFIED_USED después de:
1. credencial instalada como secret;
2. workflow físico ejecutado;
3. `rushbet_present=true`;
4. RAW/SHA/rate metadata persistida.

No afirmar que RushBet está conectada antes de eso.

---

# 18. REGLAS METODOLÓGICAS PERMANENTES

- Evidencia cuantitativa obligatoria.
- Sin evidencia suficiente → NO BET.
- Tenis y fútbol son matrices separadas.
- No mezclar modelos, variables, ledgers ni calibración entre deportes.
- Missing != 0.
- Prohibida imputación silenciosa.
- Edad faltante no bloquea por sí sola, pero se registra.
- No odds -> P_MODEL/P_MATRIX.
- Freeze inmutable.
- Settlement FINAL-only.
- PIT/anti-leakage obligatorio.
- Identidad exacta y gobernada.
- No joins silenciosos por nombre.
- No backfill histórico a un holdout prospectivo.
- No abrir métricas antes de su gate.
- No refit usando el holdout que luego se pretende evaluar.
- Persistencia transaccional / append-only.
- Comparar precio entre casas solo con evidencia válida.
- Umbral de cuota general vigente >1.50 cuando eventualmente se evalúe ejecución; esto NO desbloquea dinero real.
- Prioridad a simples; combinadas excepcionales.
- Mínimo 3 mercados por partido como regla de análisis cuando aplique, sin usar esa regla para fabricar señal.
- REAL_MONEY permanece BLOQUEADO.

---

# 19. REGLA DE OPERACIÓN Y RESPONSABILIDAD DEL ASISTENTE

El asistente debe hacer por su cuenta todo lo que las herramientas permitan:
- auditoría;
- investigación;
- GitHub;
- lectura de archivos;
- código;
- tests;
- workflows;
- logs;
- validación;
- persistencia;
- comparación;
- diagnóstico.

El usuario solo interviene si es estrictamente necesario:
- pago/suscripción;
- secret/API key;
- clic manual no disponible por herramienta;
- autorización explícita.

Si el usuario debe actuar en PC/UI:
dar UN SOLO PASO por turno y esperar captura antes del siguiente.

No pedir al usuario que repita información ya disponible físicamente.

---

# 20. DISCIPLINA DE CONTINUIDAD Y ANTI-ESTANCAMIENTO

Las reglas anteriores de throughput, doble carril y anti-estancamiento siguen vigentes SIEMPRE que no contradigan la suspensión/gobierno de auditoría y los gates físicos.

Mantener dos carriles:
1. WORLD_DISCOVERY / inventario real.
2. CALIBRATION_CONVERSION / conversión PIT→freeze.

No detener un deporte porque el otro esté bloqueado.
No repetir tres ciclos cero sin análisis de causa raíz.
No inflar volumen bajando gates.
No llamar éxito a “partidos procesados” si no convierten a observaciones prospectivas gobernadas.

---

# 21. PRÓXIMOS PASOS EXACTOS EN LA NUEVA CONVERSACIÓN

1. Verificar físicamente heads actuales de `repair/cor09-world-pipeline` y `main`.
2. Verificar MATRIX CI de la cabeza operativa.
3. Leer el handoff actual y los archivos de la sección 2.
4. Reconsultar:
   - tenis holdout actual;
   - COR11;
   - football settlement sync;
   - cualquier scheduler ejecutado después de este handoff.
5. Tenis:
   - continuar 47→600 prospectivamente;
   - mantener métricas selladas;
   - mantener ventana 4 días;
   - NO forzar Saitoh/Binda sin nueva evidencia canónica pre-corte e historia gobernada.
6. Fútbol:
   - conservar los 67 freezes inmutables;
   - settlement FINAL-only;
   - no abrir métricas anticipadamente;
   - diseñar/preregistrar cualquier gate prospectivo antes de usar outcomes;
   - si se requiere >67, crear acumulación append-only de nuevos freezes futuros sin tocar los existentes.
7. 1X2 y Over2.5:
   - congelados y aprobados solo para próximos gates;
   - NO P_MATRIX todavía.
8. BTTS V2:
   - congelado;
   - usar solo eventos prospectivos nuevos;
   - 357 antiguos permanentemente prohibidos.
9. COR11:
   - seguir solo con días reales consecutivos.
10. RushBet:
   - seguir PREACTIVATION hasta evidencia real.
11. Mantener real money bloqueado.
12. No esperar que el usuario diga “sigue” para ejecutar los pasos técnicos que las herramientas permitan dentro de este alcance.

---

# 22. CONDICIÓN DE REANUDACIÓN

La primera acción de la nueva conversación debe ser equivalente a:

**“Voy a verificar primero la cabeza física del repositorio, MATRIX CI y los estados runtime actuales. No asumiré que los números de este handoff siguen siendo los últimos si existe evidencia posterior.”**

Después continuar desde la evidencia física más reciente SIN empezar de cero y SIN perder ninguna mejora persistida.

Este archivo es un delta acumulativo sobre los handoffs anteriores. No elimina reglas anteriores salvo donde la evidencia física posterior las haya reemplazado explícitamente.
