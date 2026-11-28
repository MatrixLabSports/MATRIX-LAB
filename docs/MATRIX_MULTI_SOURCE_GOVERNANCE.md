# MATRIX-LAB-SPORTS — Gobernanza Multifuente Permanente

**Versión:** 1.0.0  
**Vigencia:** 2026-10-04  
**Zona horaria canónica:** America/Bogota  
**Alcance actual:** tenis y fútbol.

## Regla constitucional

Para tenis y fútbol, MATRIX-LAB-SPORTS debe trabajar con **todas las fuentes que tenga gestionadas y disponibles**, tanto pagas como gratuitas/públicas, respetando el rol y la autoridad de cada fuente.

Ninguna API, web, navegador, proveedor, casa o dataset individual puede sustituir a las demás ni declarar por sí solo `WORLD_COMPLETE`.

Una fuente accesible no puede omitirse silenciosamente. Si una fuente no responde, no cubre el evento, está bloqueada, exige autenticación, alcanza límite o no es utilizable, ese estado debe quedar físicamente registrado. La producción continúa con las demás fuentes, pero la ausencia queda trazada.

## Contrato obligatorio de reconciliación

El orden general es:

`fan-out multifuente → inventario por fuente → identidad canónica → reconciliación de aliases → dedupe físico → discrepancias persistidas → adjudicación → preregistro → PIT → modelo/freeze`.

Los conteos de proveedores permanecen separados hasta después de deduplicar. Está prohibido sumar conteos brutos de distintas fuentes o convertir el inventario de un proveedor en inventario mundial.

Las discrepancias de nombres, IDs, horarios, ronda, superficie, competición, ranking, lineup o estadísticas no se resuelven por overwrite silencioso. Deben persistirse y adjudicarse.

## Tenis

Fuentes estructuradas pagas obligatorias cuando estén disponibles:
- RapidAPI Tennis.
- API-Tennis.

Fuentes gratuitas/públicas y de navegador:
- SofaScore.
- Flashscore.
- ATP oficial.
- WTA oficial.
- ITF oficial.

Datasets históricos públicos gestionados:
- Jeff Sackmann.
- Tennis-Data.

Para COR02/COR03, ninguna ampliación de discovery cambia el dominio protegido:
`ATP Challenger + Hard + Singles + Match Winner`.

SofaScore/Flashscore/ATP/WTA/ITF pueden descubrir, confirmar y enriquecer, pero **no pueden saltarse** identidad, ranking PIT, histórico PIT, R218/R223, freeze prematch ni dedupe.

## Fútbol

Fuente estructurada paga principal:
- API-Football.

Fuentes gratuitas/públicas y de navegador:
- SofaScore.
- Flashscore.
- Fuentes oficiales de competición/equipo cuando corresponda.

Fuente de referencia de mercado:
- Pinnacle, solo referencia; no autorización de ejecución.

Fuentes de precio/ejecución gestionadas:
BetPlay, bwin, Betano, RushBet, Betsson, Codere, Luckia, MrYoker, Rivalo, Sportium, Stake Colombia, Wplay, YaJuego y Zamba.

Cada mercado conserva su propia gobernanza; una fuente de discovery o precios no genera P_MATRIX ni rellena features faltantes.

## Reglas que no cambian

- PIT estricto y anti-leakage.
- Missing != 0.
- No imputación silenciosa.
- No name-only joins.
- No odds → P_MATRIX.
- Freeze estrictamente prematch y luego inmutable.
- Settlement FINAL_ONLY.
- Dedupe físico antes de aumentar contadores.
- Proveniencia física y timestamp por dato.
- REAL_MONEY = BLOCKED.
- automatic_wagering = false.

El archivo machine-readable canónico de esta política es:
`config/matrix_multisource_registry.json`.
