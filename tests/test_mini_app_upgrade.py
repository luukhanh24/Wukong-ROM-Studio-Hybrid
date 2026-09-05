from __future__ import annotations

import unittest

from tests.test_telegram_mini_app import _render_mini_app_in_chrome


class MiniAppUpgradeTests(unittest.TestCase):
    def test_polling_restarts_on_visibility_and_online_without_losing_snapshot(self):
        def exercise(page):
            result = page.evaluate("""async () => {
                const { state } = await import('/modules/state.js');
                const { loadJobs } = await import('/modules/jobs.js');
                await loadJobs({ force: true });
                const first = document.querySelector('.job-history-card');
                await loadJobs({ force: true });
                const retained = first === document.querySelector('.job-history-card');
                Object.defineProperty(document, 'hidden', { configurable: true, value: true });
                document.dispatchEvent(new Event('visibilitychange'));
                const paused = state.jobsPollTimer === null;
                Object.defineProperty(document, 'hidden', { configurable: true, value: false });
                document.dispatchEvent(new Event('visibilitychange'));
                await new Promise(resolve => setTimeout(resolve, 300));
                const resumed = Boolean(state.jobsPollTimer);
                window.dispatchEvent(new Event('offline'));
                const offlineSnapshot = state.jobs.length > 0;
                window.dispatchEvent(new Event('online'));
                await new Promise(resolve => setTimeout(resolve, 300));
                return { retained, paused, resumed, online: Boolean(state.jobsPollTimer), offlineSnapshot };
            }""")
            self.assertEqual(result, dict(retained=True, paused=True, resumed=True, online=True, offlineSnapshot=True))

        _render_mini_app_in_chrome(api_enabled=True, jobs_fixture=True, initial_view="jobs", page_action=exercise)

    def test_uncertain_build_preserves_payload_key_and_account_boundary(self):
        def exercise(page):
            result = page.evaluate("""async () => {
                const { state } = await import('/modules/state.js');
                const { submitRecipe, restorePendingSubmission } = await import('/modules/build.js');
                const recipe = JSON.stringify({schemaVersion: 1, task: 'build', device:'PJD110', source:{kind:'https',uri:'https://example.com/rom.zip'},build:{preset:'plus'}});
                localStorage.setItem('wukong-submit-request', JSON.stringify({subject:String(state.me.telegramId),recipe,key:'same-build-key'}));
                restorePendingSubmission();
                document.querySelector('#source-uri').value = 'https://example.com/changed.zip';
                const original = window.fetch;
                const attempts = [];
                window.fetch = async (url, init) => {
                    if (String(url).endsWith('/v1/jobs') && init?.method === 'POST') {
                        attempts.push({body:init.body,key:new Headers(init.headers).get('Idempotency-Key')});
                        throw new TypeError('Network disconnected after dispatch');
                    }
                    return original(url, init);
                };
                try { await submitRecipe(); } catch (_) {}
                try { await submitRecipe(); } catch (_) {}
                const uncertain = !document.querySelector('#submit-recovery').hidden;
                const pending = JSON.parse(localStorage.getItem('wukong-submit-request'));
                state.me = {...state.me, telegramId:'different-user'};
                restorePendingSubmission();
                window.fetch = original;
                return {attempts, recipe, uncertain, pendingKey:pending.key, cleared:localStorage.getItem('wukong-submit-request') === null, hidden:document.querySelector('#submit-recovery').hidden};
            }""")
            self.assertEqual(result["attempts"], [{"body": result["recipe"], "key": "same-build-key"}] * 2)
            self.assertTrue(result["uncertain"])
            self.assertEqual(result["pendingKey"], "same-build-key")
            self.assertTrue(result["cleared"] and result["hidden"])

        _render_mini_app_in_chrome(api_enabled=True, page_action=exercise)

    def test_exact_responsive_viewports_keep_dock_and_collapsed_options(self):
        for width, height in [(320, 740), (390, 844), (768, 1024), (1280, 900), (844, 390)]:
            with self.subTest(width=width, height=height):
                def exercise(page):
                    result = page.evaluate("""() => ({
                        width:innerWidth, documentWidth:document.documentElement.scrollWidth,
                        dock:getComputedStyle(document.querySelector('.bottom-nav')).display,
                        positions:document.querySelectorAll('.bottom-nav [data-nav]').length,
                        advanced:document.querySelector('#build-advanced').open,
                        facts:document.querySelectorAll('.source-summary dd').length,
                        form:document.querySelector('#recipe-form').contains(document.querySelector('#submit-recipe'))
                    })""")
                    self.assertEqual(result["width"], width)
                    self.assertLessEqual(result["documentWidth"], width)
                    self.assertNotEqual(result["dock"], "none")
                    self.assertEqual(result["positions"], 5)
                    self.assertEqual(result["facts"], 4)
                    self.assertFalse(result["advanced"])
                    self.assertTrue(result["form"])

                _render_mini_app_in_chrome(api_enabled=True, window_width=width, window_height=height, page_action=exercise)
