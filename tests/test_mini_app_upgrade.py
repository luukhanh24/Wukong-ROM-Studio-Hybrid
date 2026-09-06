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

    def test_uncertain_response_without_job_id_keeps_key_and_serializes_confirm(self):
        def exercise(page):
            result = page.evaluate("""async () => {
                const { state } = await import('/modules/state.js');
                const { submitRecipe } = await import('/modules/build.js');
                const recipe = JSON.stringify({schemaVersion: 1, task: 'build', device:'PJD110', source:{kind:'https',uri:'https://example.com/rom.zip'},build:{preset:'plus'}});
                localStorage.setItem('wukong-submit-request', JSON.stringify({subject:String(state.me.telegramId), recipe, key:'malformed-success-key'}));
                const original = window.fetch;
                let attempts = 0;
                window.fetch = async (url, init) => {
                    if (String(url).endsWith('/v1/jobs') && init?.method === 'POST') { attempts += 1; return Response.json({status:'queued'}); }
                    return original(url, init);
                };
                let firstError = '';
                try { await submitRecipe(); } catch (cause) { firstError = String(cause?.message || cause); }
                const pending = JSON.parse(localStorage.getItem('wukong-submit-request'));
                const uncertain = state.submitUncertain && !document.querySelector('#submit-recovery').hidden;
                let release;
                const responseReady = new Promise(resolve => { release = resolve; });
                attempts = 0;
                window.fetch = async (url, init) => {
                    if (String(url).endsWith('/v1/jobs') && init?.method === 'POST') {
                        attempts += 1;
                        await responseReady;
                        return Response.json({job_id:'serialized-job', status:'queued'});
                    }
                    return original(url, init);
                };
                const first = submitRecipe().catch(() => null);
                await new Promise(resolve => setTimeout(resolve, 20));
                const second = await submitRecipe();
                const inFlightWhileWaiting = state.submitInFlight;
                release();
                await first;
                window.fetch = original;
                return {attempts, firstError, uncertain, key:pending.key, second, inFlightWhileWaiting, inFlight:state.submitInFlight};
            }""")
            self.assertEqual(result["attempts"], 1)
            self.assertTrue(result["firstError"])
            self.assertTrue(result["uncertain"])
            self.assertEqual(result["key"], "malformed-success-key")
            self.assertIsNone(result["second"])
            self.assertTrue(result["inFlightWhileWaiting"])
            self.assertFalse(result["inFlight"])

        _render_mini_app_in_chrome(api_enabled=True, jobs_fixture=True, page_action=exercise)

    def test_expanded_log_dom_is_bounded_to_current_window(self):
        def exercise(page):
            result = page.evaluate("""async () => {
                const { renderEvents } = await import('/modules/jobs.js');
                const events = Array.from({length: 10001}, (_, index) => ({
                    sequence: index + 1, type: 'step', step: 'inspect_rom', status: 'success',
                    timestamp: '2026-09-06T00:00:00.000Z', message: `event-${index}`
                }));
                const section = renderEvents(events, true);
                const rows = section.querySelectorAll('ol > li:not(.event-group)').length;
                const total = section.querySelector('.job-events-heading span')?.textContent || '';
                return {rows, total};
            }""")
            self.assertLessEqual(result["rows"], 500)
            self.assertIn("500", result["total"])
            self.assertIn("10001", result["total"])

        _render_mini_app_in_chrome(api_enabled=True, jobs_fixture=True, page_action=exercise)

    def test_primary_controls_meet_target_hitbox(self):
        def exercise(page):
            result = page.evaluate("""() => {
                const selectors = [
                    '#language', '#source-uri', '#paste-source', '#clear-source',
                    '#probe-source', '#device', '#preset', '#submit-recipe',
                    '.bottom-nav button'
                ];
                return selectors.flatMap((selector) => [...document.querySelectorAll(selector)])
                    .filter((node) => node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden')
                    .map((node) => ({id: node.id || node.className, width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height}));
            }""")
            self.assertTrue(result)
            undersized = [item for item in result if item["width"] < 44 or item["height"] < 44]
            self.assertEqual(undersized, [])

        _render_mini_app_in_chrome(api_enabled=True, jobs_fixture=True, page_action=exercise)

    def test_monochrome_design_tokens_and_local_geist_fonts(self):
        def exercise(page):
            result = page.evaluate("""() => {
                const root = getComputedStyle(document.documentElement);
                const body = getComputedStyle(document.body);
                const label = getComputedStyle(document.querySelector('.build-options .field > span'));
                return {
                    canvas: root.getPropertyValue('--canvas').trim(),
                    ink: root.getPropertyValue('--ink').trim(),
                    accent: root.getPropertyValue('--accent').trim(),
                    family: body.fontFamily,
                    labelSize: label.fontSize,
                };
            }""")
            self.assertEqual(result["canvas"], "#fafafa")
            self.assertEqual(result["ink"], "#0a0a0a")
            self.assertEqual(result["accent"], "#a7b2f7")
            self.assertIn("Geist Sans", result["family"])
            self.assertIn(result["labelSize"], {"11px", "12px"})

        _render_mini_app_in_chrome(api_enabled=True, window_width=390, window_height=844, page_action=exercise)

    def test_exact_responsive_viewports_keep_dock_and_collapsed_options(self):
        for width, height in [(320, 740), (390, 844), (768, 1024), (1280, 900), (844, 390)]:
            with self.subTest(width=width, height=height):
                def exercise(page):
                    result = page.evaluate("""() => ({
                        width:innerWidth, documentWidth:document.documentElement.scrollWidth,
                        dock:getComputedStyle(document.querySelector('.bottom-nav')).display,
                        desktopNav:getComputedStyle(document.querySelector('.contents-rail')).display,
                        positions:document.querySelectorAll('.bottom-nav [data-nav]').length,
                        advanced:document.querySelector('#build-advanced').open,
                        facts:document.querySelectorAll('.source-summary dd').length,
                        form:document.querySelector('#recipe-form').contains(document.querySelector('#submit-recipe'))
                    })""")
                    self.assertEqual(result["width"], width)
                    self.assertLessEqual(result["documentWidth"], width)
                    if width > 860:
                        self.assertEqual(result["dock"], "none")
                        self.assertNotEqual(result["desktopNav"], "none")
                    else:
                        self.assertNotEqual(result["dock"], "none")
                        self.assertEqual(result["desktopNav"], "none")
                    self.assertEqual(result["positions"], 5)
                    self.assertEqual(result["facts"], 4)
                    self.assertFalse(result["advanced"])
                    self.assertTrue(result["form"])

                _render_mini_app_in_chrome(api_enabled=True, window_width=width, window_height=height, page_action=exercise)

    def test_restored_studio_geometry_matches_reference_card_layout(self):
        def exercise_mobile(page):
            result = page.evaluate("""() => {
                const main = document.querySelector('main');
                const runtime = document.querySelector('.runtime-strip');
                const source = document.querySelector('.source-section');
                return {
                    mainPaddingLeft: getComputedStyle(main).paddingLeft,
                    runtimeWidth: runtime.getBoundingClientRect().width,
                    runtimeHeight: runtime.getBoundingClientRect().height,
                    runtimeRows: runtime.children.length,
                    sourceX: source.getBoundingClientRect().x,
                };
            }""")
            self.assertEqual(result, {
                "mainPaddingLeft": "10px",
                "runtimeWidth": 370,
                "runtimeHeight": 186,
                "runtimeRows": 3,
                "sourceX": 10,
            })

        _render_mini_app_in_chrome(api_enabled=True, window_width=390, window_height=844, page_action=exercise_mobile)

        def exercise_desktop(page):
            result = page.evaluate("""() => {
                const form = document.querySelector('#recipe-form');
                const source = document.querySelector('.source-section');
                const docket = document.querySelector('.dispatch-docket');
                const style = getComputedStyle(form);
                return {
                    columns: style.gridTemplateColumns,
                    columnGap: style.columnGap,
                    sourceWidth: source.getBoundingClientRect().width,
                    docketX: docket.getBoundingClientRect().x,
                };
            }""")
            self.assertEqual(result, {
                "columns": "888px 320px",
                "columnGap": "16px",
                "sourceWidth": 888,
                "docketX": 932,
            })

        _render_mini_app_in_chrome(api_enabled=True, window_width=1280, window_height=900, page_action=exercise_desktop)

    def test_restored_header_dock_and_studio_structure(self):
        def exercise_mobile(page):
            result = page.evaluate("""() => {
                const masthead = document.querySelector('.masthead');
                const dock = document.querySelector('.bottom-nav');
                const sourceFacts = document.querySelectorAll('#source-facts > dl.source-facts:not(.source-summary) > div').length;
                return {
                    mastheadPaddingTop: getComputedStyle(masthead).paddingTop,
                    mastheadPaddingBottom: getComputedStyle(masthead).paddingBottom,
                    dockBottom: getComputedStyle(dock).bottom,
                    dockSlots: dock.querySelectorAll('[data-slot]').length,
                    profileSlot: dock.querySelector('#dock-profile')?.dataset.slot,
                    sourceFacts,
                    sourceSummaryHidden: getComputedStyle(document.querySelector('.source-summary')).display,
                    deliveryHeading: Boolean(document.querySelector('.delivery-section > .section-heading')),
                    buildAdvancedHidden: document.querySelector('#build-advanced')?.hidden,
                };
            }""")
            self.assertEqual(result["mastheadPaddingTop"], "7px")
            self.assertEqual(result["mastheadPaddingBottom"], "7px")
            self.assertEqual(result["dockBottom"], "10px")
            self.assertEqual(result["dockSlots"], 5)
            self.assertEqual(result["profileSlot"], "2")
            self.assertEqual(result["sourceFacts"], 15)
            self.assertEqual(result["sourceSummaryHidden"], "none")
            self.assertTrue(result["deliveryHeading"])
            self.assertTrue(result["buildAdvancedHidden"])

        _render_mini_app_in_chrome(api_enabled=True, window_width=390, window_height=844, page_action=exercise_mobile)

        def exercise_desktop(page):
            result = page.evaluate("""() => {
                const masthead = document.querySelector('.masthead');
                const dock = document.querySelector('.bottom-nav');
                const desktopNav = document.querySelector('.contents-rail');
                const headerProfile = document.querySelector('#header-profile');
                return {
                    mastheadPaddingTop: getComputedStyle(masthead).paddingTop,
                    mastheadPaddingBottom: getComputedStyle(masthead).paddingBottom,
                    dockDisplay: getComputedStyle(dock).display,
                    desktopNavDisplay: getComputedStyle(desktopNav).display,
                    headerProfileVisible: headerProfile.getClientRects().length > 0,
                    buildColumns: getComputedStyle(document.querySelector('#build-options .field-grid.three')).gridTemplateColumns,
                };
            }""")
            self.assertEqual(result["mastheadPaddingTop"], "8px")
            self.assertEqual(result["mastheadPaddingBottom"], "8px")
            self.assertEqual(result["dockDisplay"], "none")
            self.assertNotEqual(result["desktopNavDisplay"], "none")
            self.assertTrue(result["headerProfileVisible"])
            self.assertEqual(len(result["buildColumns"].split()), 3)

        _render_mini_app_in_chrome(api_enabled=True, window_width=1280, window_height=900, page_action=exercise_desktop)

    def test_mobile_build_configuration_fields_stack_without_excess_density(self):
        for width in (390, 768):
            with self.subTest(width=width):
                def exercise(page):
                    result = page.evaluate("""() => {
                        const grid = document.querySelector('#build-options .field-grid.three');
                        const fields = [...grid.children].map((field) => {
                            const box = field.getBoundingClientRect();
                            const control = field.querySelector('select');
                            return {x: Math.round(box.x), width: Math.round(box.width), height: Math.round(control.getBoundingClientRect().height)};
                        });
                        return {columns: getComputedStyle(grid).gridTemplateColumns.split(' ').length, gap: getComputedStyle(grid).rowGap, fields};
                    }""")
                    self.assertEqual(result["columns"], 1)
                    self.assertEqual(result["gap"], "13px")
                    self.assertEqual(len({field["x"] for field in result["fields"]}), 1)
                    self.assertGreaterEqual(min(field["height"] for field in result["fields"]), 44)
                    self.assertLessEqual(max(field["height"] for field in result["fields"]), 48)

                _render_mini_app_in_chrome(api_enabled=True, window_width=width, window_height=900, page_action=exercise)
