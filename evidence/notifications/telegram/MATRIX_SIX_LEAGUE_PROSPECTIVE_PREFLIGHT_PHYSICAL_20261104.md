# MATRIX — Certificación de alcance seis ligas: intervención y resultado físico

## Marco de trabajo
Rama `repair/cor09-world-pipeline`; intervención posterior al 11/11 histórico de Championship, que permanece cerrado como comparación retrospectiva y **no** constituye seis ligas validadas prospectivamente.

Comité funcional aplicado: procedencia de datos, ingeniería de integración, identidades deportivas, estadística/OOS, seguridad de modelos, CI Windows y gobernanza de señales Telegram. Roles metodológicos; no se afirma intervención humana externa.

## Auditoría de fuentes canónicas

- Se revisó `tools/matrix_six_league_enriched_oos_audit.py` y su contrato `MATRIX_ALTERNATIVE_PRODUCER_PROSPECTIVE_EVIDENCE_V1`. Requiere exactamente seis ligas identificadas, 30 o más filas prospectivas verificadas por liga, parejas de entradas enriquecidas iguales después de cruces de identidad, fuente original congelada, fuente alternativa congelada, resultado posterior independiente, hashes y ausencia de solapamiento con holdout.
- `evidence/football_world_inventory/2026-11-04/MATRIX_ORIGINAL_ARCHIVE_LEAGUE_DISCOVERY.json` contiene **476 grupos de liga y temporada, 475 IDs de liga distintos**. Su propio campo `six_original_leagues_confirmed=false` prohíbe interpretar ese conjunto global como la selección oficial de seis.
- `evidence/football_world_inventory/2026-11-04/MATRIX_ALTERNATIVE_PRODUCER_SCOPE_CERTIFICATE.json` indica `full_alternative_producer_certified=false`, `production_p_matrix_authorized=false`, equivalencia histórica de grupos limitada y ningún certificado prospectivo de producción.

## Reparaciones codificadas

1. `tools/matrix_six_league_prospective_preflight.py` lee el inventario original con verificación de estructura/conteos; reconoce solamente un registro explícito, único y aprobado de seis ligas, todas presentes en el archivo original.
2. La evaluación formal prospectiva solo se ejecutará si coexisten ese registro y un manifiesto de fuentes; entonces se delega al auditor ya existente, que verifica hashes de evidencia de captura y resultado, integridad de entradas enriquecidas, tiempos prematch/pospartido y no contaminación del holdout.
3. `tests/test_matrix_six_league_prospective_preflight.py` verifica que no se infieran seis ligas de un universo mayor, no se acepten cohortes duplicadas o no aprobadas, no se acepten ligas inexistentes y se rechacen contadores alterados. Se incluyen también las pruebas preexistentes del auditor de seis ligas.
4. `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml` ejecuta las pruebas y la evaluación física en Windows, como investigación; `tools/windows/persist_matrix_browser_evidence.ps1` conserva su salida junto con la captura del navegador.

## Ejecución física

- Workflow: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41764214610
- Job `collect`: `completed/success`.
- **103 pruebas de integración aprobadas + 23 adicionales = 126 pruebas aprobadas**.
- Resultado físico: `evidence/football_world_inventory/2026-11-04/MATRIX_SIX_LEAGUE_PROSPECTIVE_PREFLIGHT_LAST.json`, persistido con `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- `status=BLOCKED_PROSPECTIVE_SIX_LEAGUE_EVIDENCE_INCOMPLETE`.
- `missing_evidence=[ORIGINAL_SIX_LEAGUE_COHORT_NOT_APPROVED, PROSPECTIVE_SOURCE_SNAPSHOT_MANIFEST_MISSING]`.
- `six_league_ids=[]`; `scientific_oos_validation_passed=false`.
- `original_archive_group_count=476`; `original_archived_unique_league_count=475`.
- No se reportan «cero partidos auténticos existentes»: no tener manifiesto es **ausencia de evidencia certificable**, no demostrar la ausencia de partidos.

## Próximos insumos necesarios para continuar, sin inventar

**1. Selección de las seis cohortes:** localizar el registro previo aprobado del proyecto, si existe en GitHub o artefacto anterior; si no, se requiere una decisión explícita de alcance documentada y referenciada. No seleccionar ligas por conveniencia estadística.

**2. Capturas prospectivas originales y alternativas:** para cada evento, evidencia realmente capturada antes de kickoff del fixture, historial enriquecido completo, cruces de ID, cálculo y probabilidad de ambos lados congelados y fuente con SHA-256. Las capturas originales archivadas ya no prueban por sí solas resultados de eventos futuros.

**3. Settlement y evaluación OOS:** una vez terminados los partidos, resultados de fuente independiente, observados después del kickoff, con sus hashes originales, y exclusión de cohortes anteriores/holdout. Requiere 30+ válidos por cada una de las seis ligas bajo el contrato actual; un test sintético no es cobertura real.

## Protección

Sin cambios a parámetros congelados, evaluaciones históricas originales, fórmulas, cohortes de tenis, apuestas o Telegram. Una captura de SofaScore/Flashscore o Betano no promueve el productor. `REAL_MONEY=BLOCKED`; `automatic_wagering=false`; `production_p_matrix_authorized=false`; `telegram_signal_authorized=false`.
