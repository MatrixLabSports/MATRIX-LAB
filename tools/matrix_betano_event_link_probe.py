from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidence" / "notifications" / "telegram" / "MATRIX_BETANO_EVENT_LINK_PROBE_LAST.json"


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def main():
    endpoint = os.environ.get("MATRIX_BROWSER_CDP_ENDPOINT", "http://127.0.0.1:9222")
    target_home_raw = os.environ.get("MATRIX_TARGET_HOME", "Inter Miami CF")
    target_away_raw = os.environ.get("MATRIX_TARGET_AWAY", "FC Cincinnati")
    target_home = norm(target_home_raw)
    target_away = norm(target_away_raw)
    now = datetime.now(timezone.utc).replace(microsecond=0)

    found = []
    ancestry = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint, timeout=15000)

        for ctx in browser.contexts:
            for page in list(ctx.pages):
                try:
                    if page.is_closed():
                        continue
                    if "betano.co" not in (page.url or "").casefold():
                        continue

                    nodes = page.locator("body *").all()
                    for node in nodes:
                        try:
                            txt = (node.inner_text(timeout=300) or "").strip()
                        except Exception:
                            continue

                        normalized = norm(txt)
                        if not normalized:
                            continue
                        if target_home not in normalized and target_away not in normalized:
                            continue

                        try:
                            clickable = node.evaluate(
                                """el => {
                                  const isClickable = e => {
                                    if (!e) return false;
                                    const tag = (e.tagName || '').toLowerCase();
                                    const role = (e.getAttribute && e.getAttribute('role') || '').toLowerCase();
                                    return tag === 'a' || tag === 'button' || role === 'link' || role === 'button' ||
                                           !!e.onclick || (e.hasAttribute && e.hasAttribute('href'));
                                  };
                                  let cur = el;
                                  for (let i = 0; i < 8 && cur; i++, cur = cur.parentElement) {
                                    if (isClickable(cur)) {
                                      return {
                                        tag: (cur.tagName || '').toLowerCase(),
                                        role: cur.getAttribute?.('role') || null,
                                        href: cur.getAttribute?.('href') || null,
                                        text: (cur.innerText || '').trim(),
                                        outer: (cur.outerHTML || '').slice(0, 1500)
                                      };
                                    }
                                  }
                                  return null;
                                }"""
                            )
                        except Exception:
                            clickable = None

                        found.append(
                            {
                                "matched_text": txt[:500],
                                "page_url": page.url,
                                "clickable_ancestor": clickable,
                            }
                        )

                    hits = page.get_by_text(target_home_raw, exact=True)
                    for i in range(min(hits.count(), 10)):
                        try:
                            chain = hits.nth(i).evaluate(
                                """el => {
                                  const out = [];
                                  let cur = el;
                                  for (let depth = 0; depth < 10 && cur; depth++, cur = cur.parentElement) {
                                    out.push({
                                      depth,
                                      tag: (cur.tagName || '').toLowerCase(),
                                      id: cur.id || null,
                                      cls: typeof cur.className === 'string' ? cur.className : null,
                                      role: cur.getAttribute?.('role') || null,
                                      href: cur.getAttribute?.('href') || null,
                                      tabindex: cur.getAttribute?.('tabindex') || null,
                                      dataTestId: cur.getAttribute?.('data-testid') || null,
                                      dataCy: cur.getAttribute?.('data-cy') || null,
                                      ariaLabel: cur.getAttribute?.('aria-label') || null,
                                      text: (cur.innerText || '').trim().slice(0, 700),
                                      outer: (cur.outerHTML || '').slice(0, 1800)
                                    });
                                  }
                                  return out;
                                }"""
                            )
                            ancestry.append(
                                {
                                    "page_url": page.url,
                                    "hit_index": i,
                                    "chain": chain,
                                }
                            )
                        except Exception:
                            continue
                except Exception:
                    continue

        # Never close the externally managed CDP browser.

    unique = []
    seen = set()
    for item in found:
        clickable = item.get("clickable_ancestor")
        key = (
            json.dumps(clickable, sort_keys=True, ensure_ascii=False)
            if clickable
            else item["matched_text"]
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    component_meta = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint, timeout=15000)
        for ctx in browser.contexts:
            for page in list(ctx.pages):
                try:
                    if page.is_closed() or "betano.co" not in (page.url or "").casefold():
                        continue
                    headers = page.locator('[data-qa="smart-picks-event-header"]').filter(has_text=target_home_raw)
                    for i in range(min(headers.count(), 10)):
                        try:
                            meta = headers.nth(i).evaluate("""el => {
                              const card = el.closest('[data-qa="smart-picks-card"]');
                              const safe = value => {
                                try {
                                  return JSON.parse(JSON.stringify(value, (k,v) => {
                                    if (typeof v === 'function') return undefined;
                                    if (typeof v === 'bigint') return String(v);
                                    return v;
                                  }));
                                } catch { return null; }
                              };
                              const summarize = obj => {
                                if (!obj || typeof obj !== 'object') return null;
                                const out = {};
                                for (const k of Object.keys(obj).slice(0,100)) {
                                  if (/event|fixture|match|sport|id|url|route|link|slug/i.test(k)) {
                                    const v = obj[k];
                                    if (v == null || ['string','number','boolean'].includes(typeof v)) out[k]=v;
                                    else out[k]=safe(v);
                                  }
                                }
                                return out;
                              };
                              let cur = card;
                              const chain=[];
                              for (let d=0; d<8 && cur; d++, cur=cur.parentElement) {
                                chain.push({
                                  depth:d,
                                  tag:(cur.tagName||'').toLowerCase(),
                                  attrs:Object.fromEntries([...cur.attributes].map(a=>[a.name,a.value])),
                                  ownKeys:Object.getOwnPropertyNames(cur).filter(k=>/vue|event|route|link|id/i.test(k)).slice(0,50),
                                  vueProps:summarize(cur.__vueParentComponent?.props),
                                  vueAttrs:summarize(cur.__vueParentComponent?.attrs),
                                  vueSetup:summarize(cur.__vueParentComponent?.setupState),
                                  vueExposed:summarize(cur.__vueParentComponent?.exposed),
                                  dataset:{...cur.dataset}
                                });
                              }
                              return {card_found:!!card, chain};
                            }""")
                            component_meta.append({"page_url": page.url, "hit_index": i, "meta": meta})
                        except Exception:
                            continue
                except Exception:
                    continue
        # Never close the externally managed CDP browser.

    network_resources = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint, timeout=15000)
        for ctx in browser.contexts:
            for page in list(ctx.pages):
                try:
                    if page.is_closed() or "betano.co" not in (page.url or "").casefold():
                        continue
                    resources = page.evaluate("""() => performance.getEntriesByType('resource').map(r => ({
                      name:r.name,
                      initiatorType:r.initiatorType,
                      duration:r.duration,
                      transferSize:r.transferSize
                    }))""")
                    for item in resources:
                        url = str(item.get("name") or "")
                        low = url.casefold()
                        if any(token in low for token in [
                            "event", "fixture", "match", "sport", "market", "coupon", "bet",
                            "prematch", "pre-match", "smart", "selection"
                        ]):
                            network_resources.append({
                                "page_url": page.url,
                                "url": url,
                                "initiator_type": item.get("initiatorType"),
                                "duration": item.get("duration"),
                                "transfer_size": item.get("transferSize"),
                            })
                except Exception:
                    continue
        # Never close the externally managed CDP browser.

    api_matches = []
    prematch_candidate_probe = []
    try:
        audit_path = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json")
        audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
        now_utc = datetime.now(timezone.utc)
        candidates = []
        for rec in audit.get("records", []):
            try:
                kickoff = datetime.fromisoformat(str(rec.get("kickoff")).replace("Z", "+00:00"))
            except Exception:
                continue
            if kickoff <= now_utc:
                continue
            if rec.get("recoverability") not in {
                "RECOVERABLE_WHILE_PREMATCH",
                "RECOVERABLE_WITH_BETTER_AUTHORIZED_QUOTE_WHILE_PREMATCH",
                "TEMPORAL_WAIT",
            }:
                continue
            match = str(rec.get("match") or "")
            if " vs " not in match:
                continue
            home, away = match.split(" vs ", 1)
            candidates.append({
                "fixture_id": rec.get("fixture_id"),
                "home": home.strip(),
                "away": away.strip(),
                "kickoff": kickoff.isoformat(),
                "p_matrix": rec.get("p_matrix"),
                "recoverability": rec.get("recoverability"),
            })
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint, timeout=15000)
            for ctx in browser.contexts:
                for page in list(ctx.pages):
                    try:
                        if page.is_closed() or "betano.co" not in (page.url or "").casefold():
                            continue
                        result = page.evaluate("""async (candidates) => {
                          const endpoints=[
                            '/api/home/top-events-v2/',
                            '/danae-webapi/api/live/overview/latest?includeVirtuals=true&queryLanguageId=8&queryOperatorId=17'
                          ];
                          const norm=s=>String(s||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'');
                          const containsPair=(obj,home,away)=>{
                            try {
                              const t=norm(JSON.stringify(obj));
                              return t.includes(home) && t.includes(away);
                            } catch { return false; }
                          };
                          const findObjects=(node,home,away,path='root',acc=[])=>{
                            if (node==null || acc.length>=30) return acc;
                            if (Array.isArray(node)) {
                              node.forEach((v,i)=>findObjects(v,home,away,path+'['+i+']',acc));
                              return acc;
                            }
                            if (typeof node==='object') {
                              if (containsPair(node,home,away)) {
                                const keys=Object.keys(node);
                                const eventish=keys.some(k=>/id|event|fixture|match|participant|market|selection|url|start|live/i.test(k));
                                if (eventish) acc.push({path,object:node});
                              }
                              for (const [k,v] of Object.entries(node)) findObjects(v,home,away,path+'.'+k,acc);
                            }
                            return acc;
                          };
                          const responses=[];
                          for (const endpoint of endpoints) {
                            try {
                              const r=await fetch(endpoint,{credentials:'include',cache:'no-store'});
                              const body=await r.json();
                              responses.push({endpoint,status:r.status,body});
                            } catch(e) {
                              responses.push({endpoint,error:String(e),body:null});
                            }
                          }
                          const out=[];
                          for (const c of candidates) {
                            const ch=norm(c.home), ca=norm(c.away);
                            const endpointMatches=[];
                            for (const resp of responses) {
                              if (!resp.body) { endpointMatches.push({endpoint:resp.endpoint,status:resp.status,error:resp.error,matches:[]}); continue; }
                              const buildIdIndex=(root)=>{
                                const idx=new Map();
                                const seen=new Set();
                                const visit=node=>{
                                  if (node==null || typeof node!=='object' || seen.has(node)) return;
                                  seen.add(node);
                                  if (!Array.isArray(node) && node.id!=null) idx.set(String(node.id),node);
                                  if (Array.isArray(node)) node.forEach(visit);
                                  else Object.values(node).forEach(visit);
                                };
                                visit(root);
                                return idx;
                              };
                              const idIndex=buildIdIndex(resp.body);
                              const matches=findObjects(resp.body,ch,ca).slice(0,10).map(m=>{
                                const o=m.object||{};
                                const marketIds=Array.isArray(o.marketIdList)?o.marketIdList.map(String):[];
                                const exactMarkets=[];
                                const exactOver25=[];
                                for (const mid of marketIds) {
                                  const market=idIndex.get(mid);
                                  if (!market) continue;
                                  const mname=norm(market.name);
                                  const mh=Number(market.handicap);
                                  const looksTotal=(mname.includes('goles totales') || market.type==='HCTG' || market.type==='OVUN');
                                  if (!looksTotal || mh!==2.5) continue;
                                  const selectionIds=Array.isArray(market.selectionIdList)?market.selectionIdList.map(String):[];
                                  const selections=selectionIds.map(id=>idIndex.get(id)).filter(Boolean);
                                  const overs=selections.filter(sel=>{
                                    const sn=norm(sel.name||sel.fullName||'');
                                    return Number(sel.handicap)===2.5 && sn.includes('mas de 2.5') && sel.price!=null;
                                  }).map(sel=>({
                                    id:sel.id,name:sel.name,fullName:sel.fullName,handicap:sel.handicap,
                                    price:sel.price,typeId:sel.typeId,market_id:market.id,market_name:market.name,market_type:market.type
                                  }));
                                  exactMarkets.push({
                                    id:market.id,name:market.name,type:market.type,handicap:market.handicap,
                                    selectionIdList:market.selectionIdList,selections:selections.map(sel=>({
                                      id:sel.id,name:sel.name,fullName:sel.fullName,handicap:sel.handicap,price:sel.price,typeId:sel.typeId
                                    }))
                                  });
                                  exactOver25.push(...overs);
                                }
                                return {
                                  path:m.path,
                                  event:{
                                    id:o.id ?? o.eventId ?? o.fixtureId ?? o.matchId ?? null,
                                    url:o.url ?? o.eventUrl ?? o.route ?? null,
                                    isLive:o.isLive ?? null,
                                    startTime:o.startTime ?? o.startDate ?? o.kickoff ?? null,
                                    participants:o.participants ?? o.competitors ?? null,
                                    marketIdList:o.marketIdList ?? null
                                  },
                                  exact_over25_markets:exactMarkets,
                                  exact_over25:exactOver25,
                                  exact_association_certifiable:exactOver25.length>0,
                                  object:o
                                };
                              });
                              endpointMatches.push({endpoint:resp.endpoint,status:resp.status,matches});
                            }
                            const any=endpointMatches.some(e=>e.matches.length>0);
                            out.push({...c,status:any?'BETANO_PREMATCH_CONTEXT_FOUND':'NO_BETANO_EVENT_MATCH',endpoint_matches:endpointMatches});
                          }
                          return {candidates:out};
                        }""", candidates)
                        prematch_candidate_probe.append({"page_url": page.url, "result": result})
                        break
                    except Exception as exc:
                        prematch_candidate_probe.append({"page_url": page.url, "error": str(exc)})
                if prematch_candidate_probe:
                    break
    except Exception as exc:
        prematch_candidate_probe.append({"error": str(exc)})


    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint, timeout=15000)
        for ctx in browser.contexts:
            for page in list(ctx.pages):
                try:
                    if page.is_closed() or "betano.co" not in (page.url or "").casefold():
                        continue
                    result = page.evaluate("""async ({home, away}) => {
                      const endpoints = [
                        '/api/home/top-events-v2/',
                        '/danae-webapi/api/live/overview/latest?includeVirtuals=true&queryLanguageId=8&queryOperatorId=17'
                      ];
                      const out=[];
                      const walk=(node,path='root',acc=[])=>{
                        if (node == null) return acc;
                        if (typeof node === 'string') {
                          const low=node.toLowerCase();
                          if (low.includes(home.toLowerCase()) || low.includes(away.toLowerCase())) acc.push({path,value:node});
                          return acc;
                        }
                        if (Array.isArray(node)) {
                          node.forEach((v,i)=>walk(v, path+'['+i+']', acc));
                          return acc;
                        }
                        if (typeof node === 'object') {
                          const text=JSON.stringify(node).toLowerCase();
                          if (text.includes(home.toLowerCase()) && text.includes(away.toLowerCase())) {
                            acc.push({path,object:node});
                            return acc;
                          }
                          for (const [k,v] of Object.entries(node)) walk(v, path+'.'+k, acc);
                        }
                        return acc;
                      };
                      for (const endpoint of endpoints) {
                        try {
                          const r=await fetch(endpoint,{credentials:'include',cache:'no-store'});
                          const ct=r.headers.get('content-type')||'';
                          let body;
                          if (ct.includes('json')) body=await r.json(); else body=await r.text();
                          const matches=walk(body).slice(0,20);
                          out.push({endpoint,status:r.status,contentType:ct,matches});
                        } catch (e) {
                          out.push({endpoint,error:String(e)});
                        }
                      }
                      return out;
                    }""", {"home": target_home_raw, "away": target_away_raw})
                    api_matches.append({"page_url": page.url, "results": result})
                except Exception as exc:
                    api_matches.append({"page_url": page.url, "error": str(exc)})
        # Never close the externally managed CDP browser.

    out = {
        "schema": "MATRIX_BETANO_EVENT_LINK_PROBE_V3",
        "generated_at_utc": now.isoformat(),
        "target": {"home": target_home_raw, "away": target_away_raw},
        "matches": unique[:50],
        "ancestry": ancestry[:20],
        "component_meta": component_meta[:20],
        "network_resources": network_resources[:500],
        "api_matches": api_matches[:20],
        "prematch_candidate_probe": prematch_candidate_probe[:10],
        "count": len(unique),
        "ancestry_count": len(ancestry),
        "component_meta_count": len(component_meta),
        "network_resource_count": len(network_resources),
        "api_match_context_count": len(api_matches),
        "prematch_candidate_probe_count": len(prematch_candidate_probe),
        "status": (
            "PASS_CLICKABLE_EVENT_CONTEXT_FOUND"
            if any(item.get("clickable_ancestor") for item in unique)
            else ("PASS_TEXT_CONTEXT_FOUND" if unique else "NO_EVENT_CONTEXT_FOUND")
        ),
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "status": out["status"],
                "count": out["count"],
                "ancestry_count": out["ancestry_count"],
                "ancestry": out["ancestry"][:3],
                "component_meta_count": out["component_meta_count"],
                "component_meta": out["component_meta"][:3],
                "network_resource_count": out["network_resource_count"],
                "network_resources": out["network_resources"][:40],
                "api_match_context_count": out["api_match_context_count"],
                "api_matches": out["api_matches"][:5],
                "prematch_candidate_probe_count": out["prematch_candidate_probe_count"],
                "prematch_candidate_probe": out["prematch_candidate_probe"][:5],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
