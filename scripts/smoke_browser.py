"""Optional Playwright check against a running local server; no public API calls."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default="test-results/browser")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.chromium, headless=True,
                                             args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator("#form-status")).to_contain_text("Example loaded")
        expect(page.locator("#destination")).to_have_value("Chicago")
        page.get_by_role("button", name="Build & check my itinerary").click()
        expect(page.locator("#validity")).to_have_text("Example checks passed")
        expect(page.locator(".activity")).to_have_count(5)
        expect(page.locator(".fixed-badge")).to_have_count(1)
        expect(page.locator("#result-notes")).to_contain_text("synthetic")
        page.get_by_role("button", name="Check itinerary again").click()
        expect(page.locator("#form-status")).to_have_text("Itinerary checked again.")
        with page.expect_download() as download:
            page.get_by_role("button", name="Download itinerary").click()
        download.value.save_as(output / "itinerary.json")
        assert json.loads((output / "itinerary.json").read_text())["validation"]["is_valid"]
        page.screenshot(path=str(output / "desktop.png"), full_page=True)
        expect(page.locator("#research-panel")).to_have_attribute("open", "")
        expect(page.locator(".research-step")).to_have_count(7)
        expect(page.locator("#step-position")).to_have_text("7 / 7")
        page.get_by_role("button", name="Previous step").click()
        expect(page.locator("#step-position")).to_have_text("6 / 7")
        expect(page.locator("#step-follow")).to_have_attribute("aria-pressed", "false")
        page.get_by_role("button", name="Read your trip details", exact=True).click()
        expect(page.locator("#step-position")).to_have_text("1 / 7")
        expect(page.locator("#step-previous")).to_be_disabled()
        page.get_by_role("button", name="Next step").click()
        expect(page.locator("#step-position")).to_have_text("2 / 7")
        expect(page.locator("#step-meta")).to_contain_text("Local step")
        page.get_by_role("button", name="Follow latest", exact=True).click()
        expect(page.locator("#step-position")).to_have_text("7 / 7")
        expect(page.locator("#step-next")).to_be_disabled()
        expect(page.locator("#research-disclaimer")).to_contain_text("No live websites")
        expect(page.locator(".source-card")).to_have_count(4)
        expect(page.locator("#preparation-list li")).to_have_count(5)
        expect(page.locator('a[href^="javascript:"]')).to_have_count(0)
        page.locator("#research-panel").screenshot(path=str(output / "research.png"))

        # User text must be displayed as text, never inserted as HTML.
        hostile = "Interview <img src=x onerror=alert(1)>"
        page.locator('[name="event-name"]').fill(hostile)
        page.get_by_role("button", name="Build & check my itinerary").click()
        expect(page.locator("#form-status")).to_contain_text("checks are ready")
        expect(page.locator(".activity-name").filter(has_text=hostile)).to_have_count(1)
        expect(page.locator("#schedule img")).to_have_count(0)
        page.locator("#destination").fill("Paris")
        page.get_by_role("button", name="Build & check my itinerary").click()
        expect(page.locator("#form-status")).to_contain_text("Demo mode contains only Chicago")

        page.set_viewport_size({"width": 390, "height": 844})
        page.get_by_role("button", name="Load example").click()
        expect(page.locator('[name="event-name"]')).to_have_value("Interview")
        page.get_by_role("button", name="+ Add event").click()
        expect(page.locator(".event-card")).to_have_count(2)
        page.get_by_role("button", name="Remove").last.click()
        expect(page.locator(".event-card")).to_have_count(1)
        page.get_by_role("button", name="Build & check my itinerary").click()
        expect(page.locator("#validity")).to_have_text("Example checks passed")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(output / "mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print(json.dumps({"passed": True, "activities": 5, "fixed_events": 1, "research_steps": 7,
                      "javascript_errors": errors, "screenshots": str(output)}, indent=2))


if __name__ == "__main__":
    main()
