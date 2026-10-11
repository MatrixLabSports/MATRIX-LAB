# MATRIX LIVE TENIS v0.1 — CONTRATO DE INVESTIGACIÓN

Estado: RESEARCH_ONLY / REAL_MONEY=BLOCKED
Fecha de inicio: 2026-10-06
Zona horaria operativa: America/Bogota

## Objetivo

Construir y calibrar un modelo separado del prematch que estime:

P_LIVE(P1 gana el partido | estado live observado)

El modelo LIVE no modifica, reabre ni reemplaza ninguna probabilidad prematch congelada.

## Unidad de observación

Una observación calibrable es un ESTADO LIVE ÚNICO, no una llamada HTTP.

Clave física mínima:
- provider = live_tennis_api
- match_id
- sequence

Si dos capturas tienen el mismo match_id + sequence, son duplicados de transporte y solo una puede entrar al ledger de estados únicos.

La evaluación OOS deberá agruparse por match_id. Estados del mismo partido nunca pueden repartirse entre train y test.

## Separación de dominios

Captura: singles de ATP/WTA/Challenger/ITF cuando la fuente los exponga.
Modelado: por carriles separados de tour/género/superficie hasta que exista evidencia suficiente para justificar pooling.
No se mezclan silenciosamente ITF mujeres, ITF hombres, Challenger ATP, ATP y WTA.

## Variables permitidas v0.1

Identidad/contexto:
- match_id
- tour
- tournament
- round / round_code
- surface
- player names
- rankings visibles en la captura

Estado:
- sequence
- sets P1/P2
- games por set P1/P2
- diferencial de sets
- diferencial de games acumulado
- diferencial de games del set actual
- puntos actuales P1/P2
- servidor
- is_tiebreak
- deciding_set rule/basis

Calidad/provenance:
- captured_at_utc
- accepted_at
- timestamp
- age_seconds
- observed_age_seconds
- corroborated
- sources_count
- stale
- response_sha256

## Prohibiciones

- No usar odds para generar P_LIVE.
- No usar resultado final antes del settlement.
- No backfill retroactivo de estados que nunca fueron capturados.
- No imputación silenciosa.
- Missing != 0.
- No mezclar estados live con el modelo prematch.
- No contar snapshots repetidos como nuevas observaciones.
- No evaluar snapshots del mismo partido en train y test.
- No apuestas automáticas.
- REAL_MONEY=BLOCKED.

## Resultado / settlement

La etiqueta de entrenamiento se incorpora solo cuando el partido está FINAL:
- p1_match_win = 1 si P1 ganó el partido
- p1_match_win = 0 si P2 ganó
- retirados, walkovers, abandonos o estados ambiguos se manejan en carriles explícitos y no se silencian.

## Fases

A. Captura raw append-only.
B. Dedupe por match_id + sequence.
C. Extracción de features PIT.
D. Settlement FINAL-only.
E. Dataset agrupado por match.
F. Baseline experimental.
G. Validación OOS por match y por bandas de estado.
H. Challenger y calibración.
I. Solo después de gates explícitos puede discutirse promoción.

## Primer artefacto físico

Partido 200549 — Anna Pushkareva vs Duru Soke.
Seis snapshots raw capturados; sequences observados 104, 104, 105, 105, 105, 106.
Por tanto, el seed correcto contiene 3 estados live únicos, no 6.
