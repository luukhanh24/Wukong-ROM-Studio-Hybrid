from __future__ import annotations

import hashlib
import gzip
import io
import json
import os
import subprocess
import tempfile
import tarfile
import unittest
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

from wukong.adapters import (
    HttpSourceAdapter,
    LocalSourceAdapter,
    RcloneStorageAdapter,
    SourceIntegrityError,
    SourceResolutionError,
)
from wukong.cloud_sync import CloudJobSync
from wukong.cli import main as cli_main
from wukong.content_packs import ContentPackManager, build_content_index, upload_content_packs
from wukong.github import GitHubActionsAdapter, GitHubApiError
from wukong.models import BuildRecipe, Identity, JobStatus, RecipeValidationError
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore, OrchestrationError
from wukong.routing import RunnerInventory, RunnerRouter, RunnerUnavailableError
from wukong.telegram import TelegramAccessStore
from wukong.telegram_bot import TelegramBotController
from wukong.security import validate_recipe_access


class BuildRecipeContractTests(unittest.TestCase):
    def test_recipe_round_trip_is_canonical_and_secret_free(self) -> None:
        payload = {
            "schemaVersion": 1,
            "task": "build",
            "device": "CPH2725",
            "source": {
                "kind": "https",
                "uri": "https://downloads.example/rom.zip",
                "sha256": "a" * 64,
                "sizeBytes": 2_000_000_000,
            },
            "build": {
                "preset": "custom",
                "mods": ["Gallery_mod", "Gapps"],
                "modVersion": "ColorOS_16.0.8",
                "package": True,
            },
            "execution": {"target": "github-auto"},
            "storage": {"remote": "wukong-gdrive", "publishArtifact": True},
        }

        recipe = BuildRecipe.from_dict(payload)
        serialized = recipe.to_dict()

        self.assertEqual(serialized, BuildRecipe.from_dict(serialized).to_dict())
        self.assertEqual(recipe.digest, hashlib.sha256(recipe.canonical_json.encode()).hexdigest())
        self.assertNotIn("token", recipe.canonical_json.casefold())
        self.assertEqual(recipe.to_legacy_spec()["romPath"], "https://downloads.example/rom.zip")
        self.assertEqual(recipe.to_legacy_spec()["modNames"], ["Gallery_mod", "Gapps"])

    def test_recipe_rejects_secrets_and_unsafe_remote_paths(self) -> None:
        base = {
            "schemaVersion": 1,
            "task": "source_mirror",
            "device": "CPH2725",
            "source": {"kind": "rclone", "uri": "wukong-gdrive:WukongROM/sources/rom.zip"},
        }
        with self.assertRaisesRegex(RecipeValidationError, "secret"):
            BuildRecipe.from_dict({**base, "accessToken": "do-not-store"})
        with self.assertRaisesRegex(RecipeValidationError, "traversal"):
            BuildRecipe.from_dict(
                {**base, "source": {"kind": "rclone", "uri": "wukong-gdrive:../secret"}}
            )

    def test_recipe_rejects_private_network_http_sources(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "private network"):
            BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "CPH2725",
                    "source": {"kind": "http", "uri": "http://127.0.0.1/rom.zip"},
                }
            )

    def test_recipe_rejects_path_unsafe_mod_names(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "path-safe"):
            BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "CPH2725",
                    "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                    "build": {"modVersion": "../secret"},
                }
            )

    def test_recipe_rejects_string_booleans(self) -> None:
        with self.assertRaisesRegex(RecipeValidationError, "JSON boolean"):
            BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "CPH2725",
                    "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                    "storage": {"publishArtifact": "false"},
                }
            )

    def test_identity_is_supplied_outside_recipe(self) -> None:
        recipe = BuildRecipe.from_dict(
            {
                "schemaVersion": 1,
                "task": "artifact_publish",
                "device": "CPH2725",
                "source": {"kind": "local", "uri": "C:/ROM/output.zip"},
                "requester": "admin",
            }
        )
        self.assertNotIn("requester", recipe.to_dict())
        self.assertEqual(Identity(channel="telegram", subject="42", role="user").subject, "42")


class RunnerRoutingContractTests(unittest.TestCase):
    def test_small_github_job_routes_to_pinned_hosted_runner(self) -> None:
        router = RunnerRouter()
        decision = router.choose(
            target="github-auto",
            estimated_workspace_bytes=9 * 1024**3,
            inventory=RunnerInventory(self_hosted_online=False),
        )
        self.assertEqual(decision.runner, "ubuntu-24.04")
        self.assertEqual(decision.kind, "github-hosted")

    def test_large_job_routes_to_qualified_self_hosted_runner(self) -> None:
        router = RunnerRouter()
        decision = router.choose(
            target="github-auto",
            estimated_workspace_bytes=20 * 1024**3,
            inventory=RunnerInventory(
                self_hosted_online=True,
                free_disk_bytes=180 * 1024**3,
                memory_bytes=32 * 1024**3,
                logical_cpus=12,
            ),
        )
        self.assertEqual(decision.labels, ("self-hosted", "linux", "x64", "wukong-rom"))

    def test_large_job_fails_fast_when_runner_is_offline(self) -> None:
        with self.assertRaisesRegex(RunnerUnavailableError, "offline"):
            RunnerRouter().choose(
                target="github-auto",
                estimated_workspace_bytes=20 * 1024**3,
                inventory=RunnerInventory(self_hosted_online=False),
            )

    def test_explicit_hosted_large_job_routes_to_self_hosted(self) -> None:
        decision = RunnerRouter().choose(
            target="github-hosted",
            estimated_workspace_bytes=20 * 1024**3,
            inventory=RunnerInventory(
                self_hosted_online=True,
                free_disk_bytes=180 * 1024**3,
                memory_bytes=32 * 1024**3,
                logical_cpus=12,
            ),
        )
        self.assertEqual(decision.kind, "self-hosted")

    def test_job_status_uses_hybrid_contract_names(self) -> None:
        self.assertEqual(JobStatus.SUCCEEDED.value, "succeeded")


class SourceAndStorageContractTests(unittest.TestCase):
    class _HttpResponse(io.BytesIO):
        def __init__(
            self,
            payload: bytes,
            *,
            url: str,
            content_type: str,
            status: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            super().__init__(payload)
            self._url = url
            self.headers = {"Content-Type": content_type, **(headers or {})}
            self.status = status

        def geturl(self) -> str:
            return self._url

        def getcode(self) -> int:
            return self.status

    class _SequenceOpener:
        def __init__(self, responses: list[io.BytesIO]) -> None:
            self.responses = responses
            self.requests: list[object] = []

        def open(self, request: object, *, timeout: int) -> io.BytesIO:
            self.requests.append(request)
            return self.responses.pop(0)

    class _RangeOpener:
        def __init__(self, payload: bytes, *, url: str, requests: list[Request]) -> None:
            self.payload = payload
            self.url = url
            self.requests = requests

        def open(self, request: Request, *, timeout: int) -> io.BytesIO:
            self.requests.append(request)
            range_header = request.get_header("Range")
            if not range_header or not range_header.startswith("bytes="):
                raise AssertionError("parallel request is missing byte range")
            start_text, end_text = range_header.removeprefix("bytes=").split("-", 1)
            start = int(start_text)
            end = int(end_text)
            return SourceAndStorageContractTests._HttpResponse(
                self.payload[start : end + 1],
                url=self.url,
                content_type="application/octet-stream",
                status=206,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{len(self.payload)}",
                    "Content-Length": str(end - start + 1),
                },
            )

    class _IgnoringRangeOpener:
        def __init__(self, payload: bytes, *, url: str, requests: list[Request]) -> None:
            self.payload = payload
            self.url = url
            self.requests = requests

        def open(self, request: Request, *, timeout: int) -> io.BytesIO:
            self.requests.append(request)
            return SourceAndStorageContractTests._HttpResponse(
                self.payload,
                url=self.url,
                content_type="application/zip",
                status=200,
                headers={"Content-Length": str(len(self.payload))},
            )

    class _ProbeThenIgnoreRangeOpener:
        def __init__(self, payload: bytes, *, url: str, requests: list[Request]) -> None:
            self.payload = payload
            self.url = url
            self.requests = requests

        def open(self, request: Request, *, timeout: int) -> io.BytesIO:
            self.requests.append(request)
            if request.get_header("Range") == "bytes=0-0":
                return SourceAndStorageContractTests._HttpResponse(
                    self.payload[:1],
                    url=self.url,
                    content_type="application/octet-stream",
                    status=206,
                    headers={"Content-Range": f"bytes 0-0/{len(self.payload)}"},
                )
            return SourceAndStorageContractTests._HttpResponse(
                self.payload,
                url=self.url,
                content_type="application/zip",
                status=200,
                headers={"Content-Length": str(len(self.payload))},
            )

    def test_http_source_parallel_download_assembles_ranges_in_order(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        payload = b"PK\x03\x04" + bytes(range(60))
        initial = self._SequenceOpener(
            [
                self._HttpResponse(
                    payload,
                    url=download_url,
                    content_type="application/zip",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(payload)),
                        "ETag": '"resume-etag"',
                    },
                )
            ]
        )
        range_requests: list[Request] = []

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            result = HttpSourceAdapter(
                attempts=1,
                opener=initial,
                opener_factory=lambda: self._RangeOpener(
                    payload,
                    url=download_url,
                    requests=range_requests,
                ),
                max_connections=3,
                parallel_threshold_bytes=1,
            ).materialize(resolver_url, target)

            self.assertEqual(result.path.read_bytes(), payload)
            self.assertEqual(len(range_requests), 4)
            self.assertFalse(list(target.parent.glob("*.range-*")))

    def test_http_source_parallel_download_resumes_prefix_and_range_checkpoint(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        payload = b"PK\x03\x04" + bytes(range(16))
        initial = self._SequenceOpener(
            [
                self._HttpResponse(
                    payload,
                    url=download_url,
                    content_type="application/zip",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(payload)),
                        "ETag": '"resume-etag"',
                    },
                )
            ]
        )
        range_requests: list[Request] = []

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            partial = target.with_suffix(".zip.partial")
            partial.write_bytes(payload[:4])
            partial.with_name(partial.name + ".range-4-11").write_bytes(payload[4:7])
            partial.with_name(partial.name + ".http.json").write_text(
                json.dumps(
                    {
                        "url": download_url,
                        "sizeBytes": len(payload),
                        "etag": '"resume-etag"',
                        "lastModified": None,
                    }
                ),
                encoding="utf-8",
            )
            result = HttpSourceAdapter(
                attempts=1,
                opener=initial,
                opener_factory=lambda: self._RangeOpener(
                    payload,
                    url=download_url,
                    requests=range_requests,
                ),
                max_connections=2,
                parallel_threshold_bytes=1,
            ).materialize(resolver_url, target)

            self.assertEqual(result.path.read_bytes(), payload)
            requested_ranges = {request.get_header("Range") for request in range_requests}
            self.assertEqual(requested_ranges, {"bytes=0-0", "bytes=7-11", "bytes=12-19"})

    def test_http_source_falls_back_when_server_ignores_range_probe(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        payload = b"PK\x03\x04sequential-fallback"
        initial = self._SequenceOpener(
            [
                self._HttpResponse(
                    payload,
                    url=download_url,
                    content_type="application/zip",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(payload)),
                        "ETag": '"fallback-etag"',
                    },
                )
            ]
        )
        requests: list[Request] = []

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            result = HttpSourceAdapter(
                attempts=1,
                opener=initial,
                opener_factory=lambda: self._IgnoringRangeOpener(
                    payload,
                    url=download_url,
                    requests=requests,
                ),
                max_connections=3,
                parallel_threshold_bytes=1,
            ).materialize(resolver_url, target)

            self.assertEqual(result.path.read_bytes(), payload)
            self.assertEqual([request.get_header("Range") for request in requests], ["bytes=0-0"])

    def test_http_source_falls_back_when_worker_stops_honoring_ranges(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        payload = b"PK\x03\x04worker-fallback"
        initial = self._SequenceOpener(
            [
                self._HttpResponse(
                    payload,
                    url=download_url,
                    content_type="application/zip",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(payload)),
                        "ETag": '"worker-fallback-etag"',
                    },
                )
            ]
        )
        requests: list[Request] = []

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            result = HttpSourceAdapter(
                attempts=1,
                opener=initial,
                opener_factory=lambda: self._ProbeThenIgnoreRangeOpener(
                    payload,
                    url=download_url,
                    requests=requests,
                ),
                max_connections=2,
                parallel_threshold_bytes=1,
            ).materialize(resolver_url, target)

            self.assertEqual(result.path.read_bytes(), payload)
            self.assertTrue(any(request.get_header("Range") not in {None, "bytes=0-0"} for request in requests))
            self.assertIsNone(requests[-1].get_header("Range"))

    def test_parallel_worker_uses_strong_etag_as_if_range_validator(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        payload = b"PK\x03\x04" + bytes(range(16))
        initial = self._SequenceOpener(
            [
                self._HttpResponse(
                    payload,
                    url=download_url,
                    content_type="application/zip",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(payload)),
                        "ETag": '"strong-etag"',
                    },
                )
            ]
        )
        range_requests: list[Request] = []

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            HttpSourceAdapter(
                attempts=1,
                opener=initial,
                opener_factory=lambda: self._RangeOpener(
                    payload,
                    url=download_url,
                    requests=range_requests,
                ),
                max_connections=2,
                parallel_threshold_bytes=1,
            ).materialize(resolver_url, target)

            workers = [request for request in range_requests if request.get_header("Range") != "bytes=0-0"]
            self.assertTrue(workers)
            self.assertTrue(all(request.get_header("If-range") == '"strong-etag"' for request in workers))

    def test_http_source_discards_stale_parallel_checkpoint_identity(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        payload = b"PK\x03\x04" + bytes(range(16))
        initial = self._SequenceOpener(
            [
                self._HttpResponse(
                    payload,
                    url=download_url,
                    content_type="application/zip",
                    headers={
                        "Accept-Ranges": "bytes",
                        "Content-Length": str(len(payload)),
                        "ETag": '"new-etag"',
                    },
                )
            ]
        )
        range_requests: list[Request] = []

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            partial = target.with_suffix(".zip.partial")
            partial.write_bytes(b"stale")
            partial.with_name(partial.name + ".http.json").write_text(
                json.dumps({"url": download_url, "sizeBytes": len(payload), "etag": '"old-etag"'}),
                encoding="utf-8",
            )
            result = HttpSourceAdapter(
                attempts=1,
                opener=initial,
                opener_factory=lambda: self._RangeOpener(
                    payload,
                    url=download_url,
                    requests=range_requests,
                ),
                max_connections=2,
                parallel_threshold_bytes=1,
            ).materialize(resolver_url, target)

            self.assertEqual(result.path.read_bytes(), payload)
            self.assertIn("bytes=0-9", {request.get_header("Range") for request in range_requests})
            self.assertFalse(partial.with_name(partial.name + ".http.json").exists())

    def test_http_source_uses_oplus_headers_and_downloads_redirected_rom(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        download_url = "https://93.184.216.35/rom.zip"
        opener = self._SequenceOpener(
            [
                self._HttpResponse(
                    b"PK\x03\x04rom-content",
                    url=download_url,
                    content_type="application/zip",
                ),
            ]
        )

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            result = HttpSourceAdapter(attempts=1, opener=opener).materialize(
                resolver_url,
                target,
            )

            self.assertEqual(result.path.read_bytes(), b"PK\x03\x04rom-content")
            self.assertEqual(len(opener.requests), 1)
            request_headers = dict(opener.requests[0].header_items())
            self.assertEqual(request_headers["User-agent"], "okhttp/3.12.12")
            self.assertEqual(request_headers["Userid"], "oplus-ota|16002018")

    def test_http_source_reports_ota_error_instead_of_saving_json_as_rom(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        opener = self._SequenceOpener(
            [
                self._HttpResponse(
                    b'{"body":null,"errMsg":"2306","responseCode":2306}',
                    url=resolver_url,
                    content_type="application/json;charset=UTF-8",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            with self.assertRaisesRegex(SourceResolutionError, "responseCode=2306.*errMsg=2306"):
                HttpSourceAdapter(attempts=1, opener=opener).materialize(resolver_url, target)

            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".zip.partial").exists())

    def test_http_source_reports_gzip_compressed_ota_error(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        payload = gzip.compress(b'{"body":null,"errMsg":"2306","responseCode":2306}')
        response = self._HttpResponse(
            payload,
            url=resolver_url,
            content_type="application/json",
        )
        response.headers["Content-Encoding"] = "gzip"
        opener = self._SequenceOpener(
            [response]
        )

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            with self.assertRaisesRegex(SourceResolutionError, "responseCode=2306.*errMsg=2306"):
                HttpSourceAdapter(attempts=1, opener=opener).materialize(resolver_url, target)

            self.assertFalse(target.exists())

    def test_http_source_reports_deflate_compressed_ota_error(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        payload = zlib.compress(b'{"body":null,"errMsg":"2306","responseCode":2306}')
        response = self._HttpResponse(
            payload,
            url=resolver_url,
            content_type="application/json",
        )
        response.headers["Content-Encoding"] = "deflate"
        opener = self._SequenceOpener([response])

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            with self.assertRaisesRegex(SourceResolutionError, "responseCode=2306.*errMsg=2306"):
                HttpSourceAdapter(attempts=1, opener=opener).materialize(resolver_url, target)

            self.assertFalse(target.exists())

    def test_http_source_requires_oplus_endpoint_to_redirect(self) -> None:
        resolver_url = "https://93.184.216.34/downloadCheck"
        opener = self._SequenceOpener(
            [
                self._HttpResponse(
                    b"<html>request rejected</html>",
                    url=resolver_url,
                    content_type="text/html",
                )
            ]
        )

        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "rom.zip")
            with self.assertRaisesRegex(SourceResolutionError, "did not redirect"):
                HttpSourceAdapter(attempts=1, opener=opener).materialize(resolver_url, target)

            self.assertFalse(target.exists())

    def test_safe_redirect_handler_rejects_private_target(self) -> None:
        from wukong.adapters import _SafeRedirectHandler

        request = object()
        with self.assertRaisesRegex(ValueError, "private network"):
            _SafeRedirectHandler().redirect_request(
                request,
                object(),
                302,
                "Found",
                {},
                "http://127.0.0.1/rom.zip",
            )

    def test_local_source_is_copied_and_checksum_verified(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "rom.zip")
            source.write_bytes(b"known-rom")
            expected = "726e96014500c12d3f91501c159da58b7e8a626677584b1d7666fe261aff9066"
            target = Path(root, "workspace", "rom.zip")

            result = LocalSourceAdapter().materialize(source.as_posix(), target, expected)

            self.assertEqual(result.sha256, expected)
            self.assertEqual(target.read_bytes(), b"known-rom")

    def test_local_source_removes_bad_download_on_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "rom.zip")
            source.write_bytes(b"tampered")
            target = Path(root, "workspace", "rom.zip")
            with self.assertRaises(SourceIntegrityError):
                LocalSourceAdapter().materialize(source.as_posix(), target, "0" * 64)
            self.assertFalse(target.exists())

    def test_rclone_publish_writes_metadata_and_returns_public_link(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            artifact = Path(root, "artifact.zip")
            artifact.write_bytes(b"artifact")
            calls: list[list[str]] = []

            def fake_run(args: list[str], **_: object) -> str:
                calls.append(args)
                return "https://drive.example/public\n" if args[1] == "link" else ""

            storage = RcloneStorageAdapter(remote="wukong-gdrive", run_command=fake_run)
            record = storage.publish_artifact(artifact, device="CPH2725", build="V4.1")

            self.assertEqual(record.public_url, "https://drive.example/public")
            self.assertTrue(any(command[1] == "copyto" for command in calls))
            self.assertTrue(any(command[1] == "link" for command in calls))
            metadata = json.loads(Path(root, "artifact.zip.metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["sha256"], record.sha256)
            self.assertEqual(metadata["sizeBytes"], 8)

    def test_source_mirror_uploads_sha256_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom-source")
            copied: dict[str, bytes] = {}

            def fake_run(args: list[str], **_: object) -> str:
                if args[1] == "copyto":
                    copied[args[3]] = Path(args[2]).read_bytes()
                return ""

            record = RcloneStorageAdapter(run_command=fake_run).store_source(
                source,
                device="CPH2725",
            )
            metadata_uri = record.uri + ".metadata.json"
            self.assertIn(metadata_uri, copied)
            metadata = json.loads(copied[metadata_uri])
            self.assertEqual(metadata["sha256"], record.sha256)
            self.assertEqual(metadata["sizeBytes"], len(b"rom-source"))

    def test_checkpoint_archive_round_trip_uses_one_remote_payload(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "workspace")
            source.mkdir()
            (source / "marker.json").write_text("{}", encoding="utf-8")
            nested = source / "rom-unpack" / "system"
            nested.mkdir(parents=True)
            (nested / "build.prop").write_text("version=1", encoding="utf-8")
            remote_files: dict[str, bytes] = {}

            def fake_run(args: list[str], **_: object) -> str:
                operation = args[1]
                if operation == "copyto":
                    remote_files[args[3]] = Path(args[2]).read_bytes()
                elif operation == "moveto":
                    remote_files[args[3]] = remote_files.pop(args[2])
                elif operation == "cat":
                    return remote_files[args[2]].decode("utf-8")
                return ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                operation = args[1]
                if operation == "rcat":
                    self.assertEqual(int(args[args.index("--size") + 1]), len(payload or b""))
                    remote_files[args[2]] = payload or b""
                    return b""
                if operation == "cat":
                    return remote_files[args[2]]
                raise AssertionError(args)

            storage = RcloneStorageAdapter(
                run_command=fake_run,
                stream_command=fake_stream,
            )
            uri = storage.sync_tree(source, "checkpoints/job/extract_payload")
            restored = Path(root, "restored")
            storage.restore_tree(uri, restored)

            self.assertTrue(uri.endswith(".tar"))
            self.assertEqual((restored / "marker.json").read_text(encoding="utf-8"), "{}")
            self.assertEqual(
                (restored / "rom-unpack" / "system" / "build.prop").read_text(encoding="utf-8"),
                "version=1",
            )
            self.assertIn(uri + ".metadata.json", remote_files)
            metadata = json.loads(remote_files[uri + ".metadata.json"])
            self.assertEqual(hashlib.sha256(remote_files[uri]).hexdigest(), metadata["sha256"])

    def test_checkpoint_restore_rejects_path_traversal_archive(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as handle:
                member = tarfile.TarInfo("../escape.txt")
                member.size = 6
                handle.addfile(member, io.BytesIO(b"escape"))
            uri = "wukong-gdrive:WukongROM/checkpoints/job/stage.tar"
            metadata_uri = uri + ".metadata.json"
            remote_files = {
                uri: archive.getvalue(),
                metadata_uri: json.dumps(
                    {
                        "schemaVersion": 1,
                        "sha256": hashlib.sha256(archive.getvalue()).hexdigest(),
                        "sizeBytes": len(archive.getvalue()),
                    }
                ).encode(),
            }

            def fake_run(args: list[str], **_: object) -> str:
                if args[1] == "cat":
                    return remote_files[args[2]].decode("utf-8")
                return ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                return remote_files[args[2]]

            destination = Path(root, "restore")
            with self.assertRaisesRegex(SourceIntegrityError, "unsafe checkpoint archive"):
                RcloneStorageAdapter(
                    run_command=fake_run,
                    stream_command=fake_stream,
                ).restore_tree(uri, destination)

            self.assertFalse(Path(root, "escape.txt").exists())

    def test_checkpoint_restore_removes_partial_output_on_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as handle:
                member = tarfile.TarInfo("marker.txt")
                member.size = 5
                handle.addfile(member, io.BytesIO(b"valid"))
            uri = "wukong-gdrive:WukongROM/checkpoints/job/stage.tar"
            metadata = json.dumps(
                {
                    "schemaVersion": 1,
                    "sha256": "0" * 64,
                    "sizeBytes": len(archive.getvalue()),
                }
            )

            def fake_run(args: list[str], **_: object) -> str:
                return metadata if args[1] == "cat" else ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                return archive.getvalue()

            destination = Path(root, "restore")
            with self.assertRaisesRegex(SourceIntegrityError, "checksum mismatch"):
                RcloneStorageAdapter(
                    run_command=fake_run,
                    stream_command=fake_stream,
                ).restore_tree(uri, destination)

            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_name(destination.name + ".restore-partial").exists())

    def test_checkpoint_restore_places_verified_tar_on_destination_volume(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as handle:
                member = tarfile.TarInfo("marker.txt")
                member.size = 2
                handle.addfile(member, io.BytesIO(b"ok"))
            payload = archive.getvalue()
            uri = "wukong-gdrive:WukongROM/checkpoints/job/stage.tar"
            metadata = json.dumps(
                {"sha256": hashlib.sha256(payload).hexdigest(), "sizeBytes": len(payload)}
            )

            def fake_run(args: list[str], **_: object) -> str:
                return metadata if args[1] == "cat" else ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                return archive.getvalue()

            destination = Path(root, "large-volume", "restore")
            real_temporary_directory = tempfile.TemporaryDirectory
            temporary_parents: list[Path] = []

            def recording_temporary_directory(*args: object, **kwargs: object) -> object:
                temporary_parents.append(Path(str(kwargs.get("dir"))).resolve())
                return real_temporary_directory(*args, **kwargs)

            with patch("wukong.adapters.tempfile.TemporaryDirectory", recording_temporary_directory):
                RcloneStorageAdapter(
                    run_command=fake_run,
                    stream_command=fake_stream,
                ).restore_tree(uri, destination)

            self.assertEqual(temporary_parents, [destination.parent.resolve()])
            self.assertEqual((destination / "marker.txt").read_bytes(), b"ok")

    def test_checkpoint_archive_preserves_android_absolute_symlink_without_dereferencing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "workspace")
            source.mkdir()
            link = source / "system" / "d"
            link.parent.mkdir()
            try:
                os.symlink("/sys/kernel/debug", link)
            except OSError:
                self.skipTest("Symbolic links are unavailable on this Windows host")
            remote_files: dict[str, bytes] = {}

            def fake_run(args: list[str], **_: object) -> str:
                operation = args[1]
                if operation == "copyto":
                    remote_files[args[3]] = Path(args[2]).read_bytes()
                elif operation == "moveto":
                    remote_files[args[3]] = remote_files.pop(args[2])
                elif operation == "cat":
                    return remote_files[args[2]].decode("utf-8")
                return ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                if args[1] == "rcat":
                    remote_files[args[2]] = payload or b""
                    return b""
                return remote_files[args[2]]

            storage = RcloneStorageAdapter(run_command=fake_run, stream_command=fake_stream)
            uri = storage.sync_tree(source, "checkpoints/job/stage")
            restored = Path(root, "restored")
            storage.restore_tree(uri, restored)

            self.assertTrue((restored / "system" / "d").is_symlink())
            self.assertEqual(os.readlink(restored / "system" / "d"), "/sys/kernel/debug")

    def test_checkpoint_restore_delays_symlink_creation_until_after_regular_members(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            outside = Path(root, "outside")
            outside.mkdir()
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as handle:
                link = tarfile.TarInfo("pivot")
                link.type = tarfile.SYMTYPE
                link.linkname = str(outside.resolve())
                handle.addfile(link)
                member = tarfile.TarInfo("pivot/escape.txt")
                member.size = 6
                handle.addfile(member, io.BytesIO(b"escape"))
            uri = "wukong-gdrive:WukongROM/checkpoints/job/stage.tar"
            payload = archive.getvalue()
            metadata = json.dumps(
                {"sha256": hashlib.sha256(payload).hexdigest(), "sizeBytes": len(payload)}
            )

            def fake_run(args: list[str], **_: object) -> str:
                return metadata if args[1] == "cat" else ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                return archive.getvalue()

            with self.assertRaisesRegex(SourceIntegrityError, "symbolic-link parent"):
                RcloneStorageAdapter(
                    run_command=fake_run,
                    stream_command=fake_stream,
                ).restore_tree(uri, Path(root, "restore"))

            self.assertFalse((outside / "escape.txt").exists())

    def test_checkpoint_restore_rejects_a_symlink_parent_for_a_later_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            outside = Path(root, "outside")
            outside.mkdir()
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as handle:
                pivot = tarfile.TarInfo("pivot")
                pivot.type = tarfile.SYMTYPE
                pivot.linkname = str(outside.resolve())
                handle.addfile(pivot)
                escaped = tarfile.TarInfo("pivot/escaped")
                escaped.type = tarfile.SYMTYPE
                escaped.linkname = "/target"
                handle.addfile(escaped)
            uri = "wukong-gdrive:WukongROM/checkpoints/job/stage.tar"
            payload = archive.getvalue()
            metadata = json.dumps(
                {"sha256": hashlib.sha256(payload).hexdigest(), "sizeBytes": len(payload)}
            )

            def fake_run(args: list[str], **_: object) -> str:
                return metadata if args[1] == "cat" else ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                return archive.getvalue()

            with self.assertRaisesRegex(SourceIntegrityError, "symbolic-link parent"):
                RcloneStorageAdapter(
                    run_command=fake_run,
                    stream_command=fake_stream,
                ).restore_tree(uri, Path(root, "restore"))

            self.assertFalse((outside / "escaped").exists())

    def test_checkpoint_restore_rejects_hardlink_to_a_symlink_member(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            outside = Path(root, "outside")
            outside.mkdir()
            archive = io.BytesIO()
            with tarfile.open(fileobj=archive, mode="w") as handle:
                pivot = tarfile.TarInfo("pivot")
                pivot.type = tarfile.SYMTYPE
                pivot.linkname = str(outside.resolve())
                handle.addfile(pivot)
                alias = tarfile.TarInfo("alias")
                alias.type = tarfile.LNKTYPE
                alias.linkname = "pivot"
                handle.addfile(alias)
                escaped = tarfile.TarInfo("alias/escape.txt")
                escaped.size = 6
                handle.addfile(escaped, io.BytesIO(b"escape"))
            uri = "wukong-gdrive:WukongROM/checkpoints/job/stage.tar"
            payload = archive.getvalue()
            metadata = json.dumps(
                {"sha256": hashlib.sha256(payload).hexdigest(), "sizeBytes": len(payload)}
            )

            def fake_run(args: list[str], **_: object) -> str:
                return metadata if args[1] == "cat" else ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                return archive.getvalue()

            with self.assertRaisesRegex(SourceIntegrityError, "hardlink target is not a regular"):
                RcloneStorageAdapter(
                    run_command=fake_run,
                    stream_command=fake_stream,
                ).restore_tree(uri, Path(root, "restore"))

            self.assertFalse((outside / "escape.txt").exists())

    def test_checkpoint_metadata_failure_does_not_replace_previous_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "workspace")
            source.mkdir()
            (source / "marker.txt").write_text("new", encoding="utf-8")
            previous_uri = "wukong-gdrive:WukongROM/checkpoints/job/stage/previous.tar"
            remote_files = {previous_uri: b"previous", previous_uri + ".metadata.json": b"{}"}

            def fake_run(args: list[str], **_: object) -> str:
                operation = args[1]
                if operation == "copyto":
                    raise OSError("metadata upload failed")
                if operation == "deletefile":
                    remote_files.pop(args[2], None)
                return ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                remote_files[args[2]] = payload or b""
                return b""

            with patch.object(uuid, "uuid4", return_value=uuid.UUID(int=1)):
                with self.assertRaisesRegex(OSError, "metadata upload failed"):
                    RcloneStorageAdapter(
                        run_command=fake_run,
                        stream_command=fake_stream,
                    ).sync_tree(source, "checkpoints/job/stage")

            self.assertEqual(remote_files, {
                previous_uri: b"previous",
                previous_uri + ".metadata.json": b"{}",
            })

    def test_restore_legacy_directory_checkpoint_uses_rclone_copy(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            calls: list[list[str]] = []

            def fake_run(args: list[str], **_: object) -> str:
                calls.append(args)
                return ""

            uri = "wukong-gdrive:WukongROM/checkpoints/job/legacy-stage"
            destination = Path(root, "restore")
            result = RcloneStorageAdapter(run_command=fake_run).restore_tree(uri, destination)

            self.assertEqual(result, destination.resolve())
            self.assertEqual(calls[0][1:4], ["copy", uri, str(destination.resolve())])

    def test_checkpoint_archive_round_trip_preserves_safe_hardlinks(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "workspace")
            source.mkdir()
            original = source / "cached.img"
            original.write_bytes(b"partition-cache")
            os.link(original, source / "system.img")
            remote_files: dict[str, bytes] = {}

            def fake_run(args: list[str], **_: object) -> str:
                if args[1] == "copyto":
                    remote_files[args[3]] = Path(args[2]).read_bytes()
                elif args[1] == "moveto":
                    remote_files[args[3]] = remote_files.pop(args[2])
                elif args[1] == "cat":
                    return remote_files[args[2]].decode("utf-8")
                return ""

            def fake_stream(args: list[str], payload: bytes | None = None) -> bytes:
                if args[1] == "rcat":
                    remote_files[args[2]] = payload or b""
                    return b""
                return remote_files[args[2]]

            storage = RcloneStorageAdapter(run_command=fake_run, stream_command=fake_stream)
            uri = storage.sync_tree(source, "checkpoints/job/hardlinks")
            restored = Path(root, "restored")
            storage.restore_tree(uri, restored)

            self.assertEqual((restored / "cached.img").read_bytes(), b"partition-cache")
            self.assertEqual((restored / "system.img").read_bytes(), b"partition-cache")


class OrchestratorContractTests(unittest.TestCase):
    def _recipe(self, root: str, *, target: str = "local-windows") -> BuildRecipe:
        source = Path(root, "source.zip")
        source.write_bytes(b"rom")
        return BuildRecipe.from_dict(
            {
                "schemaVersion": 1,
                "task": "build",
                "device": "CPH2725",
                "source": {"kind": "local", "uri": source.as_posix(), "sizeBytes": 1},
                "execution": {"target": target, "estimatedWorkspaceBytes": 1024},
            }
        )

    def test_submit_and_inspect_are_owner_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "jobs"))
            owner = Identity("telegram", "100", "user")
            stranger = Identity("telegram", "200", "user")

            job = orchestrator.submit(self._recipe(root), owner)

            self.assertEqual(job.status, JobStatus.QUEUED)
            self.assertEqual(orchestrator.inspect(job.job_id, owner).job_id, job.job_id)
            with self.assertRaisesRegex(OrchestrationError, "not found"):
                orchestrator.inspect(job.job_id, stranger)

    def test_admin_can_cancel_any_job_and_user_cannot(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
            )
            owner = Identity("telegram", "100", "user")
            job = orchestrator.submit(self._recipe(root), owner)
            with self.assertRaisesRegex(OrchestrationError, "not found"):
                orchestrator.cancel(job.job_id, Identity("telegram", "200", "user"))
            cancelled = orchestrator.cancel(job.job_id, Identity("telegram", "1", "admin"))
            self.assertEqual(cancelled.status, JobStatus.CANCELLED)

    def test_resume_creates_new_job_with_checkpoint_reference(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
            )
            owner = Identity("windows", "local", "user")
            job = orchestrator.submit(self._recipe(root), owner)
            orchestrator.store.update(job.job_id, status=JobStatus.FAILED, checkpoint="stage://repack")

            resumed = orchestrator.resume(job.job_id, owner)

            self.assertNotEqual(resumed.job_id, job.job_id)
            self.assertEqual(resumed.checkpoint, "stage://repack")

    def test_expired_checkpoint_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
            )
            owner = Identity("windows", "local", "user")
            job = orchestrator.submit(self._recipe(root), owner)
            expired = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            orchestrator.store.update(
                job.job_id,
                status=JobStatus.FAILED,
                checkpoint="stage://repack",
                checkpoint_at=expired,
            )
            with self.assertRaisesRegex(OrchestrationError, "expired"):
                orchestrator.resume(job.job_id, owner)

    def test_telegram_user_cannot_submit_arbitrary_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(),
                workspace_root=Path(root, "jobs"),
                access_validator=validate_recipe_access,
            )
            with self.assertRaisesRegex(RecipeValidationError, "Telegram users"):
                orchestrator.submit(self._recipe(root), Identity("telegram", "100", "user"))


class CloudSyncContractTests(unittest.TestCase):
    def test_pull_imports_remote_events_once(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "workspace"))
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "CPH2725",
                    "source": {"kind": "local", "uri": str(source)},
                    "execution": {"target": "local-windows"},
                }
            )
            job = orchestrator.submit(recipe, Identity("windows", "local", "admin"))
            remote_manifest = job.to_dict() | {"status": "running", "stage": "repack", "progress": 0.5}
            remote_events = [{"sequence": 5, "jobId": job.job_id, "timestamp": "now", "type": "state", "stage": "repack"}]

            def fake_run(args: list[str], **_: object) -> str:
                destination = Path(args[3])
                if args[2].endswith("manifest.json"):
                    destination.write_text(json.dumps(remote_manifest), encoding="utf-8")
                else:
                    destination.write_text("\n".join(json.dumps(item) for item in remote_events), encoding="utf-8")
                return ""

            sync = CloudJobSync(store, RcloneStorageAdapter(run_command=fake_run))
            self.assertEqual(sync.pull(job.job_id).stage, "repack")
            sync.pull(job.job_id)
            imported = [event for event in store.events(job.job_id) if event.payload.get("remoteSequence") == 5]
            self.assertEqual(len(imported), 1)

    def test_pull_imports_resume_checkpoint_before_actions_execute(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "workspace"))
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "CPH2725",
                    "source": {"kind": "local", "uri": str(source)},
                    "execution": {"target": "local-windows"},
                }
            )
            job = orchestrator.submit(recipe, Identity("actions", "100", "user"))
            remote_manifest = job.to_dict() | {
                "checkpoint": "wukong-gdrive:WukongROM/checkpoints/old/extract.tar",
                "checkpoint_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }

            def fake_run(args: list[str], **_: object) -> str:
                destination = Path(args[3])
                if args[2].endswith("manifest.json"):
                    destination.write_text(json.dumps(remote_manifest), encoding="utf-8")
                else:
                    destination.write_text("", encoding="utf-8")
                return ""

            pulled = CloudJobSync(store, RcloneStorageAdapter(run_command=fake_run)).pull_checkpoint(job.job_id)

            self.assertIsNotNone(pulled)
            self.assertEqual(pulled.checkpoint, remote_manifest["checkpoint"])
            self.assertEqual(store.get(job.job_id).checkpoint_at, remote_manifest["checkpoint_at"])
            self.assertEqual(pulled.status, JobStatus.QUEUED)
            self.assertIsNone(pulled.finished_at)

    def test_pull_checkpoint_rejects_a_manifest_for_another_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "workspace"))
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "CPH2725",
                    "source": {"kind": "local", "uri": str(source)},
                    "execution": {"target": "local-windows"},
                }
            )
            job = orchestrator.submit(recipe, Identity("actions", "100", "user"))
            remote_manifest = job.to_dict() | {
                "recipe_digest": "0" * 64,
                "checkpoint": "wukong-gdrive:WukongROM/checkpoints/other/extract.tar",
            }

            def fake_run(args: list[str], **_: object) -> str:
                destination = Path(args[3])
                destination.write_text(json.dumps(remote_manifest), encoding="utf-8")
                return ""

            pulled = CloudJobSync(store, RcloneStorageAdapter(run_command=fake_run)).pull_checkpoint(job.job_id)

            self.assertIsNotNone(pulled)
            self.assertIsNone(pulled.checkpoint)

    def test_pull_checkpoint_rejects_expired_or_non_cloud_references(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(store=store, workspace_root=Path(root, "workspace"))
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "CPH2725",
                    "source": {"kind": "local", "uri": str(source)},
                    "execution": {"target": "local-windows"},
                }
            )
            job = orchestrator.submit(recipe, Identity("actions", "100", "user"))
            remote_manifest = job.to_dict() | {
                "checkpoint": "local:C:/outside/workspace",
                "checkpoint_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
            }

            def fake_run(args: list[str], **_: object) -> str:
                Path(args[3]).write_text(json.dumps(remote_manifest), encoding="utf-8")
                return ""

            pulled = CloudJobSync(store, RcloneStorageAdapter(run_command=fake_run)).pull_checkpoint(job.job_id)

            self.assertIsNotNone(pulled)
            self.assertIsNone(pulled.checkpoint)


class ControlAdapterContractTests(unittest.TestCase):
    def test_cli_validate_returns_same_recipe_digest_and_runner(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recipe_path = Path(root, "recipe.json")
            recipe_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "task": "source_mirror",
                        "device": "CPH2725",
                        "source": {
                            "kind": "https",
                            "uri": "https://downloads.example/rom.zip",
                            "sizeBytes": 100,
                        },
                        "execution": {"target": "github-auto"},
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                status = cli_main(["validate", "--recipe", str(recipe_path)])

            result = json.loads(output.getvalue())
            recipe = BuildRecipe.from_dict(json.loads(recipe_path.read_text(encoding="utf-8")))
            self.assertEqual(status, 0)
            self.assertEqual(result["recipeDigest"], recipe.digest)
            self.assertEqual(result["runner"]["runner"], "ubuntu-24.04")

    def test_github_dispatch_uses_recipe_ref_and_never_serializes_token(self) -> None:
        requests: list[tuple[str, str, dict[str, object] | None]] = []

        def transport(method: str, url: str, payload: dict[str, object] | None = None) -> object:
            requests.append((method, url, payload))
            return {}

        adapter = GitHubActionsAdapter(
            owner="luukhanh24",
            repository="Wukong-ROM-Studio-Hybrid",
            token="secret-token",
            transport=transport,
        )
        adapter.dispatch("wukong-build.yml", recipe_ref="wukong-gdrive:WukongROM/recipes/abc.json")

        serialized = json.dumps(requests)
        self.assertNotIn("secret-token", serialized)
        self.assertEqual(requests[0][2]["inputs"]["recipe_ref"], "wukong-gdrive:WukongROM/recipes/abc.json")

    def test_github_runner_inventory_requires_qualified_online_runner(self) -> None:
        def transport(method: str, url: str, payload: dict[str, object] | None = None) -> object:
            return {
                "runners": [
                    {"status": "online", "busy": False, "labels": [{"name": value} for value in ["self-hosted", "linux", "x64", "wukong-rom"]]}
                ]
            }

        inventory = GitHubActionsAdapter("owner", "repo", "token", transport=transport).runner_inventory()
        self.assertTrue(inventory.self_hosted_online)

    def test_github_api_error_redacts_token(self) -> None:
        adapter = GitHubActionsAdapter(
            "owner",
            "repo",
            "top-secret",
            transport=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("top-secret failed")),
        )
        with self.assertRaisesRegex(GitHubApiError, "redacted"):
            adapter.cancel(123)

    def test_cloud_recipe_fetch_is_limited_to_private_recipe_root(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(
                [
                    os.sys.executable,
                    "tools/fetch_recipe.py",
                    "wukong-gdrive:WukongROM/sources/recipe.json",
                    "--output",
                    str(Path(root, "recipe.json")),
                ],
                cwd=Path(__file__).resolve().parent.parent,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("WukongROM/recipes", result.stderr)

    def test_workflow_recipe_is_forced_to_github_auto(self) -> None:
        repository = Path(__file__).resolve().parent.parent
        scratch = repository / ".tmp"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as root:
            recipe_path = Path(root, "local.json")
            output = Path(root, "out.json")
            recipe_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "task": "source_mirror",
                        "device": "CPH2725",
                        "source": {"kind": "https", "uri": "https://downloads.example/rom.zip"},
                        "execution": {"target": "local-windows"},
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    os.sys.executable,
                    "tools/fetch_recipe.py",
                    recipe_path.relative_to(repository).as_posix(),
                    "--output",
                    str(output),
                    "--force-github-auto",
                ],
                cwd=repository,
                check=True,
            )
            self.assertEqual(json.loads(output.read_text())["execution"]["target"], "github-auto")

    def test_workflow_surfaces_router_validation_errors(self) -> None:
        repository = Path(__file__).resolve().parent.parent
        workflow = (repository / ".github" / "workflows" / "wukong-build.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("if ! python wukong_cli.py validate", workflow)
        self.assertIn("cat .wkstudio/route.json", workflow)

    def test_hybrid_workflow_runs_tools_as_importable_modules(self) -> None:
        repository = Path(__file__).resolve().parent.parent
        sources = [
            repository / ".github" / "workflows" / "wukong-build.yml",
            repository / ".github" / "actions" / "run-hybrid" / "action.yml",
        ]

        for source in sources:
            workflow = source.read_text(encoding="utf-8")
            self.assertNotRegex(workflow, r"python3? tools/[A-Za-z0-9_]+\.py")


class TelegramAccessContractTests(unittest.TestCase):
    def test_admin_approval_and_revocation_persist_without_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root, "telegram-access.json")
            access = TelegramAccessStore(path, admin_ids={1})
            self.assertEqual(access.identity(1).role, "admin")
            self.assertIsNone(access.identity(42))

            access.approve(42, actor=access.identity(1))
            self.assertEqual(TelegramAccessStore(path, admin_ids={1}).identity(42).role, "user")
            access.revoke(42, actor=access.identity(1))
            self.assertIsNone(access.identity(42))
            self.assertNotIn("token", path.read_text(encoding="utf-8").casefold())

    def test_non_admin_cannot_manage_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            access = TelegramAccessStore(Path(root, "access.json"), admin_ids={1})
            with self.assertRaisesRegex(PermissionError, "Admin"):
                access.approve(42, actor=Identity("telegram", "2", "user"))

    def test_bot_lists_only_requesting_users_jobs_and_cloud_library(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            access = TelegramAccessStore(Path(root, "access.json"), admin_ids={1})
            access.approve(42, actor=access.identity(1))
            store = InMemoryJobStore()
            orchestrator = HybridOrchestrator(
                store=store,
                workspace_root=Path(root, "jobs"),
                access_validator=lambda _recipe, _identity: None,
            )
            source = Path(root, "rom.zip")
            source.write_bytes(b"rom")
            recipe = BuildRecipe.from_dict(
                {"schemaVersion": 1, "task": "source_mirror", "device": "CPH2725", "source": {"kind": "local", "uri": str(source)}, "execution": {"target": "local-windows"}}
            )
            own = orchestrator.submit(recipe, Identity("telegram", "42", "user"))
            other = orchestrator.submit(recipe, Identity("telegram", "99", "user"))
            controller = TelegramBotController(
                access=access,
                orchestrator=orchestrator,
                catalog_provider=lambda: {},
                diagnostics_provider=lambda: {},
                cloud_provider=lambda category: {"category": category, "entries": ["ok"]},
            )
            jobs = controller.handle(42, "/jobs")
            self.assertIn(own.job_id, jobs)
            self.assertNotIn(other.job_id, jobs)
            self.assertIn('"category": "sources"', controller.handle(42, "/cloud sources"))

    def test_regular_user_cannot_clear_shared_cache(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            access = TelegramAccessStore(Path(root, "access.json"), admin_ids={1})
            access.approve(42, actor=access.identity(1))
            controller = TelegramBotController(
                access=access,
                orchestrator=HybridOrchestrator(
                    store=InMemoryJobStore(), workspace_root=Path(root, "jobs")
                ),
                catalog_provider=lambda: {},
                diagnostics_provider=lambda: {},
                cache_clearer=lambda: {"cleared": True},
            )
            self.assertIn("Admin access", controller.handle(42, "/cache_clear"))


class ContentPackContractTests(unittest.TestCase):
    def test_content_index_groups_mod_versions_and_hashes_every_file(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "MOD" / "ColorOS_16.0.8" / "Gallery").mkdir(parents=True)
            (content / "MOD" / "ColorOS_16.0.8" / "Gallery" / "app.apk").write_bytes(b"apk")
            (content / "TWRP").mkdir()
            (content / "TWRP" / "recovery.img").write_bytes(b"img")

            index = build_content_index(content, remote="wukong-gdrive:WukongROM/content-packs")

            self.assertEqual([pack["id"] for pack in index["packs"]], ["MOD/ColorOS_16.0.8", "TWRP/v1"])
            self.assertEqual(index["packs"][0]["files"][0]["sha256"], "dd37c2d7274f7ea982cb83390c36918fee9ce8889073c44b68cdc00bdb8c3e04")

    def test_install_downloads_to_staging_and_rejects_tampered_pack(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            target = Path(root, "Content")
            index = {
                "schemaVersion": 1,
                "packs": [
                    {
                        "id": "TWRP/v1",
                        "target": "TWRP",
                        "remote": "wukong-gdrive:WukongROM/content-packs/TWRP/v1",
                        "sizeBytes": 3,
                        "files": [
                            {
                                "path": "recovery.img",
                                "sizeBytes": 3,
                                "sha256": "b99b21156d9c07e16d0e5d6704601c8fda0f74bb2bfc4e919e36a52d1f2d3aa4",
                            }
                        ],
                    }
                ],
            }

            def fake_run(args: list[str], **_: object) -> str:
                destination = Path(args[3])
                destination.mkdir(parents=True, exist_ok=True)
                (destination / "recovery.img").write_bytes(b"bad")
                return ""

            manager = ContentPackManager(target, run_command=fake_run)
            with self.assertRaisesRegex(SourceIntegrityError, "content-pack"):
                manager.install(index, "TWRP/v1")
            self.assertFalse((target / "TWRP" / "recovery.img").exists())

    def test_upload_downloads_each_pack_and_verifies_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            content = Path(root, "content")
            (content / "TWRP").mkdir(parents=True)
            (content / "TWRP" / "recovery.img").write_bytes(b"img")
            index = build_content_index(content, remote="wukong-gdrive:WukongROM/content-packs")

            def fake_run(args: list[str], **_: object) -> str:
                if args[1] == "copy" and args[2].startswith("wukong-gdrive:"):
                    destination = Path(args[3])
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination / "recovery.img").write_bytes(b"img")
                return ""

            upload_content_packs(content, index, run_command=fake_run)


if __name__ == "__main__":
    unittest.main()
