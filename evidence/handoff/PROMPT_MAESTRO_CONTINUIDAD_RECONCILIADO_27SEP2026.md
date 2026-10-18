# PROMPT MAESTRO DE CONTINUIDAD TOTAL — MATRIX-LAB-SPORTS
## POST-AUDITORÍA DE RECONCILIACIÓN TOTAL + BASELINE RECONCILIADO + RESTAURACIÓN DE FUENTE TENIS

### Fecha de empaquetado
27-SEP-2026 — America/Bogota

### Idioma obligatorio
ESPAÑOL.

### Proyecto
MATRIX-LAB-SPORTS.

### Regla suprema
Quiero que continúes mi proyecto privado MATRIX-LAB-SPORTS EXACTAMENTE desde el último estado física y canónicamente existente.

NO empieces desde cero.
NO reconstruyas por memoria nada que exista físicamente.
NO inventes avances, probabilidades, freezes, eventos, identidades, resultados, cuotas, credenciales, APIs activas, conexiones, settlements, runs, commits ni pruebas.
NO trates código existente como prueba de integración activa.
NO trates una credencial como prueba de uso exitoso.
NO trates un CI verde como prueba de que una fuente externa fue realmente usada.
NO trates mocks, fixtures, payloads de ejemplo, replay offline, shadow runtime ni capturas de navegador como prueba de uso real de una API.
NO abras métricas COR02/COR03 antes de n=600.
NO odds→P_MATRIX.
NO imputación silenciosa.
NO Missing=0.
NO cambies probabilidades/freezes/timestamps persistidos.
NO backfill retrospectivo para fabricar observaciones prospectivas.
NO uses resultados LIVE como características prematch.
NO settlement antes de FINAL.
REAL_MONEY permanece BLOCKED.

==================================================
0. AUTORIDAD Y ORDEN DE LECTURA OBLIGATORIO
==================================================

ANTES DE HACER CUALQUIER OTRA COSA:

1. Ve físicamente al repositorio:
   repo = MatrixLabSports/MATRIX-LAB
   rama operativa = repair/cor09-world-pipeline

2. Obtén el HEAD físico actual de esa rama.
   HEAD verificado al empaquetar este handoff:
   5c0afc744a400ff6640d03f626304a4cb10e6aa9

   Mensaje:
   audit: bind tennis source restoration to real provider evidence

   CI verificado para ese HEAD:
   - push MATRIX CI run 36288385528 = completed / success
   - pull_request MATRIX CI run 36288388111 = completed / success

3. Si existe un HEAD posterior, NO asumas que manda automáticamente.
   Primero verifica que respeta:
   - MATRIX_RECONCILED_BASELINE_SUPREMACY_V1
   - MATRIX_TRUTHFULNESS_AND_PHYSICAL_EVIDENCE_CONSTITUTION_V1
   - MATRIX_API_USAGE_CLAIM_GATE_V1
   - todas las reglas activas y el baseline reconciliado.
   Un commit posterior que contradiga evidencia física no puede degradar la verdad reconciliada.

4. Lee COMPLETOS, en este orden:

   A. Autoridad reconciliada:
   - docs/governance/MATRIX_RECONCILED_BASELINE_SUPREMACY_V1.md
   - evidence/audit/MATRIX_TOTAL_RECONCILIATION_AUDIT_20260926.md
   - evidence/audit/MATRIX_RECONCILED_TRUTH_STATE_20260926.json

   B. Veracidad y uso de APIs:
   - docs/governance/MATRIX_TRUTHFULNESS_AND_PHYSICAL_EVIDENCE_CONSTITUTION_V1.md
   - evidence/audit/MATRIX_API_USAGE_CLAIM_GATE_V1.md
   - evidence/audit/MATRIX_EXTERNAL_API_INVENTORY_PHYSICAL_USAGE_AUDIT_V1.md
   - evidence/audit/MATRIX_API_FOOTBALL_REAL_USAGE_AUDIT_20260926.md

   C. Integración y remediación:
   - evidence/audit/MATRIX_INTEGRATION_AUTOMATION_AUDIT_20260925.md
   - evidence/audit/MATRIX_INTEGRATION_REMEDIATION_STEP4_20260926.md
   - evidence/audit/MATRIX_INTEGRATION_REMEDIATION_STEP6_20260926.md
   - evidence/audit/MATRIX_INTEGRATION_REMEDIATION_STEP7_20260926.md
   - evidence/audit/MATRIX_INTEGRATION_REMEDIATION_STEP8_20260926.md
   - evidence/audit/MATRIX_INTEGRATION_REMEDIATION_STEP9_20260926.md
   - evidence/audit/MATRIX_INTEGRATION_REMEDIATION_STEP10_20260926.md

   D. Restauración de fuente tenis:
   - evidence/audit/MATRIX_TENNIS_SOURCE_RESTORATION_PREACTIVATION_20260926.md
   - evidence/audit/MATRIX_TENNIS_SOURCE_RESTORATION_DECISION_V1.md

   E. Runtime actual:
   - evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json
   - evidence/cor0203/runtime/MATRIX_COR0203_PRODUCTION_OBSERVABILITY_LAST.json
   - evidence/cor0203/runtime/MATRIX_COR0203_DURABLE_DISCOVERY_LAST.json
   - evidence/cor0203/runtime/MATRIX_COR0203_BATCH_RUNNER_LAST.json
   - evidence/cor0203/runtime/MATRIX_COR0203_SETTLEMENT_QUEUE_LAST.json
   - evidence/cor0203/runtime/MATRIX_COR0203_SETTLEMENT_SYNC_LAST.json
   - evidence/cor0203/runtime/MATRIX_COR0203_HISTORICAL_IDENTITY_LAST.json

5. Lee también los archivos originales de auditoría externa suministrados en el handoff:
   - MATRIX_AUDITORIA_EXTERNA_CORRECCIONES_21SEP2026.xlsx
   - MATRIX_RESUMEN_MAESTRO_HASTA_R657_21SEP2026.xlsx
   El Excel de correcciones y sus hojas CORRECCIONES_REQUERIDAS / CRITERIOS_GO_NOGO gobiernan literalmente cuando correspondan.

6. Cualquier resumen, prompt, memoria o afirmación anterior que contradiga el baseline reconciliado queda SUPERSEDIDA.
   LA EVIDENCIA FÍSICA MANDA.

==================================================
1. ESTADO REAL RECONCILIADO — NO ALTERAR SIN EVIDENCIA NUEVA
==================================================

PROYECTO:
- estado = RESEARCH_VALIDATION_NOT_PRODUCTION_READY
- external audit = NOT_CLOSED
- real money = BLOCKED
- ordinary sports production = PAUSED_EXCEPT_GOVERNED_AUDIT_VALIDATION

TENIS COR02/COR03:
- lane = ATP_CHALLENGER_HARD_COR0203
- holdout_id = A22_POST_AUDIT_VIRGIN_HOLDOUT_V1
- Window 1 = 10/200
- total = 10/600
- integrity = 10 PASS / 0 FAIL
- metrics = SEALED_UNTIL_600
- outcomes read for performance = 0
- settlement ledger records = 0
- provider identity pending = 10
- ready_result_lookup = 0
- real money = BLOCKED

MODELOS SELLADOS:
- R218_ELO_BOTH
- R223_BATCH_GLICKO_RATING_BOTH
No tuning dentro del holdout.
No cambio de binding después de la primera observación admisible.

FUENTE TENIS ACTUAL:
API-Tennis:
- NOT_CONNECTED / SOURCE_BLOCKED
- API_TENNIS_KEY_NOT_CONFIGURED
- verified MATRIX provider network calls = 0
- usuario verificó en su panel de API-Tennis 0 llamadas durante los días de su prueba
- plan de API-Tennis actualmente inactivo según evidencia del usuario
- NO afirmar que API-Tennis fue usada

CANDIDATO ALTERNATIVO PREPARADO:
RapidAPI provider key = rapidapi_tennis
Producto = Tennis API - ATP WTA ITF
Host = tennis-api-atp-wta-itf.p.rapidapi.com

Estado:
- código/adaptadores/workflow selector preparados
- pruebas CI PASS
- RAPIDAPI_TENNIS_USED = FALSE
- VERIFIED_NETWORK_CALLS = 0
- SOURCE_RESTORED = FALSE
- requiere suscripción/credencial válida y prueba física real
- no pegar ninguna API key en el chat
- no guardar secretos en el repo

RapidAPI solo puede pasar a VERIFIED_USED si TODOS son físicos:
1. suscripción válida para el producto exacto;
2. RAPIDAPI_TENNIS_KEY guardada como GitHub Secret;
3. provider explícitamente seleccionado como rapidapi_tennis;
4. workflow gobernado con network_calls > 0;
5. respuesta RAW real persistida;
6. SHA-256/provenance persistidos;
7. checkpoint enlaza request con evidencia;
8. source readiness = READY;
9. al menos un evento futuro ATP Challenger Hard descubierto con IDs reales;
10. no leakage.

ATP WEBSITE:
No convertir ATP oficial en scraper productivo sin permiso documentado.
La decisión física vigente rechaza el scraping sistemático ATP como fuente productiva por rights gate.
Capturas HAR históricas no equivalen a autorización de scraping.

==================================================
2. VERDAD ACTUAL DE APIs / FUENTES
==================================================

API-Tennis:
- NOT_CONNECTED
- 0 verified real calls

API-Football / API-Sports:
- SHADOW_OR_OFFLINE_ONLY / NOT_CONNECTED_FOR_REAL_PROVIDER_EXECUTION
- 0 verified real provider calls por MATRIX
- no workflow productivo actual inyecta API_FOOTBALL_KEY
- shadow runtime registra network_call_performed=false
- real_provider_execution_authorized=false
- la captura real de fútbol verificada fue UEFA web HTTP, NO API-Football

Sportradar:
- NOT_CONNECTED
- 0 verified provider calls found

The Odds API:
- NOT_CONNECTED
- 0 verified provider calls found

UEFA official web HTTP:
- VERIFIED_USED como fuente web
- NO confundir con API

REGLA:
Nunca afirmar “se está usando una API” sin:
credential/config OK + network_calls>0 + RAW persistido + provenance/hash + checkpoint + run/window trazable.

==================================================
3. FÚTBOL — ESTADO REAL
==================================================

Ordinary football production = PAUSED.

Motores:
- R315 Serie A = REPRODUCTION_PARITY_FAIL
- R316 Premier = REPRODUCTION_PARITY_FAIL
- R318 Bundesliga = DOMAIN_COVERAGE_BLOCKED
- R320 Ligue 1 = DOMAIN_COVERAGE_BLOCKED
- R322 Eredivisie = DOMAIN_COVERAGE_BLOCKED
- R442 LaLiga = DOCUMENTED_NOT_EXECUTABLE

No presentar fútbol como lane productivo activo.
No reanudar por intuición.
Reactivación futura requiere programa separado de motor + fuente + PIT + paridad + end-to-end.

==================================================
4. COR01-COR12 — ESTADO RECONCILIADO
==================================================

COR01 = VERIFIED_RESOLVED
COR02 = IN_PROGRESS
COR03 = IN_PROGRESS
COR04 = VERIFIED_RESOLVED
COR05 = VERIFIED_RESOLVED
COR06 = VERIFIED_RESOLVED_LITERAL_SOURCE_EVIDENCE
COR07 = VERIFIED_RESOLVED_BY_FORMAL_PAUSE
COR08 = VERIFIED_RESOLVED_HISTORICAL_THROUGHPUT
COR09 = VERIFIED_RESOLVED_LITERAL_ONE_CYCLE
COR10 = IN_PROGRESS
COR11 = IN_PROGRESS
COR12 = RESOLVED_AS_GOVERNANCE_DEFECT

External audit = NOT_CLOSED.

COR11:
último ledger reconciliado en la auditoría total = 5/14 (21-25 SEP).
NO aumentar el contador por memoria ni por paso del calendario.
Solo avanzar con evidencia física diaria conforme.

GO/NO-GO:
4/8 YES físicamente soportables.

YES:
1. historical age validity >=99%
2. clean holdout
3. literal verified source-evidence condition
4. historical throughput criterion >=100/h

NO/PENDING:
5. BSS >=3% sustained
6. temporal stability
7. rank-band stability
8. stable freeze yield >=3 cycles

REAL_MONEY = BLOCKED hasta 8/8 + autorización humana explícita.

==================================================
5. HISTÓRICO VÁLIDO — CÓMO INTERPRETARLO
==================================================

31/31 settlement histórico:
- REAL
- físicamente settlementado
- CALIBRATION_RESEARCH_ONLY
- football n=23
- tennis n=8
- NO prueba calibración actual
- NO satisface COR02/COR03

C20:
- REAL
- 23 freezes prospectivos / muestra pequeña
- diagnóstico histórico
- NO equivalente al holdout virgen post-auditoría

Auditoría 21-SEP:
- 230 eventos analizados
- 1 P_MATRIX propia
- 1 freeze
- 0 calibraciones FINAL completas en periodo A22 auditado
- global freeze yield 0.43%
- 0/6 motores fútbol operativos
- old holdout contaminado
- real money blocked

NO usar volumen de discovery/revisiones como sustituto de observaciones calibrables.

==================================================
6. MEJORAS / REMEDIACIONES QUE NO SE PUEDEN PERDER
==================================================

INTEGRATION REMEDIATION STEP 1 — HECHO:
- batch serializado;
- concurrency;
- cancel-in-progress false;
- partición por evento;
- exact trigger SHA;
- stale-count rebase;
- regression tests.

STEP 2A — HECHO:
- strong identity crosswalk dentro de producción;
- prereregister -> crosswalk -> staging.

STEP 2B — HECHO:
- scheduler repo-native en main;
- ejecuta ciclo productivo compartido;
- no depender de ChatGPT como productor principal.

STEP 3 — HECHO:
- scripts/cor0203_production_cycle.sh;
- scheduler y workflow usan ciclo compartido;
- ChatGPT COR02/03 producer automation deshabilitada para evitar productor duplicado.

STEP 4 — HECHO:
- auditoría missingness/fallback del holdout;
- 10/10 PASS;
- silent imputation = false;
- median/neutral fallback no admisible.

STEP 5 — BLOQUEO EXTERNO IDENTIFICADO:
- API-Tennis sin credencial activa/configurada;
- provider calls = 0;
- plan del usuario inactivo;
- no pagar/activar proveedor sin evaluar conscientemente.

STEP 6 — HECHO:
- observabilidad productiva determinista;
- distingue SOURCE_BLOCKED de IDLE válido.

STEP 7 — HECHO INFRAESTRUCTURA:
- settlement FINAL-only;
- hash chain;
- queue/sync;
- métricas permanecen selladas.

STEP 8 — HECHO:
- historical provider identity reconciliation exacta;
- no fuzzy match;
- append-only overlay.

STEP 9 — HECHO:
- durable discovery;
- governed acquisition queue + worker + SQLite persistence;
- checkpoint/idempotencia por hora;
- recuperación sin refetch.

STEP 10 — HECHO:
- observation count físico/transaccional;
- rebase de starting count;
- duplicados bloqueados;
- concurrency protegida.

STEP 11 — NO HECHO:
- durable per-event state machine sigue pendiente.
NO afirmar que existe.

==================================================
7. AUTOMATIZACIÓN Y RAMAS
==================================================

Repo:
MatrixLabSports/MATRIX-LAB

Default branch:
main

Rama operativa:
repair/cor09-world-pipeline

PR #1:
- open
- draft = true
- head = repair/cor09-world-pipeline
- base = integration/c2-private-live-foundation
- NO está promovida/mergeada a main

Scheduler repo-native:
- existe
- arquitectura real
- pero source restore sigue pendiente

ChatGPT:
- COR02/03 producer automation está deshabilitada
- no reactivar productor duplicado
- COR10/COR11 audit automation puede permanecer separada según estado físico

==================================================
8. REGLAS OPERATIVAS PERMANENTES
==================================================

- evidencia física > memoria/chat/resumen;
- toda instrucción nueva = ADD salvo REEMPLAZA/MODIFICA/DEROGA/SUSPENDE/ELIMINA explícito;
- PIT obligatorio;
- anti-leakage obligatorio;
- identidad correcta y corroborada;
- Missing != 0;
- no imputación silenciosa;
- no datos inventados;
- no odds->P_MATRIX;
- freezes/probabilidades/timestamps inmutables;
- no backfill retrospectivo;
- FINAL-only;
- append-only donde aplique;
- provenance + SHA-256;
- fallar cerrado;
- un evento malo no debe abortar los válidos;
- registrar -> saltar -> continuar;
- métricas COR02/COR03 selladas hasta 600;
- no tuning retrospectivo;
- no real money;
- no presentar “analizados” como éxito principal.

Vocabulario obligatorio cuando no hay evidencia:
VERIFIED / UNVERIFIED / UNKNOWN / BLOCKED / NOT_CONNECTED / NOT_EXECUTED / EVIDENCE_INSUFFICIENT.

Prohibido decir:
“hecho”, “resuelto”, “conectado”, “usado”, “PASS”, “activo”, “automatizado” o equivalente sin evidencia física terminal.

==================================================
9. ORDEN DE TRABAJO OBLIGATORIO DESDE ESTE HANDOFF
==================================================

P0 — PRIMERO:
Restaurar UNA fuente real, legal/autorizada, verificable y gobernada para tenis.

NO continuar acumulando narrativa de producción mientras source_status siga BLOCKED.

Ruta preferente preparada:
rapidapi_tennis, SOLO si el usuario decide activar/suscribir ese proveedor y agrega el secreto directamente en GitHub.
No pedir que pegue la clave en el chat.

Una fuente solo queda restaurada después de:
- network_calls > 0;
- HTTP/provider success real;
- raw response persistida;
- SHA/provenance;
- checkpoint;
- provider identity;
- source readiness READY;
- al menos un evento futuro elegible descubierto sin fabricación manual.

P0 — DESPUÉS:
Implementar STEP11 durable per-event state machine:
DISCOVERED
IDENTITY_FIXED
PREREGISTERED
ACQUISITION_PENDING
FEATURES_READY
MODEL_READY
FROZEN
FINAL_PENDING
SETTLED
CALIBRATION_ELIGIBLE
BLOCKED
Cada transición append-only/idempotente.

P0/P1:
Reconciliar COR11 desde el ledger físico, sin inventar días.

P1:
Con fuente real activa:
- reconciliar provider match keys de las 10 observaciones históricas;
- FINAL settlement solo cuando corresponda;
- outcomes_used_for_metrics sigue 0 hasta n=600;
- continuar observaciones 11..600 prospectivamente.

P1:
Promover arquitectura reparada por revisión/merge cuando esté demostrada, no dejar producción permanentemente en repair branch.

P2:
Retirar workflows legacy/stale solo después de migration proof.

==================================================
10. POLÍTICA DE REPORTE AL USUARIO
==================================================

Cada reporte operativo debe incluir, como mínimo:
- HEAD/commit usado;
- CI terminal;
- source provider;
- source status;
- verified network calls;
- raw evidence sí/no;
- Window 1 /200;
- total /600;
- nuevos freezes válidos;
- nuevos blocked + causa exacta;
- settlements;
- metrics SEALED/OPEN;
- COR02/COR03/COR10/COR11;
- GO/NO-GO;
- REAL_MONEY;
- blockers exactos.

No ocultar cero progreso.
No convertir código en ejecución.
No convertir preparación en conectividad.
No convertir provider candidate en provider active.
No convertir una credencial en una llamada.
No convertir CI PASS en uso de API.

==================================================
11. MANDATO DE CONTINUIDAD
==================================================

No pierdas ninguna mejora válida ya hecha.
No deshagas gates de integridad para ganar volumen.
No retrocedas a una narrativa pre-reconciliación.
No uses prompts históricos para sobreescribir la verdad física actual.

Desde este punto:
MATRIX_TOTAL_RECONCILIATION_AUDIT_20260926
+
MATRIX_RECONCILED_TRUTH_STATE_20260926
+
MATRIX_RECONCILED_BASELINE_SUPREMACY_V1
+
los deltas físicos posteriores verificados
constituyen el baseline de continuidad.

Primero verifica.
Después actúa.
Después persiste.
Después prueba.
Solo entonces reporta como hecho.
