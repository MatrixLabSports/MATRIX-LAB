# MATRIX — Corte de regresión Telegram (2026-11-01)

## Evidencia comprobada
- GitHub Actions ejecución 41278175728, trabajo 124764509167: conclusión SUCCESS, 13 pruebas aprobadas. **Son pruebas de contratos/diagnóstico; no demuestran envío a Telegram.**
- GitHub Actions ejecución 41277425224, trabajo 124762327992: conclusión SUCCESS, 13 pruebas aprobadas.
- Código actual: `tools/telegram_green_signal_alerts.py::discover_tennis` consume `evidence/tennis_signals/<fecha>/*.json` y filtra `governance_status` en VALIDATED/STRONG/PROMOTED, `physical_quote_verified=true`, `p_matrix`, `decimal_odds>1.50`, `ev>0`, identificador, mercado y selección.
- Los pagos RapidAPI Tennis Ultra aportados por el usuario no prueban por sí mismos que la ejecución de MATRIX obtenga datos. No atribuir el bloqueo a una suscripción vencida.

## Lo que NO se ha demostrado
- Última ejecución histórica con un envío de Telegram confirmado por registro y su SHA.
- Primera ejecución fallida posterior y diferencia de configuración, código y archivos canónicos.
- Estado actual de respuesta de RapidAPI Tennis desde el ejecutor de MATRIX.
- Existencia de candidatos canónicos actuales que cumplan los filtros, ni confirmación de envío Telegram.

## Procedimiento obligatorio para cerrar la regresión
1. Localizar run histórico con evidencia de entrega Telegram (no confundir éxito del workflow con envío).
2. Conservar run ID, job ID, SHA, fecha, conteos y log redactado sin secretos.
3. Localizar run actual equivalente y comparar SHA, variables no secretas, estado del scheduler, datos de entrada y conteos por filtro.
4. Verificar transporte RapidAPI Tennis Ultra desde el ejecutor autorizado sin revelar tokens.
5. Corregir **solo** el primer punto de divergencia demostrado; agregar prueba de regresión y CI.
6. Certificar extremo a extremo con log de candidato autorizado y resultado de envío, o registrar cero candidatos y razones. Dinero real BLOQUEADO; apuestas automáticas deshabilitadas.

**Estado:** REGRESIÓN NO CERRADA. No declarar Telegram reparado con solo pruebas unitarias.
