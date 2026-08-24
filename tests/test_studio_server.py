import json
import io
import os
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import studio_core
import studio_server


class StudioServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".wkstudio"
        self.jobs = self.runtime / "jobs"
        self.output = self.root / "ROM_BUILD_DONE"
        self.device_template = self.root / "devices_sizes.json"
        self.device_catalog = self.runtime / "devices_sizes.json"
        self.device_backups = self.root / "Backups" / "devices"
        self.device_template.write_text(
            json.dumps(
                [
                    {
                        "product_name": "PKG110",
                        "name": "OnePlus Ace 5",
                        "soc": "86xx",
                        "SuperSize": 14578294784,
                        "GroupSize": 14574100480,
                        "Partitions": ["my_company", "my_preload"],
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.patches = [
            mock.patch.dict(
                os.environ,
                {
                    "WUKONG_RCLONE_CONFIG": "",
                    "WUKONG_RCLONE_CONFIG_CONTENT_B64": "",
                },
            ),
            mock.patch.object(studio_server, "ROOT_DIR", self.root),
            mock.patch.object(studio_server, "CONTENT_ROOT", self.root),
            mock.patch.object(studio_server, "RUNTIME_DIR", self.runtime),
            mock.patch.object(studio_server, "JOBS_DIR", self.jobs),
            mock.patch.object(studio_server, "SETTINGS_PATH", self.runtime / "settings.json"),
            mock.patch.object(studio_server, "DATABASE_PATH", self.runtime / "studio.db"),
            mock.patch.object(studio_server, "CONTENT_PACKS_PATH", self.runtime / "content-packs.json"),
            mock.patch.object(studio_server, "ROM_BUILD_DONE", self.output),
            mock.patch.object(studio_core, "ROM_BUILD_DONE", self.output),
            mock.patch.object(studio_core, "DEVICE_CATALOG_TEMPLATE_PATH", self.device_template),
            mock.patch.object(studio_core, "DEVICE_CATALOG_PATH", self.device_catalog),
            mock.patch.object(studio_core, "DEVICE_CATALOG_BACKUP_DIR", self.device_backups),
            mock.patch.object(studio_core, "STAGE_CACHE_ROOT", self.runtime / "Cache" / "Payload"),
        ]
        for patch in self.patches:
            patch.start()
        studio_server.init_database()
        studio_server.save_settings({"roots": [str(self.root)]})
        with zipfile.ZipFile(self.root / "fixture.zip", "w") as archive:
            archive.writestr(
                "META-INF/com/android/metadata",
                "oplus_product_name=PKG110\noplus_version_name=fixture\n",
            )
            archive.writestr("payload.bin", b"fixture")
        self.app = studio_server.create_app(start_queue=False)
        self.client = self.app.test_client()
        self.headers = {"X-Studio-Token": studio_server.SESSION_TOKEN}

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.temp.cleanup()

    def test_process_log_writer_batches_text_but_flushes_events_immediately(self):
        class CountingBuffer(io.StringIO):
            def __init__(self):
                super().__init__()
                self.flush_count = 0

            def flush(self):
                self.flush_count += 1
                super().flush()

        output = CountingBuffer()
        writer = studio_server._ProcessLogWriter(
            output,
            flush_bytes=32,
            flush_interval=3600,
        )

        writer.write("normal line\n")
        self.assertEqual(output.flush_count, 0)
        writer.write(f"{studio_server.EVENT_PREFIX}{{}}\n")
        self.assertEqual(output.flush_count, 1)
        writer.write("x" * 40)
        self.assertEqual(output.flush_count, 2)

    def test_api_requires_token_and_local_origin(self):
        self.assertEqual(self.client.get("/api/bootstrap").status_code, 403)
        self.assertEqual(
            self.client.get(
                "/api/bootstrap",
                headers=self.headers | {"Origin": "https://example.com"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/bootstrap",
                headers=self.headers | {"Origin": "http://localhost:@example.com"},
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/bootstrap", headers=self.headers).status_code, 200)

    def test_hybrid_v1_recipe_uses_server_identity_and_owner_scoping(self):
        recipe = {
            "schemaVersion": 1,
            "task": "source_mirror",
            "device": "PKG110",
            "source": {"kind": "local", "uri": str(self.root / "fixture.zip"), "sizeBytes": 1},
            "execution": {"target": "local-windows", "estimatedWorkspaceBytes": 1024},
            "requester": "attacker",
            "role": "user",
        }
        created = self.client.post("/api/v1/jobs", headers=self.headers, json=recipe)
        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        job = created.get_json()
        self.assertEqual(job["owner"], {"channel": "windows", "subject": "local", "role": "admin"})

        inspected = self.client.get(f"/api/v1/jobs/{job['job_id']}", headers=self.headers)
        self.assertEqual(inspected.status_code, 200)
        cancelled = self.client.post(f"/api/v1/jobs/{job['job_id']}/cancel", headers=self.headers)
        self.assertEqual(cancelled.get_json()["status"], "cancelled")

    def test_hybrid_v1_rejects_secret_bearing_recipe(self):
        response = self.client.post(
            "/api/v1/recipes/validate",
            headers=self.headers,
            json={
                "schemaVersion": 1,
                "task": "source_mirror",
                "device": "PKG110",
                "source": {"kind": "local", "uri": str(self.root / "fixture.zip")},
                "accessToken": "nope",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("secrets", response.get_json()["error"])

    def test_hybrid_v1_probes_remote_rom_without_exposing_signed_url(self):
        safe_result = SimpleNamespace(
            to_dict=lambda: {
                "provider": "oplus",
                "filename": "PKG110.zip",
                "device": "OP5D2BL1",
                "version": "PKG110_16.0.8.300(CN01)",
                "sizeBytes": 8645349608,
                "deepInspected": True,
            }
        )
        with mock.patch.object(studio_server, "probe_http_source", return_value=safe_result) as probe:
            response = self.client.post(
                "/api/v1/sources/probe",
                headers=self.headers,
                json={"uri": "https://component-ota-cn.allawntech.com/downloadCheck?c=abc"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["provider"], "oplus")
        self.assertNotIn("resolvedUrl", response.get_json())
        probe.assert_called_once()

    def test_hybrid_v1_probe_requires_url(self):
        response = self.client.post(
            "/api/v1/sources/probe",
            headers=self.headers,
            json={"uri": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("required", response.get_json()["error"])

    def test_hybrid_v1_lists_catalog_jobs_diagnostics_cache_and_cloud(self):
        recipe = {
            "schemaVersion": 1,
            "task": "source_mirror",
            "device": "PKG110",
            "source": {"kind": "local", "uri": str(self.root / "fixture.zip")},
            "execution": {"target": "local-windows", "estimatedWorkspaceBytes": 1024},
        }
        self.assertEqual(self.client.post("/api/v1/jobs", headers=self.headers, json=recipe).status_code, 201)
        for endpoint in ("/api/v1/jobs", "/api/v1/catalog", "/api/v1/diagnostics", "/api/v1/cache"):
            self.assertEqual(self.client.get(endpoint, headers=self.headers).status_code, 200, endpoint)
        cloud = self.client.get("/api/v1/cloud/library?category=sources", headers=self.headers)
        self.assertEqual(cloud.status_code, 200)
        self.assertFalse(cloud.get_json()["available"])

    def test_hybrid_v1_rejects_local_source_outside_configured_roots(self):
        outside = Path(self.temp.name).parent / "outside-wukong-rom.zip"
        outside.write_bytes(b"rom")
        try:
            response = self.client.post(
                "/api/v1/recipes/validate",
                headers=self.headers,
                json={
                    "schemaVersion": 1,
                    "task": "source_mirror",
                    "device": "PKG110",
                    "source": {"kind": "local", "uri": str(outside)},
                    "execution": {"target": "local-windows"},
                },
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn("outside configured roots", response.get_json()["error"])
        finally:
            outside.unlink(missing_ok=True)

    def test_rom_renamer_api_previews_and_applies_selected_zip(self):
        source = self.root / "downloaded-rom.zip"
        with zipfile.ZipFile(source, "w") as archive:
            archive.writestr(
                "META-INF/com/android/metadata",
                "oplus_version_name=PKG110_16.0.8.300(CN01)\n",
            )

        self.assertEqual(
            self.client.post(
                "/api/tools/rom-renamer/preview",
                json={"romPath": str(source)},
            ).status_code,
            403,
        )
        preview_response = self.client.post(
            "/api/tools/rom-renamer/preview",
            headers=self.headers,
            json={"romPath": str(source)},
        )
        self.assertEqual(preview_response.status_code, 200)
        preview = preview_response.get_json()
        self.assertTrue(preview["canApply"])
        self.assertEqual(preview["entries"][0]["sourceName"], "downloaded-rom.zip")
        self.assertEqual(
            preview["entries"][0]["targetName"],
            "PKG110_16.0.8.300(CN01).zip",
        )

        applied_response = self.client.post(
            "/api/tools/rom-renamer/apply",
            headers=self.headers,
            json={"entries": preview["entries"]},
        )
        self.assertEqual(applied_response.status_code, 200)
        self.assertEqual(applied_response.get_json()["renamed"], 1)
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "PKG110_16.0.8.300(CN01).zip").is_file())

    def test_rom_renamer_folder_preview_is_sorted_and_apply_rejects_outside_root(self):
        folder = self.root / "roms"
        folder.mkdir()
        for filename, version in (("b.zip", "version-b"), ("a.zip", "version-a")):
            with zipfile.ZipFile(folder / filename, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    f"oplus_version_name={version}\n",
                )

        preview_response = self.client.post(
            "/api/tools/rom-renamer/preview",
            headers=self.headers,
            json={"folderPath": str(folder)},
        )
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(
            [entry["sourceName"] for entry in preview_response.get_json()["entries"]],
            ["a.zip", "b.zip"],
        )

        with tempfile.TemporaryDirectory() as outside_temp:
            outside = Path(outside_temp) / "outside.zip"
            with zipfile.ZipFile(outside, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_version_name=outside-version\n",
                )
            rejected = self.client.post(
                "/api/tools/rom-renamer/apply",
                headers=self.headers,
                json={
                    "entries": [
                        {
                            "sourcePath": str(outside),
                            "targetPath": str(outside.with_name("outside-version.zip")),
                        }
                    ]
                },
            )
        self.assertEqual(rejected.status_code, 400)

    def test_bootstrap_exposes_lite_mod_defaults_and_debloat_paths(self):
        payload = self.client.get("/api/bootstrap", headers=self.headers).get_json()
        self.assertIn("defaultDebloatPaths", payload)
        self.assertIn("ColorOS_16.0.7", payload["modVersions"])
        self.assertIn("ColorOS_16.0.8", payload["modVersions"])
        self.assertIn("ColorOS_16.0.8", payload["modsByVersion"])
        self.assertIn("ColorOS_16.0.8", payload["presetDefaultsByVersion"])
        self.assertEqual(payload["presetDefaults"]["lite"], studio_core.LITE_DEFAULT_MODS)
        self.assertIn("WK_Installer", payload["presetDefaults"]["lite"])
        self.assertIn("WK_Manager", payload["presetDefaults"]["resume"])
        self.assertIn("Fake_lock", payload["presetDefaults"]["resume"])
        self.assertNotIn("Gallery_mod_CN", payload["presetDefaults"]["resume"])
        self.assertNotIn("Gallery_mod_CN", payload["presetDefaults"]["both"])
        self.assertTrue(any(mod["name"] == "Fix_noti" for mod in payload["mods"]))
        self.assertNotIn("framework_patch", [step["id"] for step in payload["steps"]])
        self.assertNotIn("region_patch", [step["id"] for step in payload["steps"]])
        self.assertIn("patch_vendor_boot", [step["id"] for step in payload["steps"]])
        self.assertNotIn("frameworkAssets", payload["diagnostics"])

    def test_corrupt_settings_are_quarantined_before_defaults_load(self):
        studio_server.SETTINGS_PATH.write_text("{broken", encoding="utf-8")

        settings = studio_server.load_settings()

        self.assertEqual(settings["locale"], "vi")
        self.assertFalse(studio_server.SETTINGS_PATH.exists())
        self.assertEqual(
            len(list(studio_server.SETTINGS_PATH.parent.glob("settings.json.corrupt-*"))),
            1,
        )

    def test_device_catalog_crud_persists_override_and_backups(self):
        initial = self.client.get("/api/devices", headers=self.headers)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.get_json()["devices"][0]["product_name"], "PKG110")
        self.assertEqual(Path(initial.get_json()["storagePath"]), self.device_catalog)

        created = self.client.post(
            "/api/devices",
            headers=self.headers,
            json={
                "product_name": "PJZ110",
                "name": "OnePlus 13",
                "soc": "87xx",
                "superSize": 15354134528,
                "groupSize": 15349940224,
                "partitions": ["my_company", "system_dlkm_oki"],
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertTrue(self.device_catalog.is_file())
        self.assertEqual(len(json.loads(self.device_template.read_text(encoding="utf-8"))), 1)
        saved = json.loads(self.device_catalog.read_text(encoding="utf-8"))
        self.assertEqual([device["product_name"] for device in saved], ["PKG110", "PJZ110"])
        self.assertEqual(saved[1]["SuperSize"], 15354134528)
        self.assertTrue(any(self.device_backups.glob("devices_sizes-*.json")))

        updated = self.client.put(
            "/api/devices/PJZ110",
            headers=self.headers,
            json={
                "product_name": "PJZ110_GLOBAL",
                "name": "OnePlus 13 Global",
                "soc": "87xx",
                "SuperSize": 15354134528,
                "GroupSize": 15349940224,
                "Partitions": ["my_company"],
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertIn(
            "PJZ110_GLOBAL",
            [device["product_name"] for device in updated.get_json()["devices"]],
        )

        deleted = self.client.delete("/api/devices/PJZ110_GLOBAL", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(
            [device["product_name"] for device in deleted.get_json()["devices"]],
            ["PKG110"],
        )

    def test_device_catalog_rejects_duplicate_and_unsafe_sizes(self):
        duplicate = self.client.post(
            "/api/devices",
            headers=self.headers,
            json={
                "product_name": "pkg110",
                "name": "Duplicate",
                "soc": "86xx",
                "SuperSize": 14578294784,
                "GroupSize": 14574100480,
                "Partitions": [],
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        invalid = self.client.post(
            "/api/devices",
            headers=self.headers,
            json={
                "product_name": "TEST110",
                "name": "Invalid layout",
                "soc": "test",
                "SuperSize": 4097,
                "GroupSize": 8192,
                "Partitions": ["my_company"],
            },
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("4096", invalid.get_json()["error"])

    def test_layout_analyzer_authorizes_source_and_uses_unsaved_device_form(self):
        layout = self.root / "layout.json"
        layout.write_text(
            json.dumps(
                {
                    "block_devices": [
                        {"name": "super", "size": 14578294784, "first_sector": 2048}
                    ],
                    "group_table": [
                        {"name": "qti_dynamic_partitions_a", "maximum_size": 14574100480}
                    ],
                    "partition_table": [
                        {
                            "name": "my_company_a",
                            "group_name": "qti_dynamic_partitions_a",
                            "size": 1073741824,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        authorized = self.client.post(
            "/api/fs/authorize-layout-source",
            headers=self.headers,
            json={"path": str(layout)},
        )
        self.assertEqual(authorized.status_code, 200)
        response = self.client.post(
            "/api/layout/analyze",
            headers=self.headers,
            json={
                "sourcePath": str(layout),
                "device": {
                    "product_name": "PKG110",
                    "name": "OnePlus Ace 5 edited",
                    "soc": "86xx",
                    "SuperSize": 14578294784,
                    "GroupSize": 14574100480,
                    "Partitions": ["my_company", "my_preload"],
                },
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["configured"]["name"], "OnePlus Ace 5 edited")
        self.assertEqual(payload["comparison"]["missingConfiguredPartitions"], ["my_preload"])

    def test_settings_persist_custom_debloat_paths(self):
        response = self.client.post(
            "/api/settings",
            headers=self.headers,
            json={"roots": [str(self.root)], "debloatPaths": [r"my_stock\app\Browser"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["debloatPaths"], [r"my_stock\app\Browser"])
        payload = self.client.get("/api/bootstrap", headers=self.headers).get_json()
        self.assertEqual(payload["settings"]["debloatPaths"], [r"my_stock\app\Browser"])

    def test_settings_and_api_manage_stage_cache(self):
        response = self.client.post(
            "/api/settings",
            headers=self.headers,
            json={
                "roots": [str(self.root)],
                "stageCacheEnabled": False,
                "stageCacheMaxGb": 12,
                "theme": "dark",
                "locale": "en",
                "zipValidationMode": "deep",
            },
        )
        self.assertEqual(response.status_code, 200)
        settings = response.get_json()
        self.assertFalse(settings["stageCacheEnabled"])
        self.assertEqual(settings["stageCacheMaxGb"], 12)
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["locale"], "en")
        self.assertEqual(settings["zipValidationMode"], "deep")

        with mock.patch.object(studio_core, "RUNTIME_DIR", self.runtime):
            status = self.client.get("/api/cache", headers=self.headers)
            self.assertEqual(status.status_code, 200)
            self.assertFalse(status.get_json()["enabled"])
            cleared = self.client.post("/api/cache/clear", headers=self.headers)
            self.assertEqual(cleared.status_code, 200)
            self.assertEqual(cleared.get_json()["entryCount"], 0)

    def test_zip_validation_mode_defaults_and_normalizes_to_fast(self):
        self.assertEqual(studio_server.load_settings()["zipValidationMode"], "fast")

        response = self.client.post(
            "/api/settings",
            headers=self.headers,
            json={"zipValidationMode": "unsupported"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["zipValidationMode"], "fast")

    def test_settings_manage_studio_versions(self):
        with mock.patch.object(studio_server, "list_mod_versions", return_value=["ColorOS_16.0.7", "ColorOS_16.0.8"]):
            response = self.client.post(
                "/api/settings",
                headers=self.headers,
                json={
                    "studioVersions": {
                        "ColorOS_16.0.7": "Stable 8",
                        "ColorOS_16.0.8": "../../invalid",
                    }
                },
            )
        self.assertEqual(response.status_code, 200)
        settings = response.get_json()
        self.assertEqual(settings["studioVersions"]["ColorOS_16.0.7"], "Stable 8")
        self.assertEqual(settings["studioVersions"]["ColorOS_16.0.8"], "V4.1")

    def test_bootstrap_reports_installed_content_pack_health(self):
        target = self.root / "MOD" / "ColorOS_Test"
        target.mkdir(parents=True)
        studio_server.CONTENT_PACKS_PATH.write_text(
            json.dumps(
                [
                    {
                        "id": "coloros-test",
                        "displayName": "ColorOS Test Pack",
                        "version": "1.0.0",
                        "target": "MOD/ColorOS_Test",
                    }
                ]
            ),
            encoding="utf-8",
        )
        payload = self.client.get("/api/bootstrap", headers=self.headers).get_json()
        self.assertEqual(payload["contentPacks"][0]["id"], "coloros-test")
        self.assertTrue(payload["contentPacks"][0]["healthy"])

    def test_file_browser_rejects_traversal(self):
        outside = self.root.parent.resolve()
        response = self.client.get(
            "/api/fs/list",
            query_string={"path": str(outside)},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("outside", response.get_json()["error"])

    def test_authorize_rom_path_adds_external_parent_to_allowlist(self):
        with tempfile.TemporaryDirectory() as external:
            rom = Path(external) / "external.zip"
            rom.write_bytes(b"fixture")
            response = self.client.post(
                "/api/fs/authorize-rom",
                headers=self.headers,
                json={"romPath": str(rom)},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Path(response.get_json()["path"]), rom.resolve())
            self.assertIn(str(Path(external).resolve()), studio_server.load_settings()["roots"])

    def test_native_picker_endpoint_returns_selected_absolute_path(self):
        rom = self.root / "selected.zip"
        rom.write_bytes(b"fixture")
        with mock.patch.object(studio_server, "_pick_rom_file", return_value=rom.resolve()):
            response = self.client.post("/api/fs/pick-rom", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Path(response.get_json()["path"]), rom.resolve())

    def test_folder_picker_returns_zip_files_in_order(self):
        folder = self.root / "folder-roms"
        folder.mkdir()
        (folder / "b.zip").write_bytes(b"fixture")
        (folder / "a.zip").write_bytes(b"fixture")
        (folder / "ignore.txt").write_text("skip", encoding="utf-8")
        with mock.patch.object(
            studio_server, "_pick_rom_folder", return_value=studio_server._authorize_rom_folder(str(folder))
        ):
            response = self.client.post("/api/fs/pick-rom-folder", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(Path(payload["folder"]), folder.resolve())
        self.assertEqual([Path(path).name for path in payload["roms"]], ["a.zip", "b.zip"])

    def test_folder_path_endpoint_returns_zip_files_in_order(self):
        folder = self.root / "typed-folder-roms"
        folder.mkdir()
        (folder / "b.zip").write_bytes(b"fixture")
        (folder / "a.zip").write_bytes(b"fixture")
        response = self.client.post(
            "/api/fs/authorize-rom-folder",
            headers=self.headers,
            json={"folderPath": str(folder)},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(Path(payload["folder"]), folder.resolve())
        self.assertEqual([Path(path).name for path in payload["roms"]], ["a.zip", "b.zip"])

    def test_windows_folder_picker_authorizes_powershell_selection(self):
        folder = self.root / "native-folder-roms"
        folder.mkdir()
        (folder / "fixture.zip").write_bytes(b"fixture")
        completed = SimpleNamespace(returncode=0, stdout=str(folder), stderr="")
        with mock.patch.object(studio_server.subprocess, "run", return_value=completed) as run:
            payload = studio_server._pick_windows_rom_folder()
        self.assertEqual(Path(payload["folder"]), folder.resolve())
        self.assertEqual([Path(path).name for path in payload["roms"]], ["fixture.zip"])
        self.assertIn("-STA", run.call_args.args[0])
        self.assertNotIn("-WindowStyle", run.call_args.args[0])

    def test_artifact_history_keeps_missing_output_file(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        missing_zip = self.output / "moved.zip"
        studio_server.update_job(
            job["id"],
            status="success",
            output_zip=str(missing_zip),
        )
        payload = self.client.get("/api/artifacts", headers=self.headers).get_json()
        self.assertEqual(len(payload["artifacts"]), 1)
        self.assertFalse(payload["artifacts"][0]["artifactExists"])

    def test_artifact_history_keeps_validated_output_from_failed_notification(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        output = self.output / "fixture.zip"
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(b"validated")
        studio_server.update_job(
            job["id"],
            status="failed",
            output_zip=str(output),
            error="telegram unavailable",
        )
        payload = self.client.get("/api/artifacts", headers=self.headers).get_json()
        self.assertEqual(len(payload["artifacts"]), 1)
        self.assertTrue(payload["artifacts"][0]["artifactExists"])

    def test_artifact_history_lists_lite_and_plus_outputs_from_one_job(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        lite = self.output / "Wukong_Lite_V3.4_fixture_China_Stable_deadbeef.zip"
        plus = self.output / "Wukong_Plus_V3.4_fixture_China_Stable_deadbeef.zip"
        lite.parent.mkdir(exist_ok=True)
        lite.write_bytes(b"lite")
        plus.write_bytes(b"plus")
        studio_server.update_job(
            job["id"],
            status="success",
            output_zip=str(plus),
            steps_json=json.dumps(
                [
                    {
                        "id": "package_zip",
                        "status": "success",
                        "details": {"outputZips": [str(lite), str(plus)]},
                    }
                ]
            ),
        )
        payload = self.client.get("/api/artifacts", headers=self.headers).get_json()
        self.assertEqual(
            [Path(item["outputZip"]).name for item in payload["artifacts"]],
            [lite.name, plus.name],
        )

    def test_inspect_rom_api_accepts_valid_fixture(self):
        rom = self.root / "fixture.zip"
        with zipfile.ZipFile(rom, "w") as archive:
            archive.writestr(
                "META-INF/com/android/metadata",
                "oplus_product_name=PKG110\noplus_version_name=fixture\n",
            )
            archive.writestr("payload.bin", b"fixture")
        response = self.client.post(
            "/api/roms/inspect",
            headers=self.headers,
            json={"romPath": str(rom), "preset": "custom", "enabledSteps": []},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["ok"])

    def test_cancel_running_job_kills_process_tree(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        studio_server.update_job(job["id"], status="running", pid=98765)
        with mock.patch.object(studio_server, "_kill_process_tree") as kill:
            response = self.client.post(
                f"/api/jobs/{job['id']}/cancel", headers=self.headers
            )
        self.assertEqual(response.status_code, 200)
        kill.assert_called_once_with(98765)
        self.assertEqual(response.get_json()["status"], "cancelled")

    def test_job_rejects_unconfigured_telegram_notification(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(
            studio_server, "load_local_env", return_value={}
        ):
            with self.assertRaisesRegex(ValueError, "Telegram"):
                studio_server.create_job(
                    {
                        "romPath": str(self.root / "fixture.zip"),
                        "notifyTelegram": True,
                    }
                )

    def test_telegram_progress_expands_lite_and_plus_phases(self):
        with mock.patch.dict(
            "os.environ",
            {
                "WUKONG_TELEGRAM_BOT_TOKEN": "token",
                "WUKONG_TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ), mock.patch.object(
            studio_server, "load_local_env", return_value={}
        ), mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={
                "ok": True,
                "errors": [],
                "metadata": {"version_name": "both-progress", "product_name": "PKG110"},
                "device": {"name": "OnePlus Ace 5", "product_name": "PKG110", "soc": "86xx"},
            },
        ), mock.patch.object(
            studio_server.TELEGRAM_PROGRESS, "publish"
        ) as publish:
            job = studio_server.create_job(
                {
                    "romPath": str(self.root / "fixture.zip"),
                    "preset": "both",
                    "notifyTelegram": True,
                }
            )
            studio_server.update_job(job["id"], status="running", started_at=studio_server.utc_now())
            studio_server._publish_telegram_progress(job["id"], force=True)
            for step in [
                item["id"]
                for item in job["steps"]
                if item["id"] in studio_core.DUAL_SHARED_STEPS
            ]:
                studio_server._publish_telegram_progress(
                    job["id"],
                    {"type": "step", "step": step, "status": "success", "details": {}},
                )
            phased = [
                item["id"]
                for item in job["steps"]
                if item["id"] in studio_core.DUAL_PHASE_STEPS or item["id"] == "notify_telegram"
            ]
            for step in phased:
                studio_server._publish_telegram_progress(
                    job["id"],
                    {
                        "type": "step",
                        "step": step,
                        "status": "success",
                        "details": {"phase": "Lite"},
                    },
                )
            studio_server._publish_telegram_progress(
                job["id"],
                {
                    "type": "step",
                    "step": phased[0],
                    "status": "running",
                    "details": {"phase": "Plus"},
                },
            )

        snapshot = publish.call_args.args[0]
        labels = [step["label"] for step in snapshot["steps"]]
        self.assertGreater(snapshot["percent"], 50)
        self.assertLess(snapshot["percent"], 100)
        self.assertTrue(any(label.startswith("Lite ·") for label in labels))
        self.assertTrue(any(label.startswith("Plus ·") for label in labels))
        self.assertEqual(snapshot["deviceName"], "OnePlus Ace 5")

    def test_job_persists_selected_mods_and_custom_debloat_paths(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job(
                {
                    "romPath": str(self.root / "fixture.zip"),
                    "preset": "custom",
                    "enabledSteps": ["debloat", "apply_mod"],
                    "modNames": ["Gapps", "Chat_bubbles"],
                    "modVersion": "ColorOS_16.0.8",
                    "debloatPaths": [r"my_stock\app\Browser"],
                }
            )
        self.assertEqual(job["spec"]["modNames"], ["Gapps", "Chat_bubbles"])
        self.assertEqual(job["spec"]["modVersion"], "ColorOS_16.0.8")
        self.assertEqual(job["spec"]["debloatPaths"], [r"my_stock\app\Browser"])

    def test_job_rejects_empty_custom_plan(self):
        with self.assertRaisesRegex(ValueError, "at least one step"):
            studio_server.create_job(
                {
                    "romPath": str(self.root / "fixture.zip"),
                    "preset": "custom",
                    "enabledSteps": [],
                }
            )

    def test_job_rejects_mod_version_path_traversal(self):
        response = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={
                "romPath": str(self.root / "fixture.zip"),
                "modVersion": r"..\outside",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid MOD version", response.get_json()["error"])

    def test_job_workspace_uses_metadata_version_name_at_project_root(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={
                "ok": True,
                "errors": [],
                "metadata": {"version_name": "16.0.7.200(CN01)"},
            },
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        workspace = self.root / "16.0.7.200(CN01)"
        self.assertEqual(Path(job["workspace"]), workspace.resolve())
        self.assertEqual(job["versionName"], "16.0.7.200(CN01)")
        self.assertEqual(job["spec"]["versionName"], "16.0.7.200(CN01)")
        self.assertTrue(studio_core.is_managed_workspace(workspace, root=self.root))
        self.assertEqual(Path(job["logPath"]).parent.resolve(), self.jobs.resolve())

    def test_resume_job_reuses_ui_workspace(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            first = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
            studio_server.update_job(first["id"], status="failed")
            resumed = studio_server.create_job(
                {
                    "romPath": str(self.root / "fixture.zip"),
                    "preset": "resume",
                    "resumeFromJobId": first["id"],
                }
            )
        self.assertEqual(Path(resumed["workspace"]), Path(first["workspace"]).resolve())
        self.assertEqual(resumed["spec"]["preset"], "resume")
        self.assertEqual(resumed["spec"]["resumePreset"], first["spec"]["preset"])
        self.assertEqual(resumed["spec"]["romSha256"], first["spec"]["romSha256"])

    def test_resume_rejects_different_rom_with_same_version_name(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={"ok": True, "errors": [], "metadata": {"version_name": "fixture"}},
        ):
            first = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
            studio_server.update_job(first["id"], status="failed")
            (self.root / "fixture.zip").write_bytes(b"different-rom")
            with self.assertRaisesRegex(ValueError, "does not match"):
                studio_server.create_job(
                    {
                        "romPath": str(self.root / "fixture.zip"),
                        "preset": "resume",
                        "resumeFromJobId": first["id"],
                    }
                )

    def test_package_step_persists_output_before_worker_exit(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        output = self.output / "fixture.zip"
        studio_server._update_step(
            job["id"],
            {
                "step": "package_zip",
                "status": "success",
                "details": {"outputZip": str(output)},
            },
        )
        self.assertEqual(studio_server.get_job(job["id"])["outputZip"], str(output))

    def test_sse_returns_log_and_state(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        Path(job["logPath"]).write_text("hello studio\n", encoding="utf-8")
        studio_server.update_job(job["id"], status="cancelled")
        response = self.client.get(
            f"/api/jobs/{job['id']}/events",
            query_string={"token": studio_server.SESSION_TOKEN},
        )
        body = response.get_data(as_text=True)
        self.assertIn("event: log", body)
        self.assertIn("hello studio", body)
        self.assertIn('"lines": ["hello studio"]', body)
        self.assertIn("event: state", body)

    def test_job_log_requires_auth_and_uses_database_log_path_only(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        Path(job["logPath"]).write_text("owned log\n", encoding="utf-8")
        outside = self.root / "outside.log"
        outside.write_text("outside\n", encoding="utf-8")

        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/log").status_code, 403)
        response = self.client.get(
            f"/api/jobs/{job['id']}/log",
            query_string={"path": str(outside)},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response.content_type)
        self.assertEqual(response.get_data(as_text=True), "owned log\n")

    def test_job_metrics_and_diagnostics_bundle_exclude_secrets(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        Path(job["logPath"]).write_text("diagnostic log\n", encoding="utf-8")
        metrics = self.client.get(
            f"/api/jobs/{job['id']}/metrics",
            headers=self.headers,
        )
        self.assertEqual(metrics.status_code, 200)
        self.assertEqual(metrics.get_json()["logBytes"], Path(job["logPath"]).stat().st_size)

        bundle = self.client.get(
            f"/api/jobs/{job['id']}/diagnostics-bundle",
            headers=self.headers,
        )
        self.assertEqual(bundle.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
            self.assertIn("build.log", archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertFalse(manifest["containsSecrets"])
            settings = archive.read("settings-public.json").decode("utf-8")
            self.assertNotIn("WUKONG_TELEGRAM_BOT_TOKEN", settings)

    def test_process_metrics_reads_current_process(self):
        metrics = studio_server._process_metrics(os.getpid())
        self.assertTrue(metrics["available"])
        self.assertGreater(metrics["workingSetBytes"], 0)
        self.assertGreaterEqual(metrics["cpuTimeSeconds"], 0)

    def test_job_log_supports_incremental_tail_chunks(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        log_path = Path(job["logPath"])
        log_path.write_text("first\nsecond\n", encoding="utf-8")

        initial = self.client.get(
            f"/api/jobs/{job['id']}/log",
            query_string={"offset": -1, "limit": 8},
            headers=self.headers,
        )
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.get_data(as_text=True), "second\n")
        next_offset = int(initial.headers["X-Log-Next-Offset"])

        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("third\n")
        incremental = self.client.get(
            f"/api/jobs/{job['id']}/log",
            query_string={"offset": next_offset, "limit": 1024},
            headers=self.headers,
        )
        self.assertEqual(incremental.status_code, 200)
        self.assertEqual(incremental.get_data(as_text=True), "third\n")
        self.assertEqual(incremental.headers["X-Log-Reset"], "0")

    def test_job_log_tail_limits_large_console_payload(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        log_path = Path(job["logPath"])
        log_path.write_text("old-line\n" * 250000 + "latest-line\n", encoding="utf-8")

        response = self.client.get(
            f"/api/jobs/{job['id']}/log",
            query_string={"offset": -1, "limit": 131072},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data), 131072)
        self.assertTrue(response.get_data(as_text=True).endswith("latest-line\n"))

    def test_job_log_follow_mode_drops_large_backlog(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        log_path = Path(job["logPath"])
        log_path.write_text("old-line\n" * 10000 + "latest-line\n", encoding="utf-8")

        response = self.client.get(
            f"/api/jobs/{job['id']}/log",
            query_string={"offset": 0, "limit": 4096, "follow": 1},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Log-Reset"], "1")
        self.assertLessEqual(len(response.data), 4096)
        self.assertTrue(response.get_data(as_text=True).endswith("latest-line\n"))

    def test_sse_tail_offset_and_ansi_cleanup(self):
        log = self.jobs / "large.log"
        log.write_text("first line\n" + ("x" * 40) + "\nlast line\n", encoding="utf-8")
        offset = studio_server._log_tail_offset(log, max_bytes=20)
        self.assertGreater(offset, 0)
        with log.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            self.assertEqual(handle.read(), "last line\n")
        self.assertEqual(
            studio_server._clean_ui_log_line("\x1b[1;93mExtract:\x1b[0m 50%\r\n"),
            "Extract: 50%",
        )

    def test_queue_manager_selects_oldest_job(self):
        (self.root / "one.zip").write_bytes(b"one")
        (self.root / "two.zip").write_bytes(b"two")
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            first = studio_server.create_job({"romPath": str(self.root / "one.zip")})
            studio_server.create_job({"romPath": str(self.root / "two.zip")})
        self.assertEqual(studio_server.QueueManager()._next_job()["id"], first["id"])

    def test_worker_environment_forces_utf8(self):
        environment = studio_server._worker_environment("16.0.7.200(CN01)")
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["WUKONG_STUDIO_ASYNC_PACKAGE"], "1")
        self.assertEqual(environment["WUKONG_STUDIO_TASK_NAME"], "16.0.7.200(CN01)")

    def test_parent_process_liveness_uses_current_process_without_signalling_it(self):
        self.assertTrue(studio_server._parent_process_alive(os.getpid()))
        self.assertFalse(studio_server._parent_process_alive(2_147_483_647))

    def test_pending_package_step_stays_running_until_packager_finishes(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        output = self.output / "background.zip"
        studio_server._update_step(
            job["id"],
            {
                "step": "package_zip",
                "status": "success",
                "details": {
                    "packagingPending": True,
                    "outputZip": str(output),
                    "outputZips": [str(output)],
                    "taskId": "01-lite",
                },
            },
        )

        package_step = next(
            step for step in studio_server.get_job(job["id"])["steps"]
            if step["id"] == "package_zip"
        )
        self.assertEqual(package_step["status"], "running")
        self.assertIsNone(studio_server.get_job(job["id"])["outputZip"])

    def test_packaging_job_finishes_only_after_background_tasks_complete(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        output = str(self.output / "background.zip")
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [output],
                "expected": [output],
                "failed": None,
                "workerDone": True,
            }

        studio_server._finalize_packaging(job["id"])

        finished = studio_server.get_job(job["id"])
        self.assertEqual(finished["status"], "success")
        self.assertEqual(finished["outputZip"], output)

    def test_background_package_timing_replaces_staging_only_duration(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        output = str(self.output / "background.zip")
        studio_server._update_step(
            job["id"],
            {
                "step": "package_zip",
                "status": "success",
                "details": {
                    "packagingPending": True,
                    "outputZip": output,
                    "outputZips": [output],
                    "taskId": "01-lite",
                    "durationSeconds": 23.046,
                    "stagingSeconds": 23.046,
                },
            },
        )
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [],
                "expected": [output],
                "failed": None,
                "workerDone": True,
                "timings": {},
            }

        studio_server._handle_package_event(
            job["id"],
            {
                "type": "package",
                "status": "success",
                "taskId": "01-lite",
                "outputZip": output,
                "timing": {
                    "stagingSeconds": 23.046,
                    "compressionSeconds": 241.096,
                    "validationSeconds": 0.031,
                    "totalSeconds": 264.173,
                    "validationMode": "fast",
                },
            },
        )
        studio_server._finalize_packaging(job["id"])

        package_step = next(
            step for step in studio_server.get_job(job["id"])["steps"]
            if step["id"] == "package_zip"
        )
        details = package_step["details"]
        self.assertEqual(details["durationSeconds"], 264.173)
        self.assertEqual(details["stagingSeconds"], 23.046)
        self.assertEqual(details["compressionSeconds"], 241.096)
        self.assertEqual(details["validationSeconds"], 0.031)
        self.assertEqual(details["validationMode"], "fast")
        self.assertEqual(details["packageTimings"]["01-lite"]["totalSeconds"], 264.173)

    def test_background_package_timing_aggregates_lite_and_plus(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        outputs = [str(self.output / "lite.zip"), str(self.output / "plus.zip")]
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [],
                "expected": outputs.copy(),
                "failed": None,
                "workerDone": True,
                "timings": {},
            }

        for task_id, output, phase, timing in (
            (
                "01-lite",
                outputs[0],
                "Lite",
                {
                    "stagingSeconds": 10.0,
                    "compressionSeconds": 100.0,
                    "validationSeconds": 1.0,
                    "totalSeconds": 111.0,
                    "validationMode": "fast",
                },
            ),
            (
                "02-plus",
                outputs[1],
                "Plus",
                {
                    "stagingSeconds": 12.0,
                    "compressionSeconds": 120.0,
                    "validationSeconds": 2.0,
                    "totalSeconds": 134.0,
                    "validationMode": "fast",
                },
            ),
        ):
            studio_server._handle_package_event(
                job["id"],
                {
                    "type": "package",
                    "status": "success",
                    "taskId": task_id,
                    "phase": phase,
                    "outputZip": output,
                    "timing": timing,
                },
            )
        studio_server._finalize_packaging(job["id"])

        package_step = next(
            step for step in studio_server.get_job(job["id"])["steps"]
            if step["id"] == "package_zip"
        )
        details = package_step["details"]
        self.assertEqual(details["durationSeconds"], 245.0)
        self.assertEqual(details["stagingSeconds"], 22.0)
        self.assertEqual(details["compressionSeconds"], 220.0)
        self.assertEqual(details["validationSeconds"], 3.0)
        self.assertEqual(set(details["packageTimings"]), {"01-lite", "02-plus"})

    def test_packaging_fails_when_expected_artifact_never_completed(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        expected = str(self.output / "expected.zip")
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [],
                "expected": [expected],
                "failed": None,
                "workerDone": True,
            }

        studio_server._finalize_packaging(job["id"])

        failed = studio_server.get_job(job["id"])
        self.assertEqual(failed["status"], "failed")
        self.assertIn("did not complete", failed["error"])

    def test_cancelled_packaging_is_not_reclassified_as_failed(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        studio_server.update_job(job["id"], status="cancelled")
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [],
                "expected": [str(self.output / "expected.zip")],
                "failed": "Cancelled by user",
                "workerDone": True,
            }

        studio_server._finalize_packaging(job["id"])

        self.assertEqual(studio_server.get_job(job["id"])["status"], "cancelled")

    def test_packaging_success_cleans_claimed_workspace_only_after_completion(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={
                "ok": True,
                "errors": [],
                "metadata": {"version_name": "cleanup-fixture"},
            },
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        workspace = Path(job["workspace"])
        self.assertTrue(workspace.is_dir())
        output = str(self.output / "background.zip")
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [output],
                "expected": [output],
                "failed": None,
                "workerDone": True,
            }

        studio_server._finalize_packaging(job["id"])

        self.assertFalse(workspace.exists())
        package_step = next(
            step for step in studio_server.get_job(job["id"])["steps"]
            if step["id"] == "package_zip"
        )
        self.assertTrue(package_step["details"]["workspaceCleaned"])

    def test_old_packager_cannot_delete_reclaimed_workspace(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={"ok": True, "errors": [], "metadata": {"version_name": "shared"}},
        ):
            old = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        workspace = Path(old["workspace"])
        studio_core.prepare_workspace(
            workspace,
            "new-job",
            "shared",
            resume=False,
            root=self.root,
        )
        output = str(self.output / "background.zip")
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[old["id"]] = {
                "active": set(),
                "completed": [output],
                "expected": [output],
                "failed": None,
                "workerDone": True,
            }

        studio_server._finalize_packaging(old["id"])

        self.assertTrue(workspace.is_dir())
        package_step = next(
            step for step in studio_server.get_job(old["id"])["steps"]
            if step["id"] == "package_zip"
        )
        self.assertFalse(package_step["details"]["workspaceCleaned"])
        self.assertIn("owned by another job", package_step["details"]["cleanupWarning"])

    def test_packaging_failure_preserves_workspace_for_resume(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={
                "ok": True,
                "errors": [],
                "metadata": {"version_name": "failed-package"},
            },
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        workspace = Path(job["workspace"])
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": [],
                "expected": [],
                "failed": "ZIP validation failed",
                "workerDone": True,
            }

        studio_server._finalize_packaging(job["id"])

        self.assertTrue(workspace.is_dir())
        self.assertEqual(studio_server.get_job(job["id"])["status"], "failed")
        self.assertNotIn(job["id"], studio_server.PACKAGE_TRACKERS)
        self.assertNotIn(job["id"], studio_server.PACKAGE_PROCESSES)

    def test_packaging_failure_waits_for_active_siblings_before_tracker_cleanup(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={"ok": True, "errors": [], "metadata": {"version_name": "failed-sibling"}},
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": {"plus"},
                "completed": [],
                "expected": [str(self.output / "plus.zip")],
                "failed": "Lite packaging failed",
                "workerDone": True,
            }

        studio_server._finalize_packaging(job["id"])
        self.assertIn(job["id"], studio_server.PACKAGE_TRACKERS)

        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]]["active"].clear()
        studio_server._finalize_packaging(job["id"])
        self.assertNotIn(job["id"], studio_server.PACKAGE_TRACKERS)

    def test_package_step_merge_uses_complete_tracker_outputs(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={"ok": True, "errors": [], "metadata": {"version_name": "both"}},
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        outputs = [str(self.output / "lite.zip"), str(self.output / "plus.zip")]
        with studio_server.PACKAGE_LOCK:
            studio_server.PACKAGE_TRACKERS[job["id"]] = {
                "active": set(),
                "completed": outputs.copy(),
                "expected": outputs.copy(),
                "failed": None,
                "workerDone": False,
            }

        merged = studio_server._merge_package_step_details(job["id"], outputs[-1])

        self.assertEqual(merged, outputs)
        package_step = next(
            step for step in studio_server.get_job(job["id"])["steps"]
            if step["id"] == "package_zip"
        )
        self.assertEqual(package_step["details"]["outputZips"], outputs)

    def test_worker_command_uses_version_name_as_task_name(self):
        with mock.patch.object(
            studio_server,
            "inspect_rom",
            return_value={
                "ok": True,
                "errors": [],
                "metadata": {"version_name": "16.0.7.200(CN01)"},
            },
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        command = studio_server._worker_command(job)
        self.assertEqual(command[command.index("--task-name") + 1], "16.0.7.200(CN01)")

    def test_diagnostics_reports_python_zipfile_fallback_without_7z(self):
        with mock.patch.object(studio_server, "ROOT_DIR", self.root), mock.patch.object(
            studio_server.shutil, "which", return_value=None
        ):
            payload = studio_server.diagnostics()
        self.assertEqual(payload["sevenZip"], "Python zipfile fallback")

    def test_database_recovery_marks_interrupted_worker_failed(self):
        with mock.patch.object(
            studio_server, "inspect_rom", return_value={"ok": True, "errors": []}
        ):
            job = studio_server.create_job({"romPath": str(self.root / "fixture.zip")})
        studio_server.update_job(job["id"], status="running", pid=321)
        studio_server.init_database()
        recovered = studio_server.get_job(job["id"])
        self.assertEqual(recovered["status"], "failed")
        self.assertIsNone(recovered["pid"])

    def test_database_migration_backfills_legacy_job_version_name(self):
        database_path = self.runtime / "studio.db"
        database_path.unlink()
        rom = self.root / "legacy.zip"
        with zipfile.ZipFile(rom, "w") as archive:
            archive.writestr(
                "META-INF/com/android/metadata",
                "oplus_product_name=PKG110\noplus_version_name=legacy-version\n",
            )
        with closing(sqlite3.connect(database_path)) as database:
            database.execute(
                """
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    current_step TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    output_zip TEXT,
                    workspace TEXT NOT NULL,
                    log_path TEXT NOT NULL,
                    error TEXT,
                    pid INTEGER
                )
                """
            )
            database.execute(
                """
                INSERT INTO jobs (
                    id, status, spec_json, steps_json, created_at, workspace, log_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-job",
                    "success",
                    json.dumps({"romPath": str(rom)}),
                    "[]",
                    "2026-06-01T00:00:00+00:00",
                    str(self.jobs / "legacy-job"),
                    str(self.jobs / "legacy-job.log"),
                ),
            )
            database.commit()
        studio_server.init_database()
        self.assertEqual(studio_server.get_job("legacy-job")["versionName"], "legacy-version")


if __name__ == "__main__":
    unittest.main()
