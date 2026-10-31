# MATRIX — Inspección física de Opera: Codere, Luckia y Wplay

Fecha de inspección: 2026-10-30 (fecha de conversación; hora exacta no certificada).
Rama: `repair/cor09-world-pipeline`.

## Método
- Conector Opera: `list_tabs` y `tab_content` (árbol de accesibilidad).
- Solo lectura. No se introdujeron credenciales, no se realizaron apuestas ni se alteraron las páginas.
- No se extrajeron ni guardaron cuotas de ejecución.

## Evidencia observada
| Casa | Pestaña Opera | Observaciones |
|---|---:|---|
| Codere | 2017707265 | Página deportiva abierta; navegación DEPORTES, DIRECTO, buscador «Buscar eventos, partidos, juegos...», ligas y categorías. |
| Luckia | 2017707266 | Página de apuestas abierta; navegación y campo «Busca por equipo o deportista...». |
| Wplay | 2017707271 | Página de apuestas abierta; enlaces a eventos, buscador «Buscar eventos, juegos», formato decimal y zona GMT -5 visibles. |

## Limitaciones y reglas de certificación
- El árbol de accesibilidad es evidencia de acceso y estructura de interfaz, NO evidencia de una cuota exacta, actual, única o vinculada a mercado.
- No se certificaron selectores por partido, mercado, línea 2.5 ni selección «Más de 2.5».
- No se comprobó vigencia de cotización, referencia sharp ni entrega Telegram.
- Los adaptadores Codere, Luckia y Wplay permanecen `CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION`.
- Prohibido declarar `CERTIFIED_EXACT_OVER25` hasta tener prueba reproducible de identidad de evento, mercado, selección, precio y momento de captura.
- `real_money=BLOCKED`; `automatic_wagering=false`.

## Próximo paso
Abrir un partido futuro identificado en cada casa, inspeccionar solo su árbol accesible y comprobar la cadena completa evento → mercado → selección → cuota, sin inferirla de texto global de página. Registrar una muestra sanitizada y pruebas de rechazo de ambigüedad.
