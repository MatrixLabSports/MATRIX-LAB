# MATRIX — Auditoría de los tres faltantes del indicador histórico 8/11

Fecha: 2026-11-04 UTC; alcance: verificación de contratos, no promoción estadística.

## Hallazgo exacto, sin atribuir cifras incorrectas

La afirmación histórica "8/11 características enriquecidas retrospectivas" consta en `MATRIX_OVER25_SOLUCION_SIN_DATOS_INVENTADOS_20261103.md`, pero en los artefactos de paridad consultados **no aparece una comparación campo por campo de esas 11 características** que identifique qué tres valores difirieron. Por tanto, no existe evidencia física suficiente para asignar un nombre a las supuestas tres diferencias. Se prohíbe presentar los tres grupos de trabajo de abajo como si fueran las tres diferencias cuantitativas observadas.

La prueba 57/57 se refiere a `RAW_GROUP_PIT`; `tools/matrix_independent_over25_historical_parity.py` advierte expresamente que no certifica `CANONICAL_ENRICHED_PIT`. `tools/matrix_independent_feature_parity_audit.py` requiere crosswalk de identidad, historial nativo de al menos cinco partidos por equipo, timestamps de observación, hashes del payload y no solapamiento con el holdout.

## Tres grupos concretos comprobables, NO tres diferencias identificadas

1. **`home_history`**: recuperar al menos cinco partidos previos auténticos del local, con ID único, equipo, rival, localía, goles, hora real y fecha de actualización observada antes del congelamiento. Un historial parcial de la misma liga podría omitir partidos de copa u otras competiciones incluidos por el proveedor original.
2. **`away_history`**: mismo contrato para el visitante. No imputar cinco partidos ni mezclar nombres y proveedores como si fueran IDs estables.
3. **`prematch_lineage`**: cotejar nombres y namespaces del proveedor original con el gratuito, cotejar hashes de captura y constatar evidencia disponible **antes del corte de análisis**. El campo `lastUpdated` solo prueba fecha de actualización indicada por el proveedor, **no** que MATRIX capturó los datos en esa fecha.

## Fuentes gratuitas y alcance

- football-data.org, documentación oficial: `/v4/competitions/{code}/matches?season=YYYY`, `/v4/teams/{id}/matches`, campos `utcDate`, `status`, `score.fullTime`, `homeTeam.id`, `awayTeam.id`, `lastUpdated`. Posible reconstrucción retrospectiva de historial de goles para **competiciones realmente cubiertas**; disponibilidad por plan y completitud de cada una de las seis ligas no han sido probadas. El plan gratuito documenta 10 solicitudes/minuto. Referencias: https://www.football-data.org/documentation/quickstart y https://docs.football-data.org/general/v4/match.html y https://docs.football-data.org/general/v4/policies.html.
- SofaScore/Flashscore: cotejo calendario de partidos y nombres; no equivalen a historial nativo puntual sin evidencias observadas y respaldos congelados.
- TheSportsDB: documenta calendarios e históricos con límites gratuitos; **no** se ha demostrado que devuelva los mismos historiales de los seis campeonatos ni timestamps de captura PIT, por lo que no se autoriza como equivalente. https://www.thesportsdb.com/documentation

## Implementación realizada

- `tools/matrix_independent_enriched_gap_feasibility.py` evalúa historial bruto **de investigación** sin recalcular `p_matrix`. Rechaza resultados futuros, ausencia de marcador final, filas duplicadas, hora `lastUpdated` desconocida o posterior al corte, y cuentas insuficientes.
- `tests/test_matrix_independent_enriched_gap_feasibility.py` exige fallar cerrado sin paridad original; incorporado al workflow Windows.
- No se han usado llaves privadas ni fuentes pagas; el auditor solo admite archivos proporcionados. No se han hecho llamadas nuevas a football-data.org desde el ejecutor Windows por esta implementación.
- Para conseguir la comparación legítima de **las 11 variables por nombre**, hace falta ubicar el artefacto original que generó el conteo 8/11, o volver a calcular el diferencial sobre los **mismos partidos** con los dos bundles enriquecidos preservados al corte PIT. Nunca derivar diferencias de una evaluación histórica de grupos.

## Estado

`ENRICHED_11_FIELD_DIFF_NOT_LOCATED`; 3 grupos operativos identificados, 0 de 3 diferencias específicas verificadas. La reconstrucción técnica del historial está implementada como evaluador de viabilidad **no certificado**; falta probar datos nativos PIT reales de cada equipo y liga. `p_matrix` de reemplazo no autorizada. Parámetros congelados, cohortes y protección de Telegram intactos; `REAL_MONEY=BLOCKED` y `automatic_wagering=false`.

## Certificación de ejecución Windows — posterior a la reparación de tests

- GitHub Actions: https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41760356062
- Estado del job `collect`: **completed/success**.
- Pruebas: **89 passed** de contratos del navegador y análisis (incluyendo las 8 nuevas), **23 passed** del control prospectivo PIT y de cuotas, **112 aprobadas en total**.
- Resultado del sincronizador: `NO_GOVERNED_CANONICAL_ROWS`, `candidate_count=0`, `telegram_signal_authorized=false`, `real_money=BLOCKED`.
- `MATRIX_BROWSER_EVIDENCE_PUSHED`: persistencia confirmada.
- Fallo inicial detectado y reparado: el ejemplo de cinco partidos incluyó fechas futuras, correctamente rechazadas por el auditor. Se corrigió el dato de ensayo a octubre, **sin relajar los controles temporales**; commit `e5f96f6c`.
- No implica nueva captura nativa de football-data.org, identificación de los tres campos distintos ni aprobación estadística del proveedor alternativo.
