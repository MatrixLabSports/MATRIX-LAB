# AUDIT SYSTEM — MATRIX TENIS

## 1. Propósito

El presente documento define el sistema formal de auditoría de MATRIX TENIS.

Su objetivo es establecer criterios verificables para evaluar la calidad, seguridad, confiabilidad, trazabilidad y preparación de cada componente del sistema antes de considerarlo aprobado.

La auditoría no tendrá como finalidad confirmar que un componente simplemente funciona. Deberá determinar si existe evidencia suficiente para demostrar que funciona correctamente dentro de los límites y condiciones para los cuales fue diseñado.

Ningún módulo, modelo, regla, integración, fuente de datos o mecanismo de decisión podrá considerarse terminado únicamente porque sus pruebas actuales sean satisfactorias.

Toda aprobación deberá estar respaldada por evidencia verificable.

---

## 2. Principios fundamentales de auditoría

El sistema de auditoría de MATRIX TENIS se regirá por los siguientes principios:

1. **Evidencia antes que afirmaciones.**
   Ningún componente será declarado correcto, seguro, estable o terminado sin evidencia suficiente.

2. **Auditoría previa y posterior.**
   Los cambios relevantes deberán evaluarse antes de su incorporación y verificarse nuevamente después de su implementación.

3. **Trazabilidad.**
   Toda decisión técnica relevante deberá poder relacionarse con sus requisitos, implementación, pruebas y resultados.

4. **Reproducibilidad.**
   Siempre que técnicamente sea posible, los resultados de una auditoría deberán poder reproducirse.

5. **Independencia del resultado deportivo.**
   Una apuesta ganada o perdida no constituye por sí sola evidencia suficiente de la calidad de un modelo o decisión.

6. **Gestión explícita de hallazgos.**
   Todo defecto, riesgo, deuda técnica o incumplimiento identificado deberá registrarse y clasificarse.

7. **No aprobación por ausencia de evidencia.**
   Cuando no exista evidencia suficiente para aprobar un componente, su estado deberá permanecer pendiente.

8. **Mejora continua.**
   Los hallazgos de auditoría deberán utilizarse para fortalecer progresivamente el sistema sin introducir cambios injustificados.

   ---

## 3. Comité Multidisciplinario de Auditoría

MATRIX TENIS utilizará un enfoque de auditoría multidisciplinario. Los componentes relevantes deberán evaluarse desde las disciplinas aplicables según su naturaleza, riesgo e impacto.

La existencia del comité no implica que todas las disciplinas deban intervenir con la misma profundidad en cada cambio. La participación deberá ser proporcional al riesgo, impacto, complejidad y alcance del componente auditado.

### 3.1 Disciplinas mínimas

El comité deberá contemplar, como mínimo, las siguientes perspectivas:

1. **Arquitectura de software**
   - separación de responsabilidades;
   - acoplamiento y dependencias;
   - modularidad;
   - mantenibilidad;
   - capacidad de evolución.

2. **Ingeniería Python y backend**
   - corrección de implementación;
   - contratos e interfaces;
   - manejo de errores;
   - calidad del código;
   - comportamiento determinista cuando corresponda.

3. **Ciencia de datos**
   - calidad de variables;
   - transformaciones;
   - prevención de fuga de información;
   - representatividad de datos;
   - reproducibilidad del procesamiento.

4. **Estadística y probabilidad**
   - validez de métricas;
   - tamaño y calidad de muestras;
   - incertidumbre;
   - calibración;
   - prevención de conclusiones derivadas de ruido.

5. **QA y testing**
   - cobertura de comportamientos críticos;
   - pruebas positivas y negativas;
   - casos límite;
   - regresión;
   - criterios verificables de aceptación.

6. **Seguridad**
   - validación de entradas;
   - protección de información;
   - gestión de secretos;
   - superficies de ataque;
   - principio de mínimo privilegio.

7. **Datos y persistencia**
   - integridad;
   - consistencia;
   - procedencia;
   - versionado;
   - recuperación y conservación.

8. **DevOps e infraestructura**
   - reproducibilidad del entorno;
   - automatización;
   - despliegue;
   - observabilidad;
   - capacidad operativa.

9. **Gestión de riesgo**
   - impacto de fallos;
   - límites operativos;
   - degradación segura;
   - controles antes de decisiones relacionadas con dinero;
   - capacidad explícita de NO BET.

10. **Auditoría y gobierno**
    - cumplimiento de políticas;
    - trazabilidad de decisiones;
    - gestión de excepciones;
    - documentación de evidencia;
    - seguimiento de pendientes.

### 3.2 Regla de independencia disciplinaria

La aprobación desde una disciplina no sustituirá la evaluación de las demás disciplinas que resulten aplicables.

Por ejemplo, que un módulo supere todas sus pruebas automatizadas no demostrará por sí solo que sea estadísticamente válido, seguro, escalable o apropiado para decisiones de riesgo.

### 3.3 Regla de proporcionalidad

Los cambios de bajo riesgo podrán utilizar una auditoría simplificada.

Los cambios que afecten modelos, datos, probabilidades, riesgo, seguridad, dinero, integridad histórica, arquitectura crítica o decisiones automatizadas deberán someterse a una revisión reforzada.

La profundidad de la auditoría deberá aumentar proporcionalmente al daño potencial producido por un fallo.

---

## 4. Clasificación de hallazgos

Todo hallazgo identificado durante una auditoría deberá clasificarse según su severidad, impacto y urgencia.

### 4.1 Severidad

Los hallazgos utilizarán los siguientes niveles:

#### CRITICAL

Fallo capaz de comprometer gravemente la integridad del sistema, producir decisiones de riesgo no controladas, utilizar datos inválidos de manera silenciosa, comprometer seguridad o provocar consecuencias financieras relevantes.

Un hallazgo CRITICAL bloquea obligatoriamente la aprobación y cualquier uso del componente afectado en producción.

#### HIGH

Defecto con impacto significativo sobre exactitud, confiabilidad, trazabilidad, disponibilidad, seguridad o comportamiento esperado.

Un hallazgo HIGH bloquea la aprobación del componente afectado hasta que sea corregido o exista una excepción formal extraordinaria, documentada y aprobada.

#### MEDIUM

Problema real que debe corregirse pero que no compromete inmediatamente una función crítica bajo las condiciones actualmente autorizadas.

Podrá permitirse una aprobación condicionada únicamente cuando exista mitigación suficiente, responsable asignado y seguimiento explícito.

#### LOW

Defecto menor, mejora técnica o incumplimiento de impacto limitado que no altera materialmente la seguridad ni la corrección del componente.

Deberá registrarse y gestionarse según prioridad.

### 4.2 Prioridad

La prioridad de resolución no dependerá exclusivamente de la severidad.

Deberá considerar conjuntamente:

- severidad;
- probabilidad de ocurrencia;
- impacto potencial;
- exposición;
- dependencia técnica;
- capacidad de detección;
- existencia de mitigaciones;
- costo de retrasar la corrección.

### 4.3 Prohibición de ocultamiento

Ningún hallazgo podrá eliminarse, reclasificarse o declararse resuelto únicamente para permitir la aprobación de un componente.

Toda modificación de severidad o estado deberá conservar una justificación auditable.

---

## 5. Estados formales de auditoría

Todo componente sometido a auditoría deberá poseer uno de los siguientes estados:

- **PENDING** — todavía no existe evidencia suficiente para emitir una conclusión.
- **IN_REVIEW** — auditoría en ejecución.
- **CONDITIONALLY_APPROVED** — uso permitido bajo condiciones y limitaciones documentadas.
- **APPROVED** — evidencia suficiente para los criterios definidos y alcance evaluado.
- **REJECTED** — incumple uno o más criterios obligatorios.
- **SUSPENDED** — una aprobación anterior ha sido temporalmente retirada por nueva evidencia, incidente o degradación.

### 5.1 Significado de APPROVED

El estado APPROVED nunca significará que un componente es perfecto o que no puede fallar.

Significará exclusivamente que, para una versión, alcance, entorno y conjunto de criterios definidos, existe evidencia suficiente para aceptar el riesgo residual conocido.

Una modificación material podrá invalidar la aprobación previa y exigir una nueva auditoría.

### 5.2 Criterios mínimos para aprobación

Como mínimo, antes de aprobar un componente crítico deberá existir evidencia de:

1. requisitos y alcance identificados;
2. implementación revisada;
3. pruebas aplicables satisfactorias;
4. ausencia de hallazgos CRITICAL abiertos;
5. ausencia de hallazgos HIGH incompatibles con aprobación;
6. riesgos conocidos registrados;
7. dependencias relevantes identificadas;
8. trazabilidad suficiente;
9. documentación proporcional a su criticidad;
10. criterios de aceptación verificables.

### 5.3 Regla de evidencia insuficiente

Ante duda razonable sobre el cumplimiento de un criterio obligatorio, el componente no deberá recibir estado APPROVED.

La ausencia de evidencia no será interpretada como evidencia de ausencia de riesgo.

---

## 6. Registro formal de evidencia de auditoría

Toda auditoría deberá producir evidencia suficiente para permitir que una persona técnicamente competente pueda reconstruir qué fue evaluado, bajo qué condiciones, mediante qué criterios y con qué resultado.

La evidencia de auditoría deberá ser objetiva, verificable, trazable y proporcional a la criticidad del componente evaluado.

### 6.1 Contenido mínimo del registro

Cada registro de auditoría deberá incluir, cuando resulte aplicable:

1. identificador único de la auditoría;
2. fecha y hora de ejecución;
3. componente, módulo o proceso evaluado;
4. versión o commit evaluado;
5. alcance de la revisión;
6. criterios de aceptación utilizados;
7. pruebas ejecutadas;
8. resultados obtenidos;
9. hallazgos identificados;
10. severidad y prioridad de cada hallazgo;
11. riesgos conocidos y riesgo residual;
12. estado formal resultante;
13. responsable de la evaluación;
14. excepciones o limitaciones conocidas;
15. referencias a evidencia complementaria.

### 6.2 Integridad de la evidencia

La evidencia utilizada para justificar una decisión de auditoría no deberá modificarse, eliminarse o sustituirse de manera que impida reconstruir la decisión original.

Cuando una evidencia sea corregida, ampliada o reemplazada, deberá conservarse trazabilidad suficiente sobre:

- la evidencia anterior;
- la modificación realizada;
- la razón del cambio;
- la fecha del cambio;
- el responsable;
- el impacto sobre conclusiones anteriores.

### 6.3 Relación entre evidencia y aprobación

Ningún estado APPROVED o CONDITIONALLY_APPROVED deberá emitirse únicamente por apreciación subjetiva.

La decisión deberá poder relacionarse explícitamente con evidencia suficiente para los criterios aplicables.

Una prueba satisfactoria demostrará únicamente aquello que dicha prueba realmente evalúa.

La existencia de pruebas automatizadas exitosas no sustituirá evaluaciones de seguridad, arquitectura, estadística, riesgo, calidad de datos u otras disciplinas cuando sean aplicables.

### 6.4 Conservación y reproducibilidad

La evidencia relevante deberá conservarse durante un período proporcional a su importancia, riesgo y utilidad para investigación posterior.

Cuando sea técnicamente posible, deberá poder reconstruirse:

- qué versión fue evaluada;
- qué datos fueron utilizados;
- qué configuración estaba activa;
- qué pruebas fueron ejecutadas;
- qué resultados fueron obtenidos;
- qué criterios produjeron la decisión final.

La imposibilidad técnica de reproducir completamente una evaluación deberá quedar documentada como limitación.

### 6.5 Prohibición de evidencia retrospectiva engañosa

No deberá fabricarse, alterarse o reinterpretarse evidencia retrospectivamente con el propósito de justificar una decisión previamente tomada.

Cuando aparezca nueva evidencia después de una decisión, deberá registrarse como evidencia posterior y evaluarse su impacto sobre el estado de auditoría existente.

La trazabilidad deberá permitir distinguir claramente entre la evidencia disponible al momento de la decisión y la obtenida posteriormente.

---

## 7. Ciclo formal de auditoría

Toda auditoría deberá seguir un ciclo explícito que permita distinguir preparación, ejecución, evaluación, decisión y seguimiento.

### 7.1 Inicio de auditoría

Antes de comenzar una auditoría deberán identificarse, cuando resulten aplicables:

1. componente o cambio sometido a revisión;
2. versión o commit evaluado;
3. alcance de la auditoría;
4. criticidad del componente;
5. disciplinas del comité que deberán intervenir;
6. criterios de aceptación;
7. evidencia requerida;
8. riesgos conocidos;
9. dependencias relevantes;
10. condiciones y limitaciones del entorno de evaluación.

Una auditoría no deberá comenzar bajo la presunción de que el componente será aprobado.

### 7.2 Auditoría previa

Antes de incorporar un cambio material deberá evaluarse:

- necesidad y justificación;
- impacto arquitectónico;
- impacto sobre datos;
- impacto estadístico o analítico;
- impacto sobre seguridad;
- impacto sobre rendimiento y escalabilidad;
- impacto sobre riesgo;
- compatibilidad con contratos existentes;
- estrategia de pruebas;
- mecanismos de reversión cuando sean necesarios.

Los cambios de mayor criticidad requerirán evidencia proporcionalmente más rigurosa.

### 7.3 Auditoría posterior

Después de implementar un cambio deberá verificarse que:

- el comportamiento observado corresponda al esperado;
- las pruebas aplicables sean satisfactorias;
- no existan regresiones conocidas incompatibles con aprobación;
- los contratos relevantes continúen cumpliéndose;
- la trazabilidad sea suficiente;
- los riesgos nuevos hayan sido identificados;
- la documentación necesaria haya sido actualizada;
- los hallazgos hayan sido registrados.

La aprobación previa de un diseño no garantizará la aprobación de su implementación.

### 7.4 Decisión

La decisión final deberá utilizar uno de los estados formales definidos por este sistema de auditoría.

Toda decisión deberá estar respaldada por evidencia y deberá poder reconstruirse posteriormente.

Cuando las disciplinas aplicables produzcan conclusiones incompatibles, el componente permanecerá en revisión hasta resolver el conflicto o establecer formalmente una condición o excepción permitida.

### 7.5 Seguimiento

Los hallazgos no resueltos deberán conservar:

- identificador;
- severidad;
- prioridad;
- responsable;
- estado;
- fecha de registro;
- mitigaciones existentes;
- criterio verificable de cierre.

Un hallazgo solamente podrá considerarse cerrado cuando exista evidencia suficiente de que su criterio de resolución fue satisfecho.

---

## 8. Gestión formal de hallazgos y acciones correctivas

Todo hallazgo identificado durante una auditoría, prueba, revisión técnica, incidente, análisis retrospectivo o actividad de monitoreo deberá gestionarse de forma explícita y trazable.

Ningún hallazgo podrá considerarse resuelto únicamente porque el comportamiento observado haya dejado de reproducirse.

La resolución deberá estar respaldada por evidencia verificable.

### 8.1 Registro obligatorio

Todo hallazgo deberá registrar, como mínimo:

- identificador único;
- fecha de detección;
- componente afectado;
- versión o estado del componente;
- descripción objetiva del hallazgo;
- evidencia disponible;
- origen de la detección;
- severidad;
- prioridad;
- impacto potencial;
- responsable de seguimiento;
- estado actual;
- mitigaciones existentes;
- acción correctiva propuesta;
- criterio verificable de cierre.

Cuando corresponda, también deberá registrarse:

- probabilidad de ocurrencia;
- alcance del impacto;
- dependencias afectadas;
- riesgo residual;
- posibilidad de recurrencia;
- relación con hallazgos anteriores.

### 8.2 Estados del hallazgo

Todo hallazgo deberá mantener un estado explícito.

Los estados mínimos serán:

- **OPEN** — hallazgo confirmado y pendiente de tratamiento.
- **IN_ANALYSIS** — causa, impacto o solución todavía bajo investigación.
- **ACTION_REQUIRED** — existe una acción correctiva definida pendiente de ejecución.
- **MITIGATED** — el riesgo ha sido reducido temporalmente, pero la causa no necesariamente ha sido eliminada.
- **READY_FOR_VERIFICATION** — la corrección fue implementada y espera verificación independiente.
- **CLOSED** — existe evidencia suficiente de que el criterio de cierre fue satisfecho.
- **ACCEPTED_RISK** — el riesgo residual fue aceptado formalmente bajo condiciones documentadas.
- **REOPENED** — nueva evidencia demuestra que un hallazgo previamente cerrado requiere nueva evaluación.

El cambio de estado deberá ser trazable.

### 8.3 Análisis de causa

Los hallazgos relevantes no deberán tratarse únicamente mediante correcciones superficiales cuando exista evidencia de una causa subyacente.

Para hallazgos CRITICAL y HIGH deberá evaluarse, cuando resulte aplicable:

- causa inmediata;
- causa raíz;
- factores contribuyentes;
- posibilidad de recurrencia;
- existencia de defectos similares en otros componentes;
- deficiencias de pruebas, controles o monitoreo que permitieron su aparición.

La profundidad del análisis deberá ser proporcional al riesgo.

### 8.4 Acción correctiva

Toda acción correctiva deberá definir:

- qué será modificado;
- por qué la modificación responde al hallazgo;
- responsable;
- dependencias relevantes;
- riesgos introducidos por la corrección;
- pruebas necesarias;
- criterio verificable de éxito.

Una corrección no deberá introducirse únicamente para hacer que una prueba específica pase si no resuelve correctamente el comportamiento que dicha prueba representa.

### 8.5 Verificación independiente del cierre

Siempre que la criticidad lo justifique, la persona, proceso o disciplina que verifica el cierre deberá evaluar la evidencia independientemente de quien implementó la corrección.

Para cerrar un hallazgo deberá existir evidencia suficiente de que:

1. la acción definida fue ejecutada;
2. el criterio de cierre fue satisfecho;
3. las pruebas aplicables son satisfactorias;
4. no se identificaron regresiones materiales;
5. el riesgo residual es conocido;
6. la trazabilidad del cambio es suficiente.

Un hallazgo CRITICAL no podrá cerrarse únicamente mediante declaración del responsable de la implementación.

### 8.6 Reapertura

Un hallazgo cerrado deberá poder reabrirse cuando aparezca evidencia de:

- recurrencia;
- corrección incompleta;
- regresión;
- evidencia anterior incorrecta o insuficiente;
- ampliación material del impacto conocido;
- incumplimiento posterior del criterio utilizado para su cierre.

La reapertura deberá conservar la historia anterior del hallazgo.

No deberá eliminarse ni sobrescribirse la evidencia de su cierre previo.

### 8.7 Riesgo aceptado

La aceptación de riesgo no equivaldrá a la resolución técnica del hallazgo.

Todo estado **ACCEPTED_RISK** deberá documentar:

- riesgo conocido;
- justificación de aceptación;
- alcance autorizado;
- mitigaciones existentes;
- responsable de aceptar el riesgo;
- condiciones de vigencia;
- criterio o fecha de reevaluación cuando corresponda.

Los riesgos relacionados con decisiones monetarias, integridad de datos, seguridad, modelos analíticos o pérdida de trazabilidad deberán recibir una revisión proporcionalmente reforzada.

### 8.8 Prohibición de cierre administrativo engañoso

Ningún hallazgo podrá cerrarse, eliminarse, degradarse artificialmente o reclasificarse únicamente para:

- mejorar métricas de calidad;
- permitir una aprobación;
- reducir artificialmente el número de pendientes;
- ocultar deuda técnica;
- evitar una auditoría adicional;
- presentar una imagen de estabilidad no respaldada por evidencia.

Toda reclasificación deberá conservar su justificación y trazabilidad.

### 8.9 Métricas de gestión de hallazgos

El sistema de auditoría deberá permitir evaluar progresivamente, cuando exista información suficiente:

- cantidad de hallazgos abiertos por severidad;
- antigüedad de hallazgos;
- tiempo hasta mitigación;
- tiempo hasta cierre verificado;
- tasa de reapertura;
- recurrencia;
- distribución por componente;
- hallazgos detectados antes y después de liberación;
- deuda técnica pendiente relacionada con hallazgos.

Estas métricas deberán utilizarse para identificar debilidades sistémicas y mejorar controles, no para incentivar el ocultamiento o cierre prematuro de problemas.

### 8.10 Principio de aprendizaje

Los hallazgos relevantes deberán contribuir al aprendizaje documentado del sistema.

Cuando un defecto revele una debilidad generalizable, deberá evaluarse si corresponde mejorar:

- pruebas;
- contratos;
- arquitectura;
- validaciones;
- monitoreo;
- documentación;
- políticas;
- controles de riesgo;
- procedimientos de auditoría.

El objetivo no será únicamente corregir el defecto observado, sino reducir razonablemente la probabilidad de que la misma clase de fallo vuelva a producirse.

---

## 9. Puertas formales de calidad (Quality Gates)

MATRIX TENIS utilizará puertas formales de calidad para impedir que componentes, cambios o versiones avancen hacia estados de mayor confianza sin evidencia suficiente.

Superar una puerta no demostrará perfección. Demostrará únicamente que los criterios definidos para esa puerta fueron satisfechos con evidencia verificable.

La rigurosidad de cada puerta deberá ser proporcional a la criticidad, riesgo e impacto del cambio evaluado.

### 9.1 Gate G0 — Definición

Antes de iniciar la implementación de un cambio material deberá existir claridad suficiente sobre:

- problema o necesidad que se pretende resolver;
- alcance;
- comportamiento esperado;
- componentes potencialmente afectados;
- riesgos conocidos inicialmente;
- criterios de aceptación verificables.

Un cambio insuficientemente definido deberá permanecer en estado de preparación y no avanzar por presión de tiempo o conveniencia.

### 9.2 Gate G1 — Implementación local

Antes de considerar una implementación preparada para revisión deberá existir evidencia, según corresponda, de:

- código o configuración implementados;
- ausencia de errores sintácticos conocidos;
- pruebas unitarias relevantes;
- manejo razonable de casos límite identificados;
- ausencia de cambios accidentales;
- revisión básica de dependencias;
- documentación técnica mínima cuando resulte necesaria.

La implementación deberá corresponder al alcance autorizado.

### 9.3 Gate G2 — Verificación técnica

Antes de integrar un cambio material deberán evaluarse los controles técnicos aplicables.

Como mínimo se considerarán:

- pruebas automatizadas relevantes;
- pruebas de regresión;
- contratos e interfaces;
- calidad de datos;
- manejo de errores;
- trazabilidad;
- seguridad;
- compatibilidad;
- mantenibilidad;
- impacto sobre componentes dependientes.

Que todas las pruebas existentes pasen no será evidencia suficiente cuando las pruebas no cubran adecuadamente el riesgo introducido.

### 9.4 Gate G3 — Revisión multidisciplinaria

Los cambios cuya criticidad lo requiera deberán someterse a revisión por las disciplinas aplicables del Comité Multidisciplinario de Auditoría.

La revisión deberá evaluar, según corresponda:

- arquitectura;
- ingeniería de software;
- datos;
- estadística y probabilidad;
- dominio deportivo de tenis;
- QA y testing;
- seguridad;
- persistencia;
- infraestructura y operación;
- gestión de riesgo;
- auditoría y gobierno.

La aprobación de una disciplina no sustituirá las evaluaciones necesarias de las demás.

### 9.5 Gate G4 — Validación analítica

Todo cambio que pueda modificar resultados deportivos, probabilidades, puntuaciones, filtros, señales, recomendaciones o decisiones deberá superar una validación analítica proporcional a su impacto.

La evidencia podrá incluir, según corresponda:

- datasets identificados y versionados;
- separación apropiada entre entrenamiento, validación y prueba;
- prevención de fuga de información;
- métricas previamente definidas;
- análisis de calibración;
- análisis de incertidumbre;
- comparación contra baseline;
- pruebas retrospectivas reproducibles;
- evaluación fuera de muestra;
- análisis de estabilidad;
- sensibilidad a datos faltantes o degradados;
- documentación de limitaciones.

Un resultado favorable aislado no constituirá validación suficiente.

### 9.6 Gate G5 — Riesgo y decisión

Antes de permitir que un componente influya sobre una decisión relacionada con dinero deberá evaluarse explícitamente:

- calidad y suficiencia de la evidencia;
- incertidumbre;
- riesgo residual;
- límites operativos;
- condiciones de NO BET;
- degradación segura;
- exposición potencial;
- controles humanos requeridos;
- trazabilidad de la decisión.

El sistema deberá poder abstenerse de emitir una decisión cuando la evidencia sea insuficiente.

La ausencia de una oportunidad válida será un resultado legítimo del sistema.

### 9.7 Gate G6 — Preparación operativa

Antes de una liberación o utilización operativa relevante deberá existir evidencia proporcional de:

- configuración identificada;
- dependencias controladas;
- procedimiento de despliegue;
- capacidad de recuperación;
- logging suficiente;
- monitoreo;
- métricas operativas;
- gestión de errores;
- procedimiento de rollback cuando resulte aplicable;
- responsables definidos;
- documentación operativa necesaria.

No deberá autorizarse una liberación crítica cuya recuperación ante un fallo razonablemente previsible sea desconocida.

### 9.8 Gate G7 — Verificación posterior

Después de una liberación material deberá evaluarse si el comportamiento real permanece dentro de las condiciones autorizadas.

La verificación posterior podrá considerar:

- errores;
- excepciones;
- latencia;
- degradación;
- calidad de datos;
- cambios inesperados en distribuciones;
- comportamiento analítico;
- incidentes;
- señales anómalas;
- cumplimiento de límites de riesgo.

La aparición de nueva evidencia material podrá provocar:

- apertura de hallazgos;
- degradación del estado de auditoría;
- suspensión;
- rollback;
- nueva auditoría.

### 9.9 Evidencia de superación de un Gate

La superación de una puerta deberá poder relacionarse con:

- componente o cambio evaluado;
- versión o commit cuando corresponda;
- puerta evaluada;
- criterios aplicables;
- evidencia utilizada;
- pruebas ejecutadas;
- hallazgos abiertos;
- riesgos conocidos;
- decisión;
- responsable o mecanismo de aprobación;
- fecha.

Una afirmación de que una puerta fue superada sin evidencia trazable no tendrá validez de auditoría.

### 9.10 Fallo de un Gate

Cuando un criterio obligatorio no sea satisfecho, el Gate deberá considerarse fallido.

El fallo deberá producir una acción explícita, que podrá incluir:

- detener el avance;
- devolver el cambio a desarrollo;
- abrir un hallazgo;
- solicitar evidencia adicional;
- aplicar mitigaciones;
- reducir el alcance autorizado;
- suspender temporalmente el componente.

No deberá modificarse retrospectivamente el criterio únicamente para convertir un fallo en aprobación.

### 9.11 Excepciones

Las excepciones a un Gate deberán ser extraordinarias, explícitas y trazables.

Toda excepción deberá registrar:

- criterio incumplido;
- justificación;
- riesgo introducido;
- mitigaciones;
- alcance;
- responsable de aprobación;
- vigencia;
- condición de revisión o expiración.

Un hallazgo CRITICAL relacionado con seguridad, integridad de datos, trazabilidad esencial o control monetario no deberá ser omitido mediante una excepción ordinaria.

### 9.12 Automatización progresiva

Los Quality Gates deberán automatizarse progresivamente cuando resulte técnicamente seguro y verificable.

La automatización podrá incluir:

- ejecución de pruebas;
- análisis estático;
- validaciones de contratos;
- controles de calidad de datos;
- verificaciones de seguridad;
- medición de cobertura;
- comprobaciones de reproducibilidad;
- generación de evidencia;
- registro de resultados.

La automatización no eliminará la revisión humana cuando la naturaleza o criticidad de una decisión requiera juicio profesional.

### 9.13 Principio de no degradación silenciosa

Un componente que previamente haya superado una puerta no conservará indefinidamente ese estado si nueva evidencia demuestra que dejó de cumplir los criterios aplicables.

La pérdida de una condición necesaria deberá producir una reevaluación explícita.

El sistema deberá favorecer la detección temprana de degradaciones antes de que puedan afectar decisiones críticas.