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

    def test_offline_during_detail_request_does_not_rearm_polling(self):
        def exercise(page):
            result = page.evaluate("""async () => {
                const { state } = await import('/modules/state.js');
                const { loadJobDetail } = await import('/modules/jobs.js');
                const jobId = state.jobs[0]?.job_id || state.jobs[0]?.jobId || 'fixture-job';
                state.activeJobId = jobId;
                const original = window.fetch;
                let release;
                const pending = new Promise(resolve => { release = resolve; });
                window.fetch = async (url, init) => String(url).includes('/v1/sync?') ? pending : original(url, init);
                const request = loadJobDetail(jobId).catch(() => {});
                await new Promise(resolve => setTimeout(resolve, 30));
                Object.defineProperty(navigator, 'onLine', { configurable: true, value: false });
                window.dispatchEvent(new Event('offline'));
                const immediately = state.jobsPollTimer;
                release(new Response(JSON.stringify({ activeJob: null, events: [] }), { status: 200, headers: {'content-type':'application/json'} }));
                await request;
                await new Promise(resolve => setTimeout(resolve, 30));
                const afterAbort = state.jobsPollTimer;
                Object.defineProperty(navigator, 'onLine', { configurable: true, value: true });
                window.fetch = original;
                return { immediately, afterAbort };
            }""")
            self.assertIsNone(result["immediately"])
            self.assertIsNone(result["afterAbort"])

        _render_mini_app_in_chrome(api_enabled=True, jobs_fixture=True, initial_view="jobs", page_action=exercise)

    def test_confirmed_job_is_visible_when_profile_refresh_fails(self):
        def exercise(page):
            result = page.evaluate("""async () => {
                const { state } = await import('/modules/state.js');
                const { submitRecipe } = await import('/modules/build.js');
                const recipe = JSON.stringify({schemaVersion: 1, task: 'build', device:'PJD110', source:{kind:'https',uri:'https://example.com/rom.zip'},build:{preset:'plus'}});
                localStorage.setItem('wukong-submit-request', JSON.stringify({subject:String(state.me.telegramId), recipe, key:'confirmed-build-key'}));
                const original = window.fetch;
                let profileAttempts = 0;
                window.fetch = async (url, init) => {
                    if (String(url).endsWith('/v1/jobs') && init?.method === 'POST') return Response.json({job_id:'confirmed-created-job', status:'queued'});
                    if (String(url).endsWith('/v1/me')) { profileAttempts += 1; throw new TypeError('profile refresh unavailable'); }
                    return original(url, init);
                };
                let error = '';
                try { await submitRecipe(); } catch (cause) { error = String(cause?.message || cause); }
                window.fetch = original;
                return {profileAttempts, error, view:document.body.dataset.view, activeJobId:state.activeJobId, pending:localStorage.getItem('wukong-submit-request')};
            }""")
            self.assertEqual(result["profileAttempts"], 3)
            self.assertEqual(result["error"], "")
            self.assertEqual(result["view"], "jobs")
            self.assertEqual(result["activeJobId"], "confirmed-created-job")
            self.assertIsNone(result["pending"])

        _render_mini_app_in_chrome(api_enabled=True, jobs_fixture=True, page_action=exercise)

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
