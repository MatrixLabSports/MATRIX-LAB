# MATRIX — Recuperación del inventario PIT existente de seis ligas

## Alcance y control

Se continuó sobre `repair/cor09-world-pipeline` sin tocar matrices calibradas de fútbol ni tenis. Las seis ligas del registro de alcance son API-Football `39,61,78,135,140,239`. La paridad histórica de Championship 11/11 **no** acredita equivalencia prospectiva en estas ligas.

## Implementación físicamente codificada

- `tools/matrix_six_league_existing_evidence_recovery.py`: recorre `git ls-files evidence/` para separar grupos históricos originales, archivos JSON de análisis canónico original, investigación y nombres de manifiesto prospectivo. No trata nombres de archivos ni historia como predicciones verificadas.
- Busca nombres de manifiesto prospectivo en archivos versionados; si aparecen, exige auditoría de las tres fuentes SHA-256 (captura prematch original, alternativa y marcador final) con `tools/matrix_six_league_enriched_oos_audit.py` antes de computar una fila válida.
- `tests/test_matrix_six_league_existing_evidence_recovery.py`: pruebas de no-promoción de históricos, no-promoción del shadow, rechazo de manifiestos falsificados, gobernanza de las seis ligas y detección únicamente de archivos versionados.
- Incorporado a `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`; salida versionada por `tools/windows/persist_matrix_browser_evidence.ps1`.

## Ejecuciones reales de Windows

- Primera: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41765248714 — éxito, 108+23=131 pruebas, inventario calculado. Arrancó con el script de persistencia anterior y por eso la primera copia del inventario no quedó subida; no se declaró verificado hasta corregirlo.
- Segunda: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41765279069 — éxito, 108+23=131 pruebas, `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- Informe físico: `evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_EXISTING_EVIDENCE_RECOVERY_LAST.json`, persistido y leído directamente después de la segunda ejecución.

## Inventario comprobado del repositorio versionado

- `tracked_evidence_file_count = 63903` archivos de evidencia enumerados.
- `all_original_raw_group_files = 6930`: todos los grupos históricos originales a través de varias ligas y temporadas (no el total de partidos).
- `original_canonical_analysis_files = 4614`: archivos JSON en carpetas de análisis canónico; conteo de archivos **sin calificación individual de sus contenidos**.
- `research_shadow_json_files = 65`.
- `world_inventory_json_files = 164`.
- `strict_oos_manifest_paths = []` y `prospective_filename_candidate_count = 0`: no se halló ningún archivo versionado con el patrón estricto buscado. **No afirmar que no existen datos en otros formatos o ubicaciones.**

| Liga API-Football | Archivos de grupo histórico en inventario original | Filas certificables por manifiesto estricto | Mínimo contractual |
|---|---:|---:|---:|
| 39 | 61 | 0 | 30 |
| 61 | 60 | 0 | 30 |
| 78 | 53 | 0 | 30 |
| 135 | 86 | 0 | 30 |
| 140 | 78 | 0 | 30 |
| 239 | 130 | 0 | 30 |

Las 0 filas certificables **son el resultado del mecanismo de prueba sobre los manifiestos examinados**, no afirmación de que no existan predicciones antiguas en archivos originales ni de que no se hayan jugado partidos. Faltan 30 observaciones certificables por cada liga para superar el piso actual, sujetas a recuperar evidencia válida ya existente antes de generar una nueva observación.

## Próxima dependencia sin inventar probabilidades

Inspeccionar el contenido de los **4614 JSON de análisis canónico original**, buscando predicciones realmente congeladas, timestamps y huellas de origen. Esto debe realizarse sin crear retrospectivamente predicciones que no existieron. Comparar luego con snapshots alternativos igualmente congelados y resultados independientes. Solo la conjunción de las tres fuentes y la evaluación fuera de muestra permite producir un manifiesto real. Si no hay probabilidad original congelada para un encuentro, el productor alternativo permanece en investigación y no puede ser certificado por equiparar sus resultados al resultado final.

El ciclo de captura de casas es independiente del PIT estadístico. `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `production_p_matrix_authorized=false`, `telegram_signal_authorized=false`. Sin modificación de parámetros, cohortes originales o filtrados de seguridad.
