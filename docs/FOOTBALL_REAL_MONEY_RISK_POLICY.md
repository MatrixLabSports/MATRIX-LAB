# MATRIX FÚTBOL — Política de riesgo para CONTROLLED_LIVE

## Estado

Este módulo **no ejecuta apuestas**. Solo evalúa si una candidata que ya superó el gate científico puede llegar a revisión humana para una eventual apuesta manual y limitada.

## Principios fail-closed

1. Sin evidencia prospectiva aprobada, no hay dinero real.
2. Sin fuente de cuotas autorizada y timestamp fresco, no hay entrada.
3. Sin calidad de datos y revisión de cumplimiento, no hay entrada.
4. Cualquier kill-switch activo bloquea la operación.
5. Martingala, persecución de pérdidas y aumento de stake para recuperar pérdidas están prohibidos.
6. Kelly completo está prohibido. El valor por defecto es 0.25 Kelly, además limitado a 0.5% del bankroll por apuesta.
7. Exposición diaria máxima por defecto: 2% del bankroll.
8. Exposición por mercado máxima por defecto: 1% del bankroll.
9. Exposición total abierta máxima por defecto: 2% del bankroll.
10. Drawdown diario de 3% o drawdown desde máximo de 8% activa kill-switch.
11. Cuota pre-match con más de 30 s o live con más de 5 s se considera obsoleta por defecto.
12. La aprobación humana queda ligada a fixture, mercado, selección, versión de modelo, probabilidad, cuota, timestamp, evidencia y stake mediante SHA-256.
13. La aprobación expira y no debe reutilizarse.
14. `automatic_wager_execution_enabled` permanece siempre en `False`.

Los umbrales son parámetros de gobierno conservadores y deben revisarse con evidencia. No constituyen una promesa de rentabilidad.
