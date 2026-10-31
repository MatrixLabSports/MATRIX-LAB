# MATRIX — Reconciliación física de calendarios 20-OCT-2026

Fecha operativa: 20-OCT-2026
Zona horaria operativa: America/Bogota
Rama: repair/cor09-world-pipeline
Regla de fuentes: SofaScore -> Flashscore -> otras fuentes/API -> reconciliación -> identidad/PIT -> P_MATRIX -> freeze -> cuotas/EV -> riesgo -> Telegram.

## Evidencia física de navegador
Opera mostró como pestaña activa:
- SofaScore fútbol: https://www.sofascore.com/es/football/2026-10-20

El calendario de tenis para 20-OCT-2026 fue verificado además por la página pública:
- https://www.sofascore.com/es/tennis/2026-10-20

## Fútbol — reconciliación de control
SofaScore 20-OCT-2026 muestra 9 partidos de UEFA Champions League:
Fenerbahçe-Slavia Praha; Sabah-Dortmund; Roma-Slovan Bratislava; Porto-PSV; Liverpool-Villarreal; Manchester City-AEK; PSG-Barcelona; Napoli-Bodø/Glimt; Stuttgart-Atlético Madrid.

Flashscore reproduce los mismos 9 partidos para 20-OCT-2026.
Resultado del control de identidad del bloque UEFA Champions League: 9/9 coincidentes.

Fuentes:
- SofaScore: https://www.sofascore.com/es/football/2026-10-20
- Flashscore: https://www.flashscore.com/football/europe/champions-league/fixtures/

## Tenis — reconciliación de control
SofaScore 20-OCT-2026 muestra, entre otros:
- Almaty ATP 250: 5 individuales.
- Brussels ATP 250: el agregado visible reporta 8 y contiene una cancelación Rune-Collignon.
- Lyon ATP 250: 8 individuales en la vista actual verificada.
- Ningbo WTA 500: 9 entradas, con cancelaciones registradas.
- Osaka WTA 250: 11 entradas en una vista actual, incluyendo una suspensión y una cancelación.
- Challenger/ITF y dobles adicionales.

Flashscore confirma eventos de control del 20-OCT-2026:
- Shimabukuro-Safiullin (Almaty).
- Ann Li-Emerson Jones (Osaka).
- Putintseva-Shnaider y Paolini-Kalinina (Ningbo).
- Griekspoor-Schoenhaus (Brussels).
- Calendario ATP: Almaty, Brussels y Lyon activos del 19 al 25 de octubre.

### Hallazgo de integridad
El agregado de SofaScore para Brussels puede quedar incompleto en una captura/indexación puntual:
- Flashscore lista además Goffin-Bertola.
- La página individual de SofaScore confirma Goffin-Bertola para 20-OCT-2026 a las 10:00 UTC.
Por gobernanza, no se permite interpretar ausencia en el agregado como ausencia real del evento.

Regla aplicada:
1. Si SofaScore agregado y Flashscore discrepan, NO se elimina el evento.
2. Se busca página individual / segunda fuente.
3. El evento se incorpora solo con identidad y fecha confirmadas.
4. Cancelados/suspendidos se marcan explícitamente y no pasan a freeze prematch normal.
5. Sin identidad suficiente -> NO SIGNAL.

Fuentes:
- SofaScore tenis: https://www.sofascore.com/es/tennis/2026-10-20
- SofaScore Goffin-Bertola: https://www.sofascore.com/tennis/match/remy-bertola-david-goffin/Nqksicib
- Flashscore Brussels: https://www.flashscore.com/tennis/atp-singles/brussels-2025/fixtures/
- Flashscore ATP calendar: https://www.flashscore.com/tennis/calendar/atp/

## Estado de gate
- Calendarios físicamente encontrados: SI.
- SofaScore consultado primero: SI.
- Flashscore usado como segunda fuente: SI.
- Discrepancia detectada y documentada: SI.
- Imputación silenciosa: NO.
- Eventos cancelados/suspendidos tratados como normales: NO.
- Cuotas usadas para construir P_MATRIX: NO.
- Señales autorizadas solo por calendario: NO.

Estado: CALENDAR_RECONCILIATION_EVIDENCE_READY.
Antes de una señal, cada candidato debe completar PIT, P_MATRIX congelada, cuota ejecutable, EV positivo y riesgo correlacionado.
