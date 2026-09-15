import os

import pytest
from conftest import append, record

pytestmark = [
    pytest.mark.browser,
    pytest.mark.skipif(
        os.environ.get("CODEX_VIEW_BROWSER_TESTS") != "1", reason="opt-in browser test"
    ),
]


def test_math_live_updates_reconnect_and_mobile(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_selector("mjx-container")
        assert page.locator("article").count() == 2
        append(path, record(r"A new equation: \(\sqrt{49}=7\)"))
        sync_api.expect(page.locator("mjx-container")).to_have_count(2)
        assert page.locator("article").count() == 3
        page.context.set_offline(True)
        append(path, record("Written while disconnected"))
        page.context.set_offline(False)
        sync_api.expect(page.locator("article")).to_have_count(4)
        page.wait_for_timeout(1200)
        assert page.locator("article").count() == 4
        assert page.locator('[data-mml-node="merror"]').count() == 0
        assert errors == []
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()
