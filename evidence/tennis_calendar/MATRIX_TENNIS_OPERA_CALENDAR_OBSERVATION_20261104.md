# MATRIX TENIS — Comprobación del calendario del 4 de noviembre de 2026 en Opera

Fuente primaria 1: https://www.sofascore.com/es/tennis (pestaña Opera 2017708789).
Fuente primaria 2: https://www.flashscore.co/tenis/ (pestaña Opera 2017708388, selector visible: «miércoles, 4 de noviembre de 2026»).

Lectura directa del árbol de accesibilidad de las dos pestañas. En ese momento se identificaron **589 enlaces de encuentros /tennis/match/** en SofaScore y **678 enlaces /partido/tenis/** en Flashscore. **No son conteos de partidos únicos, certificados, de un único día, ni un cruce de los dos proveedores**. El calendario puede incluir marcadores en vivo, torneos múltiples, enlaces de portada y duplicados.

## Evidencia representativa de SofaScore

| Encuentro mostrado | Identificador enlace |
|---|---|
| Alexander Zverev — Lorenzo Musetti | https://www.sofascore.com/es/tennis/match/lorenzo-musetti-alexander-zverev/nTxspvec#id:17428224 |
| Novak Djokovic — Rinky Hijikata | https://www.sofascore.com/es/tennis/match/rinky-hijikata-novak-djokovic/HXfscZUb#id:17428208 |
| Alex Michelsen — Carlos Alcaraz | https://www.sofascore.com/es/tennis/match/alex-michelsen-carlos-alcaraz/ytkcsDJmd#id:17428221 |
| Alex Molčan — Taylor Fritz | https://www.sofascore.com/es/tennis/match/alex-molcan-taylor-fritz/RvebsFcib#id:17428228 |

## Evidencia coincidente de enlaces visibles en Flashscore

| Encuentro mostrado | Referencia |
|---|---|
| Alexander Zverev — Lorenzo Musetti | https://www.flashscore.co/partido/tenis/musetti-lorenzo-xtH2ODVI/zverev-alexander-dGbUhw9m/ |
| Novak Djokovic — Rinky Hijikata | https://www.flashscore.co/partido/tenis/djokovic-novak-AZg49Et9/hijikata-rinky-f9eT4NTQ/ |
| Alex Michelsen — Carlos Alcaraz | https://www.flashscore.co/partido/tenis/alcaraz-garfia-carlos-UkhgIFEq/michelsen-alex-nDIhfm9l/ |
| Alex Molčan — Taylor Fritz | https://www.flashscore.co/partido/tenis/fritz-taylor-UH09iaZ6/molcan-alex-drgiRTl7/ |

**Tipo de coincidencia:** nombre de ambos competidores en enlaces visibles de ambos proveedores; no se ha verificado aún el emparejamiento de IDs, el inicio UTC, la condición prematch de cada enlace ni la superficie. Estos encuentros son *referencias de trabajo*, no candidatos certificados.

## Reglas de ingreso para MATRIX TENIS

1. Mantener SofaScore y Flashscore como primeras fuentes del calendario. Filtrar por día Bogotá 2026-11-04, singles/dobles y competición antes de contar eventos únicos.
2. Comparar identidades de jugadores, torneo y kickoff UTC. Registrar discrepancias sin emparejamiento difuso.
3. Verificar superficie Hard/Clay y distinguir partidos prematch y LIVE, resultados finales, aplazados y cancelados.
4. Completar historiales auténticos para las matrices originales; preservar parámetros y ventanas originales, no reconstruir datos prematch usando resultados posteriores.
5. No generar ninguna señal verde de Telegram a partir de links, calendarios u odds mostradas sin probabilidad certificada, cuota exacta auténtica >1.50, EV positivo, referencia sharp fresca y bloqueo de kickoff.
6. Mantener `automatic_wagering=false`, `real_money=BLOCKED`.

**Estado:** pestañas y fechas verificadas en Opera; conjunto completo de fixtures normalizado e incorporado al productor canónico: PENDIENTE DE VERIFICACIÓN. Señales autorizadas desde este inventario: 0 (no evaluadas).
