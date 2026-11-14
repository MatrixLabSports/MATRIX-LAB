# MATRIX — Inspección Opera de evento Luckia — 2026-10-30

## Fuente observada
Conector Opera, solo lectura, pestaña de evento `2017707560`:
`https://www.luckia.co/apuestas/eventos/espana-laliga-fc-barcelona-deportivo-alaves/12220141/?feedProviderId=1`

La página se abrió mediante navegación de Opera a partir del enlace de evento identificado en el árbol de accesibilidad de Luckia. No se introdujeron credenciales ni se realizaron apuestas.

## Datos verificados en el árbol de accesibilidad
- Página de evento para **FC Barcelona / Deportivo Alavés**, según URL y nombres visibles.
- Categorías y mercados visibles: `Menos/Más goles`, `1ª mitad Menos/Más goles`, `2ª mitad Menos/Más goles`, `Menos/Más goles Equipo local`, `Menos/Más goles Equipo visitante`.
- Aparecen etiquetas `Menos` y `Más` y múltiples cifras decimales en el árbol, pero NO se certificó un vínculo inequívoco entre mercado, línea 2.5, selección y cuota.
- La presencia de muchos mercados similares y cuotas hace insegura cualquier extracción por texto global o posición de números.

## Estado y decisión
`luckia.adapter_status=CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION` (sin cambio de configuración).
`exact_over25_quote_certified=false`.
`provider_freshness_certified=false`.
`telegram_delivery_certified=false`.
`real_money=BLOCKED`; `automatic_wagering=false`.

## Requisitos antes de habilitar
1. Aislar el contenedor estructural del mercado `Menos/Más goles` del partido exacto.
2. Identificar la línea `2.5`, selección `Más` y cuota decimal en un único contenedor; rechazar ambigüedad.
3. Verificar fecha/hora del partido y momento de captura; bloquear partidos comenzados.
4. Construir pruebas offline de extracción y rechazo usando una muestra sanitizada y reproducible.
5. Ejecutar validación prospectiva; no usar esta inspección para generar señales.
