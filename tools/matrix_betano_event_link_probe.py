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

    out = {
        "schema": "MATRIX_BETANO_EVENT_LINK_PROBE_V3",
        "generated_at_utc": now.isoformat(),
        "target": {"home": target_home_raw, "away": target_away_raw},
        "matches": unique[:50],
        "ancestry": ancestry[:20],
        "count": len(unique),
        "ancestry_count": len(ancestry),
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
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
