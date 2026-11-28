# MATRIX — Recuperación permanente de identidades API-Football, 4 de noviembre de 2026

## Conclusión comprobada, sin inventar datos

**Se solucionó técnicamente el cruce histórico de identidades mediante registros originales**, no por semejanza aproximada de nombres. 189 archivos `fixtures/future_fixture_registry.json` de API-Football (con `capture_manifest.json` acreditado por captura) fueron indexados por `provider_fixture_id`, `provider_league_id`, identificadores de ambos clubes, fecha de kickoff y fecha real de captura.

Resultado de la corrida https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41768343185 :
- **2988 partidos** con identidad histórica original reconciliada automáticamente;
- **86 partidos** con identidades originales contradictorias que quedaron deliberadamente sin asignación;
- **3074 identificadores** de reportes de probabilidades que superaron controles de hora del reporte y de kickoff (el total no equivale sin más a 179+2967 del inventario anterior por filtros diferentes).
- **73 filas** de probabilidad generadas en o después de kickoff excluidas, además de un reporte de probabilidad ilegible (estos son registros, no necesariamente identificadores distintos).
- **189 registros originales** autenticados y aceptados.

De las seis ligas aprobadas:
| Liga ID | Partidos identificados con origen | Identidades previas catalogadas |
|---|---:|---:|
| 39, Premier League | 29 | 29 |
| 61, Ligue 1 | 25 | 25 |
| 78, Bundesliga | 26 | 26 |
| 135, Serie A | 34 | 34 |
| 140, LaLiga | 28 | 28 |
| 239, Primera A Colombia | 32 | 37 |
| **Total** | **174** | **179** |

Los cinco casos colombianos restantes forman parte de los conflictos. Nunca afirmar que los 179 están plenamente comprobados.

## Código y permanencia

- `tools/matrix_original_fixture_id_lineage_crosswalk.py`: ejecuta cruces por ID nativo; comprueba manifiestos originales, timestamps UTC, fixture en estado futuro en la captura, equipos y liga únicos; bloquea cambios contradictorios, reportes generados tarde y fuentes ausentes. No usa goles, cuotas ni resultados futuros para asignar identidades.
- `tests/test_matrix_original_fixture_id_lineage_crosswalk.py`: pruebas de identidad correcta, liga contradictoria, captura original tardía, ausencia de registro original y predicción redactada después del inicio.
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`: ejecuta el cruce con la cadencia ya existente y guarda el reporte.
- `tools/windows/persist_matrix_browser_evidence.ps1`: conserva el JSON en GitHub.
- `evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_FIXTURE_ID_LINEAGE_CROSSWALK_LAST.json`: evidencia completa con los **3074** dictámenes, sus SHA-256 y catálogo de origen, serializada de forma compacta para ser legible por la API de GitHub. La reducción de tamaño no elimina las identidades ni la distinción por estado.
- CI Windows: 125 pruebas del collector + 23 PIT = **148 aprobadas** en la primera ejecución de crosswalk.

## Lo que esto NO certifica

Este es un **cruce histórico de identidad**. Ni siquiera las 2988 coincidencias se consideran pares prospectivos de probabilidades congeladas original/alternativa con resultado final independiente. `strict_original_alternative_result_triplets_certified=0`; la validación de seis ligas permanece bloqueada por `PROSPECTIVE_SOURCE_SNAPSHOT_MANIFEST_MISSING`.

Los conflictos entre snapshots originales NO pueden resolverse inventando una liga o eligiendo arbitrariamente un horario. Se conserva evidencia legible para posterior auditoría de cada uno.

Sin tocar calibraciones de fútbol, matrices de tenis, bankroll, cuotas, referencias Pinnacle, lógica del supervisor ni canal Telegram. `production_p_matrix_authorized=false`, `telegram_signal_authorized=false`, `automatic_wagering=false`, `REAL_MONEY=BLOCKED`.

## Siguiente dependencia técnica real

La integración de identidades ya no es motivo para repetir el inventario 179/2967. El cuello de botella distinto es producir **dos pronósticos genuinamente sellados antes del kickoff**, con evidencia de entrada, captura y hashes, y liquidarlos con resultados independientemente observados después. Se deben seguir las seis cohortes del registro original, mínimo 30 observaciones prospectivas legítimas por liga. Sin proveedor original activo, no se puede reconstruir retrospectivamente un pronóstico original no emitido, y el reemplazo requerirá validación prospectiva propia y autorización científica separada.
