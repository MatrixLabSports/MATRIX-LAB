# RESUMEN EJECUTIVO DE HANDOFF — MATRIX-LAB-SPORTS
## 28-SEP-2026 — POST-R734 + TENIS 47/600 + COR10 RESUELTO + FÚTBOL FREEZE 67

## 1. Estado global
- `RESEARCH_VALIDATION_NOT_PRODUCTION_READY`
- `EXTERNAL_AUDIT = NOT_CLOSED`
- `REAL_MONEY = BLOCKED`
- `AUTOMATIC_WAGERING = FALSE`
- La evidencia física del repositorio/runtime manda sobre chat, memoria y resúmenes.

## 2. CI
Cabeza operativa previa al handoff:
`02ed415ea37000bc3a53270257e280c9d5c47635`

MATRIX CI:
- run `36424149666`
- 3158 pruebas PASS
- `MATRIX CI QUALITY GATE: PASS`

El fallo previo de tres tests era solo `NameError: _load`; quedó corregido sin modificar reglas de producción.

## 3. Correcciones externas
Resueltas:
COR01, COR04, COR05, COR06, COR07, COR08, COR09, COR10, COR12.

Pendientes:
COR02, COR03, COR11.

Estado: **9/12 resueltas, 3/12 abiertas**.

### COR10
Ya está físicamente RESUELTO mediante ejecución shadow genuina:
- Georgia vs Ukraine
- Over 2.5
- Pinnacle @2.2
- stake nominal 1000 COP
- sin transferencia de fondos
- freeze y quote pre-kickoff
- `odds_used_to_generate_probability=false`
- real money bloqueado.

### COR11
Estado reflejado al handoff:
- 8/14 días reales consecutivos
- 21–28 SEP
- no backfill
- no días sintéticos.

## 4. Tenis COR02/COR03
Proveedor:
- RapidAPI Tennis
- plan Ultra
- secreto `RAPIDAPI_TENNIS_KEY`

Holdout:
- **47/600**
- Window 1: **47/200**
- 47/47 integridad PASS
- 0 fallos
- 0 outcomes leídos para performance
- métricas selladas hasta 600
- real money bloqueado

Modelos congelados:
- R218 ELO BOTH
- R223 BATCH GLICKO RATING BOTH
- binding R707

## 5. Solución de identidad
R730 tenía 17 eventos.

Resultado actual:
- 15 PASS
- 2 BLOCKED

Bloqueados:
- evento 1471 por Keisuke Saitoh / provider id 76126
- evento 1466 por Alexandr Binda / provider id 73055

No se forzaron joins por nombre.

Mejoras:
- R731: autoridad pre-corte + Sackmann.
- R732: perfiles Ultra por ID exacto, solo biografía/identidad.
- R733: cuatro casos adicionales resueltos.
- R734: `Marat Sharipov (RUS)` proveedor → `Marat Sharipov` canónico con ID pre-corte S0MN y 27 filas históricas.

## 6. Restaging append-only
Se solucionó el problema `ALREADY_STAGED`.

Nueva herramienta:
`tools/cor0203_identity_restage_delta.py`

Regla:
- staging viejo no se sobrescribe;
- mejoras de identidad generan delta nuevo;
- sin re-selección por resultado/modelo;
- sin duplicar freezes;
- cambio canónico permitido solo con evidencia.

R731 delta:
- 1415 y 1469 congelados válidamente.
- 1475 quedó inicialmente bloqueado por etiqueta Marat.

R732 delta:
- restage de 1475 tras R734.
- freeze válido.
- holdout 46→47.

## 7. Horizonte Ultra
4 días es el horizonte operativo útil demostrado.

Probe días 5–8:
- PASS técnico
- 3 llamadas
- 900 rankings encontrados
- 0 fixtures
- 0 elegibles
- sin 429

No se promovió a 8 días porque no agrega inventario.

## 8. Fútbol canonical
`canonical_analysis/manifest.json`:
- 83 fixtures total
- 82 builder outputs
- 81 ready
- 1 future bloqueado
- 1 ya no futuro al analysis_as_of
- 2 targets rechazados
- baseline Poisson experimental
- P_MATRIX no generado
- real money bloqueado

Engine registry:
- ningún motor gobernado ejecutable para P_MATRIX todavía.
- R315/R442/R316/R318/R320/R322 no se consideran promovidos solo por identificador.

## 9. Fútbol challenger
Dataset retrospectivo:
- 2379 observaciones
- 1665 desarrollo
- 357 validación
- 357 final holdout

Final holdout V1:
- 1X2 PASS contra Poisson
- Over 2.5 PASS
- BTTS FAIL

Gobierno por mercado:
- 1X2 aprobado para próximos gates
- Over 2.5 aprobado para próximos gates
- BTTS V1 rechazado
- ninguno es P_MATRIX todavía.

## 10. BTTS V2
`btts_logistic_challenger_v2`
- congelado
- validación superior a Poisson
- espera holdout prospectivo nuevo
- los 357 del holdout final antiguo están permanentemente excluidos de training/validation/tuning.

## 11. Fútbol freeze prospectivo
Primer freeze prospectivo genuino:
- **67 eventos congelados**
- 14 excluidos
- future-only
- unseen-only
- freeze antes de kickoff
- sin imputación
- sin outcomes al freeze
- settlement FINAL-only
- odds no generan probabilidad
- P_MATRIX no generado
- real money bloqueado

Freeze SHA:
`692bf57783664baffe2b9fb3af8cc85153557ee7086a8e09fc870e292e95abe3`

## 12. Settlement fútbol
Herramienta:
`tools/api_football_prospective_api_settlement.py`

Solo FT automático.
Otros estados requieren adjudicación.

Último sync físico leído al handoff:
- 67 pendientes
- 0 settled persistidos
- metrics_opened=false
- status PASS
- archivo puede quedar obsoleto por cron, por lo que debe reconsultarse al reanudar.

## 13. Pinnacle
Pinnacle es referencia mediante API-Football, no conexión Pinnacle directa.
- bookmaker id 4
- cobertura previa 47/83
- 17 mercados
- 4021 reference quotes
- nunca genera P_MODEL/P_MATRIX.

## 14. RushBet
RushBet NO está verificada usada.
No aparece en API-Football.

Ruta preparada:
- odds-api.net
- código + tests + workflow listos
- secret esperado `ODDS_API_NET_KEY`

Estado:
`PREACTIVATION / CREDENTIAL_REQUIRED / NOT VERIFIED USED`

## 15. Reglas que NO se pueden perder
- evidencia física manda;
- no mentir ni inventar uso de API;
- Missing != 0;
- no imputación silenciosa;
- no odds→P;
- PIT/anti-leakage;
- identidad gobernada;
- no joins silenciosos por nombre;
- freeze inmutable;
- settlement FINAL-only;
- no backfill prospectivo;
- métricas selladas hasta gate;
- no reutilizar holdout para tuning;
- append-only;
- tenis/fútbol separados;
- real money bloqueado.

## 16. Próximo trabajo
Al reanudar:
1. reconsultar heads + CI;
2. leer prompt maestro nuevo;
3. confirmar tenis actual (puede haber avanzado por scheduler);
4. confirmar COR11;
5. confirmar settlement fútbol;
6. continuar tenis 47→600;
7. mantener Saitoh/Binda bloqueados salvo nueva evidencia real;
8. mantener freeze fútbol inmutable y settlement FINAL-only;
9. preregistrar cualquier gate prospectivo antes de abrir outcomes;
10. no activar RushBet sin prueba física real.

No empezar desde cero.
