# MATRIX — Luckia: alcance real del árbol de accesibilidad (30-OCT-2026)

## Evidencia física
Inspección de solo lectura en Opera, pestaña 2017707560, página de evento FC Barcelona / Deportivo Alavés. Consulta estructurada `tab_content_jq_search_query` sobre el árbol de accesibilidad.

Se observó un nodo `genericContainer` con tres hijos: contenedor id 4266, texto `Menos/Más goles` y nodo imagen id 4271. El título del mercado es accesible, pero este contenedor de título **no incluye** directamente línea, selección ni cuota.

El árbol del evento también expone un contenedor id 3970 con 1618 hijos y múltiples apariciones de `2.5`, precios decimales y otros mercados. Este contenedor **no es una unidad certificada de mercado**; la proximidad entre elementos no prueba correspondencia.

## Diagnóstico
- Evidencia suficiente para identificar el título del mercado: **SÍ**.
- Evidencia suficiente para asociar unívocamente `Más` + `2.5` + precio: **NO**.
- Evidencia suficiente para certificar frescura, inicio futuro, comparación sharp y entrega Telegram: **NO**.
- Estado Luckia: `CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION`; sin autorización para emitir cuotas.
- No se registran precios inferidos ni credenciales.
- Dinero real BLOQUEADO; apuestas automáticas desactivadas.

## Condición de salida
Requiere evidencia DOM/estructura de un contenedor individual de mercado con selección y precio inequívocos; prueba negativa ante duplicados y mercados de primera/segunda mitad; validación prospectiva de evento/horario y frescura. Hasta entonces, prohibido promover el adaptador.
