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
          const visible = [...document.querySelectorAll('button, summary, a[role="button"]')]
            .filter((node) => {
              const box = node.getBoundingClientRect();
              const style = getComputedStyle(node);
              return !node.closest('[hidden]') && box.width > 0 && box.height > 0
                && style.display !== 'none' && style.visibility !== 'hidden';
            });
          const small = visible.filter((node) => {
            const box = node.getBoundingClientRect();
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
        violations = page.evaluate("window.axe.run().then((report) => report.violations)")
        result["axeViolations"] = violations
        if violations:
            raise AssertionError(json.dumps(violations, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8789/", help="Built Mini App URL")
    parser.add_argument("--axe", action="store_true", help="Load axe-core for an optional local audit")
    parser.add_argument("--executable", default=os.environ.get("CHROME_PATH", ""), help="Chrome/Chromium executable")
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
                        page.wait_for_timeout(750)
                        result = audit_page(page, reduced=reduced, axe=args.axe)
                        print(f"{width}x{height} {theme} reduced={reduced}: {json.dumps(result, ensure_ascii=False)}")
                        page.close()
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
