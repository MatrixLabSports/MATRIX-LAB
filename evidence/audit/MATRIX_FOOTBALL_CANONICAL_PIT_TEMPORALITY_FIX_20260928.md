# MATRIX — CIERRE DE CORRECCIÓN DE TEMPORALIDAD PIT EN INPUTS CANÓNICOS DE FÚTBOL
## 28-SEP-2026

Estado: EVIDENCIA FÍSICA VERIFICADA
Rama: repair/cor09-world-pipeline
REAL_MONEY: BLOCKED
AUTOMATIC_WAGERING: false

## Problema corregido

El constructor histórico de inputs reutilizaba el timestamp de descubrimiento del fixture como `analysis_as_of`.
Después de capturar historia adicional, una observación legítimamente conocida antes del kickoff podía quedar registrada como posterior a ese `analysis_as_of` antiguo.

La corrección separa:
- `source_fixture_capture_at_utc`: instante histórico de captura del fixture;
- `analysis_as_of_utc`: instante real de canonicalización prematch.

El gate es fail-closed:
- si `analysis_as_of_utc >= kickoff_utc`, el fixture no puede entrar al conjunto canónico;
- toda historia usada debe haber ocurrido antes del target;
- toda historia usada debe haber sido observada como máximo en `analysis_as_of_utc`;
- no se genera P_MODEL/P_MATRIX en esta etapa;
- las cuotas no generan probabilidad de modelo.

## Evidencia de implementación

Commits:
- ea3ae84479282933ea0306c5d2330b51c4a042e3 — runtime analysis_as_of en FootballMatchAnalysisInput builder.
- b6f29134b2b8403ef6a70e2b0c92916714d4c550 — canonicalizador PIT.
- 6c4a22c3f6bace8b00bddd12b069e22b53445b7c — pruebas adversariales.
- 8c7ee9cae28348cee59bd0fd32168a1c47736be5 — workflow de persistencia y gates.

MATRIX CI:
- #639/#640: SUCCESS sobre ea3ae844...
- #641/#642: SUCCESS sobre b6f29134...
- #643/#644: SUCCESS sobre 6c4a22c3...
- #645/#646: SUCCESS sobre 8c7ee9ca...

Workflow:
- API-Football canonical PIT analysis inputs #1
- run_id = 36395321089
- conclusion = SUCCESS
- pruebas temporales = SUCCESS
- build canónico = SUCCESS
- invariantes PIT/gobierno = SUCCESS
- persistencia física = SUCCESS

## Resultado canónico producido

Fuente:
`evidence/api_football/canonical_analysis/manifest.json`

- analysis_as_of_utc = 2026-09-28T08:05:55+00:00
- analysis_as_of_source = RUNTIME_UTC_NOW
- total_fixture_count = 83
- builder_output_count = 82
- ready_input_count = 81
- blocked_future_input_count = 1
- not_future_at_analysis_count = 1
- rejected_target_count = 2
- p_matrix_status = NOT_GENERATED
- baseline_poisson_status = EXPERIMENTAL_NOT_PROMOTED
- model_probability_generated = false
- odds_used_to_generate_model_probability = false
- REAL_MONEY = BLOCKED
- bundle_sha256 = 79a85b4c1f36dcf109e540ddeb4e04f3f8cae9181ed14bbe6456e769d1863066

Rechazos:
1. api_football:fixture:1640827 — Serbia U18 vs Russia U18 — kickoff 2026-09-28T14:00:00+00:00 — futuro pero HISTORY_BELOW_MINIMUM.
2. api_football:fixture:1641708 — Singapore vs Bangladesh — kickoff 2026-09-28T08:00:00+00:00 — ya no era futuro a las 08:05:55 UTC.

## Dictamen de esta etapa

TEMPORALIDAD DEL INPUT CANÓNICO: CORREGIDA Y VERIFICADA POR WORKFLOW TERMINAL.

Este dictamen NO:
- promueve el baseline Poisson a P_MATRIX;
- desbloquea dinero real;
- cierra la auditoría externa;
- cierra COR02, COR03, COR10 o COR11.

Siguiente etapa gobernada:
adjudicación del motor sobre los 81 inputs canónicos prematch físicamente válidos, manteniendo el baseline Poisson como EXPERIMENTAL_NOT_PROMOTED hasta superar sus gates.
