import os
import re

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


def test_theme_selector_persists_and_follows_system_theme(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, _, _ = running_viewer
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(color_scheme="light")
        page.goto(url)

        page.get_by_role("button", name="Dark", exact=True).click()
        assert page.locator("html").get_attribute("data-theme") == "dark"
        page.reload()
        assert page.locator("html").get_attribute("data-theme") == "dark"

        page.get_by_role("button", name="System", exact=True).click()
        assert page.locator("html").get_attribute("data-theme") == "light"
        page.emulate_media(color_scheme="dark")
        sync_api.expect(page.locator("html")).to_have_attribute("data-theme", "dark")
        assert (
            page.get_by_role("button", name="System", exact=True).get_attribute("aria-pressed")
            == "true"
        )

        page.get_by_role("button", name="System", exact=True).focus()
        page.keyboard.press("ArrowRight")
        assert (
            page.get_by_role("button", name="Light", exact=True).get_attribute("aria-pressed")
            == "true"
        )
        assert page.evaluate("getComputedStyle(document.activeElement).outlineWidth") == "3px"

        page.emulate_media(reduced_motion="reduce")
        assert page.evaluate("getComputedStyle(document.documentElement).scrollBehavior") == "auto"
        page.emulate_media(media="print")
        assert not page.locator(".theme-control").is_visible()
        assert page.locator(".message").first.is_visible()
        browser.close()


def test_live_code_blocks_get_labels_and_copy_exact_source(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    source = "  print('<safe>')  \n\n"
    message = f"```py\n{source}```\n\n```made-up\n<unknown>& value\n```\n\n```\n<plain>& value\n```"
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
        page = context.new_page()
        page.goto(url)

        append(path, record(message))
        sync_api.expect(page.locator(".code-block")).to_have_count(2)
        assert page.locator(".code-language").all_text_contents() == ["Python", "made-up"]
        assert page.locator("pre.code-plain").count() == 1
        assert page.locator(".code-block .highlight").count() == 1

        python = page.locator('.code-block:has-text("Python")')
        rendered_source = python.locator("code").text_content()
        assert rendered_source == "  print('<safe>')  \n"
        python.get_by_role("button", name="Copy Python code").click()
        sync_api.expect(python.get_by_role("button")).to_contain_text("Copied")
        assert page.evaluate("navigator.clipboard.readText()") == rendered_source
        assert page.get_by_role("status", name="Copy status").text_content() == (
            "Python code copied to the clipboard."
        )
        browser.close()


def test_copy_failure_selects_source_and_gives_manual_instructions(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_init_script(
            """
            Object.defineProperty(navigator, "clipboard", {
              configurable: true,
              value: { writeText: () => Promise.reject(new Error("denied")) },
            });
            Document.prototype.execCommand = () => false;
            """
        )
        page = context.new_page()
        page.goto(url)
        append(path, record("```js\nconst answer = 42;\n```"))

        block = page.locator(".code-block")
        sync_api.expect(block).to_have_count(1)
        source = block.locator("code").text_content()
        block.get_by_role("button", name="Copy JavaScript code").click()
        sync_api.expect(block.get_by_role("button")).to_contain_text("Selected")
        assert page.get_by_role("status", name="Copy status").text_content() == (
            "Automatic copy failed. The code is selected; copy it manually."
        )
        assert page.evaluate("getSelection().toString()") == source.rstrip("\n")
        assert block.locator("code").evaluate("node => node.contains(getSelection().anchorNode)")
        browser.close()


def test_mobile_wraps_source_but_scrolls_alignment_sensitive_code(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    long_text = "x" * 300
    message = f"```python\nvalue = '{long_text}'\n```\n\n```diff\n+ value = '{long_text}'\n```"
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(url)

        append(path, record(message))
        sync_api.expect(page.locator(".code-block")).to_have_count(2)
        source = page.locator('.code-block:has-text("Python") pre')
        diff = page.locator(".code-scroll pre")
        sync_api.expect(diff).to_have_count(1)
        assert source.evaluate("node => node.scrollWidth <= node.clientWidth")
        assert diff.evaluate("node => node.scrollWidth > node.clientWidth")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        browser.close()


def test_highlighting_survives_append_replacement_and_reconnect(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        append(path, record("```python\nanswer = 42\n```"))
        sync_api.expect(page.locator(".code-language")).to_have_text("Python")
        assert page.locator(".code-block").count() == 1

        replacement = path.with_suffix(".new")
        append(replacement, record("```sql\nSELECT '$$literal$$';\n```"))
        replacement.replace(path)
        sync_api.expect(page.locator("article")).to_have_count(1)
        sync_api.expect(page.locator(".code-language")).to_have_text("SQL")
        assert page.locator(".code-block").count() == 1
        assert page.locator(".code-block mjx-container").count() == 0
        assert "$$literal$$" in page.locator(".code-block code").text_content()

        page.context.set_offline(True)
        append(path, record('```json\n{"reconnected": true}\n```'))
        page.context.set_offline(False)
        sync_api.expect(page.locator("article")).to_have_count(2)
        sync_api.expect(page.locator(".code-language")).to_have_count(2)
        assert page.locator(".code-language").all_text_contents() == ["SQL", "JSON"]
        assert page.locator(".code-block").count() == 2
        browser.close()


def test_latest_action_tracks_reading_position_and_unseen_messages(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 900, "height": 600}, reduced_motion="reduce")
        page.goto(url)

        for index in range(10):
            append(path, record(f"## Answer {index}\n\n" + "A long paragraph. " * 30))
        sync_api.expect(page.locator("article")).to_have_count(12)
        page.evaluate("scrollTo(0, 0)")
        latest = page.get_by_role("button", name=re.compile("latest message", re.I))
        sync_api.expect(latest).to_be_visible()

        latest.click()
        sync_api.expect(latest).to_be_hidden()
        assert page.evaluate("document.documentElement.scrollHeight - (scrollY + innerHeight) < 5")

        page.evaluate("scrollTo(0, 0)")
        append(path, record("A newly saved answer"))
        sync_api.expect(page.locator("article")).to_have_count(13)
        sync_api.expect(latest).to_be_visible()
        sync_api.expect(latest).to_contain_text("1 new")
        assert "has-unseen" in (latest.get_attribute("class") or "")

        page.evaluate("scrollTo(0, document.documentElement.scrollHeight)")
        sync_api.expect(latest).to_be_hidden()
        browser.close()


def test_editorial_hierarchy_and_progress_timeline(running_viewer):
    sync_api = pytest.importorskip("playwright.sync_api")
    url, path, _ = running_viewer
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)

        append(path, record("Reading the renderer", phase="commentary"))
        sync_api.expect(page.locator(".message.progress")).to_have_count(1)
        progress = page.locator(".message.progress")
        sync_api.expect(progress).to_be_hidden()
        page.locator("#progress").check()
        sync_api.expect(progress).to_be_visible()

        assistant = page.locator(".message.assistant").first
        user = page.locator(".message.user").first
        assert assistant.evaluate("node => getComputedStyle(node).backgroundColor") == (
            "rgba(0, 0, 0, 0)"
        )
        assert user.evaluate("node => getComputedStyle(node).backgroundColor") != (
            "rgba(0, 0, 0, 0)"
        )
        assert assistant.locator(".message-body").evaluate(
            "node => node.getBoundingClientRect().width <= 640"
        )
        assert progress.evaluate("node => getComputedStyle(node).backgroundColor") == (
            "rgba(0, 0, 0, 0)"
        )
        assert page.locator("header").evaluate("node => getComputedStyle(node).position") == (
            "static"
        )
        browser.close()
