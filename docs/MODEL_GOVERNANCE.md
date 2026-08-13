# MODEL GOVERNANCE — MATRIX TENIS

## 1. Propósito

El presente documento establece el marco formal de gobierno para los modelos, motores analíticos, scores, reglas, umbrales, políticas y mecanismos de decisión utilizados por MATRIX TENIS.

Su objetivo es impedir que una lógica implementada técnicamente sea considerada válida para uso analítico, predictivo, operativo o económico sin evidencia suficiente.

En MATRIX TENIS deberán distinguirse explícitamente los conceptos de:

- implementación;
- verificación técnica;
- validación estadística;
- calibración;
- validación deportiva;
- validación económica;
- autorización operativa.

Superar una de estas etapas no implicará automáticamente haber superado las demás.

---

## 2. Alcance

Este marco será aplicable, según corresponda, a:

- modelos estadísticos;
- modelos de machine learning;
- modelos probabilísticos;
- simulaciones;
- scores heurísticos;
- filtros;
- reglas deterministas;
- políticas de cobertura;
- umbrales;
- sistemas de clasificación;
- métricas derivadas;
- estimaciones de probabilidad;
- cálculo de valor esperado;
- mecanismos de gestión de riesgo;
- señales prepartido;
- señales LIVE;
- reglas de abstención o NO BET;
- sistemas futuros de recomendación;
- combinaciones o ensembles de modelos.

Una regla sencilla podrá requerir menos controles que un modelo complejo, pero ninguna lógica crítica quedará fuera de gobierno únicamente por no utilizar inteligencia artificial.

---

## 3. Principios fundamentales

### 3.1 Implementado no significa validado

La existencia de código funcional y pruebas satisfactorias demuestra que un componente puede comportarse conforme a su implementación.

No demuestra por sí sola que:

- sus parámetros sean óptimos;
- sus pesos posean fundamento estadístico;
- sus umbrales sean adecuados;
- tenga capacidad predictiva;
- esté calibrado;
- produzca valor económico;
- sea estable fuera de muestra;
- esté autorizado para decisiones relacionadas con dinero.

### 3.2 Score no significa probabilidad

Un score, ranking, clasificación o indicador interno no deberá presentarse como probabilidad salvo que exista una definición probabilística formal y evidencia suficiente de calibración.

Valores como `80/100`, `0.80`, `ALTA` o `MUY ALTA` no equivaldrán automáticamente a una probabilidad del 80%.

### 3.3 Cobertura no significa confianza predictiva

Una medida de disponibilidad o cobertura de datos deberá mantenerse conceptualmente separada de:

- calidad de datos;
- confiabilidad de la fuente;
- probabilidad del evento;
- confianza estadística;
- edge;
- expected value;
- probabilidad de acierto.

### 3.4 Parámetros provisionales

Todo peso, umbral, score o regla que no posea todavía validación suficiente deberá identificarse como provisional, experimental o heurístico.

Un parámetro provisional podrá utilizarse para desarrollo, integración y pruebas controladas, pero no deberá adquirir legitimidad científica únicamente por permanecer durante mucho tiempo en el código.

### 3.5 Evidencia antes de promoción

Ningún modelo o regla crítica deberá promoverse a un estado de mayor confianza únicamente por:

- intuición;
- prestigio de una fuente;
- resultados aislados;
- una racha favorable;
- buen rendimiento in-sample;
- conveniencia operativa;
- presión por liberar una versión.

La promoción deberá depender de criterios previamente definidos y evidencia reproducible.

### 3.6 Separación estricta por deporte

Los modelos, variables, reglas deportivas, datasets, aprendizajes y parámetros específicos de MATRIX TENIS deberán permanecer separados de los motores específicos de otros deportes.

Podrán compartirse componentes transversales de ingeniería, auditoría, seguridad, infraestructura y gestión de riesgo cuando estos no introduzcan lógica deportiva ajena.

Un componente general no deberá sustituir la especialización deportiva necesaria para producir una decisión de tenis.

### 3.7 Abstención como resultado válido

El sistema deberá poder concluir que la evidencia es insuficiente.

`NO BET`, `DESCARTAR`, `VIGILAR`, `DATOS INSUFICIENTES` o estados equivalentes serán resultados legítimos cuando las condiciones de validación no sean satisfechas.

La arquitectura no deberá forzar una selección únicamente porque exista un partido disponible.

### 3.8 Reproducibilidad

Toda evaluación relevante de un modelo deberá poder reconstruirse razonablemente mediante:

- versión del código;
- versión del modelo;
- versión de políticas;
- dataset utilizado;
- periodo temporal;
- configuración;
- parámetros;
- métricas;
- procedimiento de evaluación.

### 3.9 Prevención de fuga de información

Ningún entrenamiento, backtesting o validación podrá utilizar información que no hubiera estado disponible en el momento real de la decisión evaluada.

La prevención de leakage será un requisito obligatorio para cualquier afirmación de rendimiento predictivo.

### 3.10 Control humano sobre decisiones económicas

La automatización podrá aumentar progresivamente cuando exista evidencia suficiente.

Mientras una decisión pueda producir exposición monetaria material, deberán mantenerse los controles humanos definidos por la política de riesgo y el estado de madurez del sistema.

---

## 4. Ciclo de vida y estados de madurez

Todo modelo, score, regla, política o mecanismo de decisión relevante deberá mantener un estado de madurez explícito.

La promoción entre estados deberá estar respaldada por evidencia proporcional al riesgo.

### 4.1 EXPERIMENTAL

Componente utilizado para exploración, investigación, prototipado o integración inicial.

Podrá contener:

- parámetros provisionales;
- datos sintéticos;
- métricas de prueba;
- supuestos todavía no validados;
- lógica incompleta.

Un componente EXPERIMENTAL no estará autorizado para justificar decisiones económicas reales.

### 4.2 TECHNICALLY_VERIFIED

Componente cuya implementación ha superado los controles técnicos definidos para su alcance.

La evidencia podrá incluir:

- pruebas unitarias;
- pruebas de integración;
- validación de tipos;
- validación de rangos;
- manejo de errores;
- reproducibilidad técnica;
- ausencia de regresiones conocidas.

Este estado demuestra corrección respecto de la especificación implementada.

No demuestra capacidad predictiva.

### 4.3 RESEARCH_VALIDATED

Componente que ha superado una evaluación metodológica suficiente para justificar investigación avanzada.

Deberá existir evidencia, según corresponda, de:

- definición precisa del objetivo;
- dataset identificado;
- separación temporal adecuada;
- prevención de leakage;
- baseline;
- métricas previamente definidas;
- evaluación fuera de muestra;
- análisis de incertidumbre;
- documentación de limitaciones.

Este estado todavía no implicará autorización para decisiones económicas reales.

### 4.4 SHADOW_VALIDATED

Componente evaluado sobre eventos reales sin controlar decisiones monetarias.

En este estado el sistema podrá producir señales o predicciones en paralelo mientras las decisiones reales permanecen fuera de su control.

La evaluación deberá permitir comparar:

- predicción previa al evento;
- información realmente disponible en ese momento;
- resultado observado;
- comportamiento frente al baseline;
- calibración cuando corresponda;
- estabilidad;
- errores;
- oportunidades rechazadas;
- falsos positivos;
- falsos negativos.

Los resultados deberán registrarse antes de conocer el desenlace del evento.

### 4.5 LIMITED_LIVE

Componente autorizado para utilización real bajo límites reforzados.

Deberá operar con:

- exposición restringida;
- límites de riesgo explícitos;
- supervisión humana;
- logging reforzado;
- monitoreo;
- capacidad de suspensión inmediata;
- criterios de rollback.

La autorización LIMITED_LIVE deberá definir claramente su alcance.

### 4.6 PRODUCTION

Componente autorizado para operación normal dentro de límites documentados.

La promoción a PRODUCTION requerirá evidencia acumulada suficiente de:

- estabilidad técnica;
- validez metodológica;
- comportamiento fuera de muestra;
- desempeño en shadow;
- control de riesgo;
- trazabilidad;
- monitoreo;
- capacidad de recuperación;
- aprobación de las disciplinas aplicables.

PRODUCTION no significará validación permanente.

### 4.7 SUSPENDED

Estado aplicado cuando nueva evidencia reduce materialmente la confianza en un componente.

Podrá activarse por:

- degradación estadística;
- pérdida de calibración;
- cambios estructurales del entorno;
- defectos de datos;
- incidentes;
- regresiones;
- incumplimiento de límites;
- imposibilidad de reproducir resultados;
- hallazgos críticos.

Un componente SUSPENDED no deberá continuar produciendo decisiones autorizadas hasta nueva evaluación.

### 4.8 RETIRED

Componente retirado del uso activo.

Deberán conservarse, cuando resulte necesario para auditoría:

- versiones;
- configuración;
- métricas;
- razones del retiro;
- periodo de utilización;
- dependencias históricas;
- evidencia relevante.

### 4.9 Prohibición de promoción automática por rendimiento reciente

Ningún componente deberá ascender de estado únicamente porque una muestra reciente haya producido resultados favorables.

La promoción deberá considerar tamaño de muestra, independencia, incertidumbre, régimen temporal, sesgos potenciales y criterios previamente definidos.

### 4.10 Estado actual de componentes auditados

Con base únicamente en la evidencia actualmente verificada:

| Componente | Estado de gobierno inicial | Motivo |
| --- | --- | --- |
| `TennisDataCoverage.score()` | TECHNICALLY_VERIFIED | Implementación y comportamiento matemático protegidos por pruebas; mide cobertura, no capacidad predictiva. |
| `TennisCoveragePolicy` | TECHNICALLY_VERIFIED | Política validada técnicamente; `minimum_score` configurable y probado, pero sin evidencia actual de optimalidad deportiva. |
| `TennisEngine` | TECHNICALLY_VERIFIED | Pipeline de validación y cobertura probado; no constituye todavía un modelo predictivo de apuestas. |
| `MatrixFilterEngine` | EXPERIMENTAL | Filtro heurístico preliminar sin evidencia actual de validación predictiva. |
| `MatrixScoreEngine` | EXPERIMENTAL | Pesos y umbrales heurísticos sin evidencia actual de calibración o validación estadística. |
| `MatrixRiskEngine` | EXPERIMENTAL | Estructura determinista implementada, pero pesos y cortes requieren validación independiente antes de uso económico. |
| `MatrixAnalysisEngine` | EXPERIMENTAL | Integración v0.1 con métricas de prueba y sin evidencia directa de pruebas automatizadas específicas encontrada en la auditoría actual. |

Esta clasificación deberá actualizarse cuando aparezca nueva evidencia.

Ningún estado de esta tabla deberá elevarse sin registrar la justificación y las pruebas correspondientes.

---

## 5. Gobierno de datasets y evidencia experimental

Ninguna afirmación de capacidad predictiva deberá evaluarse sin identificar claramente los datos utilizados para producirla.

### 5.1 Identificación del dataset

Todo dataset utilizado para investigación, entrenamiento, calibración, backtesting o validación deberá poder relacionarse, cuando corresponda, con:

- nombre o identificador;
- versión;
- deporte;
- periodo temporal;
- competiciones cubiertas;
- superficies;
- fuentes;
- fecha de extracción;
- reglas de inclusión;
- reglas de exclusión;
- transformaciones;
- variables disponibles;
- datos faltantes;
- controles de calidad;
- limitaciones conocidas.

### 5.2 Separación temporal

Siempre que el problema tenga naturaleza temporal, la división de datos deberá respetar el orden real de los eventos.

No deberá utilizarse aleatoriamente información futura para mejorar artificialmente la evaluación de decisiones pasadas.

Las estrategias de validación deberán considerar, según corresponda:

- holdout temporal;
- walk-forward validation;
- rolling windows;
- expanding windows;
- validación por periodos independientes.

### 5.3 Entrenamiento, validación y prueba

Cuando exista entrenamiento de parámetros o modelos deberán diferenciarse, según corresponda:

- TRAIN;
- VALIDATION;
- TEST;
- OUT-OF-TIME;
- SHADOW/LIVE EVALUATION.

El conjunto TEST no deberá utilizarse repetidamente para ajustar decisiones hasta convertirlo de facto en otro conjunto de entrenamiento.

### 5.4 Prevención de leakage

Deberá investigarse explícitamente la posibilidad de fuga de información.

Entre otras situaciones, deberá impedirse:

- utilizar resultados finales para construir variables prepartido;
- utilizar cuotas posteriores al momento de decisión;
- incorporar estadísticas actualizadas después del evento;
- calcular normalizaciones con información futura cuando alteren la evaluación;
- utilizar rankings, lesiones o estados conocidos posteriormente como si hubieran estado disponibles antes;
- permitir que duplicados del mismo evento aparezcan en particiones incompatibles;
- ajustar reglas utilizando conocimiento del conjunto reservado para prueba.

### 5.5 Registro del momento de decisión

Para cada caso utilizado en validación real deberá conservarse, cuando sea posible:

- timestamp de decisión;
- información disponible en ese instante;
- fuente;
- cuotas disponibles;
- versión del motor;
- versión de política;
- señal emitida;
- decisión adoptada;
- resultado posterior.

La reconstrucción retrospectiva no deberá sustituir silenciosamente la información que realmente estaba disponible.

### 5.6 Casos manuales recopilados durante el desarrollo

Los análisis manuales realizados durante la construcción de MATRIX TENIS podrán conservarse como evidencia experimental.

Deberán diferenciarse de un dataset de validación formal mientras no exista suficiente estandarización de:

- captura;
- variables;
- timestamps;
- fuentes;
- mercados;
- criterios de decisión;
- resultados;
- datos faltantes.

Los casos manuales podrán utilizarse para:

- descubrir variables;
- identificar errores;
- formular hipótesis;
- diseñar contratos;
- desarrollar pruebas;
- estudiar patrones;
- preparar futuros datasets.

No deberán utilizarse por sí solos para afirmar rendimiento productivo.

### 5.7 Resultado conocido después de la decisión

La información posterior al partido podrá utilizarse para evaluar una decisión previamente registrada.

No deberá utilizarse para modificar retroactivamente la señal original.

La historia deberá conservar, cuando corresponda:

1. información disponible antes de decidir;
2. decisión original;
3. información posterior;
4. resultado;
5. evaluación retrospectiva.

### 5.8 Sesgo de selección

La evaluación deberá considerar si los partidos analizados representan realmente el universo sobre el cual se pretende operar.

Seleccionar retrospectivamente únicamente casos interesantes, ganadores, televisados, de determinadas cuotas o con información abundante podrá producir estimaciones sesgadas.

### 5.9 Duplicados y dependencia

Deberá evaluarse la existencia de observaciones dependientes.

Partidos del mismo jugador, torneo, periodo o contexto podrán estar correlacionados.

El tamaño bruto de la muestra no deberá confundirse automáticamente con el número de observaciones estadísticamente independientes.

### 5.10 Versionado de datasets

Los datasets relevantes deberán versionarse progresivamente.

Una evaluación deberá poder identificar qué versión exacta de los datos produjo sus resultados.

Las correcciones posteriores de datos no deberán destruir la posibilidad de reconstruir evaluaciones históricas relevantes.

---

## 6. Validación de modelos, scores y reglas

La validación deberá demostrar no solamente que un componente funciona técnicamente, sino que cumple razonablemente el objetivo para el cual pretende utilizarse.

Las métricas y pruebas aplicables dependerán de la naturaleza del componente.

### 6.1 Baseline obligatorio

Todo modelo o regla que pretenda aportar capacidad predictiva deberá compararse contra uno o más baselines apropiados.

Los baselines podrán incluir, según el problema:

- predicción ingenua;
- frecuencia histórica;
- regla simple previamente definida;
- modelo anterior;
- probabilidad implícita del mercado correctamente ajustada cuando resulte aplicable.

La complejidad adicional deberá justificar su existencia mediante evidencia.

### 6.2 Evaluación fuera de muestra

El rendimiento utilizado para justificar una promoción deberá incluir datos no utilizados para ajustar el componente.

El rendimiento in-sample podrá utilizarse para diagnóstico, pero no deberá presentarse como evidencia suficiente de generalización.

### 6.3 Métricas probabilísticas

Cuando un componente produzca probabilidades deberán evaluarse métricas apropiadas, según corresponda, como:

- Brier Score;
- Log Loss;
- curvas o tablas de calibración;
- error de calibración;
- discriminación;
- estabilidad por intervalos de probabilidad.

La tasa de aciertos por sí sola no será suficiente para validar probabilidades.

### 6.4 Calibración

Una predicción declarada como probabilidad deberá demostrar una relación razonable entre probabilidad pronosticada y frecuencia observada.

Una salida de `0.70` no deberá interpretarse como 70% de probabilidad únicamente porque esté expresada entre `0` y `1`.

Los procedimientos de calibración deberán evaluarse fuera de los datos utilizados para ajustarlos.

### 6.5 Métricas económicas

Cuando el objetivo incluya decisiones de mercado podrán evaluarse, entre otras:

- ROI;
- Yield;
- Expected Value;
- Closing Line Value cuando sea metodológicamente apropiado;
- drawdown;
- volatilidad de resultados;
- exposición;
- rendimiento por mercado;
- rendimiento por rango de cuota.

Las métricas económicas deberán acompañarse de tamaño de muestra, periodo evaluado e incertidumbre suficiente para evitar conclusiones engañosas.

### 6.6 Exactitud no equivale a rentabilidad

Una tasa de aciertos elevada no demostrará por sí sola rentabilidad.

Deberán considerarse las cuotas, probabilidades implícitas, margen de la casa, precio realmente disponible y exposición asumida.

Del mismo modo, una estrategia podrá presentar una tasa de aciertos inferior al 50% y aun así poseer expectativa positiva si las cuotas y probabilidades lo justifican.

### 6.7 Validación por segmentos

El rendimiento agregado deberá descomponerse cuando resulte relevante por dimensiones como:

- superficie;
- circuito;
- torneo;
- ronda;
- formato;
- rango de cuota;
- mercado;
- periodo temporal;
- calidad de datos;
- cobertura;
- jugador o grupos de jugadores cuando metodológicamente corresponda.

Un buen resultado agregado no deberá ocultar segmentos materialmente deficientes.

### 6.8 Robustez

Deberá evaluarse razonablemente si pequeñas modificaciones en parámetros, muestras o periodos producen cambios desproporcionados en los resultados.

Un sistema extremadamente sensible podrá indicar:

- sobreajuste;
- inestabilidad;
- muestra insuficiente;
- dependencia de casos particulares;
- parámetros mal identificados.

### 6.9 Incertidumbre

Las estimaciones de rendimiento deberán acompañarse de medidas de incertidumbre cuando sean técnicamente apropiadas.

No deberán comunicarse diferencias pequeñas como mejoras reales cuando puedan explicarse razonablemente por variación muestral.

### 6.10 Múltiples experimentos

Cuando se prueben numerosas variantes, parámetros, mercados o hipótesis deberá considerarse el riesgo de seleccionar retrospectivamente únicamente las configuraciones ganadoras.

El proceso experimental deberá conservar suficiente trazabilidad para conocer:

- cuántas alternativas fueron evaluadas;
- qué criterio se utilizó para seleccionarlas;
- qué datos participaron en la selección;
- qué evaluación independiente permaneció reservada.

### 6.11 Validación deportiva

Además de las métricas estadísticas, los modelos específicos de MATRIX TENIS deberán someterse a revisión de coherencia deportiva.

La validación deportiva deberá comprobar, cuando corresponda, que:

- las variables tienen significado razonable en tenis;
- su temporalidad es correcta;
- no existe información imposible de conocer en el momento de decisión;
- la interpretación no contradice la estructura real del deporte;
- los efectos observados son suficientemente estables;
- las conclusiones no dependen del prestigio o fama del jugador.

La revisión deportiva no sustituirá la validación estadística, ni la validación estadística sustituirá la revisión deportiva.

### 6.12 Pesos y umbrales

Todo peso o umbral crítico deberá mantener una justificación identificable.

Podrá originarse inicialmente como heurística para prototipado, pero antes de promoción deberá evaluarse mediante evidencia.

No deberá modificarse un umbral únicamente para mejorar retrospectivamente los resultados de una muestra conocida.

### 6.13 Criterios de promoción

Antes de comenzar una evaluación formal deberán definirse, cuando sea posible, los criterios necesarios para considerar que un componente supera la etapa.

Los criterios podrán incluir:

- métricas mínimas;
- calibración;
- estabilidad;
- tamaño de muestra;
- comportamiento por segmentos;
- límites de drawdown;
- calidad de datos;
- ausencia de hallazgos bloqueantes.

Los criterios no deberán reducirse retrospectivamente únicamente porque el modelo no logró superarlos.

---

## 7. Monitoreo, degradación y rollback

Todo componente autorizado para SHADOW_VALIDATED, LIMITED_LIVE o PRODUCTION deberá disponer de controles proporcionales a su criticidad para detectar degradación técnica, estadística, deportiva o económica.

### 7.1 Monitoreo continuo

El monitoreo deberá considerar, cuando corresponda:

- disponibilidad de datos;
- datos faltantes;
- latencia;
- errores de proveedores;
- cambios de esquema;
- distribución de variables;
- distribución de predicciones;
- cobertura;
- calibración;
- rendimiento;
- exposición;
- drawdown;
- comportamiento por segmentos;
- errores operativos;
- frecuencia de abstención;
- frecuencia y naturaleza de overrides humanos.

Una métrica aislada no deberá utilizarse como sustituto del estado general del sistema.

### 7.2 Data drift

Deberán establecerse mecanismos para detectar cambios materiales en la distribución o disponibilidad de los datos de entrada.

El data drift podrá originarse, entre otras causas, por:

- cambios de proveedor;
- modificaciones de definiciones;
- nuevas competiciones;
- cambios de superficie o categorización;
- alteraciones en frecuencia de actualización;
- pérdida de campos;
- cambios estructurales del circuito.

La existencia de drift no implicará automáticamente que el modelo sea inválido, pero deberá activar una evaluación proporcional a su magnitud e impacto.

### 7.3 Concept drift

Deberá considerarse la posibilidad de que cambie la relación entre variables y resultados.

El comportamiento histórico podrá degradarse debido a:

- evolución deportiva;
- cambios reglamentarios;
- cambios de calendario;
- modificaciones de superficies;
- cambios en condiciones competitivas;
- adaptación del mercado;
- modificaciones estructurales del entorno.

Los modelos no deberán asumir estabilidad permanente.

### 7.4 Degradación de calibración

Cuando existan probabilidades calibradas deberá monitorearse si la relación entre probabilidades pronosticadas y frecuencias observadas se deteriora.

Una degradación material podrá requerir:

- investigación;
- recalibración;
- reducción de exposición;
- retorno a SHADOW;
- suspensión.

La recalibración no deberá realizarse automáticamente sin controles cuando pueda afectar decisiones económicas.

### 7.5 Degradación económica

Un componente podrá mantener métricas predictivas razonables y simultáneamente perder utilidad económica.

Deberán investigarse, cuando corresponda:

- reducción del edge;
- deterioro del precio disponible;
- cambios del margen de mercado;
- pérdida de Closing Line Value;
- incremento de drawdown;
- concentración excesiva;
- deterioro por rango de cuota o mercado.

### 7.6 Umbrales de alerta

Los umbrales de monitoreo deberán documentarse y versionarse.

Cuando todavía no exista evidencia suficiente para establecer un umbral, deberá identificarse como provisional.

No deberán inventarse límites de alerta únicamente para aparentar control.

### 7.7 Niveles de respuesta

Los hallazgos podrán producir, según severidad:

- observación;
- advertencia;
- investigación;
- reducción de exposición;
- bloqueo de nuevas decisiones;
- retorno a SHADOW;
- estado SUSPENDED;
- rollback;
- retiro.

La respuesta deberá ser proporcional al riesgo.

### 7.8 Kill switch

Los componentes con capacidad de influir sobre exposición monetaria deberán disponer, antes de alcanzar madurez suficiente, de un mecanismo operativo para detener nuevas decisiones autorizadas.

El kill switch deberá priorizar seguridad sobre continuidad.

Su activación no deberá borrar la evidencia necesaria para investigar el incidente.

### 7.9 Rollback

Todo componente promovido a una versión operativa relevante deberá mantener una estrategia razonable de rollback.

Deberá ser posible identificar:

- versión actualmente activa;
- versión anterior estable;
- motivo del cambio;
- configuración;
- dependencias;
- procedimiento de retorno;
- riesgos del rollback.

No deberá desplegarse una modificación crítica si no existe una estrategia proporcional de recuperación.

### 7.10 Shadow después de cambios materiales

Un cambio material podrá requerir regresar temporalmente a SHADOW_VALIDATED aunque una versión anterior hubiera alcanzado PRODUCTION.

Podrán considerarse materiales cambios en:

- variables;
- proveedores;
- pesos;
- umbrales;
- algoritmo;
- calibración;
- mercados objetivo;
- reglas de riesgo;
- arquitectura de decisión.

La versión nueva deberá demostrar nuevamente que conserva las propiedades necesarias.

### 7.11 Incidentes

Los incidentes relevantes deberán conservar evidencia suficiente para determinar:

- qué ocurrió;
- cuándo ocurrió;
- qué versión estaba activa;
- qué datos fueron utilizados;
- qué decisiones fueron afectadas;
- impacto;
- causa raíz cuando pueda determinarse;
- acción correctiva;
- acción preventiva.

Los incidentes no deberán ocultarse para preservar métricas de rendimiento.

### 7.12 Degradación silenciosa

La ausencia de errores técnicos no demostrará que el sistema continúa funcionando correctamente.

Un modelo puede ejecutar sin excepciones y, aun así, haber perdido:

- calibración;
- capacidad predictiva;
- edge;
- calidad de datos;
- relevancia deportiva.

Por esta razón, el monitoreo deberá incluir comportamiento y resultados, no solamente disponibilidad del servicio.

---

## 8. Versionado, cambios y trazabilidad

Todo componente gobernado deberá poseer un nivel de versionado proporcional a su impacto y madurez.

### 8.1 Identificación de versiones

Cuando corresponda, deberán poder distinguirse independientemente:

- versión del código;
- versión del modelo;
- versión de parámetros;
- versión de políticas;
- versión del esquema de datos;
- versión del dataset;
- versión de calibración;
- versión de configuración.

No deberá asumirse que una única versión global representa adecuadamente todos estos elementos.

### 8.2 Cambios materiales

Se considerará material todo cambio capaz de alterar significativamente:

- inputs;
- outputs;
- probabilidades;
- scores;
- decisiones;
- exposición;
- interpretación;
- rendimiento;
- riesgo.

Los cambios materiales deberán requerir reevaluación proporcional a su impacto.

### 8.3 Registro de cambios

Todo cambio material deberá conservar, cuando corresponda:

- identificador;
- fecha;
- autor o responsable;
- componente afectado;
- versión anterior;
- versión nueva;
- justificación;
- evidencia;
- pruebas realizadas;
- riesgos conocidos;
- aprobación;
- estrategia de rollback.

### 8.4 Reproducibilidad histórica

Cuando una decisión sea materialmente relevante, el sistema deberá evolucionar hacia la capacidad de identificar qué combinación de código, datos, modelo, parámetros y políticas la produjo.

Una actualización futura no deberá reescribir silenciosamente la interpretación histórica de decisiones anteriores.

---

## 9. Gobierno de cambios experimentales

### 9.1 Hipótesis explícita

Los experimentos relevantes deberán comenzar con una hipótesis suficientemente definida.

Siempre que sea posible deberá establecerse antes de observar el resultado:

- qué se modifica;
- por qué;
- qué mejora se espera;
- cómo se medirá;
- contra qué baseline;
- qué resultado se considerará insuficiente.

### 9.2 Separación entre exploración y confirmación

Los mismos datos utilizados repetidamente para descubrir una regla no deberán utilizarse sin controles como única evidencia para confirmarla.

La evidencia confirmatoria deberá incorporar información suficientemente independiente.

### 9.3 Resultados negativos

Los experimentos negativos o inconclusos deberán conservarse cuando aporten conocimiento relevante.

No deberán eliminarse sistemáticamente de la historia experimental.

Registrar únicamente experimentos exitosos produciría una visión sesgada del proceso de investigación.

### 9.4 Repetibilidad

Un resultado importante deberá poder repetirse razonablemente antes de promover una modificación crítica.

Una ejecución aislada no deberá considerarse suficiente cuando el procedimiento esté sujeto a variabilidad.

---

## 10. Comité de aprobación

La promoción de componentes críticos deberá someterse a revisión multidisciplinaria proporcional al riesgo.

No todas las disciplinas deberán aprobar cada modificación trivial, pero ningún cambio crítico deberá evaluarse únicamente desde una sola perspectiva.

### 10.1 Arquitectura de software

Deberá revisar, cuando corresponda:

- separación de responsabilidades;
- modularidad;
- acoplamiento;
- escalabilidad;
- compatibilidad;
- deuda técnica;
- rollback;
- impacto sobre otros componentes.

### 10.2 Ingeniería Python y backend

Deberá revisar:

- corrección de implementación;
- mantenibilidad;
- tipos;
- manejo de errores;
- interfaces;
- rendimiento;
- pruebas;
- observabilidad.

### 10.3 Ciencia de datos

Deberá revisar:

- construcción de variables;
- datasets;
- metodología experimental;
- leakage;
- baselines;
- generalización;
- drift;
- reproducibilidad.

### 10.4 Estadística y probabilidad

Deberá revisar:

- validez de métricas;
- incertidumbre;
- calibración;
- tamaño de muestra;
- dependencia;
- significancia práctica;
- sobreajuste;
- interpretación probabilística.

### 10.5 Especialista deportivo de tenis

Deberá revisar:

- coherencia deportiva;
- significado de variables;
- contexto competitivo;
- temporalidad;
- posibles factores omitidos;
- interpretación de resultados.

La revisión deportiva no podrá sustituir evidencia estadística.

### 10.6 QA y testing

Deberá revisar:

- cobertura de pruebas;
- casos frontera;
- regresiones;
- integración;
- reproducibilidad;
- criterios de aceptación.

### 10.7 Ingeniería de datos y bases de datos

Deberá revisar:

- calidad;
- procedencia;
- esquemas;
- integridad;
- temporalidad;
- almacenamiento;
- migraciones;
- reproducibilidad de datasets.

### 10.8 Seguridad

Deberá revisar:

- superficies de ataque;
- permisos;
- secretos;
- integridad de modelos y datos;
- dependencias;
- riesgos de manipulación;
- trazabilidad de cambios críticos.

### 10.9 DevOps e infraestructura

Deberá revisar:

- despliegue;
- monitoreo;
- disponibilidad;
- rollback;
- capacidad;
- observabilidad;
- recuperación.

### 10.10 Riesgo

Deberá revisar:

- exposición;
- límites;
- concentración;
- drawdown;
- escenarios adversos;
- kill switch;
- impacto económico potencial.

### 10.11 Auditoría y gobierno

Deberá comprobar:

- evidencia;
- trazabilidad;
- cumplimiento del proceso;
- conflictos entre documentación e implementación;
- pendientes;
- excepciones;
- aprobación formal.

### 10.12 Independencia de revisión

Cuando la criticidad lo justifique, la evaluación no deberá depender exclusivamente de la misma persona, proceso o componente que diseñó la modificación.

La revisión independiente deberá buscar activamente razones por las cuales una conclusión podría estar equivocada.

---

## 11. Decisiones y excepciones

### 11.1 Registro de decisión

Las decisiones materiales deberán conservar suficiente evidencia para explicar:

- qué se decidió;
- por qué;
- alternativas consideradas;
- evidencia utilizada;
- riesgos aceptados;
- responsables;
- fecha;
- condiciones de revisión.

### 11.2 Excepciones

Toda excepción a este marco deberá ser:

- explícita;
- justificada;
- limitada en alcance;
- limitada temporalmente cuando corresponda;
- aprobada por el nivel adecuado;
- trazable.

Una excepción no deberá convertirse silenciosamente en la nueva regla.

### 11.3 Hallazgos bloqueantes

Un hallazgo crítico relacionado con leakage, integridad de datos, calibración falsa, riesgo no controlado, seguridad, reproducibilidad o utilización de información futura podrá bloquear una promoción independientemente de otras métricas favorables.

### 11.4 Conflicto entre rendimiento y control

Un componente no deberá promoverse únicamente porque produzca mayor rentabilidad histórica si para lograrlo requiere degradar controles fundamentales de calidad, seguridad, trazabilidad o riesgo.

El rendimiento deberá alcanzarse dentro del marco de control, no sustituyéndolo.

---

## 12. Pendientes de gobierno identificados en la auditoría actual

Los siguientes elementos permanecen abiertos y no deberán considerarse resueltos por la creación de este documento.

### 12.1 P-001 — Semántica de confidence

**Prioridad:** HIGH
**Estado:** OPEN

Actualmente existen conceptos diferentes denominados `confidence`.

En `TennisProcessingResult`, `confidence` representa actualmente un valor numérico relacionado con cobertura de datos.

En otros componentes analíticos existe una clasificación textual de confianza asociada a scores heurísticos.

Deberá eliminarse cualquier ambigüedad capaz de provocar que cobertura, score, clasificación o probabilidad sean interpretados como conceptos equivalentes.

Antes de modificar nombres o interfaces deberán analizarse dependencias, compatibilidad y pruebas.

### 12.2 P-002 — Validación de minimum_score

**Prioridad:** HIGH
**Estado:** OPEN

`TennisCoveragePolicy` utiliza actualmente un `minimum_score` predeterminado de `0.5`.

La implementación y sus fronteras están protegidas por pruebas.

No existe todavía evidencia verificada en la auditoría actual de que `0.5` sea el umbral deportivo óptimo.

El valor deberá permanecer identificado como parámetro no validado deportivamente hasta disponer de evidencia suficiente.

### 12.3 P-003 — Cobertura binaria

**Prioridad:** HIGH
**Estado:** OPEN

`TennisDataCoverage.score()` utiliza actualmente seis categorías booleanas con peso equivalente:

- recent form;
- surface history;
- serve stats;
- return stats;
- fatigue context;
- market data.

Este mecanismo mide presencia de categorías.

No mide todavía:

- profundidad;
- calidad;
- frescura;
- procedencia;
- confiabilidad;
- suficiencia estadística.

Deberá evaluarse si la arquitectura futura requiere dimensiones separadas en lugar de ampliar indefinidamente un único score.

### 12.4 P-004 — Pesos de MatrixScoreEngine

**Prioridad:** HIGH
**Estado:** OPEN

Los pesos actuales del score general deberán tratarse como heurísticos mientras no exista evidencia de validación.

No deberán utilizarse como prueba de importancia real de las variables ni como probabilidad implícita.

### 12.5 P-005 — Umbrales de MatrixScoreEngine

**Prioridad:** HIGH
**Estado:** OPEN

Los cortes utilizados actualmente para clasificar scores deberán someterse a validación antes de cualquier promoción del componente.

No deberán optimizarse retrospectivamente sobre una única muestra.

### 12.6 P-006 — MatrixFilterEngine

**Prioridad:** HIGH
**Estado:** OPEN

El filtro actual utiliza principalmente propiedades estructurales del partido.

Deberá definirse formalmente si su función futura será:

- elegibilidad;
- calidad mínima;
- prefiltrado operativo;
- filtrado deportivo;
- otra función específica.

No deberá presentarse como filtro predictivo mientras no exista evidencia que lo justifique.

### 12.7 P-007 — MatrixRiskEngine

**Prioridad:** HIGH
**Estado:** OPEN

Los pesos y cortes actuales del motor de riesgo requieren justificación independiente.

El hecho de que los pesos sumen `1.0` y el algoritmo funcione correctamente no demuestra que representen adecuadamente el riesgo real.

### 12.8 P-008 — MatrixAnalysisEngine v0.1

**Prioridad:** CRITICAL antes de uso económico
**Estado:** OPEN

La implementación auditada utiliza métricas de prueba y declara explícitamente que faltan estadísticas y cuotas reales.

No deberá utilizarse como evidencia de capacidad predictiva ni como motor autorizado para decisiones económicas.

Antes de promoción deberá:

- eliminar dependencia de métricas ficticias;
- integrarse con datos reales gobernados;
- respetar la especialización de MATRIX TENIS;
- disponer de pruebas específicas;
- registrar trazabilidad;
- someterse al ciclo de validación definido en este documento.

### 12.9 P-009 — Pruebas específicas de MatrixAnalysisEngine

**Prioridad:** HIGH
**Estado:** OPEN

La búsqueda realizada durante esta auditoría no encontró pruebas automatizadas directas para:

- `MatrixAnalysisEngine`;
- `_build_test_metrics`;
- sus estados finales de decisión;
- la advertencia de análisis de prueba.

Deberá diseñarse cobertura de pruebas antes de considerar este componente técnicamente verificado.

### 12.10 P-010 — Integración entre infraestructura general y motor especializado

**Prioridad:** CRITICAL antes de producción
**Estado:** OPEN

Deberá definirse contractualmente la relación entre:

- infraestructura analítica general;
- `TennisEngine`;
- filtros;
- scoring;
- riesgo;
- decisiones finales.

La infraestructura transversal no deberá introducir lógica deportiva genérica que sustituya al motor especializado de tenis.

### 12.11 P-011 — Probabilidades deportivas

**Prioridad:** CRITICAL antes de declarar capacidad predictiva probabilística
**Estado:** OPEN

La auditoría actual no ha demostrado la existencia de un modelo probabilístico calibrado de resultados o mercados de tenis.

No deberán presentarse scores internos como probabilidades mientras este pendiente permanezca abierto.

### 12.12 P-012 — Expected Value

**Prioridad:** CRITICAL antes de selección económica automatizada
**Estado:** OPEN

Deberá existir una definición matemática, datos de mercado confiables y probabilidades suficientemente validadas antes de utilizar Expected Value como criterio operativo.

### 12.13 P-013 — Backtesting formal

**Prioridad:** CRITICAL antes de promoción a SHADOW_VALIDATED
**Estado:** OPEN

Deberá construirse un procedimiento reproducible que incluya:

- datasets versionados;
- separación temporal;
- prevención de leakage;
- baselines;
- métricas;
- segmentación;
- incertidumbre;
- registro de experimentos.

### 12.14 P-014 — Dataset histórico estructurado

**Prioridad:** HIGH
**Estado:** OPEN

Los casos manuales recopilados durante el desarrollo aportan evidencia útil, pero todavía deberán evolucionar hacia un dataset estructurado y gobernado antes de utilizarse como validación formal.

### 12.15 P-015 — Datos de mercado reales

**Prioridad:** CRITICAL antes de validación económica
**Estado:** OPEN

Las evaluaciones económicas deberán utilizar precios realmente disponibles en el momento correspondiente.

No deberán sustituirse silenciosamente por cuotas posteriores o reconstruidas sin trazabilidad.

### 12.16 P-016 — Criterios cuantitativos de promoción

**Prioridad:** HIGH
**Estado:** OPEN

Antes de promover futuros modelos deberán establecerse criterios cuantitativos específicos para cada caso de uso.

Este documento define el marco, pero no inventará actualmente valores mínimos sin evidencia.

### 12.17 P-017 — Shadow mode

**Prioridad:** HIGH
**Estado:** OPEN

Deberá implementarse un mecanismo para registrar predicciones y decisiones antes de los eventos sin permitir inicialmente que el componente controle exposición monetaria.

### 12.18 P-018 — Drift y monitoreo

**Prioridad:** HIGH antes de LIMITED_LIVE
**Estado:** OPEN

Los principios de monitoreo están definidos en este documento, pero los mecanismos técnicos todavía deberán implementarse y probarse.

### 12.19 P-019 — Kill switch y rollback operativo

**Prioridad:** CRITICAL antes de LIMITED_LIVE
**Estado:** OPEN

Los principios están definidos, pero deberán existir mecanismos técnicos y procedimientos probados antes de autorizar exposición económica automatizada.

### 12.20 P-020 — Registro de modelos

**Prioridad:** MEDIUM actualmente / HIGH antes de múltiples modelos activos
**Estado:** OPEN

Deberá evaluarse la implementación de un registro formal capaz de relacionar:

- identificador de modelo;
- versión;
- estado;
- propietario;
- dataset;
- parámetros;
- métricas;
- aprobaciones;
- despliegues;
- retiro.

---

## 13. Regla de cierre de pendientes

Un pendiente de gobierno no deberá marcarse como CLOSED únicamente porque exista código relacionado.

Para cerrarlo deberá conservarse evidencia suficiente de que:

1. se implementó la solución necesaria;
2. existen pruebas apropiadas;
3. la documentación fue actualizada;
4. se evaluaron riesgos y regresiones;
5. se obtuvo la aprobación requerida;
6. el repositorio conserva trazabilidad del cambio.

Cuando un pendiente sea reemplazado por otro, deberá conservarse la relación entre ambos.

---

## 14. Estado del documento

`MODEL_GOVERNANCE.md` constituye el marco de gobierno de modelos de MATRIX TENIS.

Su aprobación documental no implica que los componentes enumerados como EXPERIMENTAL o los pendientes identificados hayan sido resueltos.

El documento deberá evolucionar de forma versionada a medida que:

- se incorporen datos reales;
- aparezcan nuevos modelos;
- se implementen probabilidades;
- se desarrollen mecanismos de backtesting;
- se incorporen proveedores;
- se habilite shadow mode;
- cambie la arquitectura;
- aparezca nueva evidencia.

La discrepancia material entre este documento y la implementación deberá registrarse como hallazgo de auditoría.
