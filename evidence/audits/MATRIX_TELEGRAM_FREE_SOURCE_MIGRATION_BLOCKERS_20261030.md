# MATRIX — Bloqueos de migración a fuentes independientes (30-OCT-2026)

Repositorio: MatrixLabSports/MATRIX-LAB. Rama: repair/cor09-world-pipeline.

## Evidencia leída del código

1. `tools/telegram_green_signal_alerts.py` blob `cd52c1bf85632d489ae10bdb0f92d27ce78b8476`: `main()` dispone de dos modos offline que terminan antes de red y envío; el modo normal exige `MATRIX_API_FOOTBALL_AUTHORIZED=1` y después exige `API_FOOTBALL_KEY`. Ningún modo offline es envío operativo.
2. El mismo supervisor define `discover_football` y `discover_tennis`, y contiene consultas a API-Football en rutas de fixture/odds y referencia Pinnacle. El método `paid_football_quote_transport_allowed` rechaza consultas de cuotas pagas tras la fecha límite.
3. `.github/workflows/telegram-green-signals.yml` blob `b31fb31868ab142191222381d10cd02a2cbbff65`: contiene una etapa de diagnóstico independiente, seguida del gate `--require-paid-use --require-key` y la validación obligatoria de `API_FOOTBALL_KEY` antes del supervisor normal.
4. `.github/workflows/matrix-independent-source-offline-check.yml` blob `d067cf094c6595ab760812f90dc64620019cf0a2`: workflow manual `workflow_dispatch`, sin secretos de proveedores y sin llamadas operativas; verifica gobernanza offline, no entrega Telegram.
5. `tools/football_subscription_deadline_guard.py` blob `8caf5b57742b5b481cd91998d35e531b799dcf6a`: `evaluate_independent_sources` explícitamente marca cobertura gratuita 2026 como no verificada y no autoriza consultas de red.

## Causa y plan seguro

El sistema conserva **dos gates independientes** para la API paga (workflow y supervisor) y una dependencia obligatoria de la clave en el modo normal. El diagnóstico independiente no equivale a migración operativa. No basta con quitar el gate del workflow: es necesario demostrar que todas las rutas de consulta que puedan ejecutarse sin la API paga están separadas y que las rutas de datos actuales y cuotas exactas cuentan con fuentes autorizadas.

Orden de trabajo: (1) ejecutar pruebas offline; (2) auditar rutas de red y dependencias; (3) diseñar adaptador explícito por proveedor con allowlist, trazabilidad y bloqueo ante ausencia de datos; (4) probar con fixtures controlados, sin red ni Telegram; (5) ejecutar integración con fuentes verificadas; (6) certificar logs de scheduler y entrega/0 BET.

## Estados que NO se pueden declarar

- No hay prueba en esta auditoría de cobertura de temporada 2026 por API-Football gratuito.
- No hay prueba de que el workflow manual se haya ejecutado exitosamente.
- No hay prueba de envío de mensajes a Telegram tras el vencimiento.
- No se ha habilitado ninguna fuente nueva, renovado una API, ni promovido mercados.

## Reglas preservadas

SofaScore y Flashscore primero para calendario; luego fuentes autorizadas. Cuota estrictamente mayor que 1.50, valor esperado positivo, mercado promovido explícitamente, validación de cuota exacta y frescura, deduplicación, `REAL_MONEY=BLOCKED`, `automatic_wagering=false`. Datos faltantes no se convierten en ceros ni se imputan silenciosamente.
