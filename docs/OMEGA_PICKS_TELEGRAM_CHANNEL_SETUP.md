# OMEGA PICKS — Telegram Channel Setup Runbook V1

## Objetivo
Crear y certificar físicamente los tres canales comerciales sin inventar su existencia.

## Canales
1. **OMEGA PICKS FREE** — público.
2. **OMEGA PICKS PREMIUM** — privado.
3. **OMEGA PICKS 3X** — privado.

## Bot
Agregar el bot oficial de MATRIX/OMEGA como administrador.

Permisos mínimos:
- FREE: publicar mensajes.
- PREMIUM: publicar mensajes + gestionar miembros/invitaciones para Membership Guard.
- 3X: publicar mensajes; gestión de acceso según el producto.

No agregar bots externos.

## Secrets esperados en GitHub
- `TELEGRAM_BOT_TOKEN`
- `OMEGA_FREE_TELEGRAM_CHAT_ID`
- `MATRIX_PREMIUM_TELEGRAM_CHAT_ID`
- `OMEGA_STAKAZO_TELEGRAM_CHAT_ID`

## Certificación
Ejecutar manualmente el workflow:
`.github/workflows/omega-picks-channel-readiness.yml`

El guard verificará por Telegram API:
- identidad del bot con `getMe`;
- existencia del canal con `getChat`;
- título exacto;
- tipo `channel`;
- username público en FREE;
- membresía del bot como administrador con `getChatMember`.

## Gate
Solo cuando los tres canales den PASS:
`PASS_READY_FOR_TEST_PUBLICATION`

Luego:
1. enviar publicación de prueba;
2. certificar imagen Premium;
3. certificar resultado FINAL;
4. certificar expulsión de membresía de prueba;
5. activar publishing comercial.

Hasta entonces:
**NO_GO_AWAITING_REAL_TELEGRAM_CHANNELS**.
