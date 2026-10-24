# MATRIX-LAB-SPORTS — REGLA PERMANENTE DE CALENDARIO MUNDIAL DE DÍA COMPLETO V1

Fecha de incorporación: 2026-10-01
Zona horaria canónica: America/Bogota
Ámbito: FÚTBOL + TENIS
Estado: PERMANENTE / ADITIVA / NO DEROGABLE POR OPTIMIZACIONES DE RENDIMIENTO

## Regla

MATRIX debe mirar y preservar el calendario mundial completo de cada día operacional desde:

- 00:00:00 America/Bogota
- hasta 23:59:59 America/Bogota

La ventana diaria NO empieza a la hora en que corre el proceso. La hora actual solo determina qué eventos siguen siendo legalmente congelables de forma prospectiva.

## Consecuencia obligatoria

Para cada deporte deben existir dos conceptos distintos:

1. WORLD_CALENDAR_INVENTORY
   - Conserva todos los eventos descubiertos del día operacional completo 00:00:00-23:59:59 America/Bogota.
   - No destruye eventos por haber empezado, por superficie, liga, torneo, ranking, identidad, modelo o mercado.
   - Sirve para medir cobertura y detectar pérdida de calendario.

2. CALIBRATION_ELIGIBLE
   - Es un subconjunto derivado del inventario mundial.
   - Solo puede incluir eventos que pasen el dominio gobernado, identidad, historial, PIT, freeze prematch y demás gates.
   - Un evento ya iniciado nunca puede convertirse retrospectivamente en observación prospectiva.

## Fútbol

API-Football debe consultar el calendario mundial por fecha con timezone=America/Bogota y preservar el inventario de la fecha completa.

La producción prospectiva debe preparar además un horizonte adelantado para evitar llegar tarde al freeze. El inventario completo y el conjunto future/freeze-eligible deben reportarse por separado.

## Tenis

La fecha de inicio de descubrimiento se deriva de America/Bogota, NO de UTC.

Ejemplo obligatorio:
- 2026-10-02 02:30 UTC = 2026-10-01 21:30 America/Bogota.
- MATRIX debe seguir considerando 2026-10-01 como el día operacional activo hasta las 23:59:59 locales.

El universo mundial puede ser mayor que el dominio COR02/COR03. COR02/COR03 sigue siendo un subconjunto gobernado y no puede ampliar silenciosamente su dominio solo para aumentar volumen.

## Prohibiciones

- No recortar el calendario del día a "desde ahora hasta medianoche" como denominador mundial.
- No usar solo los eventos que pasaron filtros de modelo como si fueran el calendario mundial.
- No recuperar como prospectivo un evento que ya comenzó.
- No relajar identidad, PIT, superficie, tour/competición o historial para inflar el contador.
- No abrir métricas selladas ni usar resultados futuros/retrospectivos para fabricar freezes.
- No habilitar apuestas automáticas ni dinero real por esta regla.

## Evidencia mínima por ciclo

Cada ciclo debe poder demostrar:
- operational_timezone = America/Bogota
- calendar_day_start_local = 00:00:00
- calendar_day_end_local = 23:59:59
- world_calendar_count
- future_at_capture_count
- calibration_eligible_count
- frozen_count
- blocked_count y causas
- provider/network calls
- PIT/freeze integrity
- REAL_MONEY=BLOCKED mientras siga vigente el bloqueo general

## Prioridad

Esta regla manda sobre cualquier implementación anterior que derive el "día" usando UTC de forma que pueda excluir las últimas horas del día de Bogotá.
