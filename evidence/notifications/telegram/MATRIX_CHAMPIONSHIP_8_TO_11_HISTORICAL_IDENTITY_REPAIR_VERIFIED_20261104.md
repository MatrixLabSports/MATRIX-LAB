# MATRIX — 8/11 → 11/11: reparación histórica de identidad de partidos, certificada por Windows

## Interpretación correcta del indicador

El indicador **8/11 significa ocho partidos históricos emparejados entre once** de English Championship en el artefacto original `MATRIX_CHAMPIONSHIP_ENRICHED_BRIDGE_WINDOWS_41652604235.json`. Nunca significó ocho variables enriquecidas entre once variables.

- Referencia original: `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ENRICHED_BRIDGE_WINDOWS_41652604235.json` (8 aprobados, 3 bloqueados).
- Diagnóstico final persistido: `evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_8_OF_11_IDENTITY_GAP_LAST.json` (8 originales y 11 aprobados en replay, tres recuperados).
- Archivo original de API-Football SHA-256: `2cfc821faab4708c646224bca62e12aefa47fbad2ad683b77fa4930e591a49f2`.
- Historial gratuito autenticado SHA-256: `28b7cfe540394b5bf1b4fec83841ce049dbf32f72d8662e4fd3811bdaf85ceff`.

## Las tres identidades físicas recuperadas

| ID API-Football | Original | ID football-data.org | Proveedor gratuito | Causa y remedio |
|---|---|---|---|---|
| 1563221 | Preston vs West Brom | 561898 | Preston North End FC vs West Bromwich Albion FC | Alias exacto West Brom → West Bromwich Albion |
| 1563222 | QPR vs Swansea | 561896 | Queens Park Rangers FC vs Swansea City AFC | Alias exacto QPR → Queens Park Rangers |
| 1563226 | Wolves vs Watford | 561903 | Wolverhampton Wanderers FC vs Watford FC | Alias exacto Wolves → Wolverhampton Wanderers |

Cada caso se emparejó **con exactamente un evento** que satisface fecha/hora de inicio y competición, con nombres de ambos equipos y orden local/visitante; el umbral de similitud volvió a superarse tras la normalización, sin usar los goles para decidir las identidades. El diagnóstico muestra `strict_name_gate_matches=1` en cada caso.

## Cambios permanentes

- `tools/matrix_championship_enriched_provider_bridge.py` incorpora únicamente tres alias explícitos para el emparejador histórico (`HISTORICAL_CALENDAR_ALIASES`), conservando todos los controles de fecha, competición, orientación, unicidad, historial y paridad.
- `tools/matrix_championship_eight_of_eleven_identity_gap_diagnostic.py` conserva el reporte original 8/11 como referencia inmutable, verifica el hash del origen gratuito y recalcula de nuevo el replay. Exige 11 partidos totales.
- `tests/test_matrix_championship_eight_of_eleven_identity_gap_diagnostic.py` verifica el nuevo 11/11 histórico y mantiene explícitos los bloqueos prospectivos.
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml` ejecuta el diagnóstico y las pruebas en el Runner Windows.
- `tools/windows/persist_matrix_browser_evidence.ps1` guarda el informe real de cada ejecución en GitHub.

## Comprobación física en GitHub Actions

- https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41762462520
- Job `collect`: `completed/success`; **91 pruebas + 23 pruebas = 114 aprobadas**.
- El JSON persistido indica `historical_paired_count=8`, `replayed_historical_paired_count=11`, `unmatched_three_repaired=true` y los tres `historical_crosswalk_recovered=true`.
- Los tres `replayed_status` son `PASS_HISTORICAL_THREE_WAY_ENRICHED_BRIDGE_ONLY`.
- `MATRIX_BROWSER_EVIDENCE_PUSHED`: persistencia física verificada.

## No confundir cierre histórico con certificación prospectiva

El calendario gratuito usado en la comparación histórica puede haber sido observado **después** del cutoff archivado `2026-10-24T09:40:17+00:00`. La reparación prueba identidad retrospectiva y paridad histórica de probabilidades en estos once encuentros; **no demuestra** que los cruces del proveedor alternativo estuvieran disponibles en una captura sellada antes del partido. No se han certificado las seis ligas ni el holdout prospectivo y no existe promoción de `p_matrix` a producción para este proveedor.

La secuencia siguiente es obtener y validar entradas enriquecidas realmente congeladas, por liga y por evento, con hashes y trazabilidad pre-kickoff, y someterlas a `tools/matrix_six_league_enriched_oos_audit.py`.

No se alteraron parámetros matemáticos ni calibraciones, no se reentrenó el modelo, no se habilitó dinero real, no se generaron apuestas ni alertas verdes. `REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `telegram_signal_authorized=false`.
