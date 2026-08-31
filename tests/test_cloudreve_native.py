from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wukong.cloudreve import CloudreveClient, CloudreveError, CloudreveStorageAdapter


class _Response:
    def __init__(self, payload: object, *, status_code: int = 200, content: bytes | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = content if content is not None else json.dumps(payload).encode("utf-8")
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class CloudreveNativeTests(unittest.TestCase):
    def test_native_upload_refreshes_token_and_sends_server_sized_chunks(self) -> None:
        calls: list[tuple[str, str, dict[str, object]]] = []

        def request(method: str, url: str, **kwargs: object) -> _Response:
            calls.append((method, url, kwargs))
            if url.endswith("/session/token/refresh"):
                return _Response({"code": 0, "data": {"access_token": "access", "refresh_token": "next"}})
            if method == "PUT" and url.endswith("/file/upload"):
                return _Response(
                    {
                        "code": 0,
                        "data": {
                            "session_id": "session",
                            "chunk_size": 4,
                            "expires": 4102444800,
                            "uri": "cloudreve://my/WukongROM/_staging/job/rom.zip",
                            "storage_policy": {"type": "local", "chunk_concurrency": 1},
                        },
                    }
                )
            if "/file/info?" in url:
                return _Response({"code": 0, "data": {"size": 10}})
            return _Response({"code": 0, "data": None})

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"abcdefghij")
            progress: list[int] = []
            client = CloudreveClient("https://cloud.example", "refresh", request=request)
            client.upload_file(
                artifact,
                "cloudreve://my/WukongROM/_staging/job/rom.zip",
                progress_callback=lambda event: progress.append(int(event["bytesTransferred"])),
            )

        chunk_calls = [call for call in calls if "/file/upload/session/" in call[1]]
        self.assertEqual(3, len(chunk_calls))
        self.assertEqual([b"abcd", b"efgh", b"ij"], [call[2]["data"] for call in chunk_calls])
        self.assertEqual([4, 8, 10], progress)
        self.assertEqual("Bearer access", chunk_calls[0][2]["headers"]["Authorization"])

    def test_native_upload_rejects_a_chunk_larger_than_proxy_budget(self) -> None:
        def request(method: str, url: str, **_: object) -> _Response:
            if url.endswith("/session/token/refresh"):
                return _Response({"code": 0, "data": {"access_token": "access"}})
            return _Response(
                {
                    "code": 0,
                    "data": {
                        "session_id": "session",
                        "chunk_size": 101 * 1024 * 1024,
                        "expires": 4102444800,
                        "storage_policy": {"type": "local"},
                    },
                }
            )

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            client = CloudreveClient("https://cloud.example", "refresh", request=request)
            with self.assertRaisesRegex(CloudreveError, "chunk_too_large"):
                client.upload_file(artifact, "cloudreve://my/WukongROM/_staging/job/rom.zip")

    def test_native_upload_supports_onedrive_ranges_and_completion_callback(self) -> None:
        calls: list[tuple[str, str, dict[str, object]]] = []

        def request(method: str, url: str, **kwargs: object) -> _Response:
            calls.append((method, url, kwargs))
            if url.endswith("/session/token/refresh"):
                return _Response({"code": 0, "data": {"access_token": "access"}})
            if method == "PUT" and url.endswith("/file/upload"):
                return _Response(
                    {
                        "code": 0,
                        "data": {
                            "session_id": "session",
                            "callback_secret": "callback",
                            "chunk_size": 4,
                            "expires": 4102444800,
                            "upload_urls": ["https://onedrive.example/upload-session"],
                            "storage_policy": {"type": "onedrive"},
                        },
                    }
                )
            if url == "https://onedrive.example/upload-session":
                return _Response({}, status_code=202)
            if "/callback/onedrive/session/callback" in url:
                return _Response({"code": 0, "data": None})
            if "/file/info?" in url:
                return _Response({"code": 0, "data": {"size": 10}})
            raise AssertionError(f"Unexpected request: {method} {url}")

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"abcdefghij")
            client = CloudreveClient("https://cloud.example", "refresh", request=request)
            client.upload_file(artifact, "cloudreve://my/WukongROM/_staging/job/rom.zip")

        range_calls = [call for call in calls if call[1] == "https://onedrive.example/upload-session"]
        self.assertEqual(
            [
                "bytes 0-3/10",
                "bytes 4-7/10",
                "bytes 8-9/10",
            ],
            [str(call[2]["headers"]["Content-Range"]) for call in range_calls],
        )
        self.assertEqual([b"abcd", b"efgh", b"ij"], [call[2]["data"] for call in range_calls])
        callback = next(call for call in calls if "/callback/onedrive/session/callback" in call[1])
        self.assertEqual("POST", callback[0])
        self.assertEqual("Bearer access", callback[2]["headers"]["Authorization"])

    def test_storage_adapter_uses_sidecar_as_completion_marker(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.uploaded: list[str] = []
                self.moved: list[tuple[str, str]] = []
                self.files: dict[str, int] = {}

            def read_json_file(self, uri: str) -> dict[str, object] | None:
                return None

            def get_file(self, uri: str) -> dict[str, object] | None:
                size = self.files.get(uri)
                return {"path": uri, "size": size} if size is not None else None

            def ensure_folder(self, uri: str) -> None:
                return None

            def upload_file(self, source: Path, uri: str, **_: object) -> dict[str, object]:
                self.uploaded.append(uri)
                self.files[uri] = source.stat().st_size
                return {"path": uri, "size": self.files[uri]}

            def move(self, uri: str, destination: str) -> None:
                self.moved.append((uri, destination))
                self.files[f"{destination}/{uri.rsplit('/', 1)[-1]}"] = self.files.pop(uri)

        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "rom.zip")
            artifact.write_bytes(b"rom")
            fake = FakeClient()
            adapter = CloudreveStorageAdapter(fake)
            record = adapter.mirror_artifact(
                artifact,
                relative_path="ROM/V6/Plus/rom.zip",
                staging_key="job",
            )

        self.assertEqual("cloudreve://my/WukongROM/ROM/V6/Plus/rom.zip", record.uri)
        self.assertEqual(
            [
                "cloudreve://my/WukongROM/_staging/job/rom.zip",
                "cloudreve://my/WukongROM/ROM/V6/Plus/rom.zip.metadata.json",
            ],
            fake.uploaded,
        )
        self.assertEqual(
            [("cloudreve://my/WukongROM/_staging/job/rom.zip", "cloudreve://my/WukongROM/ROM/V6/Plus")],
            fake.moved,
        )


if __name__ == "__main__":
    unittest.main()
