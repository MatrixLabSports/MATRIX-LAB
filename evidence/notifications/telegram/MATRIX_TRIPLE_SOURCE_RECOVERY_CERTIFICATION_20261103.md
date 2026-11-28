# MATRIX — Certificación física de identidad independiente, 2026-11-03 UTC

## Alcance
Proyecto MatrixLabSports/MATRIX-LAB, rama repair/cor09-world-pipeline.
Se utiliza el comité técnico como disciplina de revisión (datos, identidad, modelos, CI y seguridad), no se afirma haber convocado expertos externos.

## Evidencia nueva y verificable

- Archivo original independiente: `evidence/football_world_inventory/2026-11-03/MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json`: 19 encuentros.
- Contraste SofaScore: `MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json`: 7 coincidencias preexistentes.
- Contraste Flashscore: `MATRIX_FLASH_FOOTBALL_CROSSCHECK.json`: 7 coincidencias preexistentes.
- Verificador `tools/matrix_independent_triple_source_calendar_certificate.py`, commit `f2e0cc55`. Exige identidad por ID de la fuente, SofaScore ID, Flashscore MID y tiempo exacto, prohíbe duplicados y rechaza inconsistencias.
- Pruebas `tests/test_matrix_independent_triple_source_calendar_certificate.py`, commit `7ad96333`.
- Flujo de GitHub `.github/workflows/matrix-independent-three-source-identity.yml`, commit `1880a3d8`: ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41579399295 concluida SUCCESS; cinco pruebas aprobadas; certificado generado, subido como artefacto y persistido en commit `53a5b94ab1`.
- Certificado en `evidence/football_world_inventory/2026-11-03/MATRIX_TRIPLE_SOURCE_CALENDAR_IDENTITY_CERTIFICATE.json`: 7 identidades de calendario confirmadas entre las tres fuentes, 12 no confirmadas. Fixture IDs de football-data.org confirmados: 555073, 561917, 561918, 561921, 561922, 561924, 561928.
- Prueba de Windows: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41579553501, resultado SUCCESS, **44 pruebas aprobadas**, CDP y recolección activos. Evidencia de recolección: 14 páginas, 0 candidatos canónicos y 0 cuotas exactas Betano. Auditoría de candidatos antigua: `AUDIT_TIMESTAMP_UNVERIFIED_OR_STALE`, bloqueada.

## Límites reales: NO SE HA RECUPERADO EL PRODUCTOR

El certificado acredita solamente la identidad de calendario en la fuente independiente y dos navegadores. No acredita equivalencia de `fixture_id` API-Football, liga/temporada/grupos, características estadísticas PIT, normalización de históricos, paridad de modelo, `p_matrix` de producción, cuotas ejecutables o señales Telegram. No se copiaron `p_over25_research` al modelo ni se modificó calibración.

La fuente anterior tiene corte de suscripción el 28 de octubre de 2026, programado en `tools/api_football_prospective_horizon.py`. La ruta de football-data.org sigue sin una crosswalk de IDs de proveedor ni prueba retrospectiva de características históricas. La evidencia de 3 de noviembre contiene 10 scores de investigación no autorizados, y 0 cuotas exactas verificadas. La ausencia de archivos `evidence/api_football/daily_prematch_reports/2026-11-03/over25_shadow_ev` continúa.

## Próxima condición para desbloquear

1. Identificar una fuente autorizada para el histórico exigido por `tools/api_football_canonicalize_analysis_inputs.py` y la evaluación congelada de `tools/api_football_prospective_market_freeze.py`.
2. Probar one-to-one de ID de partido, liga, temporada y equipos; rehacer características PIT con evidencia antes del kickoff; ejecutar paridad OOS respecto al modelo calibrado.
3. Solo entonces producir nuevo archivo canónico prospectivo y revalidar cuota exacta + referencia sharp + valor esperado + kickoff + control de correlación.
4. Hasta esa certificación: `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `0 BET`.

Ningún resultado aquí autoriza envío de señales ni apuestas.
