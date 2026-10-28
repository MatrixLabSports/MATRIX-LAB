# MATRIX — DOCUMENTO MAESTRO DE ARQUITECTURA COMERCIAL Y OPERATIVA V1

**Corte:** 28-OCT-2026  
**Proyecto:** MATRIX  
**Repositorio:** MatrixLabSports/MATRIX-LAB  
**Rama operativa:** repair/cor09-world-pipeline  
**Estado:** ARQUITECTURA APROBADA PARA IMPLEMENTACIÓN CONTROLADA  
**Dinero real MATRIX:** BLOQUEADO  
**Apuestas automáticas:** DESHABILITADAS

## 1. Regla cero

MATRIX no inventa picks, cuotas, resultados, ventas, miembros ni evidencia. Ninguna obligación comercial puede relajar los filtros deportivos. Si no existe una señal que supere los gates, se publica 0 PICKS. Todo dato operativo debe tener fuente física o quedar marcado PENDIENTE DE VERIFICACIÓN.

## 2. Comité élite ampliado

La arquitectura se gobierna con estos roles funcionales:

- Dirección de Producto: portafolio Free / Premium / STAKAZO.
- Dirección Cuantitativa: P_MATRIX, EV, calibración y calidad.
- Especialista de Combinadas: probabilidad conjunta y correlación.
- Chief Risk Officer: exposición, concentración y límites.
- Product Manager de Suscripciones: semanal, mensual, renovaciones y vencimientos.
- Pricing Strategist: precios, promociones y elasticidad.
- Growth & Funnel Lead: conversión Free → Premium.
- CRM / Retención: renovación, churn y cohortes.
- Telegram Automation Engineer: delivery, imágenes, resultados y membresías.
- Security Engineer: canales privados, bots, fingerprints y accesos.
- Data & Audit Lead: ledgers, hashes, evidencia y deduplicación.
- Finance / Unit Economics: ingresos, costos, margen y autofinanciación.
- Cumplimiento consumidor: publicidad, términos y condiciones.
- Juego responsable: comunicación de riesgo y mayores de edad.
- Privacidad / Seguridad de datos: minimización y acceso.
- Customer Experience: soporte y reposiciones.
- Antifraude: reventa, filtraciones y abuso de cupos.

## 3. Portafolio comercial aprobado

| Producto | Precio | Entrega | Regla de cantidad |
| --- | ---: | --- | --- |
| MATRIX FREE | COP 0 | Canal público gratuito | Hasta 4 picks/día; mínimo 0 |
| PREMIUM SEMANAL | COP 50.000 | Canal Premium | Objetivo 6–10 picks/día |
| PREMIUM MENSUAL | COP 150.000 | Canal Premium | Objetivo 6–10 picks/día |
| STAKAZO MATRIX 3X | COP 15.000 por cupo | Producto independiente | 30 cupos/día máximo |

**Regla inmutable:** “objetivo 6–10” no significa garantía de volumen. Si los gates producen menos señales, se entregan menos. Nunca se crea una señal para cumplir publicidad.

## 4. MATRIX FREE

### Objetivo
Embudo de adquisición y demostración verificable.

### Reglas
- Canal gratuito pero **PRIVADO**, no público.
- Ingreso mediante solicitud/enlace controlado.
- Máximo 4 picks válidos por día Bogotá.
- 0 PICKS permitido.
- Publica resultados cerrados del Premium para prueba social.
- Debe mostrar ganadas y perdidas; no se permite seleccionar únicamente resultados favorables.
- No revela antes del cierre los picks exclusivos del Premium.
- Ningún bot externo o agente de IA está autorizado dentro de la arquitectura MATRIX.

### Limitación técnica
No existe garantía absoluta contra fotografía externa, transcripción manual o filtración por un usuario autorizado. Por ese motivo la seguridad combina acceso privado, protección de contenido, watermark y auditoría.

## 5. MATRIX PREMIUM

### Planes
- Semanal: COP 50.000 / 7 días.
- Mensual: COP 150.000 / 30 días.

### Contenido
Objetivo operativo de 6–10 picks diarios, sujeto a disponibilidad de señales aprobadas.

### Flujo de publicación
P_MATRIX → gate deportivo → cuota exacta → EV → riesgo → PICK aprobado → imagen premium → Telegram → FINAL → imagen GANADA/PERDIDA → Telegram → ledger.

### Tarjeta Premium
Debe contener:
- MATRIX PICKS PREMIUM.
- partido;
- mercado;
- casa;
- cuota;
- hora;
- identificador verificable;
- watermark repetido;
- fingerprint opaco.

No debe revelar:
- lógica interna del modelo;
- comité;
- variables privadas;
- credenciales;
- infraestructura;
- promesas de ganancia.

## 6. STAKAZO MATRIX 3X

### Definición
Combinada especial con cuota decimal total estrictamente superior a 3.00.

### Capacidad
- 30 cupos máximos por edición diaria.
- COP 15.000 por cupo.
- Los 30 compradores reciben acceso al mismo paquete A/B/C, no 30 combinadas diferentes.

### Cadena
- A — PRINCIPAL: se entrega al comprar.
- B — RESERVA 1: se libera solo si A pierde.
- C — RESERVA 2: se libera solo si B pierde.
- Después de C termina la cobertura.

### Naturaleza de la garantía
La garantía es **de reposición de servicio**, no de ganancia.
- Máximo: 2 reposiciones.
- No se promete resultado ganador.
- No se promete recuperación económica.
- Las pérdidas anteriores permanecen en el historial.

### Requisitos temporales
B debe iniciar después de que A pueda resolverse. C debe iniciar después de que B pueda resolverse. Una cadena simultánea no es válida para reposición.

### Sellado previo
A, B y C deben existir antes de conocer el resultado de A y conservar:
- fixture IDs;
- mercados;
- cuotas;
- inputs P_MATRIX;
- inputs EV;
- kickoffs;
- timestamp;
- SHA256.

### Gate
STAKAZO_3X_READY solo puede activarse si:
- A/B/C existen;
- todas las piernas pasan MATRIX;
- cada combinada tiene cuota >3.00;
- probabilidad conjunta calculada;
- EV conjunto calculado;
- correlación revisada;
- secuencia temporal válida;
- evidencia completa.

Si falta una condición: STAKAZO_3X_NO_DISPONIBLE_HOY.

## 7. Seguridad de Telegram — MATRIX ACCESS GUARD

### Política aprobada
FREE será público. PREMIUM y STAKAZO serán privados.

- FREE prioriza alcance y adquisición.
- PREMIUM y STAKAZO priorizan control de acceso y exclusividad.

Todos:
- solicitud de ingreso o enlace controlado;
- contenido protegido;
- bots externos prohibidos;
- agentes de IA externos prohibidos;
- conectores externos prohibidos salvo aprobación explícita;
- bot MATRIX con permisos mínimos;
- allowlist de administradores/bots;
- auditoría de accesos.

### Protección de contenido
Las publicaciones del bot deben usar `protect_content=true`.

Telegram documenta que la protección de contenido reduce reenvío y guardado y, a nivel de canal/grupo, puede impedir capturas dentro de clientes compatibles. No evita una fotografía tomada desde otro dispositivo.

### Bots externos
La política MATRIX es allowlist-only. La API de bots no permite enumerar arbitrariamente todos los suscriptores ordinarios de un canal como mecanismo universal de “detección de bots”; por eso la defensa real es canal privado + join request + administradores controlados + enlaces individuales.

## 8. MATRIX MEMBERSHIP GUARD

### Estados
PENDING_PAYMENT → ACTIVE → EXPIRING_48H → EXPIRING_24H → RENEWED o EXPIRED → REMOVED_FROM_PREMIUM.

### Reglas
- Semanal: 7 días.
- Mensual: 30 días.
- Avisos: 48 h y 24 h antes del vencimiento.
- Renovación verificada: extender vigencia.
- Sin renovación al vencer: retirar automáticamente del Premium.
- Método Telegram codificado: banChatMember + unbanChatMember para retirarlo y permitir un reingreso futuro mediante nueva invitación.
- Enlace anterior debe revocarse.
- No guardar tarjetas, credenciales de pago, teléfonos ni nombres completos en el repositorio.
- Cliente identificado por ID opaco; Telegram user ID se considera dato operativo.

## 9. Arquitectura de ingresos

### Ingresos
1. Premium semanal.
2. Premium mensual.
3. STAKAZO 3X.
4. Futuras líneas aprobadas por gobierno comercial.

### Separación financiera
Los ingresos comerciales verificados son caja operativa. El P/L de apuestas PAPER/SHADOW no es ingreso operativo y no puede financiar infraestructura bajo la política de autofinanciación existente.

## 10. Publicidad y cumplimiento

### Prohibido
- “ganancia garantizada”;
- “apuesta segura”;
- “100% ganador”;
- esconder pérdidas;
- esconder condiciones esenciales;
- prometer cantidades de picks que obliguen a relajar gates.

### Permitido
- “objetivo de 6–10 picks premium diarios sujeto a señales que superen los filtros MATRIX”;
- “STAKAZO 3X incluye hasta dos reposiciones si las anteriores pierden”;
- “la reposición no garantiza un resultado favorable”;
- cupos exactos, precio y vigencia visibles.

### Base pública consultada
La SIC exige información veraz y suficiente y señala que las condiciones objetivas anunciadas obligan al anunciante; las condiciones esenciales de promociones no deben ocultarse. Coljuegos mantiene lineamientos de juego responsable. Antes del lanzamiento comercial se requiere revisión profesional colombiana final del encuadre tributario, consumidor y de juego responsable.

## 11. Automatizaciones

### Ya codificado
- Renderer PNG Premium.
- Watermark/fingerprint por signal_key.
- PICK aprobado → render Premium.
- sendPhoto Premium cuando existe chat ID.
- Workflow de resultados Premium cada 5 minutos.
- `protect_content=true` para mensajes/fotos enviados por el bot MATRIX.
- Política comercial central.
- Política de seguridad Telegram.
- Política de membresías.
- Política STAKAZO 3X.
- Guard de coherencia de arquitectura.
- Membership Guard cada 15 minutos.
- Ledger de membresías inicial vacío y sin PII.

### Implementación parcial / requiere certificación física final
- Resultado Premium actualmente conserva dependencia de API-Football en el watcher existente; la continuidad post-vencimiento requiere fallback de resultado físicamente certificado.
- El canal Premium necesita `MATRIX_PREMIUM_TELEGRAM_CHAT_ID` configurado para certificar delivery real de tarjetas.
- El Membership Guard necesita bot administrador y channel ID para certificar una expulsión real con un miembro de prueba.

### Pendiente de implementar
- Publicador MATRIX FREE con contador máximo 4/día.
- Ledger independiente FREE.
- Repost automático de resultados Premium hacia FREE.
- Generador matemático STAKAZO A/B/C.
- Gate de correlación/probabilidad/EV conjunto.
- Sellado SHA256 de A/B/C.
- Control de 30 cupos y ledger de ventas.
- Activación automática de reserva B/C.
- Creación/revocación automática de enlaces individuales.
- Auditoría de administradores/bots allowlist.
- Avisos de membresía 48h/24h.
- Checkout/pago: proveedor todavía no seleccionado.
- Revisión legal/tributaria profesional previa a lanzamiento.

## 12. Evidencia física de repositorio — corte 28-OCT-2026

Commits de esta fase:
- e0878d5e — política comercial inicial de productos.\n- 991c44b5 — corrección: MATRIX FREE pasa a canal público de adquisición.
- ded045bd — seguridad inicial de canales y bots.\n- 4a425073 — corrección: MATRIX FREE pasa a público; Premium/STAKAZO continúan privados.
- 881e5315 — política de membresías.
- cc1ac642 — política STAKAZO 3X.
- 8a91c048 — guard de invariantes comerciales.\n- 212fb0ee — guard corregido: FREE público; canales pagos privados.
- 66bb5bb3 — test del guard.
- 274c5628 — protect_content en Telegram operativo.
- 79491b56 — Membership Guard.
- 37fbf85a — test de estados de membresía.
- 0c37042a — ledger inicial de membresías.
- faafef33 — workflow Membership Guard 15m.

Evidencia Premium previamente existente:
- tools/matrix_premium_cards.py
- tools/matrix_premium_result_watcher.py
- .github/workflows/matrix-premium-results-5m.yml
- tests/test_matrix_premium_cards.py
- tests/test_matrix_premium_result_watcher.py

## 13. Criterios de lanzamiento comercial

MATRIX no pasa a lanzamiento hasta tener PASS en:
1. Canal FREE público creado, con protección de contenido y sin información exclusiva sensible.
2. Canal PREMIUM privado creado y protegido.
3. Bot MATRIX administrador con permisos mínimos.
4. Test real de pick → imagen → Premium.
5. Test real de FINAL → imagen GANADA/PERDIDA.
6. Test real de membresía de prueba vencida → retirada automática.
7. Publicador FREE 0–4/día probado.
8. STAKAZO A/B/C probado prospectivamente sin backfill.
9. Ledger de cupos y reposiciones probado.
10. Términos comerciales y revisión legal/tributaria final.
11. Pago y conciliación definidos.
12. Ningún gate deportivo relajado.
13. REAL_MONEY sigue BLOCKED.

## 14. Veredicto del comité

**ARQUITECTURA: APROBADA.**  
**IMPLEMENTACIÓN: EN CURSO.**  
**LANZAMIENTO COMERCIAL: NO-GO hasta completar los criterios del punto 13.**

La prioridad técnica inmediata es cerrar el flujo de publicación Premium y luego construir FREE y STAKAZO 3X sobre la misma infraestructura auditada, manteniendo seguridad y membresías como capas transversales.


## 15. Marca pública y adquisición — OMEGA PICKS

### Decisión de naming
La marca pública seleccionada por el comité de Naming, Brand Strategy, Sports Marketing, Diseño, Dirección de Arte y Color es **OMEGA PICKS**.

MATRIX permanece como nombre interno del motor tecnológico y de gobierno. No se utiliza como marca comercial principal ante el público.

### Arquitectura de marca
- TikTok: **OMEGA PICKS**.
- Telegram público: **OMEGA PICKS FREE**.
- Telegram privado: **OMEGA PICKS PREMIUM**.
- Producto 3X: **OMEGA PICKS 3X**.

### Jerarquía de mensajes
**Slogan principal de marca:**  
**Los datos hablan. Tú decides.**

**Frase de campaña/publicidad:**  
**El deporte se siente. Las decisiones se calculan.**

**Mensaje técnico/comercial secundario:**  
**Analizamos datos. Buscamos valor.**

### Principio de comunicación
OMEGA PICKS no se posiciona como una marca de intuición o corazonadas. Su propuesta pública se apoya en análisis estadístico, probabilidades, cuotas, valor esperado, calibración y control de riesgo. Ningún mensaje puede prometer resultado favorable, ganancia segura o certeza.

### Sistema visual
Dirección principal: símbolo **Ω** angular, fuerte y reconocible, con sensación de movimiento/avance, usable como avatar y watermark.

Paleta propuesta:
- Grafito: `#0B0D10`.
- Azul cobalto eléctrico: `#146BFF`.
- Blanco: `#FFFFFF`.

Criterio de colorimetría: contraste alto, estética sports-tech, precisión y confianza sin depender de los códigos visuales típicos de casas de apuestas. El logo debe funcionar también en una sola tinta.

### MATRIX ACQUISITION FUNNEL
**TikTok → OMEGA PICKS FREE → OMEGA PICKS PREMIUM → OMEGA PICKS 3X**

TikTok:
- máximo 1 pick gratuito diario;
- 0 picks permitido si ningún candidato supera los gates;
- resultados cerrados y contenido educativo sin revelar lógica propietaria;
- enlace al Telegram FREE.

Telegram FREE:
- público;
- hasta 4 picks diarios;
- resultados verificables;
- conversión hacia Premium.

Premium:
- privado;
- objetivo 6–10 picks/día sujeto a gates;
- membresía semanal/mensual.

OMEGA PICKS 3X:
- producto separado;
- máximo 30 cupos;
- política A/B/C ya definida.

### Roles incorporados
- Brand Identity Designer.
- Art Director.
- Color Strategist / especialista en psicología del color.
- Naming Specialist.
- Brand Strategist.
- Sports Marketing Director.
- Growth Lead.
- Sponsorship Research Analyst.
- Brand Partnerships & Sponsorship Manager.
- Paid Media Strategist.

### Verificación pendiente antes de registro/lanzamiento pago
La búsqueda web es un filtro preliminar, no una autorización marcaria. Antes de registrar o invertir en publicidad se requiere búsqueda formal de antecedentes marcarios en Colombia (SIC/SIPI), disponibilidad de usuarios sociales y dominio.


## 16. Identidad visual oficial congelada — OMEGA PICKS

**Estado:** OFFICIAL_VISUAL_IDENTITY_FREEZE — 28-OCT-2026.

### Logo
Símbolo Ω metálico integrado con una gráfica estadística ascendente.

### Paleta aprobada
- Azul Omega: `#007BFF`.
- Grafito: `#0B0D12`.
- Plata metálica: `#C0C6D1`.
- Blanco: `#FFFFFF`.
- Cian energía: `#00D6FF`.

Colores funcionales:
- Verde valor: `#00C853` — solo estados positivos/valor.
- Naranja energía: `#FF8A00` — acción/dinamismo.
- Rojo alerta: `#FF2D2D` — riesgo/alerta/pérdida.

### Mensajes oficiales
- **Marca:** Los datos hablan. Tú decides.
- **Campaña:** El deporte se siente. Las decisiones se calculan.
- **Técnico/comercial:** Analizamos datos. Buscamos valor.

### Activos canónicos
- `config/OMEGA_PICKS_BRAND_SYSTEM.json`
- `docs/OMEGA_PICKS_BRAND_BOOK_V1.md`
- `assets/brand/omega_picks/omega_picks_primary.svg`
- `assets/brand/omega_picks/omega_picks_avatar.svg`
- `assets/brand/omega_picks/omega_picks_monochrome.svg`
- `tools/omega_picks_brand_guard.py`
- `tests/test_omega_picks_brand_guard.py`

La identidad no puede cambiar por preferencia aislada sin actualizar el sistema, el guard y la evidencia.


## 17. Provisionamiento real de canales Telegram

### Estado físico
**NO_GO_AWAITING_REAL_TELEGRAM_CHANNELS**

En la verificación del 28-OCT-2026, el Browser Connector de Opera no estaba conectado y no existían en esta sesión `chat_id` verificables para los tres canales objetivo. Por lo tanto, no se afirma que los canales hayan sido creados.

### Contrato codificado
- **OMEGA PICKS FREE** — público.
- **OMEGA PICKS PREMIUM** — privado.
- **OMEGA PICKS 3X** — privado.

### Guard físico
`tools/omega_picks_channel_readiness.py` verifica los canales reales por Telegram Bot API mediante `getMe`, `getChat` y `getChatMember`.

### Secrets
- `TELEGRAM_BOT_TOKEN`
- `OMEGA_FREE_TELEGRAM_CHAT_ID`
- `MATRIX_PREMIUM_TELEGRAM_CHAT_ID`
- `OMEGA_STAKAZO_TELEGRAM_CHAT_ID`

### Workflow de certificación
`.github/workflows/omega-picks-channel-readiness.yml`

### Branding operativo
Las tarjetas y captions Premium ya fueron migrados públicamente de MATRIX a **OMEGA PICKS**. MATRIX permanece como nombre interno del motor.

### Evidencia
- `config/OMEGA_PICKS_TELEGRAM_CHANNELS.json`
- `tools/omega_picks_channel_readiness.py`
- `tests/test_omega_picks_channel_readiness.py`
- `tests/test_omega_picks_public_branding.py`
- `docs/OMEGA_PICKS_TELEGRAM_CHANNEL_SETUP.md`
- `evidence/governance/OMEGA_PICKS_CHANNEL_LAUNCH_STATE_20261028.json`

### Gate de lanzamiento
No se habilita publicación comercial hasta certificar:
1. los tres canales reales;
2. bot administrador;
3. FREE público;
4. PREMIUM/3X privados;
5. publicación de prueba;
6. FINAL → resultado;
7. Membership Guard real.
