import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio_env import load_local_env


class StudioEnvTests(unittest.TestCase):
    def test_local_env_loads_supported_values_without_overriding_process_env(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "telegram.env"
            path.write_text(
                "# ignored\n"
                "WUKONG_TELEGRAM_BOT_TOKEN=local-token\n"
                "WUKONG_TELEGRAM_CHAT_ID='12345'\n"
                "WUKONG_TELEGRAM_ADMIN_IDS=12345,67890\n"
                "IGNORED_KEY=value\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"WUKONG_TELEGRAM_BOT_TOKEN": "process-token"},
                clear=True,
            ):
                loaded = load_local_env(path)
                self.assertNotIn("WUKONG_TELEGRAM_BOT_TOKEN", loaded)
                self.assertEqual(os.environ["WUKONG_TELEGRAM_BOT_TOKEN"], "process-token")
                self.assertEqual(os.environ["WUKONG_TELEGRAM_CHAT_ID"], "12345")
                self.assertEqual(os.environ["WUKONG_TELEGRAM_ADMIN_IDS"], "12345,67890")
                self.assertNotIn("IGNORED_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
