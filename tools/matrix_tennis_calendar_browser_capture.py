"""Capture raw tennis calendar pages, without certifying match counts."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

URLS = {
    "sofascore": "https://www.sofascore.com/es/tennis/{day}",
    "flashscore": "https://www.flashscore.co/tenis/?d={day}",
}


def capture(day, output):
    from playwright.sync_api import sync_playwright
    datetime.strptime(day, "%Y-%m-%d")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "MATRIX_TENNIS_RAW_BROWSER_CAPTURE_V1",
        "target_date_bogota": day,
        "sources": {},
        "world_calendar_complete": False,
        "exact_match_counts_certified": False,
        "canonical_reconciliation": False,
        "real_money": "BLOCKED",
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for source, template in URLS.items():
                url = template.format(day=day)
                item = {"requested_url": url, "status": "FAILED"}
                try:
                    page = browser.new_page(locale="es-CO", timezone_id="America/Bogota")
                    response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(5000)
                    body = page.locator("body").inner_text(timeout=15000)
                    if not body.strip() or response is None or response.status >= 400:
                        raise RuntimeError("HTTP_ERROR_OR_EMPTY_PAGE")
                    html = page.content()
                    (output / (source + ".html")).write_text(html, encoding="utf-8")
                    (output / (source + ".txt")).write_text(body, encoding="utf-8")
                    page.screenshot(path=str(output / (source + ".png")), full_page=True)
                    item.update({
                        "status": "RAW_CAPTURED_UNVERIFIED",
                        "http_status": response.status,
                        "final_url": page.url,
                        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                        "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
                        "text_sha256": hashlib.sha256(body.encode()).hexdigest(),
                        "exact_match_count": None,
                    })
                    page.close()
                except Exception as exc:
                    item["error"] = str(exc)[:300]
                result["sources"][source] = item
        finally:
            browser.close()
    result["both_pages_captured"] = all(
        value["status"] == "RAW_CAPTURED_UNVERIFIED"
        for value in result["sources"].values()
    )
    (output / "manifest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date-bogota", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = capture(args.target_date_bogota, args.out)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["both_pages_captured"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
