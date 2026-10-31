from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config"/"OMEGA_PICKS_BRAND_SYSTEM.json"
ASSET=ROOT/"assets"/"brand"/"omega_picks"

def validate():
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    errors=[]
    if cfg.get("public_brand")!="OMEGA PICKS": errors.append("PUBLIC_BRAND")
    if cfg["slogans"]["primary"]!="Los datos hablan. Tú decides.": errors.append("PRIMARY_SLOGAN")
    if cfg["slogans"]["campaign"]!="El deporte se siente. Las decisiones se calculan.": errors.append("CAMPAIGN_SLOGAN")
    if cfg["slogans"]["technical_commercial"]!="Analizamos datos. Buscamos valor.": errors.append("TECHNICAL_SLOGAN")
    required={"omega_blue":"#007BFF","graphite":"#0B0D12","metallic_silver":"#C0C6D1","white":"#FFFFFF","energy_cyan":"#00D6FF"}
    for k,v in required.items():
        if cfg["palette"].get(k,{}).get("hex")!=v: errors.append(f"COLOR_{k}")
    for name in ["omega_picks_primary.svg","omega_picks_avatar.svg","omega_picks_monochrome.svg"]:
        p=ASSET/name
        if not p.exists(): errors.append(f"MISSING_{name}")
        elif "<svg" not in p.read_text(encoding="utf-8"): errors.append(f"INVALID_{name}")
    if cfg["truth_rules"]["no_guaranteed_profit_claims"] is not True: errors.append("TRUTH_PROFIT")
    if cfg["truth_rules"]["no_guaranteed_win_claims"] is not True: errors.append("TRUTH_WIN")
    return errors

if __name__=="__main__":
    e=validate()
    if e: raise SystemExit("OMEGA_PICKS_BRAND_INVALID:"+",".join(e))
    print("OMEGA_PICKS_BRAND_SYSTEM_PASS")
