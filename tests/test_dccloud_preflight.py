from __future__ import annotations

import base64
import io
import json
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from tools.dccloud_preflight import _anonymous_share_list_url, _verify_anonymous_share


class _Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200) -> None:
        super().__init__(body)
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _json_response(payload: object) -> _Response:
    return _Response(json.dumps(payload).encode("utf-8"))


class DCloudPreflightTests(unittest.TestCase):
    def test_short_share_url_becomes_anonymous_file_listing_request(self) -> None:
        result = _anonymous_share_list_url("https://cloud.example/s/BokhN")

        parsed = urlsplit(result)
        self.assertEqual("https", parsed.scheme)
        self.assertEqual("cloud.example", parsed.netloc)
        self.assertEqual("/api/v4/file", parsed.path)
        self.assertEqual(["cloudreve://BokhN@share"], parse_qs(parsed.query)["uri"])

    def test_canonical_share_url_is_supported(self) -> None:
        result = _anonymous_share_list_url(
            "https://cloud.example/home?path=cloudreve%3A%2F%2FBokhN%40share"
        )

        self.assertEqual(
            ["cloudreve://BokhN@share"],
            parse_qs(urlsplit(result).query)["uri"],
        )

    def test_non_share_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cloudreve folder share"):
            _anonymous_share_list_url("https://cloud.example/home")

    @mock.patch("tools.dccloud_preflight.urlopen")
    def test_anonymous_probe_is_listed_downloaded_and_read_only(self, open_url: mock.Mock) -> None:
        probe_body = b"probe\n"
        open_url.side_effect = [
            _json_response(
                {
                    "code": 0,
                    "data": {
                        "files": [{"name": "probe.txt", "path": "cloudreve://abc@share/probe.txt"}],
                        "parent": {"name": "ROM"},
                        "props": {"capability": "gIaYAQ=="},
                        "context_hint": "hint",
                    },
                }
            ),
            _json_response({"code": 0, "data": {"urls": [{"url": "https://download.example/probe"}]}}),
            _Response(probe_body),
        ]

        _verify_anonymous_share(
            "https://cloud.example/s/abc",
            "ROM",
            probe_name="probe.txt",
            probe_body=probe_body,
        )

        self.assertEqual(3, open_url.call_count)

    @mock.patch("tools.dccloud_preflight.urlopen")
    def test_anonymous_write_capability_is_rejected(self, open_url: mock.Mock) -> None:
        capability = bytearray(base64.b64decode("gIaYAQ=="))
        capability[0] |= 1  # NavigatorCapabilityCreateFile
        open_url.return_value = _json_response(
            {
                "code": 0,
                "data": {
                    "files": [],
                    "parent": {"name": "ROM"},
                    "props": {"capability": base64.b64encode(capability).decode("ascii")},
                    "context_hint": "hint",
                },
            }
        )

        with self.assertRaisesRegex(SystemExit, "write permissions"):
            _verify_anonymous_share("https://cloud.example/s/abc", "ROM")


if __name__ == "__main__":
    unittest.main()
