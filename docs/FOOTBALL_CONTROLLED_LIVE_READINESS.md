# MATRIX FÚTBOL — Controlled Live Readiness Gate

## Objetivo

Este gate define cuándo un mercado de fútbol puede pasar de investigación/paper trading a **revisión controlada en vivo con aprobación humana**. No transmite apuestas, no inicia transacciones y no habilita ejecución automática.

## Principio fail-closed

La ausencia de evidencia equivale a bloqueo. No existe override por intuición, racha reciente, reputación de equipo, cuota atractiva ni presión operativa.

## Evidencia mínima por mercado

- test final temporal protegido con tamaño mínimo;
- Brier score y error de calibración dentro de política;
- superioridad frente a baseline con evidencia de incertidumbre;
- múltiples folds walk-forward sin fuga temporal;
- paper trading suficiente y mayoritariamente liquidado;
- captura de cuotas suficiente, con fuente autorizada y timestamps íntegros;
- reproducibilidad verificada mediante artefactos SHA-256;
- política de riesgo aprobada;
- kill switch verificado;
- aprobación humana obligatoria;
- revisión de cumplimiento completada;
- cero P0 abiertos;
- evidencia criptográfica mínima.

## Estados

- `BLOCKED`: falta al menos un gate.
- `CONTROLLED_LIVE_REVIEW_ELIGIBLE`: todos los gates pasaron para ese mercado concreto.

Incluso en el segundo estado, `automatic_wager_execution_enabled=False` permanece como invariante del módulo.

## Regla de promoción

La promoción es específica por mercado y versión de modelo. Validar `over_2_5` no habilita 1X2, BTTS, córners, tarjetas ni ningún otro mercado.
