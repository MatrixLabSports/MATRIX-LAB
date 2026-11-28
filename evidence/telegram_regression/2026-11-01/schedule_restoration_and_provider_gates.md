# MATRIX — Reparación física de programación y límites de proveedor (2026-11-01)

## Tenis
- `.github/workflows/tennis-world-rolling-horizon.yml` estaba presente en `repair/cor09-world-pipeline`, ausente en `main` (consultas directas GitHub).
- Copiado sin modificar a `main`, commit `876a58640025fdb354011e04c934e7c8053b6645`.
- Relectura de `main`: existe; cron `17 */2 * * *`; checkout operativo `repair/cor09-world-pipeline`.
- Pendiente certificar primer run automático y producción de señales. Sus gates SofaScore/Flashscore, reporte diario y RapidAPI permanecen.
- El flujo `telegram-green-signals.yml` en `main` mantiene cron `7,22,37,52 * * * *` (15 minutos).

## Fútbol
- `Pillow` añadido a instalación CI en commit `ab25d1f5822a8b51151478729a61a3e35c9232c2`.
- Run posterior `41280640133`, job `124771679015`: log literal `API_FOOTBALL_PAID_WINDOW_EXPIRED_NO_RENEWAL_AUTHORIZED`. Falla el paso de suscripción, no el import PIL.
- Política de `config/MATRIX_FOOTBALL_SUBSCRIPTION_DEADLINE.json`: pago hasta 2026-10-28; sin renovación autorizada; plan gratuito sin verificación ni llamadas autorizadas.
- No saltar el guard, no realizar llamadas a API-Football no autorizadas. Evaluar fuentes independientes verificadas antes de habilitar productor.

## Resultado
- Reparación de programación TENIS: **CODED_AND_RE-READ**, no E2E.
- Reparación Pillow FÚTBOL: **CODED_AND_RUNTIME_PROGRESS_CONFIRMED**, suscripción aún bloqueada.
- Telegram: programación declarada en main cada 15 minutos, entrega real NO comprobada.
- Ninguna señal inventada. REAL_MONEY=BLOCKED, automatic_wagering=false.
