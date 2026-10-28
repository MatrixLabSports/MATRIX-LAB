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
    target_home_raw=os.environ.get("MATRIX_TARGET_HOME","Inter Miami CF")
    target_away_raw=os.environ.get("MATRIX_TARGET_AWAY","FC Cincinnati")
    target_home=norm(target_home_raw)
    target_away=norm(target_away_raw)
    now=datetime.now(timezone.utc).replace(microsecond=0)
    found=[]
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp(endpoint,timeout=15000)
        for ctx in browser.contexts:
            for page in list(ctx.pages):
                try:
                    if page.is_closed(): continue
                    if "betano.co" not in (page.url or "").casefold(): continue
                    nodes=page.locator("body *").all()
                    for node in nodes:
                        try:
                            txt=(node.inner_text(timeout=300) or "").strip()
                        except Exception:
                            continue
                        n=norm(txt)
                        if not n:
                            continue
                        if target_home not in n and target_away not in n:
                            continue
                        try:
                            rec=node.evaluate("""el => {
                              const isClickable = e => {
                                if (!e) return false;
                                const tag=(e.tagName||'').toLowerCase();
                                const role=(e.getAttribute&&e.getAttribute('role')||'').toLowerCase();
                                return tag==='a' || tag==='button' || role==='link' || role==='button' ||
                                       !!(e.onclick) || (e.hasAttribute&&e.hasAttribute('href'));
                              };
                              let cur=el;
                              for (let i=0;i<8 && cur;i++,cur=cur.parentElement) {
                                if (isClickable(cur)) {
                                  return {
                                    tag:(cur.tagName||'').toLowerCase(),
                                    role:cur.getAttribute?.('role')||null,
                                    href:cur.getAttribute?.('href')||null,
                                    text:(cur.innerText||'').trim(),
                                    outer:(cur.outerHTML||'').slice(0,1500)
                                  };
                                }
                              }
                              return null;
                            }""")
                        except Exception:
                            rec=None
                        found.append({
                          "matched_text":txt[:500],
                          "page_url":page.url,
                          "clickable_ancestor":rec
                        })
                except Exception:
                    continue
        # Do not close externally managed CDP browser.
    unique=[]
    seen=set()
    for x in found:
        key=json.dumps(x.get("clickable_ancestor"),sort_keys=True,ensure_ascii=False) if x.get("clickable_ancestor") else x["matched_text"]
        if key in seen: continue
        seen.add(key); unique.append(x)
    out={
      "schema":"MATRIX_BETANO_EVENT_LINK_PROBE_V2",
      "generated_at_utc":now.isoformat(),
      "target":{"home":target_home_raw,"away":target_away_raw},
      "matches":unique[:50],
      "count":len(unique),
      "status":"PASS_CLICKABLE_EVENT_CONTEXT_FOUND" if any(x.get("clickable_ancestor") for x in unique) else ("PASS_TEXT_CONTEXT_FOUND" if unique else "NO_EVENT_CONTEXT_FOUND"),
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":out["status"],"count":out["count"],"matches":out["matches"][:10]},ensure_ascii=False))

if __name__=="__main__":
    main()
