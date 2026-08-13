import unittest

import Uploader


class UploaderTests(unittest.TestCase):
    def test_notification_message_keeps_vietnamese_and_emoji(self):
        message = Uploader.build_notification_message("fixture.zip", 1024, 65)
        self.assertIn("\u2705 <b>ROM Build Ho\u00e0n T\u1ea5t!</b>", message)
        self.assertIn("\U0001f4e6 <b>Dung l\u01b0\u1ee3ng:</b> 1.00 KB", message)
        self.assertIn("\u23f1 <b>Th\u1eddi gian build:</b> 1p 5s", message)
        self.assertNotIn("?", message)


if __name__ == "__main__":
    unittest.main()
