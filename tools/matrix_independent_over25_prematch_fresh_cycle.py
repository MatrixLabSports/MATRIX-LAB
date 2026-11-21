"""Idempotent current/next Bogota-day seal from actual prior provider captures.

Safe to run on each Windows collector cycle. Does not call a provider, invent
models, backdate a freeze, or publish any governed predictions.
"""
from __future__ import annotations
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from tools.matrix_independent_over25_prematch_freeze import freeze,canonical,ROOT

def cycle(root:Path,*,now:datetime)->dict:
    day=now.astimezone(ZoneInfo("America/Bogota")).date()
    checks=[]
    for d in (day,day+timedelta(days=1)):
        date=d.isoformat()
        folder=root/"evidence"/"football_world_inventory"/date
        a=folder/"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json"
        b=folder/"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"
        if not a.is_file() or not b.is_file():
            checks.append({"date":date,"status":"REQUIRED_AUTHENTIC_PROVIDER_SOURCE_MISSING",
                "sealed_count":0,"blocked":[]})
            continue
        try:
            intake_bytes=a.read_bytes();shadow_bytes=b.read_bytes()
            report=freeze(json.loads(intake_bytes),json.loads(shadow_bytes),
                intake_bytes=intake_bytes,shadow_bytes=shadow_bytes,now=now,
                folder=root/ROOT/date)
            report_path=folder/"MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_REPORT.json"
            report_path.parent.mkdir(parents=True,exist_ok=True)
            report_path.write_bytes(canonical(report))
            checks.append({"date":date,"status":report["status"],
                "sealed_count":report["immutable_prematch_freeze_count"],
                "blocked":report["blocked"][:30],"report_path":str(report_path.relative_to(root)).replace("\\","/")})
        except (OSError,ValueError,TypeError,KeyError,UnicodeError,json.JSONDecodeError) as exc:
            checks.append({"date":date,"status":"BLOCKED_INVALID_AUTHENTIC_SOURCES",
                "sealed_count":0,"error_type":type(exc).__name__,
                "blocked":[{"reason":str(exc)[:180]}]})
    return {"schema":"MATRIX_INDEPENDENT_OVER25_RESEARCH_CYCLE_V1",
      "checked_at_utc":now.astimezone(timezone.utc).isoformat(),
      "checks":checks,"total_immutable_research_freezes_seen":sum(x["sealed_count"] for x in checks),
      "model_promoted":False,"telegram_signal_authorized":False,
      "automatic_wagering":False,"real_money":"BLOCKED"}

def main():
    result=cycle(Path.cwd(),now=datetime.now(timezone.utc))
    out=Path("evidence/football_world_inventory/MATRIX_INDEPENDENT_OVER25_PREMATCH_FREEZE_CYCLE_LAST.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(canonical(result))
    print(json.dumps({"status":[x["status"] for x in result["checks"]],
      "research_freeze_count":result["total_immutable_research_freezes_seen"],
      "telegram_signal_authorized":False},sort_keys=True))

if __name__=="__main__":main()
