# MATRIX — Intervención directa Over 2.5, sin promoción artificial ni cuotas inventadas

**Corte físico:** 2026-11-03 14:57:32 UTC (09:57 Bogotá) en el repositorio privado `MatrixLabSports/MATRIX-LAB`, rama `repair/cor09-world-pipeline`.

## Problema preciso

El productor matemático congelado de API-Football es distinto de la fuente de investigación football-data.org. Una coincidencia de 57/57 características de grupos históricos y 8/11 características enriquecidas retrospectivas **no** garantiza paridad prospectiva del modelo enriquecido, exportación de `p_matrix` ni autorización de envío a Telegram. La cuota global de `odds-api.net` está `BLOCKED_EXHAUSTED` tras HTTP 429 y faltan referencias Pinnacle frescas.

En el navegador real hay un adaptador certificado del mercado exacto de Betano, pero la captura anterior al inicio de ventana no halló cuotas de eventos objetivo. Otros adaptadores colombianos están en estado `CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION` y no se promueven a fuentes exactas.

## Reparación física hecha ahora: conectar seis futuros auténticos al navegador

- `tools/matrix_selfhosted_browser_quote_collector.py`, commits `d0725048` y `314bccb3`: búsqueda de precios de **investigación** del navegador prioriza paquetes inmutables `MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_*.json`, verifica las **cinco fuentes y sus hashes**, ejecuta el filtro de kickoff `scope`, y no usa archivos diarios incompatibles cuando existe evidencia atómica.
- Los seis partidos tienen IDs auténticos de football-data.org y cruces con SofaScore+Flashscore, todos con `p_matrix=None`, `research_only=true`, `production_probability_authorized=false`, `telegram_signal_authorized=false`; los hashes del paquete no se copian desde probabilidades sintetizadas.
- `tests/test_matrix_browser_independent_research_quote_targets.py` (`9ea7dded`): ensaya en horario prospectivo con evidencia real los seis targets, preserva identidad ante mutaciones del diario, rechaza paquetes alterados y resultados tras kickoff, e impide crear una señal desde investigación.
- [GitHub Actions #41658687895](https://github.com/MatrixLabSports/MATRIX-LAB/actions/runs/41658687895) **completed/success**. Runner Windows: **65 pruebas aprobadas de browser**, **23 pruebas de recuperación y cuota**, CDP `PASS_CDP_REACHABLE`, **14 páginas autorizadas capturadas**, `MATRIX_BROWSER_EVIDENCE_PUSHED`.
- El colector real terminó a `2026-11-03T14:57:32Z` con `research_only_quote_target_count=0`, `betano_exact_quote_count=0`: **era anterior al período permitido**. Esto no demuestra falta de cotizaciones futuras ni certifica precio alguno.
- [Paquete fuente auténtico #41651322786](https://github.com/MatrixLabSports/MATRIX-LAB/blob/repair/cor09-world-pipeline/evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ATOMIC_PIT_RUN_41651322786.json); los horarios del mismo registro son:
  - ID `561917` Birmingham City - Millwall, 20:00 UTC (15:00 Bogotá). Ventana de búsqueda desde 18:00 UTC (13:00 Bogotá).
  - IDs `561918` Portsmouth - Swansea; `561921` Derby - Norwich; `561922` Blackburn - Stoke; `561924` Watford - Lincoln; `561928` Charlton - Bolton, 19:45 UTC (14:45 Bogotá). Ventana desde 17:45 UTC (12:45 Bogotá).
- Son ventanas para **buscar evidencia de mercado**, nunca horario para emitir señales sin todos los gates. El recolector programado de navegador opera cada cinco minutos en `main` con checkout de la rama de investigación. No se hizo ni se permite ninguna apuesta automática.

## Qué no se ha podido certificar todavía

1. **Paridad prospectiva completa del componente enriquecido original:** requiere, para los mismos partidos, datos originales compatibles con corte PIT o una validación prospectiva formal del reemplazo con historial/holdout. Los resultados archivados comparables no sustituyen esa prueba; no se copian probabilidades de investigación al productor original.
2. **Cotización real** Over 2.5 exacta en casa elegible y **referencia sharp Pinnacle** fresca <=120 segundos: cero confirmadas al momento de la captura. La cuenta odds-api.net rechaza HTTP 429 por cuota agotada; sin reactivación verificada o proveedor sharp autorizado no existe sustituto honesto.
3. **Nuevo `p_matrix` gobernado más precio y EV aprobados** y las entradas del supervisor de Telegram: no se ha demostrado el circuito end-to-end, por lo tanto **0 BET**.

## Reglas inalteradas

`REAL_MONEY=BLOCKED`; `automatic_wagering=false`; no `p_matrix` creada de investigación; no refit, sin alterar parámetros congelados, cohortes, stakes ni CLV; no apuesta ni señal Telegram fabricada. El éxito de CI verifica software y fuentes existentes, no precios ausentes ni rentabilidad futura.
