# MATRIX — Diagnóstico técnico de paridad de características / 2026-11-03 UTC

## Evidencia de fuente

El certificado de tres fuentes de 2026-11-03 ha sido persistido como `evidence/football_world_inventory/2026-11-03/MATRIX_TRIPLE_SOURCE_CALENDAR_IDENTITY_CERTIFICATE.json` (commit `53a5b94ab1`). Siete partidos del calendario están identificados por football-data.org, SofaScore y Flashscore, SIN crosswalk a API-Football.

El shadow independiente `MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json` contiene conteos históricos de investigación para esos siete partidos: seis con 13 encuentros por equipo y uno con 20 encuentros por equipo. Los conteos no equivalen a observaciones históricas individuales verificadas en PIT. Los siete registros declaran `calibrated_source_parity_verified=false`.

El contrato original `app/research/football/match_analysis_input.py` exige:
- identidad y namespace de fixture/equipos, liga/temporada, `source_payload_sha256`;
- mínimo cinco observaciones históricas válidas por equipo (20 preferidas);
- observaciones individuales con goles no negativos, rival, rol de local/visitante, kickoff y marca de observación;
- historial congelado antes del inicio y conocido antes de `as_of_utc`, sin fuga futura;
- compatibilidad de características con `tools/api_football_canonicalize_analysis_inputs.py` y evaluación en `tools/api_football_prospective_market_freeze.py`.

La fuente `football-data.org` del 3 de noviembre tiene identificadores de proveedor distintos; los conteos de shadow son insuficientes para demostrar la equivalencia del histórico de calibración original. No se ha descargado/inventado una fila de modelo faltante ni reclasificado un `p_over25_research` como `p_matrix`.

## Código reproducible

- `tools/matrix_independent_feature_parity_audit.py`, commit `659fe25a`, evaluación read-only por partido con siete requisitos de evidencia pendientes.
- `tests/test_matrix_independent_feature_parity_audit.py`, commit `c56d3664`: controles de equivalencia no certificada, datos faltantes, kickoff distinto, reclasificación inválida y duplicados.
- `.github/workflows/matrix-independent-three-source-identity.yml`, commit `82953877`: genera certificado JSON histórico y prueba sus contratos (ver estado de ejecución `41579899796` antes de declarar éxito).
- `.github/workflows/matrix-selfhosted-browser-quotes-5m.yml`, commit `2a0e5444`: garantiza ejecutar nuevos tests en Runner Windows.

## Prueba física

- Windows runner: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41580047970, trabajo `125732703462`: **SUCCESS**, `49 passed in 1.50s`, CDP PASS, `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- Ciclo de recolección: 14 páginas, cero candidatos, cero precios exactos Betano. Auditoría de candidatos del supervisor anterior: obsoleta; rechazada.
- Trabajo de certificado histórico Ubuntu: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41579899796; **no darlo por completado sin revisar conclusión y artefacto**.

## Estado y paso siguiente

- Resuelto: identidad de calendario (7), integridad de diagnóstico y pruebas del puente.
- No resuelto: históricos de fútbol fuente-a-fuente con timestamp/procedencia individual verificable, crosswalk de IDs, validación OOS de paridad, fuente canónica para nuevos partidos, cuota exacta en casa autorizada, referencia sharp y señales.
- No se modifica calibración, no se completan cohortes con datos inventados, no se habilita dinero real. Estado `0 BET`.
