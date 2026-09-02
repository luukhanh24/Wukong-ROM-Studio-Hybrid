from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from tools.dccloud_preflight import (
    _anonymous_share_list_url,
    _multipart_canary,
    _native_canary,
    _verify_anonymous_share,
)
from wukong.adapters import RcloneStorageAdapter


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

    @mock.patch("tools.dccloud_preflight.urlopen")
    def test_deleted_share_is_reported_as_actionable_configuration_error(self, open_url: mock.Mock) -> None:
        open_url.return_value = _json_response({"code": 40058, "msg": "Share not found"})

        with self.assertRaisesRegex(SystemExit, "public share was not found.*update WUKONG_DCCLOUD_SHARE_URL"):
            _verify_anonymous_share("https://cloud.example/s/abc", "ROM")

    def test_multipart_canary_round_trips_and_cleans_remote_folders(self) -> None:
        objects: dict[str, bytes] = {}
        purged: list[str] = []

        def run(args: list[str], **_: object) -> str:
            command = args[1]
            if command == "copyto":
                source, destination = args[2], args[3]
                if source.startswith("wukong-dccloud:") and destination.startswith("wukong-dccloud:"):
                    objects[destination] = objects[source]
                elif destination.startswith("wukong-dccloud:"):
                    objects[destination] = Path(source).read_bytes()
                else:
                    Path(destination).write_bytes(objects[source])
                return ""
            if command == "cat":
                if args[2] not in objects:
                    raise RuntimeError("missing")
                return objects[args[2]].decode("utf-8")
            if command == "lsjson":
                size = len(objects[args[2]]) if args[2] in objects else -1
                return json.dumps({"Size": size})
            if command == "purge":
                prefix = args[2].rstrip("/") + "/"
                purged.append(args[2])
                for key in list(objects):
                    if key == args[2] or key.startswith(prefix):
                        del objects[key]
                return ""
            return ""

        result = _multipart_canary(
            RcloneStorageAdapter(remote="wukong-dccloud", root="", run_command=run),
            "ROM",
            1,
        )

        self.assertEqual(1, result["multipartCanaryMiB"])
        self.assertEqual(1, result["parts"])
        self.assertEqual({}, objects)
        self.assertTrue(any(":ROM/_canary/" in target for target in purged))
        self.assertTrue(any(":_staging/" in target for target in purged))

    def test_multipart_canary_reports_cleanup_failure(self) -> None:
        objects: dict[str, bytes] = {}

        def run(args: list[str], **_: object) -> str:
            command = args[1]
            if command == "copyto":
                source, destination = args[2], args[3]
                if source.startswith("wukong-dccloud:") and destination.startswith("wukong-dccloud:"):
                    objects[destination] = objects[source]
                elif destination.startswith("wukong-dccloud:"):
                    objects[destination] = Path(source).read_bytes()
                else:
                    Path(destination).write_bytes(objects[source])
                return ""
            if command == "cat":
                if args[2] not in objects:
                    raise RuntimeError("missing")
                return objects[args[2]].decode("utf-8")
            if command == "lsjson":
                return json.dumps({"Size": len(objects[args[2]]) if args[2] in objects else -1})
            if command == "purge" and ":ROM/_canary/" in args[2]:
                raise RuntimeError("purge failed")
            if command == "purge":
                return ""
            return ""

        with self.assertRaisesRegex(RuntimeError, "cleanup failed"):
            _multipart_canary(
                RcloneStorageAdapter(remote="wukong-dccloud", root="", run_command=run),
                "ROM",
                1,
            )

    def test_native_canary_publishes_one_final_file_and_cleans_up(self) -> None:
        class FakeClient:
            def __init__(self) -> None:
                self.files: dict[str, bytes] = {}
                self.deleted: list[str] = []

            def read_json_file(self, uri: str) -> dict[str, object] | None:
                body = self.files.get(uri)
                return json.loads(body) if body is not None else None

            def get_file(self, uri: str) -> dict[str, object] | None:
                body = self.files.get(uri)
                return {"path": uri, "size": len(body)} if body is not None else None

            def ensure_folder(self, uri: str) -> None:
                return None

            def upload_file(self, source: Path, uri: str, **_: object) -> dict[str, object]:
                self.files[uri] = source.read_bytes()
                return {"path": uri, "size": len(self.files[uri])}

            def move(self, uri: str, destination: str) -> None:
                final_uri = f"{destination}/{uri.rsplit('/', 1)[-1]}"
                self.files[final_uri] = self.files.pop(uri)

            def delete(self, uri: str) -> None:
                self.deleted.append(uri)
                self.files.pop(uri, None)

            def download_file(self, uri: str, destination: Path) -> None:
                destination.write_bytes(self.files[uri])

            def list_children(self, uri: str) -> list[dict[str, object]]:
                prefix = uri.rstrip("/") + "/"
                return [
                    {"name": key[len(prefix) :], "path": key}
                    for key in self.files
                    if key.startswith(prefix) and "/" not in key[len(prefix) :]
                ]

        client = FakeClient()
        result = _native_canary(client, "ROM", 1)  # type: ignore[arg-type]

        self.assertEqual(1, result["nativeCanaryMiB"])
        self.assertEqual(1, result["finalFiles"])
        self.assertEqual({}, client.files)
        self.assertTrue(any("/ROM/_canary/" in uri for uri in client.deleted))
        self.assertTrue(any("/_staging/" in uri for uri in client.deleted))


if __name__ == "__main__":
    unittest.main()
