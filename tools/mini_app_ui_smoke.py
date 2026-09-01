"""Run the Mini App viewport/theme/reduced-motion acceptance smoke.

The script is intentionally test-only: it drives a built/static Mini App URL
with Playwright and can optionally load axe-core from its CDN. No browser or
accessibility dependency is shipped with the production bundle.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


VIEWPORTS = ((320, 568), (375, 812), (390, 844), (768, 900), (1280, 900))


def audit_page(page, *, reduced: bool, axe: bool) -> dict[str, object]:
    if axe:
        page.add_script_tag(url="https://cdn.jsdelivr.net/npm/axe-core@4.10.2/axe.min.js")
    result = page.evaluate(
        """
        ({ reduced, axe }) => {
          const visible = [...document.querySelectorAll('button, summary, a[role="button"], input:not([type="hidden"]), select, textarea')]
            .filter((node) => {
              const box = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return !node.closest('[hidden]') && box.width > 0 && box.height > 0
                && style.display !== 'none' && style.visibility !== 'hidden';
            });
          const small = visible.filter((node) => {
            const target = node.matches('input[type="checkbox"], input[type="radio"]')
              ? (node.closest('label') || node) : node;
            const box = target.getBoundingClientRect();
            return box.width < 44 || box.height < 44;
          }).map((node) => node.id || node.textContent.trim().slice(0, 40));
          const longRunning = [...document.querySelectorAll('*')].filter((node) => {
            const style = getComputedStyle(node);
            return style.animationName !== 'none' && parseFloat(style.animationDuration) > (reduced ? .08 : 0);
          }).map((node) => node.id || node.className).slice(0, 10);
          return {
            overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
            small,
            scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
            longRunning,
            axeReady: Boolean(axe && window.axe)
          };
        }
        """,
        {"reduced": reduced, "axe": axe},
    )
    if result["overflow"]:
        raise AssertionError("horizontal overflow")
    if result["small"]:
        raise AssertionError(f"controls below 44px: {result['small']}")
    if reduced and result["scrollBehavior"] != "auto":
        raise AssertionError("reduced motion kept smooth scrolling")
    if axe and result["axeReady"]:
        violations = page.evaluate("window.axe.run({ runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } }).then((report) => report.violations)")
        result["axeViolations"] = violations
        if violations:
            raise AssertionError(json.dumps(violations, ensure_ascii=False))
    if axe and not result["axeReady"]:
        raise AssertionError("axe-core did not load; rerun with network access or install the dev/test fixture")
    return result


def exercise_surfaces(page, *, reduced: bool, axe: bool) -> None:
    """Walk the public navigation and common disclosure/focus surfaces.

    This stays deliberately fixture-free: the built preview can exercise all
    view shells without credentials, while authenticated job/admin content is
    covered by the repository's API-backed Playwright tests.
    """
    for view in ("build", "jobs", "catalog", "profile", "system"):
        nav = page.locator(f'[data-nav="{view}"]:visible').first
        if nav.count():
            nav.click()
            page.wait_for_timeout(180)
            audit_page(page, reduced=reduced, axe=axe)
    # Exercise roving-tablist semantics where a surface exposes tabs.
    tabs = page.locator('[role="tab"]')
    if tabs.count():
        tabs.first.focus()
        page.keyboard.press("End")
        page.keyboard.press("Home")
        page.keyboard.press("ArrowRight")
        audit_page(page, reduced=reduced, axe=axe)
    # Open common disclosure panels so their mobile layout is included.
    page.locator("details").evaluate_all("nodes => nodes.slice(0, 4).forEach(node => { node.open = true; })")
    page.wait_for_timeout(80)
    audit_page(page, reduced=reduced, axe=axe)
    # Source metadata uses progressive disclosure on narrow screens.
    build_nav = page.locator('[data-nav="build"]:visible').first
    if build_nav.count():
        build_nav.click()
        page.wait_for_timeout(120)
    source = page.locator("#source-uri")
    if source.count() and source.is_visible():
        source.fill("https://component-ota-cn.allawntech.com/downloadCheck?fixture=1")
        source.dispatch_event("input")
        page.wait_for_timeout(120)
        toggle = page.locator("#toggle-source-facts")
        if toggle.count() and toggle.is_visible():
            toggle.click()
        audit_page(page, reduced=reduced, axe=axe)
    # Dialogs must trap Tab, close on Escape, and return focus to their trigger.
    dialog = page.locator("#user-create-dialog")
    if dialog.count():
        page.evaluate("""() => {
          const trigger = document.createElement('button');
          trigger.id = 'smoke-dialog-trigger';
          trigger.type = 'button';
          trigger.textContent = 'smoke';
          document.body.append(trigger);
          trigger.focus();
          document.querySelector('#user-create-dialog')?.showModal();
        }""")
        page.wait_for_timeout(30)
        page.keyboard.press("Tab")
        if not dialog.locator(":focus").count():
            raise AssertionError("dialog focus escaped while tabbing")
        page.keyboard.press("Escape")
        if dialog.get_attribute("open") is not None:
            raise AssertionError("dialog did not close on Escape")
        if page.locator("#smoke-dialog-trigger").evaluate("node => document.activeElement === node") is not True:
            raise AssertionError("dialog did not restore focus to trigger")
        page.locator("#smoke-dialog-trigger").evaluate("node => node.remove()")
    else:
        page.evaluate("""() => [...document.querySelectorAll('dialog')].forEach((dialog) => {
          if (!dialog.open) { try { dialog.showModal(); dialog.close(); } catch (_) {} }
        })""")
    page.wait_for_timeout(50)
    audit_page(page, reduced=reduced, axe=axe)


def install_authenticated_fixture(page) -> None:
    """Install a local Telegram/API fixture for authenticated surface audits."""
    page.add_init_script("""
      (() => {
        const events = {};
        window.Telegram = { WebApp: {
          platform: 'android', version: '7.7', colorScheme: 'light',
          initData: 'query_id=smoke&user=%7B%22id%3A123%2C%22first_name%22%3A%22Smoke%22%7D&auth_date=1&hash=smoke',
          initDataUnsafe: { user: { id: 123, first_name: 'Smoke' } },
          safeAreaInset: { top: 0, bottom: 8 }, contentSafeAreaInset: { top: 0, bottom: 12 },
          ready() {}, expand() {}, isVersionAtLeast() { return true; },
          onEvent(name, callback) { events[name] = callback; },
          offEvent(name, callback) { if (events[name] === callback) delete events[name]; },
          setHeaderColor() {}, setBackgroundColor() {},
          BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
          HapticFeedback: { notificationOccurred() {}, impactOccurred() {}, selectionChanged() {} },
          openTelegramLink() {}, openLink() {}, close() {}
        }};
      })();
    """)

    def fulfill(route):
        path = route.request.url.split("/v1/", 1)[-1].split("?", 1)[0]
        if path in {"session/open", "me"}:
            payload = {"user": {"telegramId": "123", "displayName": "Smoke User", "username": "smoke", "role": "user", "accessStatus": "approved", "buildCredits": 3, "jobCount": 0}, "maintenance": {"enabled": False, "message": ""}}
        elif path == "rom-catalog/devices":
            payload = {"devices": []}
        elif path == "sync":
            payload = {"activeJob": None, "jobs": [], "total": 0, "totalPages": 1, "page": 1, "pageSize": 20, "statusCounts": {"active": 0, "succeeded": 0, "failed": 0}}
        elif path == "rom-catalog":
            payload = {"releases": [], "total": 0, "page": 1, "pageSize": 20, "totalPages": 1}
        elif path == "mod-release-versions":
            payload = {"modReleaseVersions": {}}
        elif path == "preset-labels":
            payload = {"presetLabels": {}}
        else:
            payload = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    # Keep the deterministic WebApp bridge above; the real CDN script would
    # replace the fixture before app.js reads initData.
    page.route("https://telegram.org/js/telegram-web-app.js", lambda route: route.abort())
    page.route("**/v1/**", fulfill)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8789/", help="Built Mini App URL")
    parser.add_argument("--axe", action="store_true", help="Load axe-core for an optional local audit")
    parser.add_argument("--executable", default=os.environ.get("CHROME_PATH", ""), help="Chrome/Chromium executable")
    parser.add_argument("--authenticated-fixture", action="store_true", help="Use a local Telegram/API fixture to exercise authenticated surfaces")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        launch = {"headless": True}
        if args.executable:
            launch["executable_path"] = args.executable
        browser = playwright.chromium.launch(**launch)
        try:
            for width, height in VIEWPORTS:
                for theme in ("light", "dark"):
                    for reduced in (False, True):
                        page = browser.new_page(viewport={"width": width, "height": height})
                        if args.authenticated_fixture:
                            install_authenticated_fixture(page)
                        page.add_init_script(
                            f"localStorage.setItem('wukong-theme', {json.dumps(theme)})"
                        )
                        page.emulate_media(reduced_motion="reduce" if reduced else "no-preference")
                        for attempt in range(3):
                            try:
                                page.goto(args.url, wait_until="domcontentloaded", timeout=15_000)
                                break
                            except PlaywrightTimeoutError:
                                if attempt == 2:
                                    raise
                        # Authenticated fixture boots through the same session
                        # gate as Telegram; give its initial API round-trip a
                        # little longer before asserting landmarks.
                        page.wait_for_timeout(1500 if args.authenticated_fixture else 750)
                        result = audit_page(page, reduced=reduced, axe=args.axe)
                        print(f"{width}x{height} {theme} reduced={reduced}: {json.dumps(result, ensure_ascii=False)}")
                        try:
                            exercise_surfaces(page, reduced=reduced, axe=args.axe)
                        except AssertionError as error:
                            raise AssertionError(f"{width}x{height} {theme} reduced={reduced}: {error}") from error
                        page.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
