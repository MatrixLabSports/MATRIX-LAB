# MATRIX — Corrección canónica del indicador 8/11

Se localizó y leyó el artefacto físico:
`evidence/football_world_inventory/2026-11-03/MATRIX_CHAMPIONSHIP_ENRICHED_BRIDGE_WINDOWS_41652604235.json`.

**Interpretación verificada:** el denominador 11 corresponde a `original_canonical_targets` (once **partidos** históricos de Championship), no a once características del modelo. El numerador 8 corresponde a `historical_three_way_parity_count`: ocho partidos con probabilidades históricas iguales entre original enriquecido, original de grupo y grupo de proveedor alternativo.

Los tres partidos bloqueados figuran en `rows` con:
- `1563221` — `BLOCKED_HISTORICAL_TEAM_CROSSWALK_MISSING`
- `1563222` — `BLOCKED_HISTORICAL_TEAM_CROSSWALK_MISSING`
- `1563226` — `BLOCKED_HISTORICAL_TEAM_CROSSWALK_MISSING`

**No hay ninguna evidencia de que sean tres características matemáticas divergentes.** Cualquier informe previo que describa ese 8/11 como once variables debe considerarse supersedido para esta cifra.

El motor `tools/matrix_championship_enriched_provider_bridge.py` produce ese conteo. El diagnóstico complementario `tools/matrix_championship_eight_of_eleven_identity_gap_diagnostic.py` rastrea los tres ID al bundle original y busca candidatos de identidad sin usar goles del partido objetivo.

**Límites no resueltos:** archivo histórico ≠ captura prospectiva original; el cruce de equipos a posteriori no acredita un cruce disponible antes del PIT. La validación de seis ligas requiere pares enriquecidos verdaderamente congelados. Sin certificación del proveedor alternativo, `p_matrix` sigue sin autorización; cuota auténtica y referencia Pinnacle permanecen gates separados.

`REAL_MONEY=BLOCKED`, `automatic_wagering=false`, `telegram_signal_authorized=false`. Las matrices y calibraciones no se modificaron.
