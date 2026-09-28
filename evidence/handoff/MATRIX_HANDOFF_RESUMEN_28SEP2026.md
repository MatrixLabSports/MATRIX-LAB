# RESUMEN EJECUTIVO DE HANDOFF — MATRIX-LAB-SPORTS
## 28-SEP-2026 — POST API-FOOTBALL PRO + PINNACLE + TENIS 26/600 + RUSHBET PREACTIVATION

## 1. Estado global

MATRIX sigue en:
- `RESEARCH_VALIDATION_NOT_PRODUCTION_READY`
- `EXTERNAL_AUDIT = NOT_CLOSED`
- `REAL_MONEY = BLOCKED`
- `AUTOMATIC_WAGERING = FALSE`

Regla de autoridad:
**la evidencia física del repositorio/runtime manda sobre chat, memoria o resúmenes.**

## 2. Estado COR

Resueltos:
- COR01
- COR04
- COR05
- COR06
- COR07
- COR08
- COR09
- COR12

Pendientes:
- COR02
- COR03
- COR10
- COR11

Total: **8/12 resueltos, 4/12 abiertos**.

### COR02/COR03
Holdout limpio ELO/GLICKO:
- 26/600 observaciones.
- Window 1: 26/200.
- 26/26 integridad PASS.
- 0 outcomes leídos para performance.
- métricas selladas hasta 600.
- modelos congelados: R218 ELO + R223 Glicko.
- NO backfill.
- NO odds-to-P.
- NO tuning del holdout.

### COR10
Software de evidencia de ejecución corregido.
Pendiente:
- al menos una ejecución futura genuina verificable.
- actual: 0.
- jamás fabricar una ejecución.

### COR11
- 8/14 días reales consecutivos.
- 21–28 SEP.
- updater y workflow automático ya implementados.
- no backfill ni días sintéticos.

## 3. Tenis

Fuente real restaurada:
- `rapidapi_tennis`
- host `tennis-api-atp-wta-itf.p.rapidapi.com`
- llamadas de red reales verificadas.
- fuente READY.
- raw/provenance/checkpoint persistidos.

Holdout:
- pasó 10 -> 11 -> 19 -> **26/600**.
- último batch físico R727 añadió 7.

Scheduler:
- `COR02-03 repo-native hourly scheduler`
- minuto 17 de cada hora UTC.
- independiente de chat/Opera.

Auditoría mundial de APIs tenis:
- archivo `MATRIX_TENNIS_API_GLOBAL_AUDIT_20260928.md`
- top 3 de fit documental MATRIX:
  1. Tennis API/RapidAPI
  2. Live Tennis API
  3. API-Tennis
- benchmark live común todavía pendiente.
- no asumir 100% de cobertura por documentación.

## 4. Fútbol — API-Football Pro

Plan Pro físicamente verificado.
Capacidad:
- 7,500 requests/day.
- temporada 2026 accesible.
- `team last=20` accesible.

Descubrimiento:
- 84 fixtures proveedor.
- 83 futuros elegibles.
- 166 equipos.
- 36 competiciones.
- 25 países.

Historial:
- 37 league+season groups.
- 37 capturados.
- team-last fallback: 89 equipos.

Readiness:
- **82/83 HISTORY_READY**.
- único bloqueado: Serbia U18 vs Russia U18.
- historial 4 vs 3, mínimo 5.
- no bajar mínimo.

Pendiente clave:
- canonicalizar los 82 inputs.
- arreglar temporalidad real de `analysis_as_of`.
- no generar probabilidades con timestamp ficticio.
- baseline Poisson sigue siendo experimental, no promocionarlo silenciosamente a P_MATRIX.

## 5. Pinnacle

Confirmada dentro de API-Football:
- bookmaker id = 4.
- catálogo API-Football: 33 bookmakers.

Cobertura auditada:
- 83 futuros.
- 47 con Pinnacle.
- 36 sin Pinnacle.
- cobertura 56.63%.
- 17 mercados.

Integración final:
- **4,021 reference quotes**.
- 47 fixtures.
- 17 mercados.
- ledger hash-chain.
- provider `api_football`.
- bookmaker `Pinnacle`.
- role `REFERENCE`.
- `odds_used_to_generate_model_probability = false`.
- `probability_source = MODEL_ONLY`.
- commit evidencia: `374b085`.

Pinnacle quedó priorizada como referencia de mercado cuando exista quote válida.

## 6. RushBet

Nombre correcto: **RushBet**.

Hecho:
- NO aparece en API-Football.
- no fingir que viene de API-Football.

Ruta seleccionada:
- `odds-api.net`
- documentación declara catálogo Colombia con:
  - RushBet
  - BetPlay
  - Betano
  - Bwin
  - otras casas.

Código ya listo:
- `tools/odds_api_net_colombia_catalog_probe.py`
- `tests/test_odds_api_net_colombia_catalog_probe.py`

Workflow main:
- `Odds API Colombia bookmaker catalog audit`

CI:
- head operativo previo al handoff:
  `c748a4162cfc131d117c1dbbda77e9a9a85d813e`
- MATRIX CI #631 SUCCESS
- PR #632 SUCCESS.

Estado:
- `PREACTIVATION / CREDENTIAL_REQUIRED / NOT YET VERIFIED USED`.

Para activar:
1. suscripción odds-api.net.
2. guardar `ODDS_API_NET_KEY` como GitHub secret.
3. ejecutar workflow.
4. verificar físicamente RushBet/BetPlay/Betano/Bwin.
5. persistir RAW+SHA+rate limits.
6. después, y solo después, VERIFIED_USED.

## 7. Arquitectura de odds actual

Modelo:
- P_MODEL/P_MATRIX nunca sale de cuotas.

Referencia:
- Pinnacle.

Casas de comparación/ejecución:
- BetPlay
- Betano
- Bwin
- RushBet
según evidencia real disponible.

Objetivo:
`P_MODEL vs Pinnacle vs BetPlay vs Betano vs Bwin vs RushBet`

Después:
- vig/overround;
- dispersión de precios;
- edge teórico;
- closing-line value;
- nunca odds -> P_MODEL.

## 8. Trabajo simultáneo

Carril tenis:
- 26/600 -> seguir prospectivamente.

Carril fútbol:
- 82 HISTORY_READY -> canonical input correcto -> motor gobernado -> freeze prospectivo -> market comparison.

Un deporte nunca debe detener al otro.

## 9. Reglas de interacción

- Español.
- Asistente hace todo lo que pueda con herramientas.
- Usuario solo para pagos, secretos, clics inaccesibles y autorizaciones.
- Si el usuario opera GitHub/UI: un clic por turno y esperar captura.
- No pedir API keys en chat.
- No repetir trabajo manual si GitHub connector puede hacerlo.
- Nunca afirmar PASS sin logs físicos.

## 10. Archivos más importantes

### Reconciliación
- `docs/governance/MATRIX_RECONCILED_BASELINE_SUPREMACY_V1.md`
- `evidence/audit/MATRIX_TOTAL_RECONCILIATION_AUDIT_20260926.md`
- `evidence/audit/MATRIX_RECONCILED_TRUTH_STATE_20260926.json`

### Tenis
- `evidence/cor0203/runtime/MATRIX_COR0203_PRODUCTION_OBSERVABILITY_LAST.json`
- `evidence/cor0203/runtime/MATRIX_COR0203_HOLDOUT_INTEGRITY_LAST.json`
- `evidence/cor0203/holdout/MATRIX_COR0203_HOLDOUT_BATCH_R727.json`
- `evidence/audit/MATRIX_TENNIS_API_GLOBAL_AUDIT_20260928.md`

### Fútbol
- `evidence/api_football/team_last_fallback/history_readiness_after_team_last.json`
- `evidence/api_football/pro_entitlement_probe/manifest.json`

### Pinnacle
- `evidence/api_football/pinnacle_reference/manifest.json`
- `evidence/api_football/pinnacle_reference/pinnacle_reference_odds.jsonl`

### RushBet
- `evidence/audit/MATRIX_RUSHBET_SOURCE_SELECTION_20260928.md`
- `tools/odds_api_net_colombia_catalog_probe.py`
- `.github/workflows/odds-api-net-colombia-catalog.yml` en main.

### COR11
- `evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_R727.json`
- `tools/cor11_cadence_update.py`

## 11. Próximo trabajo

Al abrir conversación nueva:
1. verificar heads actuales;
2. leer prompt maestro de handoff;
3. confirmar tenis actual 26/600 o número posterior;
4. confirmar COR11 8/14 o número posterior;
5. continuar fútbol 82 HISTORY_READY;
6. si el usuario quiere RushBet, resolver suscripción/key y ejecutar su catálogo;
7. mantener dinero real bloqueado.

No empezar desde cero.
