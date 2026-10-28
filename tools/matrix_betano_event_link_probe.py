from __future__ import annotations
import json, os, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_BETANO_EVENT_LINK_PROBE_LAST.json"

def norm(v):
    x=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+"," ",x).strip()

def main():
    endpoint=os.environ.get("MATRIX_BROWSER_CDP_ENDPOINT","http://127.0.0.1:9222")
    target_home=norm(os.environ.get("MATRIX_TARGET_HOME","Inter Miami CF"))
    target_away=norm(os.environ.get("MATRIX_TARGET_AWAY","FC Cincinnati"))
    now=datetime.now(timezone.utc).replace(microsecond=0)
    found=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=15000)
        for ctx in browser.contexts:
            for page in list(ctx.pages):
                try:
                    if page.is_closed(): continue
                    if "betano.co" not in (page.url or "").casefold(): continue
                    anchors=page.locator("a").all()
                    for a in anchors:
                        try:
                            txt=(a.inner_text(timeout=1000) or "").strip()
                            href=a.get_attribute("href") or ""
                        except Exception:
                            continue
                        n=norm(txt)
                        if target_home in n or target_away in n:
                            found.append({"text":txt,"href":href,"page_url":page.url})
                except Exception:
                    continue
        # Do not close externally managed CDP browser.
    out={
      "schema":"MATRIX_BETANO_EVENT_LINK_PROBE_V1",
      "generated_at_utc":now.isoformat(),
      "target":{"home":target_home,"away":target_away},
      "links":found,
      "count":len(found),
      "status":"PASS_LINKS_FOUND" if found else "NO_EVENT_LINK_FOUND",
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"count":out["count"],"links":out["links"][:10]},ensure_ascii=False))

if __name__=="__main__":
    main()
