# MATRIX — Contrato de persistencia honesta
**Establecido por el usuario:** 17 de noviembre de 2026 (America/Bogota).
**Ámbito:** todo trabajo futuro sobre MATRIX: fútbol, tenis Hard/Clay/Live, datos, calibraciones, PIT, CLV, cuotas, Telegram, infraestructura, auditorías y anexos.
**Naturaleza:** contrato de proceso y reporte; no constituye un certificado técnico ni modifica ningún gate de producción.

## Principio rector
Agotar vías **legítimas y viables** antes de concluir que una reparación está bloqueada, sin inventar ni extrapolar evidencia. El objetivo final en Telegram es la recepción verificable de una señal simulada auténtica: identidad canónica certificada, datos PIT anteriores al inicio, probabilidad P_MATRIX oficial, cuotas reales frescas de casa autorizada, referencia sharp válida, EV positivo y todos los gates vigentes satisfechos. Un mensaje de prueba o un workflow «SUCCESS» no equivale a esa recuperación.

## Obligaciones de investigación, implementación y persistencia
1. **Continuidad:** leer el estado y los hashes disponibles antes de actuar. Preservar logros, parámetros congelados, archivos originales y ejecuciones previas; no iniciar MATRIX desde cero.
2. **Tres vías razonables cuando existan:** para cada bloqueo registrar y evaluar la vía primaria y al menos dos alternativas legítimas materialmente distintas. Si no existen tres accesibles, registrar cada vía accesible y el motivo concreto de las no disponibles. Ninguna regla exige hacer peticiones a un servicio sin autorización o con cuota agotada.
3. **Fuente prioritaria:** SofaScore y Flashscore primero, después fuentes estructuradas gratuitas con cobertura vigente y autorización demostrada (por ejemplo football-data.org, TheSportsDB); API-Football 2026 no se presumirá accesible. No eludir términos de servicio, bloqueos ni límites de cuota.
4. **Reintentos justificados:** si falla una primera ejecución por temporalidad, transporte, dependencia, scheduler o evidencia insuficiente, repetir tras cambiar una condición pertinente y conservar el historial. No declarar imposibilidad por un solo intento; tampoco afirmar haber ejecutado futuros ciclos que todavía no se han producido.
5. **Cobertura exhaustiva:** revisar el universo real del pedido (por ejemplo los 45 registros, o seis ligas por separado), salvo que una limitación documentada impida su cobertura. Una muestra se identifica siempre como muestra; las respuestas parciales de API no prueban inexistencia en todo el proveedor.
6. **Separación de estados:** «implementado», «prueba unitaria aprobada», «ejecución completa exitosa», «evidencia física admitida», «PIT certificado», «modelo autorizado», «cuota verificada», «mensaje Telegram recibido» y «objetivo cumplido» son estados distintos.
7. **Evidencia por afirmación:** ruta del archivo, rama, commit, SHA-256 o SHA de blob, ejecución, marca de tiempo UTC/Bogotá, denominador y conteo exacto. Cuando falte evidencia, marcar «NO VERIFICADO», «BLOQUEADO» o «NO DETERMINABLE» y explicar el motivo; jamás sustituirlo por cero.
8. **Integridad PIT:** no imputar, completar con valores por defecto, reciclar observaciones, reconstruir después del kickoff o convertir resultados postpartido en predicciones prospectivas. Timestamp y procedencia por variable, con control de identidad y orden temporal.
9. **Protección irreversible sin autorización:** no cambiar parámetros calibrados, no promover mercados, no relajar puertas de calidad, no odds→P, no apostar dinero real automáticamente. Mantener REAL_MONEY=BLOCKED y automatic_wagering=false. Investigación no puede depositar candidatos autorizados en carpetas de producción.
10. **Gobierno de cuotas:** fuente exacta, bookmaker permitido, mercado/selección coincidente, hora de captura, frescura y referencia sharp; cuota mayor que 1.50, EV y mínimos vigentes según el gate real. Rechazo si falta dato.
11. **Protección de credenciales:** no copiar tokens, chat IDs, claves de proveedores ni información privada a commits o informes. Verificar delivery mediante identificadores de mensajes únicamente cuando un envío real esté autorizado y confirmado.
12. **Sin éxitos semánticos falsos:** código existente o tests exitosos no certifican funcionamiento extremo a extremo; un commit exitoso no certifica envío ni disponibilidad futura. No tratar «sin candidatos» como «no hay cuotas en el mercado».
13. **Continuidad entre conversaciones:** registrar resultados y bloqueos comprobables con referencia a las evidencias auténticas en GitHub y paquete de entrega. Un resumen o plantilla no sustituye los archivos de datos reales.

## Registro de intento por bloqueo (mínimo)
- Fecha UTC y Bogotá; objetivo específico; universo y denominador exactos.
- Vía intentada y por qué era legítima; URI/endpoint/código autorizados; rama y commit.
- Prueba física: respuesta HTTP, JSON bruto y hash, salida de comando, job/run, marcas de captura y kickoff, o evidencia documental equivalente.
- Resultado exacto: candidatos, certificados por nivel, rechazados por causal, no evaluados.
- Fallo técnico y causa comprobada (sin conjetura); siguiente alternativa distinta; fecha de reintento solo si efectivamente programada.
- Decisión: RESUELTO CON EVIDENCIA / PARCIAL CON EVIDENCIA / BLOQUEADO POR LIMITACIÓN REAL / SIN EVIDENCIA SUFICIENTE.
- Guardrails comprobados: calibración intacta, sin promociones, sin apuestas reales, sin datos imputados.

## Mínimos para informar que Telegram volvió a funcionar
Todos deben estar comprobados en **el mismo candidato** y en secuencia anterior al kickoff:
1. Fixture de producción con identidad independiente y horario de fuentes concordantes.
2. Variables PIT completas y originales; captura y archivo SHA previo al partido.
3. Motor gobernado original, parámetros congelados y P_MATRIX oficial con trazabilidad.
4. Cuota ejecutable auténtica de bookmaker colombiano permitido, referencia sharp fresca, EV y umbrales satisfechos.
5. Gates de identidad, temporalidad, riesgo, cuotas, frescura y duplicados aprobados.
6. Mensaje real devuelto como aceptado por Telegram y, donde sea posible, verificado en ledger/recepción (sin exponer el token).
7. Ninguna apuesta automática real; informe exacto con hashes y ejecución.

**Si falta cualquiera:** no declarar señales verdes recuperadas.

## Reporte obligatorio
| Apartado | Contenido |
|---|---|
| OBJETIVO | Criterio de éxito, no objetivo decorativo |
| ESTADO | Resuelto / Parcial / Bloqueado / Sin verificar |
| UNIVERSO | Denominador total, fuente y restricciones de cobertura |
| EVIDENCIA | Archivos, commits, SHA, run IDs y marcas de tiempo |
| VÍAS | Primaria, alternativa 2, alternativa 3, y reintentos realizados realmente |
| RESULTADOS | Conteos exactos por etapa y causal de rechazo |
| PROTECCIONES | Comparación de calibraciones y señales con estado anterior |
| LÍMITE REAL | Datos inaccesibles, proveedores bloqueados, cuota vencida, falta de PIT, etc. |
| ACCIÓN CONCRETA | El siguiente trabajo ejecutable sin falsear el estado |

## Salvedad expresa
Este documento registra la disciplina exigida; por sí solo **no ejecuta los controles automáticamente**, no certifica un productor ni activa Telegram. La conformidad se demuestra al ejecutar el proceso y presentar el expediente físico correspondiente.

## Anexo permanente — MATRIX Híbrida Élite (19 de noviembre de 2026)

El contrato complementario [MATRIX_RETO_CONTRATO_PERMANENTE_HIBRIDA_V1.md](MATRIX_RETO_CONTRATO_PERMANENTE_HIBRIDA_V1.md)
forma parte obligatoria del mismo reto, no es un proyecto opcional. En cada
revisión se deben conservar y reportar los cuatro bloques (fútbol Over 2.5;
Challenger Hard; Challenger Clay; Live Tennis), el inventario completo de
42 mercados, los motores híbridos de investigación, la evaluación
prospectiva y los bloqueos hasta cierre legítimo.

El control físico automatizado se define en
`tools/matrix_hybrid_permanent_challenge_guard.py` y
`.github/workflows/matrix-hybrid-permanent-challenge-guard.yml`.
La ejecución exitosa del guardián **no significa** que las probabilidades
híbridas estén certificadas ni que Telegram pueda emitir señales.
