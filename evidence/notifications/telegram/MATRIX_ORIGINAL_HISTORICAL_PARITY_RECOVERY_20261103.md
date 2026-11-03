# MATRIX — Recuperación de paridad histórica original, 2026-11-03 UTC

## Evidencia auténtica y reutilización, NO duplicación

Se releyeron los comparadores preexistentes:
- `tools/matrix_independent_over25_historical_parity.py`
- `tools/matrix_independent_over25_brazil_raw_feature_parity.py`
- `tools/matrix_football_independent_over25_shadow.py`
- `app/research/football/match_analysis_input.py`

### Paridad de características de grupo ya alcanzada (investigación histórica)
- Brasil Serie A, `evidence/football_world_inventory/2026-11-03/MATRIX_BRAZIL_ORIGINAL_RAW_FEATURE_PARITY_LAST.json`: 284 resultados históricos emparejados sin discrepancias de marcador; 237 encuentros evaluables por ambos productores y **237 características/probabilidades de grupo coincidentes**, cero diferencias en el subconjunto evaluable. Otros 47 bloqueados por historia de grupo insuficiente. `original_calibrated_feature_equivalence_verified=false`.
- Italia Serie A, `evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_OVER25_HISTORICAL_PARITY.json`: 75 resultados emparejados sin discrepancias, 30 evaluables por ambos y **30 características/probabilidades de grupo coincidentes**, cero diferencias; 45 bloqueados por grupo insuficiente. `calibrated_model_feature_equivalence_verified=false`.
- Ambos documentos tienen `all_six_leagues_equivalence_verified=false`. Son concordancias parciales REALES, NO una certificación de PIT enriquecido ni del modelo de producción.

### Championship, siguiente área comprobable
- `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ORIGINAL_ARCHIVE_GAP_LAST.json` certificó **38** grupos históricos archivados `league_40_season_2026.bin`.
- Archivo seleccionado: `evidence/api_football/prospective_daily/2026-10-24/20261024T093953Z/history/raw/league_40_season_2026.bin` (SHA-256 esperado según inventario: `ca731d6d91fb3f5dde0c3e2222dcd83582886231bfced1c82fc1bad51d90c931`). Ciclo `cycle_summary.json` original status `PASS`, corte `2026-10-24T09:40:21+00:00`.
- Fuente de contraste: `football-data.org/v4/competitions/ELC/matches` con código independiente 2016. El token se toma únicamente de GitHub Actions Secrets. No se graba ni expone token.
- Nuevo comparador read-only: `tools/matrix_independent_over25_championship_raw_feature_parity.py`, commit `e8de7243`. Reutiliza `parse_archive`, `parse_free`, `compare` y `compare_raw_features`, aplicados a Championship.
- Pruebas de rechazo seguro: `tests/test_matrix_independent_over25_championship_raw_feature_parity.py`, commit `c57cdc11`.
- Flujo real con proveedor autenticado: `.github/workflows/matrix-championship-original-archive-gap.yml`, commit `d6d7059e`, ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41580629419. **No dar por confirmados resultados externos antes de revisar el trabajo y su archivo final.**
- Runner Windows, comprobaciones sin secreto: `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`, commit `4f3f62f6`, ejecución https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41580676306, `collect` completed/success. Las pruebas del comparador no autorizan por sí mismas paridad entre fuentes.

### Auditoría de los siete partidos
- Certificado de identidad triple preexistente: 7 de 19 fixtures.
- Shadow independiente tiene conteos históricos de al menos 5/5 equipos para los siete (6 partidos con 13/13 y uno con 20/20).
- Evaluador `tools/matrix_independent_feature_parity_audit.py` y sus pruebas (commits `659fe25a`, `c56d3664`) separan conteos de investigación, evidencia PIT individual y equivalencia de modelo. Runner Windows previo https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41580047970: 49 pruebas aprobadas.
- Archivo por partido del nuevo auditor, cuando GitHub lo publique: `evidence/football_world_inventory/2026-11-03/MATRIX_INDEPENDENT_FEATURE_PARITY_AUDIT.json` (workflow https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41579899796). No declarar subida de ese fichero hasta verificarlo.

## Resultado prudente

Comprobado: identidad calendario 7; Brasil e Italia con identidad/resultado y características de grupo históricos equivalentes en subconjuntos de referencia; tests de seguridad; archivo original Championship disponible.
Pendiente: resultado autenticado de paridad de Championship, crosswalk de IDs y características `CANONICAL_ENRICHED_PIT` en todos los grupos relevantes, `p_matrix` original prospectivo, cuotas exactas y confirmación de referencia sharp; Telegram continúa `0 BET`.

Se preservan modelos, calibraciones, holdouts, históricos, cuotas y safeguards originales. `REAL_MONEY=BLOCKED`; `automatic_wagering=false`. No backfill pospartido ni probabilidades de investigación promovidas a producción.
