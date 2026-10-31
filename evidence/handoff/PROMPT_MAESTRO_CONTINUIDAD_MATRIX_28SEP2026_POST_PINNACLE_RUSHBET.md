# PROMPT MAESTRO DE CONTINUIDAD TOTAL — MATRIX-LAB-SPORTS
## HANDOFF 28-SEP-2026 — POST API-FOOTBALL PRO + PINNACLE + TENIS 26/600 + RUSHBET PREACTIVATION

IDIOMA OBLIGATORIO: **ESPAÑOL**

PROYECTO: **MATRIX-LAB-SPORTS**

REPOSITORIO: **MatrixLabSports/MATRIX-LAB**

RAMA OPERATIVA: **repair/cor09-world-pipeline**

RAMA POR DEFECTO / WORKFLOWS: **main**

ZONA HORARIA CANÓNICA: **America/Bogota**

ESTADO GLOBAL: **RESEARCH_VALIDATION_NOT_PRODUCTION_READY**

EXTERNAL_AUDIT: **NOT_CLOSED**

REAL_MONEY: **BLOCKED**

AUTOMATIC_WAGERING: **FALSE**

---

# 0. REGLA SUPREMA

Continúa EXACTAMENTE desde el último estado físico y canónico existente.

NO empieces desde cero.

NO reconstruyas por memoria algo que ya exista físicamente.

NO inventes avances, llamadas de API, PASS, cobertura, cuotas, probabilidades, ejecución, settlement, CI, hashes ni archivos.

NO llames “usada” a una API solo porque exista código, adaptador, secreto o prueba.

La autoridad es:

1. repositorio/runtime físico y evidencia de proveedor;
2. ledgers, SHA-256, workflows terminales y artefactos persistidos;
3. auditoría reconciliada;
4. resúmenes/handoffs;
5. memoria/chat.

Si este prompt contradice evidencia física posterior, MANDA LA EVIDENCIA FÍSICA POSTERIOR.

Antes de afirmar que algo está PASS, verifica físicamente el workflow/CI correspondiente.

---

# 1. CABEZAS FÍSICAS AL CREAR ESTE HANDOFF

Cabeza operativa ANTES de crear los archivos de handoff:

`c748a4162cfc131d117c1dbbda77e9a9a85d813e`

mensaje:
`test(odds): cover Colombia bookmaker catalog probe`

MATRIX CI para esa cabeza:
- push #631 = SUCCESS
- pull_request #632 = SUCCESS

Cabeza main ANTES del handoff:

`c06e69271f8fe7f8f76ecc5f637b39d985e0c53d`

mensaje:
`ci(odds): add Colombia bookmaker catalog audit`

IMPORTANTE: al iniciar una nueva conversación, vuelve a consultar las dos ramas. Pueden existir commits posteriores.

---

# 2. LECTURA OBLIGATORIA EN LA NUEVA CONVERSACIÓN

Lee físicamente, en este orden:

## A. Autoridad reconciliada
- `docs/governance/MATRIX_RECONCILED_BASELINE_SUPREMACY_V1.md`
- `evidence/audit/MATRIX_TOTAL_RECONCILIATION_AUDIT_20260926.md`
- `evidence/audit/MATRIX_RECONCILED_TRUTH_STATE_20260926.json`
- `docs/governance/MATRIX_TRUTHFULNESS_AND_PHYSICAL_EVIDENCE_CONSTITUTION_V1.md`
- `evidence/audit/MATRIX_API_USAGE_CLAIM_GATE_V1.md`

## B. Auditoría externa / COR
- `MATRIX_INSTRUCCIONES_CORRECCION_21SEP2026.docx` si está disponible en Biblioteca
- `MATRIX_AUDITORIA_EXTERNA_CORRECCIONES_21SEP2026.xlsx` si está disponible
- `MATRIX_CORRECTION_BOARD_R704.md` si está en Biblioteca
- COR literal manda sobre interpretaciones posteriores.

## C. Tenis COR02/COR03 actual
- `evidence/cor0203/runtime/MATRIX_COR0203_PRODUCTION_OBSERVABILITY_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json`
- `evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R727.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_MODEL_BINDING_R707.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_ELO_GLICKO_PROSPECTIVE_BUNDLE_R706.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_SETTLEMENT_QUEUE_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_SETTLEMENT_SYNC_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_CROSSWALK_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_HISTORY_GATE_R727.json`

## D. Fuente tenis y auditoría global de APIs
- `evidence/audit/MATRIX_TENNIS_SOURCE_RESTORATION_VERIFICATION_20260928.md`
- `evidence/audit/MATRIX_TENNIS_API_GLOBAL_AUDIT_20260928.md`
- `tools/cor0203_rapidapi_tennis_discovery.py`
- `tools/tennis_world_coverage_audit.py`

## E. Fútbol API-Football
- `evidence/api_football/pro_entitlement_probe/manifest.json`
- `evidence/api_football/fixtures/future_fixture_registry.json`
- `evidence/api_football/history/history_capture_manifest.json`
- `evidence/api_football/team_last_fallback/history_readiness_after_team_last.json`
- `evidence/api_football/team_last_fallback/manifest.json`

## F. Pinnacle
- `evidence/api_football/bookmakers/manifest.json`
- `evidence/api_football/pinnacle_coverage/manifest.json`
- `evidence/api_football/pinnacle_reference/manifest.json`
- `evidence/api_football/pinnacle_reference/pinnacle_reference_odds.jsonl`
- `app/providers/api_football/pinnacle_reference.py`
- `app/application/football/odds_runtime.py`
- `app/research/football/odds_ledger.py`

## G. RushBet
- `evidence/audit/MATRIX_RUSHBET_SOURCE_SELECTION_20260928.md`
- `tools/odds_api_net_colombia_catalog_probe.py`
- `tests/test_odds_api_net_colombia_catalog_probe.py`
- workflow en main:
  `.github/workflows/odds-api-net-colombia-catalog.yml`

## H. COR11
- `evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_R727.json`
- `tools/cor11_cadence_update.py`
- workflow main:
  `.github/workflows/cor11-real-day-cadence.yml`

---

# 3. ESTADO COR — NO ALTERAR SIN EVIDENCIA

CERRADOS / RESUELTOS:
- COR01
- COR04
- COR05
- COR06
- COR07
- COR08
- COR09
- COR12

ABIERTOS:
- COR02
- COR03
- COR10
- COR11

Total actual: **8/12 resueltos, 4/12 pendientes**.

## COR02
Criterio:
- estabilidad temporal Y por bandas de ranking;
- PASS sostenido en 3 ventanas consecutivas;
- ventanas 1–200, 201–400, 401–600;
- no abrir métricas antes de n=600.

## COR03
Criterio:
- BSS >= 3% sostenido en validación repetida;
- mismo holdout limpio de 600;
- métricas selladas hasta n=600.

## COR10
Causa raíz de software corregida.
Toda ejecución futura debe preservar:
- casa/bookmaker;
- stake;
- cuota decimal;
- timestamp;
- captura/evidencia SHA-256.

Anti-vacuidad:
- 0 ejecuciones futuras NO es PASS.
- estado actual: 0 ejecuciones futuras genuinas.
- NO fabricar una ejecución para cerrar COR10.

## COR11
Criterio:
- cadencia documentada y respetada >=2 semanas consecutivas reales.
Estado físico:
- **8/14 días reales**
- 21–28 SEP 2026.
No backfill.
No días sintéticos.
No usar rollover UTC para crear un día.
El updater fail-closed ya está implementado.

---

# 4. TENIS — ESTADO FÍSICO ACTUAL

Proveedor activo y físicamente verificado:
`rapidapi_tennis`
host:
`tennis-api-atp-wta-itf.p.rapidapi.com`

Restauración real verificada:
- network_calls > 0;
- durable raw evidence;
- checkpoint/provenance;
- source readiness READY;
- automatic wagering false.

## Holdout COR02/COR03

`holdout_id = A22_POST_AUDIT_VIRGIN_HOLDOUT_V1`

Estado físico más reciente:
- **26/600**
- Window 1: **26/200**
- remaining total: 574
- metrics = `SEALED_UNTIL_600`
- outcomes read for performance = 0
- failed observations = 0
- passed observations = 26
- silent imputation detected = false
- integrity = PASS
- REAL_MONEY = BLOCKED

R727 añadió 7 nuevas observaciones:
- starting count = 19
- ending count = 26
- metrics unopened
- outcome = null
- freeze antes de event start.

Modelos congelados:
- ELO: `R218_ELO_BOTH`
- Glicko: `R223_BATCH_GLICKO_RATING_BOTH`
- binding: `MATRIX_COR0203_MODEL_BINDING_R707_V1`

NO cambiar modelo después de la primera observación válida del holdout.
NO usar R251 como COR02/COR03.
NO backfill histórico.
NO peek de outcomes.
NO odds -> P.
Missing != 0.
No imputación silenciosa.

Scheduler:
`COR02-03 repo-native hourly scheduler`
- cron minuto 17 de cada hora UTC;
- corre sobre la rama operativa;
- no depende del chat ni de Opera.

Regla operativa:
**tenis continúa prospectivamente 26 -> 600 aunque fútbol tenga bloqueos.**

---

# 5. AUDITORÍA MUNDIAL DE APIs TENIS

Archivo:
`evidence/audit/MATRIX_TENNIS_API_GLOBAL_AUDIT_20260928.md`

Auditoría DOCUMENTAL completada; live comparative probe sigue pendiente.

Top 3 de fit interno MATRIX documentado:
1. Tennis API / RapidAPI — principal all-around.
2. Live Tennis API — histórico/PIT/PBP.
3. API-Tennis — redundancia mundial/live/odds/draw.

NO tratar el score documental como prueba de cobertura live.
NO comprar/promover otro proveedor sin benchmark empírico común si todavía es posible probar primero.

Existe:
`tools/tennis_world_coverage_audit.py`
para auditar ATP y WTA sobre ventana live.
No afirmar resultados live de ese auditor si todavía no hay evidencia persistida de una ejecución real.

---

# 6. FÚTBOL — API-FOOTBALL PRO

Secret existente:
`API_FOOTBALL_KEY`
NO mostrarlo ni pedir que se pegue en chat.

Plan Pro verificado físicamente:
- entitlement Pro = PASS
- 7,500 requests/day
- historial 2026 accesible
- team last=20 accesible.

## Descubrimiento mundial
Captura futura:
- 84 provider fixtures
- 83 estrictamente future eligible
- 166 equipos
- 36 competiciones
- 25 países.

## Historial
Agrupación league+season:
- 37 grupos capturados
- 37 llamadas
- provider errors = 0.

Fallback `team + last=20`:
- 89 equipos deficientes consultados
- 89 llamadas
- provider errors = 0.

Resultado:
- **82/83 partidos HISTORY_READY**
- **1/83 bloqueado**

Bloqueado:
- Serbia U18 vs Russia U18
- Serbia U18 history = 4
- Russia U18 history = 3
- mínimo = 5
- NO bajar el mínimo para inflar conversión.

## Punto crítico pendiente
Antes de producir probabilidades de fútbol:
- construir `FootballMatchAnalysisInput` canónico;
- usar un `analysis_as_of` temporalmente verdadero y compatible con el momento real de observación;
- no reutilizar un timestamp antiguo de fixture discovery para aparentar PIT;
- validar identidad, historial y anti-leakage.

Motor físicamente identificado:
- baseline Poisson transparente experimental.
NO llamarlo P_MATRIX gobernado todavía.
NO promocionarlo a motor ejecutable sin la adjudicación física correspondiente.

Regla operativa:
**fútbol continúa en paralelo con tenis; un bloqueo en un deporte no detiene el otro.**

---

# 7. PINNACLE — YA INTEGRADA EN FÚTBOL

API-Football bookmaker catalog:
- 33 bookmakers.
- Pinnacle encontrada.
- bookmaker_id = **4**.

Cobertura real auditada sobre 83 partidos futuros:
- 47 con odds Pinnacle.
- 36 sin odds Pinnacle.
- coverage = **56.626506%**
- 17 mercados distintos.
- 83 llamadas.
- provider errors = 0.

Integración física:
- **4,021 cotizaciones Pinnacle**
- 47 fixtures
- 17 mercados
- quote_role = `REFERENCE`
- provider = `api_football`
- bookmaker = `Pinnacle`
- bookmaker_id = 4
- ledger hash-chain verificado.
- odds_used_to_generate_model_probability = false
- probability_source = `MODEL_ONLY`
- REAL_MONEY = BLOCKED.

Workflow de integración terminó SUCCESS.
Evidence commit:
`374b085`

Pinnacle tiene prioridad como **referencia de mercado** cuando existe una referencia válida, pero:
- NO genera P_MODEL/P_MATRIX.
- NO sustituye el modelo.
- sirve para comparación, dispersión y CLV.

---

# 8. RUSHBET — ESTADO EXACTO

Corrección de nombre:
**RushBet**.

Hecho físico:
- RushBet NO aparece en los 33 bookmakers de API-Football.
- Por tanto, NO fingir que API-Football la suministra.

Proveedor candidato seleccionado documentalmente:
**odds-api.net**

Razón:
- documentación pública declara catálogo Colombia;
- documenta `rushbet`, `betplay`, `betano`, `bwin`;
- un solo feed podría cubrir varias casas colombianas;
- snapshots pre-match y provenance/freshness.

Estado:
`PREACTIVATION / CREDENTIAL_REQUIRED / NOT YET VERIFIED USED`

Código ya creado:
- `tools/odds_api_net_colombia_catalog_probe.py`
- `tests/test_odds_api_net_colombia_catalog_probe.py`

Workflow ya creado en main:
- `Odds API Colombia bookmaker catalog audit`
- archivo: `.github/workflows/odds-api-net-colombia-catalog.yml`

CI del código:
- operational head `c748a416...`
- MATRIX CI push #631 SUCCESS
- PR #632 SUCCESS.

Siguiente gate RushBet:
1. usuario decide/suscribe plan de odds-api.net;
2. guardar key SOLO como GitHub Actions secret:
   `ODDS_API_NET_KEY`
3. ejecutar workflow:
   `Odds API Colombia bookmaker catalog audit`
4. verificar físicamente:
   - rushbet_present=true
   - betplay_present=true
   - betano_present=true
   - bwin_present=true
5. persistir RAW + SHA + rate metadata.
6. solo entonces puede pasar a VERIFIED_USED.

NO pedir al usuario que pegue la key en chat.
NO decir que RushBet ya está conectada.
NO usar scraping directo de RushBet si existe una vía API gobernable.

---

# 9. CASAS / ARQUITECTURA DE ODDS

Pinnacle:
- referencia eficiente ya integrada.

BetPlay / Betano / Bwin / RushBet:
- casas de comparación/ejecución según evidencia disponible.

API-Football ya expone:
- Bwin
- Betano
- Pinnacle
- y otras casas.
Pero RushBet no.

Objetivo de arquitectura:
`P_MODEL`
vs
`Pinnacle reference`
vs
`BetPlay`
vs
`Betano`
vs
`Bwin`
vs
`RushBet`

Calcular solamente después de identidad/temporalidad correctas:
- implied probability descriptiva;
- vig/overround;
- price dispersion;
- theoretical edge respecto al modelo;
- CLV cuando exista closing reference;
- NO odds-to-P_MODEL.

---

# 10. COR11 AUTOMATIZADO

Implementado:
- `tools/cor11_cadence_update.py`
- tests adversariales;
- workflow `COR11 real-day cadence` en main.

Comportamiento:
- solo agrega el siguiente día calendario real de Bogotá;
- exige commit/evidencia física calificante;
- rechaza gaps;
- no backfill;
- no días sintéticos;
- al llegar a 14/14 puede emitir:
  `MATRIX_COR11_CLOSURE_EVIDENCE.json`

Estado actual todavía:
**8/14**.

---

# 11. REGLAS PERMANENTES DE VERACIDAD Y OPERACIÓN

Queda terminantemente prohibido:
- afirmar uso de API sin llamada real verificable;
- afirmar PASS sin ejecución terminal;
- afirmar persistencia sin archivo/commit;
- afirmar cobertura mundial total sin benchmark;
- Missing = 0;
- imputación silenciosa;
- odds -> P_MATRIX;
- leakage futuro;
- backfill en holdout prospectivo;
- settlement antes de FINAL;
- modificar una probabilidad/freeze ya congelado;
- fabricar una ejecución para COR10.

Toda evidencia de API debe intentar preservar:
- endpoint;
- parámetros públicos;
- timestamp;
- raw body;
- SHA-256;
- provider identity;
- rate-limit metadata cuando exista;
- linkage al evento/fixture;
- secreto fuera de logs/commits/chat.

REAL_MONEY sigue BLOQUEADO.

---

# 12. FORMA DE TRABAJO CON EL USUARIO

Idioma: español.

El asistente hace por su cuenta:
- investigación;
- auditoría;
- lectura física;
- diseño;
- código;
- tests;
- workflows;
- revisión de logs;
- persistencia que pueda realizar vía herramientas disponibles.

El usuario solo interviene cuando es estrictamente necesario:
- pago/suscripción;
- secreto/API key;
- clic manual no disponible por herramienta;
- autorización explícita.

Cuando el usuario deba usar GitHub o una interfaz:
**dar UN SOLO PASO/CLICK por turno y esperar captura.**

No hacerle repetir al usuario trabajo que puede hacer el asistente con GitHub.

---

# 13. DOS CARRILES SIMULTÁNEOS

Mantener SIEMPRE separados:

## CARRIL TENIS
26/600 -> descubrimiento real -> preregistro -> identidad -> PIT -> R218/R223 -> freeze -> holdout -> settlement FINAL-only -> métricas al completar 600.

## CARRIL FÚTBOL
83 futuros -> 82 HISTORY_READY -> canonical input temporalmente correcto -> motor gobernado/adjudicación -> probability diagnostic/prospective freeze -> Pinnacle reference -> demás casas -> settlement/calibración.

Si tenis se bloquea, fútbol continúa.
Si fútbol se bloquea, tenis continúa.

Nunca mezclar:
- modelos;
- variables;
- probabilidades;
- ledgers;
- settlement;
- calibración.

---

# 14. PRÓXIMOS PASOS EXACTOS AL REANUDAR

1. Consultar físicamente heads actuales de:
   - `repair/cor09-world-pipeline`
   - `main`
2. Verificar CI de la cabeza operativa.
3. Leer los archivos de la sección 2.
4. Confirmar el holdout actual de tenis; no asumir que sigue 26 si el scheduler avanzó.
5. Confirmar estado COR11; no asumir 8/14 si ya cambió el día físico.
6. Confirmar que Pinnacle reference manifest sigue PASS e íntegro.
7. Continuar fútbol con canonicalización de los 82 HISTORY_READY y corrección de `analysis_as_of`.
8. Continuar tenis automáticamente hacia 600 sin abrir métricas.
9. Para RushBet, si el usuario quiere activarla:
   - resolver suscripción odds-api.net;
   - secret `ODDS_API_NET_KEY`;
   - ejecutar `Odds API Colombia bookmaker catalog audit`;
   - leer logs físicamente.
10. No comprar otra API tenis sin comparar empíricamente si el objetivo es decidir proveedor.

---

# 15. CONDICIÓN DE CONTINUIDAD

Este prompt es un HANDOFF, no una licencia para ignorar el repositorio.

La primera frase operativa de la nueva conversación debe equivaler a:

**“Voy a verificar primero la cabeza física del repositorio y los estados runtime actuales; no asumiré que los números de este handoff siguen siendo los últimos si hay evidencia posterior.”**

Después, continuar el trabajo sin empezar desde cero y sin perder ninguna mejora ya persistida.
