from __future__ import annotations

import unittest

from wukong.adapters import _parse_rclone_progress


class RcloneProgressTests(unittest.TestCase):
    def test_extracts_current_file_bytes_speed_percent_and_eta(self) -> None:
        progress = _parse_rclone_progress(
            '{"stats":{"bytes":128,"totalBytes":1024,"speed":64,"eta":14,'
            '"transferring":[{"name":"ROM.zip","bytes":256,"size":1024,"speed":128.5,"eta":6}]}}'
        )

        self.assertEqual(
            {
                "bytes": 256,
                "totalBytes": 1024,
                "speedBytesPerSecond": 128.5,
                "etaSeconds": 6.0,
                "percent": 25.0,
            },
            progress,
        )


if __name__ == "__main__":
    unittest.main()
