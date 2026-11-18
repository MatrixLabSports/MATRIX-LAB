# MATRIX — Probabilidad sin CLV y evidencia prospectiva alternativa (18-NOV-2026)

**Estado: RESEARCH_ONLY / NO_PRODUCTION_PROMOTION / REAL_MONEY=BLOCKED.**

Revisión independiente del 18-NOV-2026. Este archivo es una lectura/auditoría de fuentes existentes: no recalcula probabilidades, no fabrica datos, no cambia umbrales ni certifica paridad.

## Conclusión operacional

CLV no es una entrada necesaria para calcular una probabilidad del modelo: el productor alternativo de investigación registró `odds_used_to_generate_probability=false`, `parameter_refit=false` y `target_outcomes_used=false`. Eso no exime de cuotas legítimas, EV, referencia sharp fresca, calibración, identidad y PIT para autorizar señales.

## Comprobantes originales

- `evidence/football_world_inventory/2026-11-18/MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json` — Git blob `08d5d83faf4e22abbc2b6e23fcf950bf1fdc0806`, cuatro fixtures, `FOOTBALL_DATA_ORG`, estado `DISCOVERY_ONLY_NO_GOVERNED_PROBABILITY_OR_QUOTES`.
- `evidence/football_world_inventory/2026-11-18/MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json` — Git blob `6f9f8b2faa0d875f3532cbaae34596eb67ead6e2`, cuatro pronósticos experimentales, `historical_source_equivalence_verified=false`.
- `evidence/football_world_inventory/2026-11-18/MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json` — Git blob `bd8b99311be3d64b6fe2f1d3a8fe576871abee49`, cuatro snapshots prepartido declarados `FROZEN`.
- `evidence/football_world_inventory/2026-11-18/MATRIX_THESPORTSDB_CROSSCHECK.json` — Git blob `dd2c1f7a3ec5e843e13ff98bd29ba7a1f5fb455d`, `verified_identity_hint_count=0`.
- `evidence/notifications/telegram/MATRIX_BROWSER_GOVERNED_INTAKE_LAST.json` — Git blob `c55a4fe5528823883292e8d87d8f966848953004`, `candidate_count=0`, corte `2026-11-18T07:15:33Z`.
- `evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_STEPWISE_CERTIFICATION_LAST.json` — Git blob `4e71495eb6c4b1641bbe09f0ee18c40e65af6560`, corte histórico, 0 pares prospectivos completos por liga.

Estos SHA son identificadores de blobs Git consultados, no son una declaración de que esta auditoría haya recalculado todos los hashes SHA-256 internos de cada archivo.

## Cuatro pronósticos congelados sin CLV

Los cuatro pertenecen al **Campeonato Brasileiro Série A**, código `BSA`, proveedor `football-data.org`, identificador de competición `2013`. No pertenecen a ninguna de las seis ligas originales de MATRIX (`39,61,78,135,140,239`). No incrementan las seis cohortes.

| ID proveedor | Encuentro | Kickoff UTC | Probabilidad experimental Over 2.5 | Archivo de congelación |
|---|---|---|---:|---|
| 555081 | Coritiba FBC – Santos FC | 2026-11-18T22:30:00Z | 0.5365894733 | `evidence/football_research_freezes/2026-11-18/555081_85b6982076a82fa86f98.json` |
| 555086 | Clube do Remo – Chapecoense AF | 2026-11-18T23:00:00Z | 0.5400713760 | `evidence/football_research_freezes/2026-11-18/555086_85b6982076a82fa86f98.json` |
| 555082 | Cruzeiro EC – SE Palmeiras | 2026-11-18T23:30:00Z | 0.5188483056 | `evidence/football_research_freezes/2026-11-18/555082_85b6982076a82fa86f98.json` |
| 555083 | CR Flamengo – CA Paranaense | 2026-11-18T23:30:00Z | 0.5503874033 | `evidence/football_research_freezes/2026-11-18/555083_85b6982076a82fa86f98.json` |

Cada archivo de congelación fue leído y contiene `model_calculated_at_utc=2026-11-18T04:25:19.430952+00:00` anterior a su `kickoff_utc`. Los cuatro registran `source_fixture_crosswalk_verified=false`, `original_vs_alternative_equivalence_certified=false`, `scientific_holdout_certified=false`, `production_p_matrix_authorized=false` y `telegram_signal_authorized=false`. Los historiales reportan 20 registros de cada equipo, pero eso no certifica equivalencia PIT respecto al productor oficial.

## Diagnóstico

1. Existe productor **alternativo experimental** capaz de congelar probabilidades prepartido sin utilizar cuotas. No es el productor oficial.
2. Falta cruzar identidades SofaScore + Flashscore + proveedor estadístico; la investigación complementaria TheSportsDB no certificó identidades para estos cuatro.
3. Falta la paridad PIT completa entre entradas originales y alternativas y la liquidación futura de resultados auténticos sin backfill.
4. La cobertura de estas cuatro congelaciones no adelanta ninguno de los seis umbrales contractuales de 30 por liga.
5. Telegram sigue sin candidatos canónicos en el comprobante consultado; el problema de entrada precede a CLV. Ninguna reparación CLV por sí sola desbloquea señales.

## Próxima intervención sin relajación de gates

Recuperar snapshots originales de los **45 candidatos de fútbol del 17-NOV**, verificar uno a uno la triple identidad, kickoff con evidencia independiente y diez componentes PIT prepartido, y enlazarlos solo a las cohortes existentes si cumplen su criterio original. En paralelo, conservar estas cuatro congelaciones brasileñas únicamente como laboratorio experimental de calibración futura.

**No hay autorización para emitir señales, modificar calibraciones existentes, convertir odds a probabilidades, o sustituir información faltante por cero/promedios.**
