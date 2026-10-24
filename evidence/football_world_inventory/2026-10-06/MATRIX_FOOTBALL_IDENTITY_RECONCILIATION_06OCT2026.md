# MATRIX-LAB-SPORTS — Reconciliación de identidad fútbol 06-OCT-2026

Dictamen gobernado: la cobertura browser y la identidad modelable se mantienen separadas. SofaScore mostró 860 partidos / 290 competiciones, Flashscore 209 visibles, API-Football recibió 200 y produjo 146 futuros con identidad, 138 PIT-ready y 132 candidatos gobernados de freeze. De esos 132, 118 ya existían y 14 fueron freezes nuevos; hubo 0 colisiones físicas.

Los 6 gaps browser-only se probaron con 14 llamadas de binding: 4 quedaron BLOCKED_TEAM_BINDING y 2 BLOCKED_NO_EXACT_FIXTURE_ON_DATE. Se promovieron 0 por nombre. football-data.org respondió HTTP 200 autenticado pero 0 partidos accesibles para la fecha y world_complete=false.

Mercados: Over 2.5 ACTIVE_V2/STRONG (425 freezes, 222 settlements, 203 pendientes); 1X2 ACTIVE_V2/DEVELOPING (425/222/203); Player Shots v3 DEVELOPING (0 freezes, requiere lineup y línea real); Team Total Shots Home/Away DEVELOPING (0 freezes, requieren línea canónica + PIT actual); Team Fouls Total DEVELOPING (1 freeze, 0 calibraciones).

Número que manda para el ciclo: 132 eventos alcanzaron el gate de candidatos de freeze; no equivale a 132 apuestas ni 132 observaciones nuevas. Protecciones intactas: no backfill, Missing≠0, sin imputación silenciosa, sin join por nombre, dedupe físico antes del contador, no odds→P_MATRIX, métricas selladas, automatic_wagering=false, REAL_MONEY=BLOCKED.
