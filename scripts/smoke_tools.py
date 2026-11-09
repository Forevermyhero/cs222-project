"""Browser checks for backend demo and portable tools; public HTTP is mocked."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/tools")
    parser.add_argument("--output", default="test-results/tools")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors, requests_seen = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
                                    args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))

        def reply(route):
            url = route.request.url
            requests_seen.append(url)
            if "geocoding-api" in url:
                data = {"results": [{"id": 1, "name": "Chicago", "latitude": 41.88,
                                     "longitude": -87.63, "timezone": "America/Chicago"}]}
            elif "overpass-api" in url:
                data = {"elements": [
                    {"type": "node", "id": 1, "lat": 41.88, "lon": -87.62,
                     "tags": {"name": "Art Museum", "opening_hours": "Mo-Fr 09:00-17:00",
                              "website": "https://example.org/visit"}},
                    {"type": "node", "id": 2, "lat": 41.89, "lon": -87.63,
                     "tags": {"name": "Gallery <img src=x onerror=alert(1)>",
                              "website": "javascript:alert(1)"}},
                ]}
            elif "router.project-osrm" in url:
                data = {"code": "Ok", "durations": [[0, 1250], [1300, 0]]}
            else:
                raise AssertionError(f"Unexpected public request: {url}")
            route.fulfill(json=data, headers={"Access-Control-Allow-Origin": "*"})

        context.route("https://**/*", reply)
        # Managed Chromium blocks file:// navigation. Serve the unchanged portable
        # HTML bytes through a local intercepted URL without changing browser policy.
        portable_url = "http://127.0.0.1:8000/portable-workbench-check"
        context.route(portable_url, lambda route: route.fulfill(
            content_type="text/html", body=(root / "docs" / "travel-tools.html").read_text()))
        page.goto(portable_url)
        expect(page.locator("#place")).to_be_disabled()
        page.get_by_role("button", name="开始查询数据").click()
        expect(page.locator("#status")).to_contain_text("查询完成")
        expect(page.locator(".place-card")).to_have_count(2)
        expect(page.locator("#city-facts")).to_contain_text("America/Chicago")
        expect(page.locator("#places")).to_contain_text("Mo-Fr 09:00-17:00")
        expect(page.locator("#places")).to_contain_text("未知 / 数据未提供")
        expect(page.locator("#places img")).to_have_count(0)
        expect(page.locator('a[href^="javascript:"]')).to_have_count(0)
        expect(page.locator("#route-result")).to_contain_text("21 分钟")
        expect(page.locator("#route-result")).to_contain_text("22 分钟")
        expect(page.locator("#logs .log")).to_have_count(3)
        assert any("-87.62,41.88;-87.63,41.89" in url for url in requests_seen)
        assert len(requests_seen) == 3
        page.locator("#logs details").first.locator("summary").click()
        expect(page.locator("#logs pre").first).to_contain_text('"latitude": 41.88')
        with page.expect_download() as download:
            page.get_by_role("button", name="下载本次查询 JSON").click()
        download.value.save_as(output / "tools.json")
        evidence = json.loads((output / "tools.json").read_text())
        assert evidence["data_mode"] == "live" and not evidence["cross_checked"]
        assert evidence["records"][0]["source_urls"][0].startswith("https://geocoding-api")
        page.screenshot(path=str(output / "portable-fixtures.png"), full_page=True)

        # Cached routes cause no additional provider call.
        page.get_by_role("button", name="查询 A ↔ B 驾车时间").click()
        expect(page.locator("#logs .log").last).to_have_class("log cached")
        assert len(requests_seen) == 3
        page.locator("#to").select_option(page.locator("#from").input_value())
        page.get_by_role("button", name="查询 A ↔ B 驾车时间").click()
        expect(page.locator("#status")).to_have_text("请选择两个不同地点。")
        expect(page.locator("#route-result")).to_be_empty()

        # File mode still works fully offline with explicitly synthetic fixtures.
        context.set_offline(True)
        page.locator("#mode").select_option("demo")
        page.get_by_role("button", name="开始查询数据").click()
        expect(page.locator("#status")).to_contain_text("查询完成")
        expect(page.locator(".place-card")).to_have_count(4)
        expect(page.locator("#logs .log.example")).to_have_count(3)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "portable-offline-mobile.png"), full_page=True)
        context.set_offline(False)

        # A failed real-mode request must never become a demo result.
        page.reload()
        context.unroute("https://**/*", reply)
        context.route("https://**/*", lambda route: route.fulfill(
            status=503, json={"error": "Injected service unavailable"}))
        page.get_by_role("button", name="开始查询数据").click()
        expect(page.locator("#status")).to_contain_text("Injected service unavailable")
        expect(page.locator("#logs .log.failed")).to_have_count(1)
        expect(page.locator(".place-card")).to_have_count(0)
        expect(page.locator("#run")).to_be_enabled()

        context.unroute("https://**/*")
        page.goto(args.url)
        page.locator("#mode").select_option("demo")
        page.get_by_role("button", name="开始查询数据").click()
        expect(page.locator("#status")).to_contain_text("查询完成")
        expect(page.locator(".place-card")).to_have_count(4)
        expect(page.locator("#route-result")).to_contain_text("20 分钟")
        assert not errors, errors
        browser.close()
    print(json.dumps({"passed": True, "public_requests": "mocked", "tools": 3,
                      "javascript_errors": errors, "screenshots": str(output)}, indent=2))


if __name__ == "__main__":
    main()
