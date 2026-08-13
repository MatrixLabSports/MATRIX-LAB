# DATA DICTIONARY — MATRIX TENIS

## 1. Propósito

El presente documento define el diccionario formal de datos de MATRIX TENIS.

Su objetivo es establecer una definición única, verificable y trazable para los datos utilizados por la plataforma, evitando ambigüedades semánticas, inconsistencias entre módulos y utilización de información cuyo significado, procedencia o calidad no pueda determinarse.

Ningún dato deberá utilizarse en procesos críticos únicamente porque esté disponible.

Todo dato relevante deberá poseer una definición explícita, un tipo esperado, reglas de validación, procedencia identificable y condiciones conocidas de utilización.

El diccionario constituye una referencia contractual para los componentes de ingesta, almacenamiento, procesamiento, análisis, modelado, riesgo, auditoría y presentación de MATRIX TENIS.

---

## 2. Alcance

Este diccionario cubrirá progresivamente los datos relacionados con:

- identificación de jugadores;
- identificación de partidos;
- torneos y competiciones;
- superficies y condiciones de juego;
- fecha, hora y localización;
- formato y ronda;
- resultados históricos;
- forma reciente;
- estadísticas de servicio;
- estadísticas de devolución;
- historial por superficie;
- fatiga y carga competitiva;
- contexto competitivo;
- datos de mercado y cuotas;
- información disponible antes del partido;
- información generada durante el partido;
- decisiones analíticas;
- señales y estados operativos;
- cobertura y calidad de datos;
- procedencia de la información;
- timestamps y temporalidad;
- resultados observados;
- evidencia utilizada para validación y auditoría.

La incorporación de nuevas categorías deberá realizarse de forma controlada y documentada.

---

## 3. Principios fundamentales de datos

### 3.1 Definición antes de utilización

Ningún campo crítico deberá incorporarse a una decisión sin conocer claramente qué representa.

### 3.2 Procedencia verificable

Todo dato relevante deberá poder relacionarse, cuando sea técnicamente aplicable, con su fuente o mecanismo de generación.

### 3.3 Temporalidad explícita

Deberá distinguirse entre:

- cuándo ocurrió un evento;
- cuándo fue observado;
- cuándo fue recibido;
- cuándo fue almacenado;
- cuándo fue utilizado por el sistema.

Esta distinción será especialmente importante para impedir sesgos retrospectivos y fuga de información futura.

### 3.4 Separación entre dato observado y dato derivado

Los datos obtenidos directamente de una fuente deberán diferenciarse de métricas, estimaciones, probabilidades o señales calculadas por MATRIX TENIS.

### 3.5 Ausencia no equivale a cero

Un dato desconocido, no disponible o no recibido no deberá representarse automáticamente como cero.

### 3.6 Validación proporcional al riesgo

Los datos utilizados en decisiones de mayor impacto deberán estar sujetos a controles de calidad más rigurosos.

### 3.7 Inmutabilidad histórica

Los datos históricos utilizados como evidencia no deberán modificarse silenciosamente.

Toda corrección material deberá conservar trazabilidad suficiente para reconstruir qué información estaba disponible originalmente.

### 3.8 No utilización de información futura

Ningún proceso de evaluación histórica, entrenamiento, backtesting o validación podrá utilizar información que no hubiera estado disponible en el momento real de la decisión evaluada.

### 3.9 Evolución controlada del esquema

Los cambios en nombres, significado, tipos, unidades, reglas o estructura de campos deberán gestionarse de forma explícita y auditable.

### 3.10 Calidad antes que volumen

La disponibilidad de grandes cantidades de datos no justificará su utilización si su calidad, significado, temporalidad o procedencia son insuficientes.

---

## 4. Contrato formal de datos

Todo campo incorporado formalmente a MATRIX TENIS deberá poseer una especificación suficiente para determinar qué representa, cómo debe interpretarse y bajo qué condiciones puede utilizarse.

La profundidad de la especificación será proporcional a la criticidad del dato.

### 4.1 Atributos mínimos de un campo

Cuando sean aplicables, deberán documentarse los siguientes atributos:

1. **nombre canónico:** identificador oficial y único utilizado por el sistema;
2. **nombre descriptivo:** denominación comprensible para documentación e interfaces;
3. **definición:** significado exacto del campo;
4. **dominio:** entidad o contexto al cual pertenece;
5. **tipo de dato:** tipo lógico esperado;
6. **unidad:** unidad de medida cuando corresponda;
7. **nulabilidad:** determina si la ausencia del valor está permitida;
8. **valores permitidos:** dominio, enumeración, rango o restricciones válidas;
9. **fuente:** origen primario o mecanismo mediante el cual se obtiene;
10. **método de captura:** API, proveedor, carga manual, cálculo interno u otro mecanismo autorizado;
11. **temporalidad:** momento al que representa el dato;
12. **timestamp de observación:** momento en que el dato fue observado por el sistema;
13. **timestamp de recepción:** momento en que fue recibido;
14. **timestamp de almacenamiento:** momento en que quedó persistido;
15. **frecuencia de actualización:** periodicidad esperada;
16. **reglas de validación:** controles necesarios antes de aceptar el valor;
17. **reglas de calidad:** condiciones para determinar su aptitud de uso;
18. **tratamiento de ausencia:** comportamiento cuando el valor no está disponible;
19. **transformaciones:** operaciones aplicadas desde el dato original;
20. **dependencias:** campos o procesos necesarios para producirlo o interpretarlo;
21. **consumidores:** componentes autorizados que utilizan el campo;
22. **criticidad:** impacto potencial de un error en el dato;
23. **sensibilidad:** clasificación aplicable desde seguridad y privacidad;
24. **procedencia:** información necesaria para reconstruir su linaje;
25. **versión de esquema:** versión contractual bajo la cual se interpreta;
26. **estado:** condición de gobierno del campo;
27. **responsable:** rol encargado de mantener su definición;
28. **evidencia de validación:** referencia a pruebas o controles que respaldan su utilización.

No todos los campos requerirán materializar físicamente cada atributo dentro de una misma estructura de almacenamiento.

Sin embargo, los atributos necesarios para interpretar, validar, auditar y reproducir correctamente un dato crítico deberán estar disponibles mediante metadatos, contratos, registros o documentación controlada.

### 4.2 Nombre canónico

El nombre canónico deberá ser estable, inequívoco y suficientemente descriptivo.

No deberán coexistir múltiples nombres oficiales para representar exactamente el mismo concepto sin una regla explícita de compatibilidad o migración.

Los alias provenientes de proveedores externos deberán mapearse al nombre canónico interno sin eliminar la posibilidad de reconstruir el valor y denominación originales.

### 4.3 Tipo lógico y representación física

El tipo lógico de un dato no deberá confundirse con su representación física.

Por ejemplo, una fecha podrá recibirse originalmente como texto, pero su contrato deberá establecer que conceptualmente representa una fecha o instante temporal.

Las conversiones entre representaciones deberán ser deterministas, validadas y trazables cuando afecten datos críticos.

### 4.4 Unidades

Todo dato cuantitativo cuya interpretación dependa de una unidad deberá declarar dicha unidad explícitamente.

No deberán combinarse silenciosamente valores expresados en unidades incompatibles.

Toda conversión de unidades utilizada en procesos analíticos deberá ser reproducible.

### 4.5 Nulabilidad y ausencia

La ausencia de información deberá distinguirse de valores legítimos como:

- `0`;
- `False`;
- cadena vacía cuando esta posea significado contractual;
- empate;
- resultado neutral.

Cuando resulte necesario, deberán diferenciarse causas de ausencia tales como:

- dato no disponible;
- dato todavía no recibido;
- dato no aplicable;
- dato rechazado por calidad;
- dato desconocido;
- dato pendiente de confirmación.

### 4.6 Datos observados, normalizados y derivados

MATRIX TENIS deberá distinguir, cuando sea aplicable, entre:

- **RAW:** dato recibido de la fuente;
- **NORMALIZED:** dato transformado a la representación canónica interna;
- **DERIVED:** dato calculado a partir de otros datos;
- **MODEL_OUTPUT:** estimación o resultado producido por un modelo;
- **DECISION_OUTPUT:** señal o decisión generada por el sistema.

Una transformación no deberá provocar que un dato derivado sea presentado como si hubiera sido observado directamente.

### 4.7 Criticidad del dato

Los datos podrán clasificarse, como mínimo, en:

- **CRITICAL**
- **HIGH**
- **MEDIUM**
- **LOW**

La criticidad deberá considerar el efecto potencial de errores sobre:

- decisiones analíticas;
- probabilidades;
- evaluación de valor;
- gestión de riesgo;
- decisiones relacionadas con dinero;
- integridad histórica;
- entrenamiento y validación de modelos;
- auditoría;
- operación del sistema.

Los controles deberán aumentar proporcionalmente a la criticidad.

---

## 5. Estado de implementación de los datos

El diccionario deberá distinguir claramente entre datos actualmente implementados y capacidades futuras.

Los estados mínimos serán:

- **IMPLEMENTED** — existe representación explícita en el software actual.
- **PARTIAL** — existe representación parcial, pero faltan elementos contractuales relevantes.
- **PLANNED** — capacidad prevista pero todavía no implementada.
- **DERIVED** — dato calculado internamente a partir de otros datos.
- **EXTERNAL** — dato esperado desde una fuente externa o proveedor.
- **DEPRECATED** — dato cuya utilización debe eliminarse progresivamente.

La documentación de un campo como PLANNED o EXTERNAL no implicará que MATRIX TENIS ya disponga de dicho dato.

---

## 6. Entidades y campos actualmente implementados

Esta sección documenta únicamente estructuras cuya existencia ha sido verificada en el código actual de MATRIX TENIS.

### 6.1 TennisMatchContract

**Estado:** IMPLEMENTED
**Implementación:** `app/sports/tennis/contract.py`

Representa el contrato básico de identidad deportiva de un partido de tenis.

| Campo | Tipo actual | Estado | Definición contractual actual |
| --- | --- | --- | --- |
| `player1` | `str` | IMPLEMENTED | Primer jugador identificado en el contrato del partido. |
| `player2` | `str` | IMPLEMENTED | Segundo jugador identificado en el contrato del partido. |
| `tournament` | `str` | IMPLEMENTED | Nombre del torneo asociado al partido. |
| `surface` | `str` | IMPLEMENTED | Superficie declarada para el partido. |

Reglas actualmente verificadas:

- `player1` no puede estar vacío;
- `player2` no puede estar vacío;
- `tournament` no puede estar vacío;
- `surface` no puede estar vacía;
- `player1` y `player2` no pueden representar al mismo jugador ignorando mayúsculas y minúsculas.

### 6.2 TennisMatchModel

**Estado:** IMPLEMENTED / PARTIAL
**Implementación:** `app/sports/tennis/match_model.py`

Representa información operativa adicional de un partido.

| Campo | Tipo actual | Estado | Definición contractual actual |
| --- | --- | --- | --- |
| `contract` | `TennisMatchContract` | IMPLEMENTED | Contrato base del partido. |
| `tour` | `str` | PARTIAL | Circuito o tour declarado para el partido. |
| `round` | `str` | IMPLEMENTED | Ronda competitiva del partido. |
| `datetime` | `str` | PARTIAL | Representación textual actual de fecha y hora del partido. |
| `status` | `str` | IMPLEMENTED | Estado operativo del partido. |

Valores permitidos actualmente para `status`:

- `scheduled`
- `live`
- `finished`
- `retired`
- `walkover`
- `cancelled`

Valores permitidos actualmente para `round`:

- `Q1`
- `Q2`
- `Q3`
- `R128`
- `R64`
- `R32`
- `R16`
- `QF`
- `SF`
- `F`

`status` se valida utilizando normalización mediante `strip().casefold()`.

`round` se valida utilizando normalización mediante `strip().upper()`.

La semántica contractual completa de `tour` y `datetime`, incluyendo catálogo, formato temporal y zona horaria, permanece pendiente de definición reforzada.

### 6.3 Superficie

**Estado:** IMPLEMENTED
**Control actual:** `TennisDataQualityEngine.ALLOWED_SURFACES`

Valores actualmente aceptados:

- `hard`
- `clay`
- `grass`
- `carpet`

La validación actual normaliza el valor mediante eliminación de espacios exteriores y comparación sin distinguir mayúsculas y minúsculas.

La existencia de este catálogo no implica todavía una política completa de normalización entre proveedores externos.

### 6.4 TennisHistoricalMatch

**Estado:** IMPLEMENTED / PARTIAL
**Implementación:** `app/sports/tennis/historical_match.py`

Representa un partido histórico desde la perspectiva de un jugador.

| Campo | Tipo actual | Estado | Definición contractual actual |
| --- | --- | --- | --- |
| `player` | `str` | IMPLEMENTED | Jugador desde cuya perspectiva se registra el partido. |
| `opponent` | `str` | IMPLEMENTED | Rival del jugador registrado. |
| `date` | `str` | PARTIAL | Fecha histórica del partido en representación textual actual. |
| `tournament` | `str` | IMPLEMENTED | Torneo del partido histórico. |
| `surface` | `str` | IMPLEMENTED | Superficie del partido histórico. |
| `won` | `bool` | IMPLEMENTED | Indica si el jugador registrado ganó el partido. |
| `sets_won` | `int` | PARTIAL | Sets ganados por el jugador registrado. |
| `sets_lost` | `int` | PARTIAL | Sets perdidos por el jugador registrado. |
| `games_won` | `int` | PARTIAL | Games ganados por el jugador registrado. |
| `games_lost` | `int` | PARTIAL | Games perdidos por el jugador registrado. |

Reglas actualmente verificadas:

- `player` no puede estar vacío;
- `opponent` no puede estar vacío;
- `player` y `opponent` no pueden ser iguales ignorando mayúsculas y minúsculas.

Las restricciones numéricas, consistencia entre resultado y marcador, formato temporal y normalización completa permanecen pendientes de endurecimiento contractual.

### 6.5 TennisPlayerHistory

**Estado:** IMPLEMENTED
**Implementación:** `app/sports/tennis/player_history.py`

Representa el historial disponible de un jugador.

Campos principales:

- `player: str`
- `matches: tuple[TennisHistoricalMatch, ...]`

Ventanas históricas estándar actualmente implementadas:

- `5`
- `10`
- `20`
- `30`
- `50`

Estas ventanas representan cantidades máximas de partidos recientes solicitados.

La existencia de una ventana no implica por sí sola que todas las métricas deportivas profesionales estén disponibles para dicha ventana.

### 6.6 TennisDataCoverage

**Estado:** IMPLEMENTED
**Implementación:** `app/sports/tennis/data_coverage.py`

Representa disponibilidad de categorías de evidencia mediante indicadores booleanos.

Campos actuales:

- `recent_form`
- `surface_history`
- `serve_stats`
- `return_stats`
- `fatigue_context`
- `market_data`

Todos los campos deben ser exactamente booleanos.

El método `score()` calcula la proporción de categorías de evidencia disponibles.

Este valor representa **cobertura de datos**, no calidad, confiabilidad, probabilidad de acierto ni poder predictivo.

### 6.7 Regla de interpretación

La presencia de una categoría de cobertura como `serve_stats=True` significa únicamente que el sistema considera disponible esa categoría de evidencia.

No significa que el modelo de datos actual ya almacene explícitamente todas las estadísticas detalladas de servicio, tales como:

- aces;
- dobles faltas;
- porcentaje de primeros servicios;
- puntos ganados con primer servicio;
- puntos ganados con segundo servicio;
- hold percentage.

Estas variables deberán documentarse como IMPLEMENTED únicamente cuando exista evidencia directa de su representación y validación en el software.

---

## 7. Trazabilidad de análisis y resultados de procesamiento

### 7.1 TennisAnalysisContext

**Estado:** IMPLEMENTED
**Implementación:** `app/sports/tennis/analysis_context.py`

Representa el contexto auditable e inmutable asociado a una ejecución de análisis de MATRIX TENIS.

| Campo | Tipo actual | Estado | Definición contractual actual |
| --- | --- | --- | --- |
| `analysis_id` | `str` | IMPLEMENTED | Identificador único de la ejecución de análisis. |
| `created_at` | `datetime` | IMPLEMENTED | Momento UTC asociado a la creación del contexto. |
| `engine_version` | `str` | IMPLEMENTED | Versión declarada del motor que ejecuta el análisis. |
| `policy_version` | `str` | IMPLEMENTED | Versión declarada de la política aplicada al análisis. |

Reglas actualmente verificadas para `analysis_id`:

- debe ser de tipo `str`;
- debe representar un UUID válido;
- debe utilizar el formato canónico de UUID.

Reglas actualmente verificadas para `created_at`:

- debe ser una instancia de `datetime`;
- debe contener información de zona horaria;
- su desplazamiento UTC debe ser exactamente cero.

Reglas actualmente verificadas para `engine_version`:

- debe ser de tipo `str`;
- no puede estar vacío;
- no puede contener espacios exteriores.

Reglas actualmente verificadas para `policy_version`:

- debe ser de tipo `str`;
- no puede estar vacío;
- no puede contener espacios exteriores.

La clase está definida como `frozen=True`, por lo que su representación mediante dataclass es inmutable después de su creación.

El método de clase `create()` genera actualmente:

- un nuevo `analysis_id` mediante UUID4;
- `created_at` mediante la hora actual en UTC;
- las versiones de motor y política proporcionadas a la operación.

Este contexto constituye una base de trazabilidad técnica. Su existencia no demuestra por sí sola que todos los artefactos, datos de entrada, decisiones y resultados del análisis estén todavía enlazados de extremo a extremo.

### 7.2 TennisProcessingResult

**Estado:** IMPLEMENTED / PARTIAL
**Implementación:** `app/sports/tennis/processing_result.py`

Representa el resultado actual de una operación de procesamiento de MATRIX TENIS.

| Campo | Tipo declarado | Estado | Definición contractual actual |
| --- | --- | --- | --- |
| `accepted` | `bool` | PARTIAL | Indica la decisión de aceptación declarada por el procesamiento. |
| `reason` | `str` | PARTIAL | Razón textual declarada para el resultado. |
| `confidence` | `float` | IMPLEMENTED / PARTIAL | Valor numérico de confianza declarado por el procesamiento. |

`confidence` tiene actualmente un valor predeterminado de `0.0`.

La validación explícita actualmente verificada exige:

```text
0.0 <= confidence <= 1.0
```

Los valores fuera de ese intervalo producen un `ValueError`.

### 7.3 Semántica de confidence

El campo `confidence` no deberá interpretarse automáticamente como:

- probabilidad calibrada de victoria;
- probabilidad real del evento;
- edge frente al mercado;
- expected value;
- certeza estadística;
- garantía de acierto;
- recomendación automática de apuesta.

Hasta que exista una definición matemática, procedimiento de calibración, validación empírica y pruebas específicas, `confidence` deberá tratarse únicamente como un valor interno acotado entre `0.0` y `1.0`.

### 7.4 Principio de trazabilidad temporal

Los campos `analysis_id`, `created_at`, `engine_version` y `policy_version` deberán utilizarse como base para poder reconstruir qué versión del sistema produjo una decisión y cuándo fue creada.

La evolución futura del sistema deberá ampliar esta trazabilidad para relacionar, cuando corresponda:

- datos de entrada;
- fuentes y proveedores;
- timestamps de adquisición;
- transformaciones;
- versión del esquema;
- versión del motor;
- versión de políticas;
- resultado del procesamiento;
- evidencia utilizada;
- decisión final;
- cambios posteriores.

Ninguna capacidad futura de trazabilidad deberá documentarse como IMPLEMENTED hasta que exista evidencia verificable de su funcionamiento.
