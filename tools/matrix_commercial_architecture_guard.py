from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(name):
    return json.loads((ROOT/"config"/name).read_text(encoding="utf-8"))

def validate():
    p=load("MATRIX_COMMERCIAL_PRODUCT_POLICY.json")
    s=load("MATRIX_TELEGRAM_CHANNEL_SECURITY_POLICY.json")
    m=load("MATRIX_MEMBERSHIP_POLICY.json")
    x=load("MATRIX_STAKAZO_3X_POLICY.json")
    errors=[]
    if p["products"]["PREMIUM_WEEKLY"]["price_cop"]!=50000: errors.append("WEEKLY_PRICE")
    if p["products"]["PREMIUM_MONTHLY"]["price_cop"]!=150000: errors.append("MONTHLY_PRICE")
    if x["price_per_slot_cop"]!=15000: errors.append("STAKAZO_PRICE")
    if x["daily_slot_cap"]!=30: errors.append("STAKAZO_CAP")
    if x["combined_decimal_odds_exclusive_min"]!=3.0: errors.append("STAKAZO_ODDS")
    if x["customer_promise"]["maximum_replacements"]!=2: errors.append("REPLACEMENTS")
    if s["channels"]["FREE"]["visibility"]!="PUBLIC": errors.append("FREE_VISIBILITY")
    if s["channels"]["PREMIUM"]["visibility"]!="PRIVATE" or s["channels"]["STAKAZO"]["visibility"]!="PRIVATE": errors.append("PAID_CHANNEL_PRIVACY")
    if any(v["external_bots_allowed"] for v in s["channels"].values()): errors.append("BOT_POLICY")
    if not all(v["protect_content"] for v in s["channels"].values()): errors.append("PROTECT_CONTENT")
    if m["plans"]["WEEKLY"]["duration_days"]!=7 or m["plans"]["MONTHLY"]["duration_days"]!=30: errors.append("MEMBERSHIP_DURATION")
    if p["truth_in_advertising"]["profit_guarantee"]: errors.append("PROFIT_GUARANTEE")
    if p["sports_governance"]["force_volume"]: errors.append("FORCE_VOLUME")
    return errors

if __name__=="__main__":
    errs=validate()
    if errs:
        raise SystemExit("MATRIX_COMMERCIAL_POLICY_INVALID:"+",".join(errs))
    print("MATRIX_COMMERCIAL_ARCHITECTURE_POLICY_PASS")
