from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.error import URLError
from urllib.request import Request

from wukong.cli import main as cli_main
from wukong.adapters import SourceResolutionError
from wukong.source_probe import probe_http_source


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, *, url: str, status: int, headers: dict[str, str]) -> None:
        super().__init__(payload)
        self._url = url
        self.status = status
        self.headers = Message()
        for key, value in headers.items():
            self.headers[key] = value

    def geturl(self) -> str:
        return self._url

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class _InitialOpener:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self.payload = payload
        self.final_url = final_url
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: float | None = None) -> _Response:
        self.requests.append(request)
        return _Response(
            self.payload[:1],
            url=self.final_url,
            status=206,
            headers={
                "Content-Type": "application/zip",
                "Content-Length": "1",
                "Content-Range": f"bytes 0-0/{len(self.payload)}",
                "Accept-Ranges": "bytes",
                "Content-Disposition": 'attachment; filename="PKG110_16.0.9.zip"',
                "ETag": '"fixture-etag"',
                "Last-Modified": "Tue, 09 Jun 2026 11:30:59 GMT",
                "x-amz-meta-filemd5": "a28632dc4e3e2c8b51cc6e938c87b6fb",
            },
        )


class _RangeOpener:
    def __init__(self, payload: bytes, final_url: str) -> None:
        self.payload = payload
        self.final_url = final_url
        self.requests: list[Request] = []

    def open(self, request: Request, timeout: float | None = None) -> _Response:
        self.requests.append(request)
        value = request.get_header("Range") or ""
        unit, bounds = value.split("=", 1)
        start_text, end_text = bounds.split("-", 1)
        start = int(start_text)
        end = min(len(self.payload) - 1, int(end_text))
        body = self.payload[start : end + 1]
        return _Response(
            body,
            url=self.final_url,
            status=206,
            headers={
                "Content-Type": "application/zip",
                "Content-Length": str(len(body)),
                "Content-Range": f"{unit} {start}-{end}/{len(self.payload)}",
            },
        )


class _FlakyInitialOpener(_InitialOpener):
    def __init__(self, payload: bytes, final_url: str) -> None:
        super().__init__(payload, final_url)
        self.calls = 0

    def open(self, request: Request, timeout: float | None = None) -> _Response:
        self.calls += 1
        if self.calls == 1:
            raise URLError("temporary OPlus edge failure")
        return super().open(request, timeout)


def _fixture_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "META-INF/com/android/metadata",
            "\n".join(
                [
                    "oplus_product_name=PKG110",
                    "oplus_version_name=PKG110_16.0.9.400",
                    "post-sdk-level=36",
                    "post-timestamp=1786441098",
                    "post-security-patch-level=2026-06-01",
                    "ota-type=AB",
                ]
            ),
        )
        archive.writestr("payload_properties.txt", "FILE_SIZE=123\nFILE_HASH=base64hash\n")
        archive.writestr("payload.bin", b"fixture")
    return output.getvalue()


class SourceProbeTests(unittest.TestCase):
    def test_probe_retries_a_transient_initial_oplus_failure(self) -> None:
        payload = _fixture_zip()
        resolver = "https://93.184.216.34/downloadCheck?c=abc"
        final_url = "https://93.184.216.35/rom.zip?expires=9999999999&signature=signed"
        initial = _FlakyInitialOpener(payload, final_url)

        result = probe_http_source(
            resolver,
            opener=initial,
            opener_factory=lambda: _RangeOpener(payload, final_url),
            timeout=2,
        )

        self.assertEqual("PKG110", result.product_name)
        self.assertEqual(2, initial.calls)

    def test_probe_rejects_an_expired_direct_signed_url_before_network_io(self) -> None:
        payload = _fixture_zip()
        expired = "https://93.184.216.35/rom.zip?expires=1700000000&signature=expired"
        initial = _InitialOpener(payload, expired)

        with self.assertRaisesRegex(SourceResolutionError, "signed.*expired"):
            probe_http_source(expired, opener=initial, timeout=2)

        self.assertEqual([], initial.requests)

    def test_probe_rejects_a_signed_url_that_will_expire_before_a_cloud_build_can_download_it(self) -> None:
        payload = _fixture_zip()
        now = 1_787_484_600
        near_expiry = (
            "https://93.184.216.35/rom.zip?"
            f"expires={now + 633}&signature=short-lived"
        )
        initial = _InitialOpener(payload, near_expiry)

        with mock.patch("wukong.source_probe.time.time", return_value=now):
            with self.assertRaisesRegex(SourceResolutionError, "signed.*expires too soon"):
                probe_http_source(near_expiry, opener=initial, timeout=2)

        self.assertEqual([], initial.requests)

    def test_probe_does_not_treat_an_unsigned_expires_parameter_as_a_signed_download(self) -> None:
        payload = _fixture_zip()
        ordinary = "https://93.184.216.35/rom.zip?expires=1700000000&view=ota"
        initial = _InitialOpener(payload, ordinary)

        result = probe_http_source(
            ordinary,
            opener=initial,
            opener_factory=lambda: _RangeOpener(payload, ordinary),
            timeout=2,
        )

        self.assertEqual("PKG110", result.product_name)
        self.assertNotEqual([], initial.requests)

    def test_probe_rejects_relative_aws_and_oss_v4_expirations(self) -> None:
        payload = _fixture_zip()
        now = 1_787_484_900
        urls = (
            "https://93.184.216.35/rom.zip?X-Amz-Date=20260823T113000Z&"
            "X-Amz-Expires=2000&X-Amz-Signature=short-lived",
            "https://93.184.216.35/rom.zip?x-oss-date=20260823T113000Z&"
            "x-oss-expires=2000&x-oss-signature=short-lived",
        )

        for uri in urls:
            with self.subTest(uri=uri):
                initial = _InitialOpener(payload, uri)
                with mock.patch("wukong.source_probe.time.time", return_value=now):
                    with self.assertRaisesRegex(SourceResolutionError, "signed.*expires too soon"):
                        probe_http_source(uri, opener=initial, timeout=2)
                self.assertEqual([], initial.requests)

    def test_probe_resolves_oplus_and_reads_remote_zip_metadata_without_full_download(self) -> None:
        payload = _fixture_zip()
        resolver = "https://93.184.216.34/downloadCheck?c=abc"
        final_url = "https://93.184.216.35/rom.zip?Signature=signed"
        initial = _InitialOpener(payload, final_url)
        ranges = _RangeOpener(payload, final_url)

        result = probe_http_source(
            resolver,
            opener=initial,
            opener_factory=lambda: ranges,
            timeout=2,
        )

        self.assertEqual("oplus", result.provider)
        self.assertEqual("PKG110_16.0.9.zip", result.filename)
        self.assertEqual(len(payload), result.size_bytes)
        self.assertEqual("PKG110", result.device)
        self.assertEqual("PKG110", result.product_name)
        self.assertEqual("PKG110_16.0.9.400", result.version)
        self.assertEqual("16", result.android_version)
        self.assertEqual("2026-08-11 09:38:18", result.build_date)
        self.assertEqual("2026-06-01", result.security_patch)
        self.assertEqual("AB", result.ota_type)
        self.assertTrue(result.deep_inspected)
        self.assertGreater(len(ranges.requests), 0)
        public = result.to_dict()
        self.assertNotIn("resolvedUrl", public)
        self.assertNotIn("Signature=signed", json.dumps(public))
        self.assertEqual("16", public["androidVersion"])
        self.assertEqual("2026-08-11 09:38:18", public["buildDate"])

    def test_probe_reports_headers_when_remote_zip_metadata_is_unavailable(self) -> None:
        payload = b"not-a-zip"
        resolver = "https://93.184.216.34/downloadCheck?c=abc"
        final_url = "https://93.184.216.35/rom.zip?Signature=signed"

        result = probe_http_source(
            resolver,
            opener=_InitialOpener(payload, final_url),
            opener_factory=lambda: _RangeOpener(payload, final_url),
            timeout=2,
        )

        self.assertEqual(len(payload), result.size_bytes)
        self.assertEqual('"fixture-etag"', result.etag)
        self.assertEqual("a28632dc4e3e2c8b51cc6e938c87b6fb", result.md5)
        self.assertFalse(result.deep_inspected)
        self.assertIsNotNone(result.warning)

    def test_cli_exposes_safe_source_probe_for_actions(self) -> None:
        safe = mock.Mock()
        safe.to_dict.return_value = {
            "provider": "oplus",
            "productName": "PKG110",
            "version": "fixture",
        }
        output = io.StringIO()
        with mock.patch("wukong.cli.probe_http_source", return_value=safe), mock.patch(
            "wukong.cli.sys.stdout", output
        ):
            status = cli_main(["probe-source", "https://example.com/downloadCheck?c=secret"])

        self.assertEqual(0, status)
        payload = json.loads(output.getvalue())
        self.assertEqual("PKG110", payload["productName"])
        self.assertNotIn("secret", output.getvalue())

    def test_probe_bounds_total_remote_range_requests(self) -> None:
        payload = _fixture_zip()
        resolver = "https://93.184.216.34/downloadCheck?c=abc"
        final_url = "https://93.184.216.35/rom.zip?Signature=signed"
        with mock.patch("wukong.source_probe.MAX_RANGE_REQUESTS", 0):
            result = probe_http_source(
                resolver,
                opener=_InitialOpener(payload, final_url),
                opener_factory=lambda: _RangeOpener(payload, final_url),
                timeout=2,
            )

        self.assertFalse(result.deep_inspected)
        self.assertIn("too many range requests", result.warning or "")


if __name__ == "__main__":
    unittest.main()
