import os
import unittest
from unittest import mock

from telegram_progress import TelegramProgressReporter, render_progress_message


class TelegramProgressTests(unittest.TestCase):
    def snapshot(self, **overrides):
        payload = {
            "jobId": "job-progress",
            "status": "running",
            "versionName": "PKG110_16.0.7.702(CN01)",
            "edition": "Lite + Plus",
            "studioVersion": "V3.4",
            "deviceName": "OnePlus Ace 5",
            "productName": "PKG110",
            "percent": 45,
            "currentLabel": "Lite · Đóng gói ROM ZIP",
            "progressMessage": "ZIP 45%",
            "elapsedSeconds": 3723,
            "steps": [
                {"label": "Phân tích ROM", "status": "success"},
                {"label": "Lite · Đóng gói ROM ZIP", "status": "running"},
                {"label": "Plus · Áp dụng MOD", "status": "pending"},
            ],
            "error": None,
            "locale": "vi",
        }
        payload.update(overrides)
        return payload

    def test_progress_message_is_detailed_and_visual(self):
        message = render_progress_message(self.snapshot())

        self.assertIn("ĐANG BUILD ROM", message)
        self.assertIn("Wukong Lite + Plus V3.4", message)
        self.assertIn("█████████░░░░░░░░░░░  45%", message)
        self.assertIn("Lite · Đóng gói ROM ZIP", message)
        self.assertIn("Plus · Áp dụng MOD", message)
        self.assertIn("01:02:03", message)

    def test_terminal_message_mentions_separate_artifact_report(self):
        message = render_progress_message(
            self.snapshot(
                status="success",
                percent=100,
                currentLabel="Đã hoàn tất",
                finalReportSent=True,
                steps=[{"label": "Đóng gói ROM ZIP", "status": "success"}],
            )
        )

        self.assertIn("BUILD ROM HOÀN TẤT", message)
        self.assertIn("Báo cáo artifact chi tiết đã được gửi", message)

    def test_failed_message_shows_stage_and_error(self):
        message = render_progress_message(
            self.snapshot(
                status="failed",
                currentLabel="Plus · Tạo super.img",
                error="lpmake exited with code 1",
                steps=[{"label": "Plus · Tạo super.img", "status": "failed"}],
            )
        )

        self.assertIn("BUILD ROM THẤT BẠI", message)
        self.assertIn("Plus · Tạo super.img", message)
        self.assertIn("lpmake exited with code 1", message)

    def test_reporter_sends_then_edits_the_same_message(self):
        send_response = mock.Mock(status_code=200, text="")
        send_response.raise_for_status.return_value = None
        send_response.json.return_value = {"ok": True, "result": {"message_id": 321}}
        edit_response = mock.Mock(status_code=200, text="")
        edit_response.raise_for_status.return_value = None
        edit_response.json.return_value = {"ok": True, "result": {"message_id": 321}}
        reporter = TelegramProgressReporter(minimum_interval=0)

        with mock.patch.dict(
            os.environ,
            {
                "WUKONG_TELEGRAM_BOT_TOKEN": "secret-token",
                "WUKONG_TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ), mock.patch("requests.post", side_effect=[send_response, edit_response]) as post:
            self.assertTrue(reporter._deliver(self.snapshot()))
            self.assertTrue(reporter._deliver(self.snapshot(percent=75)))

        self.assertTrue(post.call_args_list[0].args[0].endswith("/sendMessage"))
        self.assertTrue(post.call_args_list[1].args[0].endswith("/editMessageText"))
        self.assertNotIn("secret-token", str(post.call_args_list[0].kwargs["json"]))
        self.assertEqual(post.call_args_list[1].kwargs["json"]["message_id"], 321)

    def test_reporter_coalesces_small_updates_and_ignores_late_events(self):
        reporter = TelegramProgressReporter(minimum_interval=0)
        with mock.patch.dict(
            os.environ,
            {
                "WUKONG_TELEGRAM_BOT_TOKEN": "token",
                "WUKONG_TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ), mock.patch.object(reporter, "_ensure_thread"):
            self.assertTrue(reporter.publish(self.snapshot(percent=45)))
            self.assertFalse(reporter.publish(self.snapshot(percent=49)))
            self.assertTrue(reporter.publish(self.snapshot(percent=50)))
            self.assertTrue(
                reporter.publish(
                    self.snapshot(status="success", percent=100, currentLabel="Đã hoàn tất"),
                    force=True,
                )
            )
            self.assertFalse(reporter.publish(self.snapshot(percent=60)))

        self.assertEqual(reporter._queue.qsize(), 3)


if __name__ == "__main__":
    unittest.main()
