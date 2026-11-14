# MATRIX — Intervención: búsqueda del evento Betano por enlace visible

**Fecha:** 2026-11-03 (Bogotá). **Rama:** `repair/cor09-world-pipeline`.

## Evidencia anterior al cambio
El archivo `evidence/notifications/telegram/MATRIX_BROWSER_CDP_COLLECTION_LAST.json` guardó una extracción de investigación para Fenerbahçe SK vs Liverpool FC: mercado exacto Más de 2,5, precio 1.40, evento 91590438. Fue una lectura histórica, no una cuota ejecutable, porque no había `p_matrix` gobernada y la cuota era inferior al mínimo 1.50. También conservaba 14 páginas capturadas y cero cuotas de ejecución.

## Defecto corregido en código
El recolector `tools/matrix_selfhosted_browser_quote_collector.py` buscaba eventos principalmente en respuestas de destacados. Ahora también puede inspeccionar enlaces de partido **visibles y ya renderizados en Betano**, aun cuando no haya respuesta de destacados. Limita candidatos, exige ambas identidades de equipo y una ruta de evento numérica de Betano bajo HTTPS. La extracción final sigue requiriendo abrir el detalle y corroborar su título, mercado y selección. No realiza apuestas, ni evita controles antibot.

## Pruebas agregadas
`tests/test_matrix_betano_visible_event_links.py`: enlace válido, coincidencia de ambos equipos, rechazo de hosts/esquemas/rutas no autorizados y límite de candidatos.

## Alcance y bloqueos que NO se levantaron
Este cambio aumenta las rutas de descubrimiento de evento; **no** demuestra cobertura completa, ni certifica BetPlay ni otras casas. Para obtener nueva evidencia física hace falta una ejecución del runner conectado al navegador, durante una ventana de eventos, que registre la captura y el resultado de las pruebas. El cambio de código no prueba por sí mismo que aparezcan cuotas futuras.

Se mantienen: equivalencia prospectiva original pendiente, probabilidad `p_matrix` de producción no autorizada, referencia sharp Pinnacle fresca no acreditada, `REAL_MONEY=BLOCKED`, apuestas automáticas deshabilitadas, mínimo de cuota mayor a 1.50, bloqueo por kickoff y ausencia de señales verdes salvo que se cumplan los controles originales.

**Estado:** cambio codificado; ejecución real con esta versión y suite de pruebas en runner: PENDIENTE DE VERIFICACIÓN.
