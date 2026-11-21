# MATRIX — Ejecución de remediación “Nivel Sindicato” — 13-OCT-2026

## Alcance

Este artefacto ejecuta el plan de acción entregado por el usuario el 13-OCT-2026. Los archivos nombrados por el plan como `MATRIX_AUDITORIA_NIVEL_SINDICATO_13OCT2026.md` y `MATRIX_DISENO_CLV_TRACKING_13OCT2026.md` no estaban presentes en el árbol actual del repositorio al momento de la implementación; por eso la ejecución se apoya en el plan suministrado y en los contratos CLV/prospective que sí existen físicamente en MATRIX.

No se autoriza dinero real. Todo permanece en SHADOW/PAPEL.

## 1. CLV Tracking — IMPLEMENTADO Y ACTIVO

Se reutilizó el ledger prospectivo hash-chain existente y se agregó `tools/football_clv_tracking_cycle.py`.

Reglas físicas:
- entrada admitida solo si la cuota trae timestamp físico + SHA propio;
- no se reconstruyen timestamps históricos;
- referencia de cierre: Pinnacle vía API-Football, bookmaker_id=4;
- Pinnacle se usa como referencia, no como casa ejecutora;
- cierre solo prematch, dentro de la ventana gobernada final de 15 minutos;
- la cotización del proveedor Pinnacle debe tener antigüedad <=120 segundos; la banda nominal de 3 h NO cuenta como closing line;
- el mercado Over/Under 2.5 debe estar completo para hacer devig;
- se registran CLV log-price y CLV contra probabilidad de cierre devigged;
- métricas selladas hasta 300 cierres.

Primer ciclo físico: 27 decisiones congeladas, 0 cierres disponibles en la ventana del run, métricas cerradas 0/300.

## 2. Bankroll / sizing — CÓDIGO LISTO, ACTIVACIÓN BLOQUEADA

El bankroll papel actual de unidades fijas continúa siendo la autoridad mientras CLV acumula evidencia.

Se añadió `app/research/football/paper_stake_ledger.py`:
- Kelly fraccionado por defecto 1/4;
- Kelly completo prohibido;
- tope de stake papel 0.5% del bankroll;
- si CLV no está abierto o no confirma CLV positivo, el stake calculado aplicable es 0;
- ledger append-only/hash-chain;
- dinero real siempre BLOQUEADO.

No sustituye todavía la política fija de Telegram.

## 3. Sharp book — PINNACLE YA EXISTÍA Y QUEDÓ CONECTADO AL CLV

MATRIX ya tenía físicamente una capa Pinnacle de referencia vía API-Football:
- 48 fixtures;
- 4,057 cuotas de referencia;
- 17 mercados;
- `direct_pinnacle_api_connection=false`;
- odds nunca generan P_MATRIX.

El nuevo CLV usa `source_quality_flag=SHARP_PINNACLE_VIA_API_FOOTBALL_STRICT_120S`. La infraestructura Pinnacle existente es válida como referencia, pero su auditoría histórica reportó 0 cotizaciones que cumplieran el gate estricto de 120 s; por tanto, el feed de cierre sharp todavía debe demostrarse prospectivamente y no se relaja el gate para fabricar CLV.

## 4. Riesgo correlacionado — MOTOR LISTO, LÍMITES NO INVENTADOS

Se añadió `app/research/football/correlated_exposure.py`.

Agrupa exposición por:
- fixture;
- torneo + día;
- día operacional.

No existen límites por defecto. La activación exige que el equipo fije explícitamente los máximos, como ordena el plan. Hasta entonces el módulo está diseñado/testeado pero no conectado a señales.

## 5. Cobertura — NO SE ABREN MERCADOS NUEVOS

La premisa antigua de “SofaScore fútbol 140 lower-bound / Mostrar más” fue corregida físicamente:
- SofaScore fútbol exacto: 138;
- SofaScore tenis: 603;
- Flashscore fútbol: 78;
- Flashscore tenis: 326;
- `calendar_baseline_complete=true`.

Las diferencias entre fuentes pasan a reconciliación browser→APIs.

Lanes actuales:
- Team Fouls: 1/30;
- Team Total Shots Home: 0/30;
- Team Total Shots Away: 0/30;
- BTTS: `BLOCKED_NEW_CHALLENGER_REQUIRED`.

No se habilita expansión adicional.

## 6. Robustez estadística — PROTOCOLO CONGELADO

Se creó `docs/governance/MATRIX_REGIME_WALK_FORWARD_PROTOCOL_V1.json`.

Estado actual:
- tenis COR02/COR03: 212/600, métricas selladas;
- Team Fouls: 1/30;
- Team Shots: 0/30.

Cuando abran los gates, la evaluación será cronológica y por régimen con Brier, Log Loss, ECE y Maximum Calibration Error. Un régimen degradado se documenta; no se retunea el incumbent sobre su propia validación.

## 7. Velocidad / ejecución — DIFERIDA

No se automatiza bet placement ni se invierte en latencia de ejecución mientras MATRIX siga en SHADOW/PAPEL.

La activación futura exige previamente:
1. CLV validado;
2. sizing validado en papel;
3. límites de correlación aprobados;
4. autorización futura explícita de gobernanza.

## Estado global

`INFRASTRUCTURE_REMEDIATED_CLV_EVIDENCE_ACCUMULATING_DOWNSTREAM_ACTIVATION_GATED`

Esto significa que las brechas de infraestructura/gobernanza ya tienen implementación física, pero no se finge que la evidencia estadística CLV ya existe: el gate sigue sellado hasta completar la muestra prospectiva requerida.
