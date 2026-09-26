# AUDITORÍA PRINCIPAL DE INTEGRACIÓN, AUTOMATIZACIÓN Y CONFIABILIDAD
## MATRIX-LAB-SPORTS — 25-SEP-2026

### Alcance
Auditoría histórica y actual de MATRIX TENIS y MATRIX FÚTBOL desde el arranque del proyecto hasta el estado físico actual del repositorio `MatrixLabSports/MATRIX-LAB`, branch `repair/cor09-world-pipeline`.

Objetivo: determinar, sin inferencias no demostradas, qué piezas existen, cuáles están realmente conectadas, cuáles dependen de intervención externa/manual, y qué explica el bajo volumen de observaciones prospectivas calibrables.

### Estado físico auditado
- Repo: MatrixLabSports/MATRIX-LAB
- Default branch: main
- Rama operativa actual: repair/cor09-world-pipeline
- PR #1: draft, head repair/cor09-world-pipeline -> base integration/c2-private-live-foundation
- Head al inicio de esta auditoría: 77c8f29cc857e96fa29e692171aa047c0ff6649d
- COR02/COR03 holdout: 9/200 Window 1; 9/600 total
- Métricas: SEALED_UNTIL_600
- REAL_MONEY: BLOCKED
- Football ordinary production: PAUSED by governance

---

# 1. VEREDICTO

El principal cuello actual NO es la ausencia de modelos, pruebas o componentes aislados.

El cuello principal es que la arquitectura de producción NO está cerrada de extremo a extremo.

La ruta real que hoy produce COR02/COR03 es:

fuente/web/automatización externa
-> creación física manual/externa de PREFEATURE
-> creación física manual/externa de STATIC4
-> creación física manual/externa de PROSPECTIVE_EVENTS
-> push a GitHub
-> cor0203-batch-freeze.yml
-> tools/cor0203_prospective_producer.py
-> holdout persistido

Los siguientes componentes existen en el repositorio pero NO están referenciados por ningún workflow de producción actual:
- app/research/tennis/world_calendar_registry.py
- app/core/governed_acquisition_queue.py
- app/core/acquisition_worker.py
- app/core/pipeline_engine.py
- app/research/tennis/r251_world_pipeline.py
- app/application/football/repeatable_live_ingestion.py
- app/core/settlement_rules.py

Por tanto, hay arquitectura implementada y probada que no gobierna la ruta viva.

---

# 2. HALLAZGOS CRÍTICOS P0

## P0-01 — No existe scheduler/orquestador repo-native de producción continua
Workflows actuales:
- cor0203-batch-freeze.yml
- cor0203-preholdout-snapshot.yml
- cor0203-prospective-freeze.yml
- cor06-archive-raw-body.yml
- cor06-football-exact-capture.yml
- matrix-ci.yml

Ninguno contiene `schedule:`.
Ninguno contiene `repository_dispatch:`.

La producción COR02/COR03 depende de que alguien/otro sistema escriba primero un manifest de eventos prospectivos.

Conclusión: GitHub Actions NO descubre eventos por sí solo.

## P0-02 — Descubrimiento mundial desconectado del freeze
`world_calendar_registry.py` puede validar calendario mundial y elegibilidad COR02/COR03, pero ningún workflow lo invoca.

`r251_world_pipeline.py` puede prerregistrar y validar BASE12, pero ningún workflow lo invoca.

La ruta viva actual bypassa ambos.

Conclusión: WORLD_DISCOVERY y CALIBRATION_CONVERSION existen conceptualmente, pero no están unidos por un proceso productivo único.

## P0-03 — Cola y worker de adquisición existen pero no están conectados a producción
`governed_acquisition_queue.py` construye una cola gobernada.
`acquisition_worker.py` ejecuta colas, soporta checkpoints, raw evidence, budgets e idempotencia.
Existen tests con SQLite durable y recuperación después de crash.

Pero ningún workflow de producción actual los invoca.

Conclusión: la infraestructura de adquisición robusta está disponible pero no está en el camino real COR02/COR03.

## P0-04 — Automatizaciones externas están funcionando como orquestador sustituto
La automatización COR02/COR03 actual realiza discovery, decide cuándo escribir artefactos y usa herramientas externas para persistir.

R717 demostró que existía una automatización activa obsoleta anclada en R666 mientras el proyecto estaba mucho más adelante.

R722 demostró un fallo actual:
- PREFEATURE quedó físicamente persistido.
- el paso siguiente STATIC4 no pudo escribirse.
- blocker físico: REPOSITORY_WRITE_BLOCKED_BY_TOOL_SAFETY_CHECK.
- holdout permaneció 9/600.

Conclusión: el sistema puede quedar a mitad de evento porque la orquestación crítica vive fuera del runtime del repositorio.

## P0-05 — El batch actual no es seguro para alta concurrencia
`cor0203-batch-freeze.yml`:
- hace checkout explícito de la rama, no del SHA exacto que disparó el job;
- busca el manifest con revisión máxima presente en la rama;
- no declara `concurrency:` ni lock;
- escribe y hace push a la misma rama;
- usa `starting_observation_count` declarado en el manifest.

Riesgo demostrado por diseño:
si entran varios manifests cercanos, un job puede procesar un head más nuevo que el commit que lo disparó.
Dos lotes con el mismo starting count pueden competir.
El segundo puede fallar con HOLDOUT_COUNT_DRIFT o push conflict.

Conclusión: la arquitectura actual no soporta de forma robusta el objetivo de alto volumen concurrente.

## P0-06 — Fallo de un evento puede abortar el lote completo
En `cor0203-batch-freeze.yml`, el history gate hace `raise ValueError` cuando un jugador carece de historial/ELO/Glicko.
El productor también aborta ante un evento post-start o fuera de dominio.

No hay partición automática:
VALIDOS -> continuar
BLOQUEADOS -> persistir blocker

Esto contradice la disciplina operativa REGISTRAR -> SALTAR -> CONTINUAR para producción masiva.

Conclusión: un solo evento malo puede reducir el throughput de todos los válidos del mismo lote.

## P0-07 — No hay retry/dead-letter nativo en el flujo COR02/COR03
El worker genérico sí tiene mecanismos de recuperación/checkpoints.
El workflow COR02/COR03 no los usa.

No se encontró:
- dead-letter queue;
- retry por evento;
- recuperación automática de batch parcialmente válido;
- rebase automático de starting count.

Conclusión: los fallos quedan para intervención externa.

## P0-08 — Settlement y calibración final no están conectados al pipeline vivo
`settlement_rules.py` existe.
Ningún workflow actual lo referencia.

Tampoco existe workflow que:
- detecte FINAL para los freezes COR02/COR03;
- persista outcome después del evento;
- abra métricas solo al alcanzar 600;
- ejecute automáticamente las tres ventanas y bandas de ranking.

Conclusión: incluso llegando a 600, el cierre completo todavía necesita integración adicional.

## P0-09 — Identidad fuerte existe en diseño pero la ruta viva acepta nombres
`world_calendar_registry.py` exige player IDs reales.
`r251_world_pipeline.py` está diseñado alrededor de IDs.

Pero `cor0203_batch_linkage_gate.py` verifica únicamente nombres reales.
No exige `source_id` no vacío.

El productor `cor0203_prospective_producer.py` consulta historial usando el nombre del jugador como clave.

Se han observado manifests con `source_id=""`.

Conclusión: la producción viva no está aplicando completamente la política canónica de identidad por ID.

No se afirma que esto haya causado una colisión concreta en las 9 observaciones actuales; se afirma que el código permite el riesgo.

## P0-10 — El código permite defaults neutrales/medianas sin flag explícito
`cor0203_prospective_producer.py` contiene:
- `rate(..., default=0.5)`;
- `history_form` retorna 0.5 si no hay matches;
- surface/serve/return/opponent-strength usan pares [0,0] que derivan a 0.5;
- `score_spec` sustituye valores no numéricos/no finitos por la mediana del modelo.

El history gate comprueba n_history > 0 y presencia ELO/Glicko, pero no prueba que cada denominador de cada feature sea observado.

Conclusión:
el código permite una forma de imputación/prior neutral no marcada como missing.

NO se declara que las 9 observaciones estén contaminadas sin una auditoría feature-by-feature.
Sí se declara que el comportamiento permitido por el código no está alineado de forma explícita con Missing != 0 / no silent imputation.

---

# 3. HALLAZGOS IMPORTANTES P1

## P1-01 — Workflow legacy hard-coded
`cor0203-prospective-freeze.yml` está hard-coded a artefactos R713.

No es un productor genérico para nuevas revisiones.

Riesgo: deuda técnica y confusión operativa.

## P1-02 — Snapshot no programado
`cor0203-preholdout-snapshot.yml` solo corre por:
- cambio del propio workflow;
- workflow_dispatch manual.

No tiene schedule.

Riesgo: la base live puede quedar desactualizada al cambiar de período si no se dispara explícitamente.

## P1-03 — Provenance del discovery más débil que el contrato mundial
`world_calendar_registry.py` exige `source_snapshot_sha256`.

La ruta actual de manifests puede persistir referencias narrativas/URLs sin snapshot hash equivalente.

R722 contiene identity_source/schedule_source narrativos, pero no source snapshot SHA dentro del prefeature.

Conclusión: el contrato de provenance más fuerte existe, pero la ruta viva no lo aplica.

## P1-04 — Autoridad de horarios no está normalizada centralmente
R718 ya documentó una incertidumbre de timezone en la fuente de horario.

No se encontró un adaptador central de:
venue timezone -> source timestamp -> UTC canonical -> crosscheck.

Riesgo: cutoff/freeze windows pueden perderse o quedar con evidencia horaria débil.

## P1-05 — Rama operativa no es main
Default branch = main.
La producción auditada vive en `repair/cor09-world-pipeline`.
PR #1 es draft hacia `integration/c2-private-live-foundation`.

Esto no es un bug por sí mismo durante auditoría.
Sí significa que no existe todavía un camino de promoción/deployment cerrado desde reparación -> integración -> main.

## P1-06 — Observabilidad de producción insuficiente
No se encontró un workflow que publique continuamente:
- world events discovered/hour;
- eligible events/hour;
- preregistered/hour;
- PIT complete/hour;
- frozen/hour;
- discovery->prereg latency;
- prereg->freeze latency;
- missed prestart windows;
- provider freshness;
- blockers by root cause;
- retry success rate;
- queue age.

Conclusión: se puede tener CI verde sin tener producción efectiva.

## P1-07 — KPI histórico equivocado para el objetivo actual
R657 documentó:
- 230 eventos analizados;
- 1 P_MATRIX;
- 1 freeze;
- 1 calibrable;
- global freeze yield 0.004347826;
- último ciclo throughput 13/h.

Después COR08 demostró throughput >=100/h en ciclos auditables, pero eso mide capacidad de análisis/procesamiento, no necesariamente freezes válidos por hora.

Conclusión: throughput de eventos y throughput calibrable se trataron como métricas distintas, pero operativamente se priorizó demasiado la primera.

KPI que debe gobernar producción:
- valid prospective freezes/hour;
- executable freeze yield;
- median discovery-to-freeze latency.

## P1-08 — CI fuerte no equivale a producción conectada
En los 100 runs recientes del branch:
- MATRIX CI: 95 runs, 92 success, 0 failure, 3 other.
- COR02-03 governed batch freeze: 3 runs, 2 success, 1 failure.
- COR02-03 prospective holdout freeze: 2 runs, 2 success.

Conclusión:
la calidad de código está mucho más ejercitada que el camino de producción real.

---

# 4. MATRIZ TENIS — DIAGNÓSTICO

Fortalezas:
- modelo binding R218/R223 sellado;
- holdout virgen protegido;
- no metrics peek;
- prefeature ordering;
- PIT preperiod;
- SHA/provenance parcial;
- batch producer funcional;
- CI robusta.

Debilidad principal:
- no existe ingestión automática de draws/fixtures -> world calendar -> identity -> prereg -> acquisition -> STATIC4 -> manifest.

La IA/web externa está cubriendo hoy ese hueco.

Esto explica por qué los freezes aparecen uno a uno y no en lotes masivos.

La restricción ATP Challenger Hard también reduce el suministro natural de eventos. Eso es INTENCIONAL y no debe confundirse con un fallo de automatización.

---

# 5. MATRIZ FÚTBOL — DIAGNÓSTICO

Estado actual:
- ordinary production formalmente PAUSED por COR07.
- por tanto, cero producción nueva de fútbol en este momento es una decisión de gobierno, no un fallo de scheduler.

Históricamente:
- motores R315/R316/R318/R320/R322/R442 tenían estados de paridad/cobertura/ejecutabilidad distintos;
- R657 registró varios bloqueados/no ejecutables.

En el repo existen:
- acquisition queue;
- acquisition worker;
- API-Football services;
- repeatable live ingestion;
- durable SQLite controls;
- tests de integridad.

Pero no existe un workflow productivo actual que una esos componentes con un ciclo futuro -> P_MATRIX -> freeze.

Conclusión:
fútbol tiene componentes más maduros de adquisición/live que la ruta COR02/COR03, pero actualmente están fuera de producción por gobierno y no conforman un pipeline prospectivo continuo activo.

---

# 6. LO QUE NO ES CULPA DE LA AUTOMATIZACIÓN

No todo el 9/600 es software desconectado.

Factores legítimos:
1. dominio holdout deliberadamente estrecho: ATP Challenger Hard;
2. emparejamientos futuros solo son admisibles cuando hay dos identidades reales;
3. horarios deben estar fijados antes del freeze;
4. jugadores sin historial autorizado deben bloquearse;
5. no puede usarse backfill retrospectivo;
6. métricas permanecen selladas hasta 600;
7. fútbol está pausado y no puede aportar a este holdout.

Por tanto, una automatización perfecta aumentará mucho la captura y reducirá eventos perdidos, pero no puede fabricar 600 partidos instantáneamente.

---

# 7. CAUSA RAÍZ CONSOLIDADA

La arquitectura evolucionó como una colección de controles muy sólidos, pruebas y módulos especializados, pero el PRODUCTOR DE PRODUCCIÓN quedó fragmentado.

En términos simples:

TENEMOS:
- piezas de discovery;
- piezas de queue;
- piezas de worker;
- piezas de identity;
- piezas de PIT;
- piezas de models;
- piezas de freeze;
- piezas de settlement;
- tests.

NO TENEMOS todavía, conectado y residente:
un único orquestador durable que ejecute todas esas piezas automáticamente y continúe ante fallos parciales.

---

# 8. REMEDIACIÓN RECOMENDADA

## Fase A — P0: unificar el runtime
Crear un único `matrix_production_orchestrator` gobernado:

SOURCE ADAPTERS
-> WORLD DISCOVERY
-> CANONICAL IDENTITY
-> FUTURE/TIME AUTHORITY
-> DOMAIN ROUTER
-> PERSISTED PREREGISTRATION
-> GOVERNED ACQUISITION QUEUE
-> DURABLE ACQUISITION WORKER
-> FEATURE COMPLETENESS GATE
-> MODEL ROUTER
-> P/FREEZE
-> OUTCOME WATCH
-> FINAL SETTLEMENT
-> CALIBRATION LEDGER

## Fase B — persistencia de estado
Implementar event-state machine durable por event_id:
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

Cada transición append-only.

## Fase C — batch isolation
Un evento malo nunca debe abortar los buenos.

Particionar:
- READY
- RETRYABLE
- PERMANENT_BLOCKED

## Fase D — locks/concurrency
- usar SHA del trigger, no branch head mutable;
- `concurrency` por holdout/domain;
- asignación transaccional del observation_index;
- no usar starting count manual como mecanismo de coordinación;
- idempotency key por event_id + model binding + holdout.

## Fase E — identity/provenance
- IDs canónicos obligatorios;
- source snapshot SHA obligatorio;
- fixture/draw adapter oficial;
- venue timezone authority;
- no nombre como primary join key.

## Fase F — missingness
Reemplazar defaults silenciosos por:
- observed value;
- explicit prior/imputation flag si el contrato lo permite;
- o BLOCKED.

Auditar las 9 observaciones existentes para comprobar si algún fallback fue realmente usado antes de continuar el holdout.

## Fase G — automation
Mover la lógica crítica de ChatGPT automation al runtime del repositorio/servicio.
Las automatizaciones de ChatGPT deben quedar como monitor/auditor, no como productor transaccional principal.

## Fase H — observabilidad
Dashboard mínimo:
- world_discovered/h
- eligible/h
- preregistered/h
- features_ready/h
- frozen/h
- settled/h
- freeze_yield global
- freeze_yield eligible
- discovery_to_freeze_p50/p95
- missed_window count
- blockers by cause
- oldest queue age

---

# 9. DICTAMEN

VEREDICTO: INTEGRATION_AUTOMATION_GAP_CONFIRMED

No se encontró evidencia de un único conector omitido cuya activación por sí sola resuelva todo.

Sí se encontró evidencia física de que:
1. la producción viva depende de automatización externa para etapas críticas;
2. módulos centrales no están conectados a workflows;
3. el batch actual no es seguro para alta concurrencia;
4. un solo fallo puede detener un lote;
5. identity/provenance fuerte no gobierna completamente la ruta viva;
6. settlement/calibration no están integrados al productor;
7. R722 demostró que la automatización actual puede quedar a mitad de una conversión.

Prioridad recomendada:
NO seguir optimizando partido por partido.
Primero cerrar el orquestador end-to-end y auditar missingness/identity de las 9 observaciones existentes.
