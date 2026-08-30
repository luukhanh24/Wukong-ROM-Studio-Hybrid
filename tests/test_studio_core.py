import json
import hashlib
import io
import shutil
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from contextlib import redirect_stdout

import studio_core
import batch_unpack
import batch_repack
import img_tool
import partition_config
import super_tool
import avb_footer
import wk_manager_patcher
from batch_repack import sync_configs as sync_repack_configs
from partition_config import (
    PartitionConfigError,
    sync_partition_configs,
    validate_repacked_partition,
    write_partition_tree_fingerprint,
)
from src.core.payload_extract import _write_extents, _write_zero_extents


class RecordingWriter:
    def __init__(self):
        self.writes = []

    def write(self, position, data):
        self.writes.append((position, data))


class StudioCoreTests(unittest.TestCase):
    def test_sanitize_version_name_blocks_path_components(self):
        self.assertEqual(
            studio_core.sanitize_version_name("../../16.0 / CN:stable"),
            "16.0_CN_stable",
        )
        self.assertEqual(studio_core.sanitize_version_name(".."), "rom")

    def test_rom_renamer_previews_and_applies_metadata_version_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "download.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_version_name=PKG110_16.0.8.300(CN01)\n",
                )

            preview = studio_core.preview_rom_renames([source])

            self.assertTrue(preview["canApply"])
            self.assertEqual(preview["entries"][0]["status"], "ready")
            self.assertEqual(
                preview["entries"][0]["targetName"],
                "PKG110_16.0.8.300(CN01).zip",
            )
            result = studio_core.apply_rom_renames(preview["entries"])
            self.assertEqual(result["renamed"], 1)
            self.assertFalse(source.exists())
            self.assertTrue((root / "PKG110_16.0.8.300(CN01).zip").is_file())

    def test_rom_renamer_rejects_unsafe_and_duplicate_targets_without_partial_rename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            unsafe = root / "unsafe.zip"
            first = root / "first.zip"
            second = root / "second.zip"
            for path, version in (
                (unsafe, "../escape"),
                (first, "same-version"),
                (second, "same-version"),
            ):
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr(
                        "META-INF/com/android/metadata",
                        f"oplus_version_name={version}\n",
                    )

            preview = studio_core.preview_rom_renames([unsafe, first, second])

            self.assertFalse(preview["canApply"])
            self.assertTrue(all(entry["status"] == "error" for entry in preview["entries"]))
            with self.assertRaises(studio_core.StudioError):
                studio_core.apply_rom_renames(preview["entries"])
            self.assertTrue(unsafe.is_file())
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())

    def test_rom_renamer_reports_already_named_zip_as_unchanged(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "fixture.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_version_name=fixture\n",
                )

            preview = studio_core.preview_rom_renames([source])

            self.assertFalse(preview["canApply"])
            self.assertEqual(preview["entries"][0]["status"], "unchanged")

    def test_rom_renamer_reports_corrupt_missing_metadata_and_existing_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            corrupt = root / "corrupt.zip"
            corrupt.write_bytes(b"not-a-zip")
            missing = root / "missing.zip"
            with zipfile.ZipFile(missing, "w") as archive:
                archive.writestr("payload.bin", b"fixture")
            source = root / "source.zip"
            target = root / "occupied.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_version_name=occupied\n",
                )
            with zipfile.ZipFile(target, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_version_name=occupied\n",
                )

            preview = studio_core.preview_rom_renames([corrupt, missing, source])

            self.assertEqual(preview["errors"], 3)
            self.assertIn("valid ZIP", preview["entries"][0]["error"])
            self.assertIn("META-INF/com/android/metadata", preview["entries"][1]["error"])
            self.assertIn("already exists", preview["entries"][2]["error"])
            self.assertTrue(source.is_file())

    def test_version_workspace_is_project_child_and_cleanup_requires_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version(
                "../../16.0 / CN:stable",
                root=root,
            )
            self.assertEqual(workspace, (root / "16.0_CN_stable").resolve())
            workspace.mkdir()
            with self.assertRaisesRegex(studio_core.StudioError, "unmanaged"):
                studio_core.cleanup_workspace(workspace, root=root)
            workspace.rmdir()
            studio_core.claim_workspace(workspace, "job-1", workspace.name, root=root)
            self.assertTrue(studio_core.cleanup_workspace(workspace, root=root))

    def test_cleanup_rejects_workspace_reclaimed_by_new_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version("fixture", root=root)
            studio_core.claim_workspace(workspace, "old-job", "fixture", root=root)
            studio_core.claim_workspace(
                workspace,
                "new-job",
                "fixture",
                root=root,
            )

            with self.assertRaisesRegex(studio_core.StudioError, "owned by another job"):
                studio_core.cleanup_workspace(
                    workspace,
                    root=root,
                    expected_job_id="old-job",
                )

            self.assertTrue(workspace.is_dir())
            self.assertTrue(
                studio_core.cleanup_workspace(
                    workspace,
                    root=root,
                    expected_job_id="new-job",
                )
            )

    def test_resume_rejects_workspace_from_outdated_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version("fixture", root=root)
            workspace.mkdir()
            (workspace / studio_core.WORKSPACE_MARKER_NAME).write_text(
                json.dumps(
                    {
                        "kind": studio_core.WORKSPACE_MARKER_KIND,
                        "versionName": "fixture",
                        "jobId": "old-job",
                    }
                ),
                encoding="utf-8",
            )
            self.assertTrue(studio_core.is_managed_workspace(workspace, root=root))
            self.assertFalse(studio_core.is_resume_compatible_workspace(workspace, root=root))
            with self.assertRaisesRegex(studio_core.StudioError, "outdated pipeline"):
                studio_core.prepare_workspace(
                    workspace,
                    "resume-job",
                    "fixture",
                    resume=True,
                    root=root,
                )
            studio_core.prepare_workspace(
                workspace,
                "fresh-job",
                "fixture",
                resume=False,
                root=root,
            )
            self.assertTrue(studio_core.is_resume_compatible_workspace(workspace, root=root))

    def test_resume_workspace_requires_matching_rom_and_spec_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version("fixture", root=root)
            studio_core.claim_workspace(
                workspace,
                "job-1",
                "fixture",
                root=root,
                rom_sha256="rom-a",
                spec_fingerprint="spec-a",
            )
            self.assertTrue(
                studio_core.is_resume_compatible_workspace(
                    workspace,
                    root=root,
                    rom_sha256="rom-a",
                    spec_fingerprint="spec-a",
                )
            )
            self.assertFalse(
                studio_core.is_resume_compatible_workspace(
                    workspace,
                    root=root,
                    rom_sha256="rom-b",
                    spec_fingerprint="spec-a",
                )
            )

    def test_resume_does_not_reuse_lite_phase_marker_for_plus_work(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            marker = workspace / ".studio-markers" / "apply_mod.json"
            marker.parent.mkdir()
            marker.write_text(
                json.dumps(
                    {
                        "step": "apply_mod",
                        "status": "success",
                        "details": {"phase": "Lite"},
                        "romSha256": "rom-a",
                        "specFingerprint": "spec-a",
                    }
                ),
                encoding="utf-8",
            )
            spec = studio_core.BuildSpec(
                romPath="rom.zip",
                preset="resume",
                enabledSteps=["apply_mod"],
                romSha256="rom-a",
                specFingerprint="spec-a",
            )
            self.assertEqual(studio_core.plan_steps(spec, workspace), ["apply_mod"])

    def test_managed_workspace_is_cleaned_after_validated_package(self):
        events = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version("fixture", root=root)
            studio_core.claim_workspace(workspace, "test-job", "fixture", root=root)
            (workspace / "large-build-data").write_bytes(b"x")

            def package(context):
                context.output_zip = root / "ROM_BUILD_DONE" / "fixture.zip"
                return {"outputZip": str(context.output_zip), "validation": {"size": 1}}

            with mock.patch.object(
                studio_core,
                "inspect_rom",
                return_value={
                    "ok": True,
                    "metadata": {"version_name": "fixture", "product_name": "PKG110"},
                    "device": {"product_name": "PKG110"},
                },
            ), mock.patch.object(
                studio_core, "plan_steps", return_value=["package_zip"]
            ), mock.patch.dict(
                studio_core.STAGE_HANDLERS, {"package_zip": package}, clear=True
            ), mock.patch.object(
                studio_core, "ROOT_DIR", root
            ), mock.patch.object(
                studio_core, "JOBS_DIR", root / ".wkstudio" / "jobs"
            ):
                result = studio_core.execute_build(
                    "test-job",
                    studio_core.BuildSpec(romPath="fixture.zip"),
                    workspace,
                    events.append,
                )
            self.assertTrue(result["workspaceCleaned"])
            self.assertFalse(workspace.exists())

    def test_managed_workspace_is_cleaned_when_notification_fails_after_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version("fixture", root=root)
            studio_core.claim_workspace(workspace, "test-job", "fixture", root=root)

            def package(context):
                context.output_zip = root / "ROM_BUILD_DONE" / "fixture.zip"
                return {"outputZip": str(context.output_zip), "validation": {"size": 1}}

            def notify(_context):
                raise studio_core.StudioError("telegram unavailable")

            with mock.patch.object(
                studio_core,
                "inspect_rom",
                return_value={
                    "ok": True,
                    "metadata": {"version_name": "fixture", "product_name": "PKG110"},
                    "device": {"product_name": "PKG110"},
                },
            ), mock.patch.object(
                studio_core, "plan_steps", return_value=["package_zip", "notify_telegram"]
            ), mock.patch.dict(
                studio_core.STAGE_HANDLERS,
                {"package_zip": package, "notify_telegram": notify},
                clear=True,
            ), mock.patch.object(
                studio_core, "ROOT_DIR", root
            ), mock.patch.object(
                studio_core, "JOBS_DIR", root / ".wkstudio" / "jobs"
            ):
                with self.assertRaisesRegex(studio_core.StudioError, "telegram unavailable"):
                    studio_core.execute_build(
                        "test-job",
                        studio_core.BuildSpec(romPath="fixture.zip"),
                        workspace,
                    )
            self.assertFalse(workspace.exists())

    def test_custom_plan_honors_exact_target_steps(self):
        spec = studio_core.BuildSpec(
            romPath="rom.zip",
            preset="custom",
            enabledSteps=["debloat"],
        )
        self.assertEqual(studio_core.plan_steps(spec), ["debloat"])

    def test_notify_telegram_is_added_with_explicit_custom_steps(self):
        spec = studio_core.BuildSpec(
            romPath="rom.zip",
            preset="custom",
            enabledSteps=["debloat"],
            notifyTelegram=True,
        )
        self.assertEqual(studio_core.plan_steps(spec), ["debloat", "package_zip", "notify_telegram"])

    def test_notify_telegram_requires_package_zip_in_custom_plan(self):
        spec = studio_core.BuildSpec(
            romPath="rom.zip",
            preset="custom",
            enabledSteps=[
                "inspect_rom",
                "extract_payload",
                "unpack_partitions",
                "debloat",
                "apply_mod",
                "sync_configs",
                "repack_partitions",
                "notify_telegram",
                "repack_super",
            ],
            notifyTelegram=True,
        )
        self.assertEqual(
            studio_core.plan_steps(spec),
            [
                "inspect_rom",
                "extract_payload",
                "unpack_partitions",
                "debloat",
                "apply_mod",
                "sync_configs",
                "repack_partitions",
                "repack_super",
                "package_zip",
                "notify_telegram",
            ],
        )

    def test_standard_plan_honors_explicit_enabled_steps(self):
        spec = studio_core.BuildSpec(
            romPath="rom.zip",
            preset="standard",
            enabledSteps=[
                "inspect_rom",
                "extract_payload",
                "unpack_partitions",
                "debloat",
                "sync_configs",
                "repack_partitions",
                "repack_super",
                "patch_vbmeta",
                "patch_vendor_boot",
                "package_zip",
            ],
        )
        with self.assertRaisesRegex(studio_core.StudioError, "protected boot-partition"):
            studio_core.plan_steps(spec)
        steps = []
        self.assertNotIn("region_patch", steps)
        self.assertNotIn("region_patch", studio_core.STEP_ORDER)
        self.assertNotIn("region_patch", studio_core.STAGE_HANDLERS)
        self.assertNotIn("framework_patch", steps)
        self.assertNotIn("framework_patch", studio_core.STEP_ORDER)
        self.assertNotIn("framework_patch", studio_core.STAGE_HANDLERS)
        self.assertNotIn("patch_vendor_boot", steps)
        self.assertIn("patch_vendor_boot", studio_core.STEP_ORDER)
        self.assertIn("patch_vendor_boot", studio_core.STAGE_HANDLERS)

    def test_vendor_boot_is_optional_not_a_preset_default(self):
        self.assertNotIn(
            "patch_vendor_boot",
            studio_core.plan_steps(studio_core.BuildSpec(romPath="rom.zip", preset="lite")),
        )
        self.assertNotIn(
            "patch_vendor_boot",
            studio_core.plan_steps(studio_core.BuildSpec(romPath="rom.zip", preset="resume")),
        )
        self.assertNotIn(
            "patch_vendor_boot",
            studio_core.plan_steps(studio_core.BuildSpec(romPath="rom.zip", preset="both")),
        )

    def test_resume_reuses_only_valid_marked_source(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "source_rom"
            source.mkdir()
            for name in ["boot.img", "vbmeta.img", "vendor_boot.img", "system.img"]:
                (source / name).write_bytes(b"x")
            marker = workspace / ".studio-markers" / "extract_payload.json"
            marker.parent.mkdir()
            marker.write_text(json.dumps({"status": "success"}), encoding="utf-8")
            spec = studio_core.BuildSpec(romPath="rom.zip", preset="resume")
            self.assertNotIn("extract_payload", studio_core.plan_steps(spec, workspace))

    def test_empty_mod_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "MOD_DIR", Path(temp)
        ):
            (Path(temp) / "Empty").mkdir()
            with self.assertRaisesRegex(studio_core.StudioError, "no supported"):
                studio_core.validate_mod("Empty")

    def test_mod_versions_are_listed_and_build_spec_keeps_selection(self):
        self.assertIn("ColorOS_16.0.7", studio_core.list_mod_versions())
        self.assertIn("ColorOS_16.0.8", studio_core.list_mod_versions())
        spec = studio_core.BuildSpec.from_dict(
            {"romPath": "rom.zip", "preset": "lite", "modVersion": "ColorOS_16.0.8"}
        )
        self.assertEqual(spec.modVersion, "ColorOS_16.0.8")
        legacy_spec = studio_core.BuildSpec.from_dict(
            {"romPath": "rom.zip", "preset": "lite", "modVersion": "ColorOS_800"}
        )
        self.assertEqual(legacy_spec.modVersion, "ColorOS_16.0.8")
        self.assertEqual(
            spec.selected_mod_names(),
            studio_core.preset_default_mods("lite", "ColorOS_16.0.8"),
        )
        self.assertEqual(
            studio_core.studio_version_name(
                studio_core.BuildSpec(romPath="rom.zip", modVersion="ColorOS_16.0.5")
            ),
            "V3.4",
        )
        self.assertEqual(
            studio_core.studio_version_name(
                studio_core.BuildSpec(romPath="rom.zip", modVersion="ColorOS_16.0.8")
            ),
            "V4.1",
        )
        with self.assertRaisesRegex(studio_core.StudioError, "Invalid MOD version"):
            studio_core.BuildSpec.from_dict(
                {"romPath": "rom.zip", "modVersion": r"..\outside"}
            )

    def test_apply_mod_uses_selected_mod_version_directory(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "MOD_DIR", Path(temp) / "MOD"
        ):
            mod_root = Path(temp) / "MOD"
            for version, content in (("ColorOS_16.0.7", "700"), ("ColorOS_16.0.8", "800")):
                target = mod_root / version / "Fixture" / "system"
                target.mkdir(parents=True)
                (target / "version.txt").write_text(content, encoding="utf-8")
            unpack = Path(temp) / "rom-unpack"
            destination = unpack / "system_unpacked" / "system"
            destination.mkdir(parents=True)

            result = studio_core.apply_selected_mods(
                ["Fixture"],
                unpack,
                None,
                Path(temp) / "workspace",
                "ColorOS_16.0.8",
            )

            self.assertEqual(result["modVersion"], "ColorOS_16.0.8")
            self.assertEqual(result["modifiedPartitions"], ["system"])
            self.assertEqual((destination / "version.txt").read_text(encoding="utf-8"), "800")

    def test_lite_and_resume_presets_select_expected_mods(self):
        lite = studio_core.BuildSpec.from_dict({"romPath": "rom.zip", "preset": "lite"})
        resume = studio_core.BuildSpec.from_dict({"romPath": "rom.zip", "preset": "resume"})
        self.assertEqual(
            lite.selected_mod_names(),
            studio_core.preset_default_mods("lite"),
        )
        self.assertNotIn("Gallery_mod_CN", lite.selected_mod_names())
        self.assertEqual(
            resume.selected_mod_names(),
            [
                mod["name"]
                for mod in studio_core.list_mods()
                if mod["ready"]
                and mod["name"] not in studio_core.PLUS_DEFAULT_EXCLUDED_MODS
            ],
        )
        self.assertNotIn("Gallery_mod_CN", resume.selected_mod_names())
        self.assertIn("Fake_lock", resume.selected_mod_names())
        self.assertTrue(
            all(
                set(mod["partitions"]).issubset(studio_core.MOD_PARTITIONS) or mod["patchOnly"]
                for mod in studio_core.list_mods()
                if mod["name"] in resume.selected_mod_names()
            )
        )

    def test_output_zip_name_uses_edition_and_v3(self):
        self.assertEqual(
            studio_core.output_zip_name("fixture", studio_core.BuildSpec(romPath="rom.zip", preset="lite")),
            "Wukong_Lite_V3.4_fixture_China_Stable.zip",
        )
        self.assertEqual(
            studio_core.output_zip_name("fixture", studio_core.BuildSpec(romPath="rom.zip", preset="resume")),
            "Wukong_Plus_V3.4_fixture_China_Stable.zip",
        )
        self.assertEqual(
            studio_core.output_zip_name("fixture", studio_core.BuildSpec(romPath="rom.zip", preset="custom")),
            "Wukong_Custom_V3.4_fixture_China_Stable.zip",
        )

    def test_preset_label_is_used_for_filename_and_branding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            manifest = unpack / "my_manifest_unpacked" / "my_manifest"
            product = unpack / "my_product_unpacked" / "my_product"
            manifest.mkdir(parents=True)
            product.mkdir(parents=True)
            for partition in (manifest, product):
                (partition / "build.prop").write_text(
                    "ro.build.version.oplusrom.display=16.0.7\n",
                    encoding="utf-8",
                )

            spec = studio_core.BuildSpec.from_dict({
                "romPath": "fixture.zip",
                "preset": "plus",
                "modVersion": "ColorOS_16.0.7",
                "modReleaseVersion": "KhanhDZ",
                "editionLabels": {"plus": "Complete"},
            })

            self.assertEqual(studio_core.build_edition_name(spec), "Complete")
            self.assertEqual(
                studio_core.output_zip_name("fixture", spec),
                "Wukong_Complete_KhanhDZ_fixture_China_Stable.zip",
            )
            result = studio_core.patch_build_branding(
                unpack,
                studio_core.build_edition_name(spec),
                studio_core.studio_version_name(spec),
            )

            self.assertEqual(result["manifestDisplayVersion"], 1)
            self.assertEqual(result["productDisplayVersion"], 1)
            self.assertIn("| Complete | KhanhDZ", (manifest / "build.prop").read_text(encoding="utf-8"))
            self.assertIn("| Complete | KhanhDZ", (product / "build.prop").read_text(encoding="utf-8"))

            resumed = studio_core.BuildSpec.from_dict({
                "romPath": "fixture.zip",
                "preset": "resume",
                "modVersion": "ColorOS_16.0.7",
                "editionLabels": {"plus": "Complete"},
            })
            self.assertEqual(studio_core.build_edition_name(resumed), "Complete")

    def test_both_preset_composes_renamed_lite_and_plus_labels(self):
        spec = studio_core.BuildSpec.from_dict({
            "romPath": "fixture.zip",
            "preset": "both",
            "modVersion": "ColorOS_16.0.7",
            "editionLabels": {"lite": "Essential", "plus": "Complete"},
        })
        self.assertEqual(studio_core.build_edition_name(spec), "Essential + Complete")
        self.assertEqual(
            studio_core.output_zip_name("fixture", studio_core.replace(spec, preset="lite")),
            "Wukong_Essential_V3.4_fixture_China_Stable.zip",
        )

    def test_custom_job_label_drives_branding_and_output_filename(self):
        spec = studio_core.BuildSpec.from_dict({
            "romPath": "fixture.zip",
            "preset": "custom",
            "modVersion": "ColorOS_16.0.7",
            "editionLabels": {"custom": "Limited"},
        })
        self.assertEqual(studio_core.build_edition_name(spec), "Limited")
        self.assertEqual(
            studio_core.output_zip_name("fixture", spec),
            "Wukong_Limited_V3.4_fixture_China_Stable.zip",
        )

    def test_preset_labels_reject_windows_filename_characters(self):
        with self.assertRaises(studio_core.StudioError):
            studio_core.BuildSpec.from_dict({
                "romPath": "fixture.zip",
                "preset": "plus",
                "editionLabels": {"plus": "Build:Pro"},
            })

    def test_studio_version_name_reads_runtime_override(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / "settings.json").write_text(
                json.dumps({"studioVersions": {"ColorOS_16.0.7": "V9.2"}}),
                encoding="utf-8",
            )
            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime):
                spec = studio_core.BuildSpec(
                    romPath="rom.zip",
                    modVersion="ColorOS_16.0.7",
                    preset="lite",
                )
                self.assertEqual(studio_core.studio_version_name(spec), "V9.2")

    def test_per_job_release_label_overrides_runtime_for_filename_and_branding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            unpack = root / "rom-unpack"
            manifest = unpack / "my_manifest_unpacked" / "my_manifest"
            product = unpack / "my_product_unpacked" / "my_product"
            runtime.mkdir()
            manifest.mkdir(parents=True)
            product.mkdir(parents=True)
            (runtime / "settings.json").write_text(
                json.dumps({"studioVersions": {"ColorOS_16.0.7": "V9.2"}}),
                encoding="utf-8",
            )
            for partition in (manifest, product):
                (partition / "build.prop").write_text(
                    "ro.build.version.oplusrom.display=16.0.7\n",
                    encoding="utf-8",
                )
            spec = studio_core.BuildSpec.from_dict({
                "romPath": "fixture.zip",
                "preset": "plus",
                "modVersion": "ColorOS_16.0.7",
                "modReleaseVersion": "KhanhDZ",
            })
            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime):
                self.assertEqual(studio_core.studio_version_name(spec), "KhanhDZ")
                self.assertEqual(
                    studio_core.output_zip_name("fixture", spec),
                    "Wukong_Plus_KhanhDZ_fixture_China_Stable.zip",
                )
                result = studio_core.patch_build_branding(
                    unpack, "Plus", studio_core.studio_version_name(spec)
                )
            self.assertEqual(result["manifestDisplayVersion"], 1)
            self.assertEqual(result["productDisplayVersion"], 1)
            self.assertIn("| Plus | KhanhDZ", (manifest / "build.prop").read_text(encoding="utf-8"))
            self.assertIn("| Plus | KhanhDZ", (product / "build.prop").read_text(encoding="utf-8"))

    def test_runtime_studio_version_override_reaches_zip_info_and_build_prop(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "runtime"
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            manifest = workspace / "rom-unpack" / "my_manifest_unpacked" / "my_manifest"
            runtime.mkdir()
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            manifest.mkdir(parents=True)
            (runtime / "settings.json").write_text(
                json.dumps({"studioVersions": {"ColorOS_16.0.7": "V9.2"}}),
                encoding="utf-8",
            )
            manifest_prop = manifest / "build.prop"
            manifest_prop.write_text(
                "ro.build.version.oplusrom.display=16.0.7\n",
                encoding="utf-8",
            )
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (source / "vendor_boot.img").write_bytes(b"source-vendor-boot")
            (build / "super.img").write_bytes(b"super")
            (build / "vbmeta.img").write_bytes(b"patched-vbmeta")
            context = studio_core.BuildContext(
                job_id="customver",
                spec=studio_core.BuildSpec(
                    romPath="fixture.zip",
                    preset="resume",
                    modVersion="ColorOS_16.0.7",
                ),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
                modified_partitions={"system"},
            )

            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime), mock.patch.object(
                studio_core, "ROOT_DIR", root
            ), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", root / "out"
            ), mock.patch.object(
                studio_core, "_run_command"
            ), mock.patch.object(
                studio_core, "validate_rom_repack", return_value=True
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=None
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_patched_vbmeta", return_value=True
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": ["vendor_boot.img"]}
            ):
                studio_core._stage_repack(context)
                result = studio_core._stage_package(context)

            self.assertEqual(
                manifest_prop.read_text(encoding="utf-8"),
                "ro.build.version.oplusrom.display=16.0.7 | Plus | V9.2\n",
            )
            with zipfile.ZipFile(result["outputZip"], "r") as archive:
                info = archive.read("info.txt").decode("utf-8").splitlines()
                self.assertEqual(info[3], "Plus")
                self.assertEqual(info[4], "V9.2")
            self.assertIn("Wukong_Plus_V9.2_fixture_China_Stable_customve.zip", result["outputZip"])

    def test_studio_version_name_rejects_invalid_runtime_override(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = Path(temp)
            (runtime / "settings.json").write_text(
                json.dumps({"studioVersions": {"ColorOS_16.0.8": "../../bad"}}),
                encoding="utf-8",
            )
            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime):
                spec = studio_core.BuildSpec(
                    romPath="rom.zip",
                    modVersion="ColorOS_16.0.8",
                    preset="lite",
                )
                self.assertEqual(studio_core.studio_version_name(spec), "V4.1")
        self.assertEqual(
            studio_core.output_zip_name(
                "fixture",
                studio_core.BuildSpec(
                    romPath="rom.zip",
                    preset="lite",
                    modVersion="ColorOS_16.0.8",
                ),
            ),
            "Wukong_Lite_V4.1_fixture_China_Stable.zip",
        )

    def test_telegram_notification_contains_build_details_and_time(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(
            "os.environ",
            {
                "WUKONG_TELEGRAM_BOT_TOKEN": "token",
                "WUKONG_TELEGRAM_CHAT_ID": "12345",
                "WUKONG_TELEGRAM_TIMEZONE": "Asia/Bangkok",
                "WUKONG_TELEGRAM_TIMEOUT": "10",
                "WUKONG_TELEGRAM_PARSE_MODE": "MarkdownV2",
                "WUKONG_TELEGRAM_LOCALE": "vi",
            },
            clear=True,
        ), mock.patch.object(
            studio_core, "load_local_env", return_value={}
        ), mock.patch(
            "requests.post"
        ) as post:
            previous_artifact = Path(temp) / "previous.zip"
            previous_artifact.write_bytes(b"previous")
            artifact = Path(temp) / "fixture.zip"
            artifact.write_bytes(b"zip")
            context = studio_core.BuildContext(
                job_id="job-telegram",
                spec=studio_core.BuildSpec(
                    romPath="fixture.zip",
                    preset="lite",
                    modNames=["Block_ota"],
                ),
                workspace=Path(temp),
                metadata={"version_name": "16.0.7", "product_name": "PKG110"},
                device={"product_name": "PKG110", "name": "OnePlus Ace 5", "soc": "86xx"},
                output_zip=artifact,
                output_zips=[previous_artifact, artifact],
                started_at=0,
            )

            result = studio_core._stage_notify(context)

            post.return_value.raise_for_status.assert_called_once_with()
            payload = post.call_args.kwargs["json"]
            self.assertEqual(payload["chat_id"], "12345")
            self.assertEqual(payload["parse_mode"], "HTML")
            self.assertIn("<b>BUILD ROM HOÀN TẤT</b>", payload["text"])
            self.assertIn("<b>Wukong Lite V3.4</b>", payload["text"])
            self.assertIn("<b>Thiết bị &amp; ROM</b>", payload["text"])
            self.assertIn("OnePlus Ace 5", payload["text"])
            self.assertIn("Danh sách MOD: Block_ota", payload["text"])
            self.assertIn("ZIP CRC · Manifest · cấu trúc super.img", payload["text"])
            self.assertIn("<b>Thời gian</b>", payload["text"])
            self.assertIn("<b>Job:</b> <code>job-telegram</code>", payload["text"])
            self.assertIn("fixture.zip", payload["text"])
            self.assertNotIn("previous.zip", payload["text"])
            self.assertEqual(result["artifacts"], [str(artifact)])
            self.assertEqual(result["locale"], "vi")
            self.assertNotIn("?", payload["text"])
            self.assertNotIn("chatId", result)

    def test_telegram_notification_uses_english_locale(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(
            "os.environ",
            {
                "WUKONG_TELEGRAM_BOT_TOKEN": "token",
                "WUKONG_TELEGRAM_CHAT_ID": "12345",
                "WUKONG_TELEGRAM_LOCALE": "en",
            },
            clear=True,
        ), mock.patch.object(
            studio_core, "load_local_env", return_value={}
        ), mock.patch(
            "requests.post"
        ) as post:
            artifact = Path(temp) / "fixture.zip"
            artifact.write_bytes(b"zip")
            context = studio_core.BuildContext(
                job_id="job-english",
                spec=studio_core.BuildSpec(
                    romPath="source.zip",
                    preset="resume",
                    modNames=["WK_Manager", "Fake_lock"],
                ),
                workspace=Path(temp),
                metadata={"version_name": "16.0.7", "product_name": "PKG110"},
                device={"name": "OnePlus Ace 5", "soc": "86xx"},
                output_zip=artifact,
            )

            result = studio_core._stage_notify(context)

            text = post.call_args.kwargs["json"]["text"]
            self.assertIn("<b>ROM BUILD COMPLETED</b>", text)
            self.assertIn("<b>Wukong Plus V3.4</b>", text)
            self.assertIn("<b>Device &amp; ROM</b>", text)
            self.assertIn("MOD list: WK_Manager, Fake_lock", text)
            self.assertIn("Validated artifact", text)
            self.assertEqual(result["locale"], "en")

    def test_telegram_notification_403_is_non_fatal(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.dict(
            "os.environ",
            {
                "WUKONG_TELEGRAM_BOT_TOKEN": "token",
                "WUKONG_TELEGRAM_CHAT_ID": "12345",
            },
            clear=True,
        ), mock.patch.object(
            studio_core, "load_local_env", return_value={}
        ), mock.patch(
            "requests.post"
        ) as post:
            import requests

            artifact = Path(temp) / "fixture.zip"
            artifact.write_bytes(b"zip")
            response = requests.Response()
            response.status_code = 403
            post.return_value.raise_for_status.side_effect = requests.HTTPError(
                "403 Client Error: Forbidden",
                response=response,
            )
            context = studio_core.BuildContext(
                job_id="job-telegram",
                spec=studio_core.BuildSpec(romPath="fixture.zip", preset="lite"),
                workspace=Path(temp),
                metadata={"version_name": "16.0.7", "product_name": "PKG110"},
                device={"product_name": "PKG110"},
                output_zip=artifact,
                output_zips=[artifact],
                started_at=0,
            )

            result = studio_core._stage_notify(context)

            self.assertFalse(result["notified"])
            self.assertEqual(result["statusCode"], 403)
            self.assertIn("send /start", result["warning"])

    def test_both_preset_packages_lite_then_plus_from_same_unpack(self):
        events = []
        calls = []
        selective_calls = []
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = studio_core.workspace_for_version("fixture", root=root)
            studio_core.claim_workspace(workspace, "job-both", "fixture", root=root)

            def make_handler(step):
                def handler(context):
                    calls.append((step, context.spec.preset, tuple(context.spec.modNames)))
                    selective_calls.append((step, context.spec.preset, context.selective_repack))
                    if step == "package_zip":
                        output = root / "out" / studio_core.output_zip_name(
                            "fixture",
                            context.spec,
                            f"_{context.job_id[:8]}",
                        )
                        output.parent.mkdir(exist_ok=True)
                        output.write_text("zip", encoding="utf-8")
                        context.output_zip = output
                        if output not in context.output_zips:
                            context.output_zips.append(output)
                        return {
                            "outputZip": str(output),
                            "outputZips": [str(path) for path in context.output_zips],
                        }
                    return {}

                return handler

            handlers = {
                step: make_handler(step)
                for step in studio_core.STEP_ORDER
                if step in studio_core.DEFAULT_STEPS | studio_core.PLUS_DEFAULT_STEPS
            }
            handlers["notify_telegram"] = make_handler("notify_telegram")
            with mock.patch.object(
                studio_core,
                "inspect_rom",
                return_value={
                    "ok": True,
                    "metadata": {"version_name": "fixture", "product_name": "PKG110"},
                    "device": {"product_name": "PKG110"},
                },
            ), mock.patch.dict(
                studio_core.STAGE_HANDLERS,
                handlers,
                clear=True,
            ), mock.patch.object(
                studio_core, "ROOT_DIR", root
            ), mock.patch.object(
                studio_core, "JOBS_DIR", root / ".wkstudio" / "jobs"
            ):
                result = studio_core.execute_build(
                    "job-both",
                    studio_core.BuildSpec.from_dict(
                        {
                            "romPath": "fixture.zip",
                            "preset": "both",
                            "notifyTelegram": True,
                        }
                    ),
                    workspace,
                    events.append,
                )

            package_calls = [call for call in calls if call[0] == "package_zip"]
            self.assertEqual([call[1] for call in package_calls], ["lite", "resume"])
            package_and_notify_calls = [
                (step, preset)
                for step, preset, _mods in calls
                if step in {"package_zip", "notify_telegram"}
            ]
            self.assertEqual(
                package_and_notify_calls,
                [
                    ("package_zip", "lite"),
                    ("notify_telegram", "lite"),
                    ("package_zip", "resume"),
                    ("notify_telegram", "resume"),
                ],
            )
            self.assertEqual(
                [preset for step, preset, _mods in calls if step == "patch_vendor_boot"],
                [],
            )
            self.assertIn("Wukong_Lite_V3.4_fixture_China_Stable_job-both.zip", result["outputZips"][0])
            self.assertIn("Wukong_Plus_V3.4_fixture_China_Stable_job-both.zip", result["outputZips"][1])
            self.assertIn(("repack_partitions", "resume", True), selective_calls)
            self.assertFalse(workspace.exists())

    def test_both_preset_honors_explicit_mod_selection_for_each_phase(self):
        spec = studio_core.BuildSpec(
            romPath="fixture.zip",
            preset="both",
            modVersion="ColorOS_16.0.9",
            modNames=["Fix_Metis", "Camera_mod"],
        )
        defaults = {
            "lite": ["Fix_Metis", "WK_Installer"],
            "resume": ["Fix_Metis", "WK_Installer", "Camera_mod", "Gapps"],
        }

        with mock.patch.object(
            studio_core,
            "preset_default_mods",
            side_effect=lambda preset, _version: defaults[preset],
        ):
            lite = studio_core._lite_spec(spec)
            plus = studio_core._plus_delta_spec(spec)

        self.assertEqual(["Fix_Metis"], lite.modNames)
        self.assertEqual(["Camera_mod"], plus.modNames)

    def test_stark_patch_adds_removes_and_replaces_lines(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "build.prop"
            target.write_text(
                "ro.keep=1\n"
                "ro.change=old\n"
                "remove.this=true\n",
                encoding="utf-8",
            )
            patch = root / "stark_build.prop"
            patch.write_text(
                "+ro.added=1\n"
                "-remove.this=true\n"
                "ro.change=new\n",
                encoding="utf-8",
            )
            result = studio_core.apply_stark_patch(patch, target)
            self.assertEqual(result, {"added": 1, "removed": 1, "replaced": 1})
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "ro.keep=1\nro.change=new\nro.added=1\n",
            )
            self.assertEqual(
                target.read_bytes(),
                b"ro.keep=1\nro.change=new\nro.added=1\n",
            )

    def test_stark_patch_inserts_oplus_feature_before_config_close(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "com.oplus.oplus-feature.xml"
            target.write_text(
                "<oplus-config>\n"
                "\t<oplus-feature name=\"oplus.software.keep\"/>\n"
                "</oplus-config>\n",
                encoding="utf-8",
            )
            patch = root / "stark_com.oplus.oplus-feature.xml"
            patch.write_text(
                "+\t<oplus-feature name=\"oplus.software.hans_restriction_exp\"/>\n",
                encoding="utf-8",
            )

            result = studio_core.apply_stark_patch(patch, target)

            self.assertEqual(result, {"added": 1, "removed": 0, "replaced": 0})
            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "<oplus-config>\n"
                "\t<oplus-feature name=\"oplus.software.keep\"/>\n"
                "\t<oplus-feature name=\"oplus.software.hans_restriction_exp\"/>\n"
                "</oplus-config>\n",
            )

    def test_stark_seapp_patch_inserts_wukong_domain_before_generic_priv_app(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "plat_seapp_contexts"
            target.write_text(
                "user=_app isPrivApp=true domain=priv_app type=privapp_data_file levelFrom=user\n",
                encoding="utf-8",
            )
            patch = root / "stark_plat_seapp_contexts"
            dedicated = (
                "user=_app isPrivApp=true name=com.wukong.manager "
                "domain=wukong_manager_app type=privapp_data_file levelFrom=user"
            )
            patch.write_text(f"+{dedicated}\n", encoding="utf-8")

            first = studio_core.apply_stark_patch(patch, target)
            second = studio_core.apply_stark_patch(patch, target)

            content = target.read_text(encoding="utf-8")
            self.assertEqual(first["added"], 1)
            self.assertEqual(second["added"], 0)
            self.assertEqual(content.count(dedicated), 1)
            self.assertLess(content.index(dedicated), content.index("domain=priv_app"))

    def test_stark_vendor_sepolicy_blocks_priv_app_vendor_sysfs_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "vendor_sepolicy.cil"
            target.write_text("", encoding="utf-8")
            patch = root / "stark_vendor_sepolicy.cil"
            patch.write_text(
                "+(allow priv_app_34_0 vendor_sysfs_kgsl (dir (read getattr open search)))\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(studio_core.StudioError, "Unsafe WK_Manager vendor SELinux rule"):
                studio_core.apply_stark_patch(patch, target)

    def test_stark_platform_policy_applies_explicit_priv_app_metric_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "plat_sepolicy.cil"
            target.write_text("(type wukong_manager_app)\n", encoding="utf-8")
            patch = root / "stark_plat_sepolicy.cil"
            patch.write_text(
                "+(allow priv_app sysfs_kgsl (file (read getattr open map)))\n"
                "+(allow wukong_manager_app sysfs_kgsl (file (read getattr open map)))\n",
                encoding="utf-8",
            )

            studio_core.apply_stark_patch(patch, target)

            content = target.read_text(encoding="utf-8")
            self.assertIn("allow priv_app sysfs_kgsl", content)
            self.assertIn("allow wukong_manager_app sysfs_kgsl", content)

    def test_vendor_sepolicy_guard_rejects_existing_unsafe_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "vendor_unpacked" / "vendor" / "etc" / "selinux" / "vendor_sepolicy.cil"
            policy.parent.mkdir(parents=True)
            policy.write_text(
                "(allow priv_app_34_0 vendor_sysfs_kgsl (dir (read getattr open search)))\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(studio_core.StudioError, "Unsafe vendor SELinux rules"):
                studio_core.validate_no_unsafe_vendor_priv_app_sysfs(root)

    def test_wk_manager_power_policy_uses_dedicated_domains(self):
        mod = Path("MOD/ColorOS_16.0.7/WK_Manager")
        policy = mod / "system/system/etc/selinux/stark_plat_sepolicy.cil"
        seapp = mod / "system/system/etc/selinux/stark_plat_seapp_contexts"
        shared = Path("STARK/WK_Manager")
        shared_policy = shared / "system/system/etc/selinux/stark_plat_sepolicy.cil"
        shared_seapp = shared / "system/system/etc/selinux/stark_plat_seapp_contexts"
        shared_contexts = shared / "system/system/etc/selinux/stark_plat_file_contexts"
        init_rc = shared / "system/system/etc/init/hw/stark_init.rc"

        policy_text = policy.read_text(encoding="utf-8")
        seapp_text = seapp.read_text(encoding="utf-8")
        init_text = init_rc.read_text(encoding="utf-8")
        power_policy_text = shared_policy.read_text(encoding="utf-8")

        self.assertIn("(type wukong_manager_app)", policy_text)
        self.assertIn("(type wukong_manager_app_userfaultfd)", policy_text)
        self.assertIn(
            '(typetransition wukong_manager_app wukong_manager_app anon_inode "[userfaultfd]" wukong_manager_app_userfaultfd)',
            policy_text,
        )
        self.assertIn(
            "(allow wukong_manager_app wukong_manager_app_userfaultfd (anon_inode (ioctl read create)))",
            policy_text,
        )
        self.assertIn(
            "(allow wukong_manager_app wukong_manager_app (anon_inode (ioctl read create)))",
            policy_text,
        )
        for rule in studio_core.WK_MANAGER_ART_RUNTIME_POLICY_RULES:
            self.assertIn(rule, policy_text)
        self.assertNotIn("+user=_app isPrivApp=true name=com.wukong.manager domain=wukong_manager_app", seapp_text)
        self.assertIn("-user=_app isPrivApp=true name=com.wukong.manager domain=wukong_manager_app", seapp_text)
        self.assertIn(
            "+user=_app isPrivApp=true name=com.wukong.manager "
            "domain=wukong_manager_app type=privapp_data_file levelFrom=user",
            shared_seapp.read_text(encoding="utf-8"),
        )
        self.assertIn("(type wukong_system_powerd)", power_policy_text)
        self.assertIn(
            "(allow wukong_manager_app wukong_system_powerd (unix_stream_socket (connectto)))",
            power_policy_text,
        )
        self.assertIn(
            "/dev/socket/wukong_system_power u:object_r:wukong_system_power_socket:s0",
            shared_contexts.read_text(encoding="utf-8"),
        )
        self.assertTrue((shared / "system/system/bin/wukong-system-powerd").is_file())
        self.assertTrue((shared / "system/system/etc/init/wukong-system-powerd.rc").is_file())
        self.assertNotIn("priv_app_34_0 vendor_sysfs_", policy_text)
        self.assertIn("chmod 0444 /sys/class/kgsl/kgsl-3d0/gpuclk", init_text)
        self.assertIn("chmod 0444 /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq", init_text)
        self.assertIn(
            "chmod 0444 /sys/devices/platform/soc/3d00000.qcom,kgsl-3d0/kgsl/kgsl-3d0/clock_mhz",
            init_text,
        )
        self.assertFalse((mod / "system/system/etc/init/wukong_manager_metrics.rc").exists())

    def test_wk_manager_art_runtime_policy_fallback_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            policy = Path(temp) / "plat_sepolicy.cil"
            policy.write_text("(type wukong_manager_app)\n", encoding="utf-8")

            first = studio_core._ensure_wk_manager_art_runtime_policy(policy)
            second = studio_core._ensure_wk_manager_art_runtime_policy(policy)

            content = policy.read_text(encoding="utf-8")
            self.assertEqual(first, 3)
            self.assertEqual(second, 0)
            for rule in studio_core.WK_MANAGER_ART_RUNTIME_POLICY_RULES:
                self.assertEqual(content.count(rule), 1)

    def test_tracked_wk_manager_system_policy_contains_runtime_and_power_rules(self):
        self.assertEqual(
            studio_core.WK_MANAGER_SYSTEM_POLICY_PATCH,
            studio_core.STARK_ROOT
            / "WK_Manager/system/system/etc/selinux/stark_plat_sepolicy.cil",
        )
        content = studio_core.WK_MANAGER_TRACKED_SYSTEM_POLICY_FALLBACK.read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            studio_core.WK_MANAGER_TRACKED_SYSTEM_POLICY_FALLBACK,
            studio_core.CONFIG_ROOT / "wk_manager_system_policy.cil",
        )

        for rule in studio_core.WK_MANAGER_ART_RUNTIME_POLICY_RULES:
            self.assertIn(f"+{rule}", content)
        self.assertIn(
            "+(typeattributeset netdomain (wukong_manager_app))",
            content,
        )
        self.assertIn(
            "+(allow wukong_manager_app wukong_system_powerd (unix_stream_socket (connectto)))",
            content,
        )
        self.assertNotIn("stark_vendor_sepolicy", content)

    def test_desktop_wk_manager_policy_has_one_canonical_stark_location(self):
        expected = (
            studio_core.STARK_ROOT
            / "WK_Manager/system/system/etc/selinux/stark_plat_sepolicy.cil"
        )

        self.assertEqual(studio_core.WK_MANAGER_SYSTEM_POLICY_PATCH, expected)

    def test_wk_manager_metrics_hook_patches_existing_init_rc(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            init_dir = unpack / "system_unpacked" / "system" / "system" / "etc" / "init" / "hw"
            init_dir.mkdir(parents=True)
            init = init_dir / "init.rc"
            init.write_text(
                "on post-fs-data\n"
                "    write /dev/null post-fs-data\n"
                "\n"
                "on boot\n"
                "    write /dev/null boot\n",
                encoding="utf-8",
            )
            legacy_rc = init_dir.parent / "wukong_manager_metrics.rc"
            legacy_rc.write_text("on boot\n    chmod 0444 /legacy\n", encoding="utf-8")

            mod_dir = Path("MOD/ColorOS_16.0.7/WK_Manager")
            first = studio_core._patch_wk_manager_metrics_init_rc(unpack, mod_dir)
            second = studio_core._patch_wk_manager_metrics_init_rc(unpack, mod_dir)

            content = init.read_text(encoding="utf-8")
            self.assertEqual(first, 2)
            self.assertEqual(second, 0)
            self.assertFalse(legacy_rc.exists())
            self.assertEqual(content.count(studio_core.WK_MANAGER_METRICS_INIT_BLOCK_START), 1)
            self.assertIn("on property:sys.boot_completed=1", content)
            self.assertIn("chmod 0444 /sys/class/kgsl/kgsl-3d0/gpuclk", content)
            self.assertIn(
                "chmod 0444 /sys/devices/platform/soc/3d00000.qcom,kgsl-3d0/devfreq/3d00000.qcom,kgsl-3d0/cur_freq",
                content,
            )
            self.assertLess(content.index("write /dev/null boot"), content.index(studio_core.WK_MANAGER_METRICS_INIT_BLOCK_START))
            self.assertNotIn(b"\r", init.read_bytes())

    def test_wk_manager_power_service_installs_payload_policy_and_repack_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            system = unpack / "system_unpacked" / "system" / "system"
            selinux = system / "etc" / "selinux"
            config = unpack / "system_unpacked" / "config"
            selinux.mkdir(parents=True)
            config.mkdir(parents=True)
            (selinux / "plat_sepolicy.cil").write_text(
                "\n".join(
                    f"(type {name})"
                    for name in (
                        "init",
                        "wukong_manager_app",
                        "tmpfs",
                        "appdomain_tmpfs",
                        "privapp_data_file",
                        "system_file",
                        "sysfs",
                        "sysfs_devices_system_cpu",
                        "sysfs_kgsl",
                        "sysfs_thermal",
                    )
                )
                + "\n(typeattribute domain)\n",
                encoding="utf-8",
            )
            (selinux / "plat_file_contexts").write_text(
                "/system/bin/sh u:object_r:shell_exec:s0\n",
                encoding="utf-8",
            )
            (selinux / "plat_seapp_contexts").write_text(
                "user=_app isPrivApp=true domain=priv_app type=privapp_data_file levelFrom=user\n",
                encoding="utf-8",
            )
            (config / "system_fs_config").write_text("system 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/system u:object_r:system_file:s0\n",
                encoding="utf-8",
            )

            source = root / "shared" / "WK_Manager"
            source_bin = source / "system" / "system" / "bin" / "wukong-system-powerd"
            source_rc = source / "system" / "system" / "etc" / "init" / "wukong-system-powerd.rc"
            source_policy = source / "system" / "system" / "etc" / "selinux"
            source_bin.parent.mkdir(parents=True)
            source_rc.parent.mkdir(parents=True)
            source_policy.mkdir(parents=True, exist_ok=True)
            elf = bytearray(64)
            elf[:6] = b"\x7fELF\x02\x01"
            elf[18:20] = (183).to_bytes(2, "little")
            source_bin.write_bytes(elf)
            source_rc.write_text(
                "service wukong-system-powerd /system/bin/wukong-system-powerd\n"
                "    class late_start\n"
                "    disabled\n"
                "    user system\n"
                "    group system everybody\n"
                "    socket wukong_system_power stream 0660 system everybody "
                "u:object_r:wukong_system_power_socket:s0\n"
                "on property:sys.boot_completed=1\n"
                "    start wukong-system-powerd\n",
                encoding="utf-8",
            )
            (source_policy / "stark_plat_seapp_contexts").write_text(
                "+user=_app isPrivApp=true name=com.wukong.manager "
                "domain=wukong_manager_app type=privapp_data_file levelFrom=user\n",
                encoding="utf-8",
            )
            (source_policy / "stark_plat_file_contexts").write_text(
                "+/system/bin/wukong-system-powerd u:object_r:wukong_system_powerd_exec:s0\n"
                "+/system/system/bin/wukong-system-powerd u:object_r:wukong_system_powerd_exec:s0\n"
                "+/dev/socket/wukong_system_power u:object_r:wukong_system_power_socket:s0\n",
                encoding="utf-8",
            )
            (source_policy / "stark_plat_sepolicy.cil").write_text(
                "+(type wukong_system_powerd)\n"
                "+(roletype object_r wukong_system_powerd)\n"
                "+(type wukong_system_powerd_exec)\n"
                "+(roletype object_r wukong_system_powerd_exec)\n"
                "+(type wukong_system_power_socket)\n"
                "+(roletype object_r wukong_system_power_socket)\n"
                "+(typeattributeset domain (wukong_system_powerd))\n"
                "+(allow wukong_manager_app wukong_system_powerd (unix_stream_socket (connectto)))\n"
                "+(allow wukong_system_powerd vendor_sysfs_kgsl (file (read write)))\n",
                encoding="utf-8",
            )

            vendor_image = root / "source_rom" / "vendor.img"
            vendor_image.parent.mkdir()
            vendor_image.write_bytes(b"vendor-erofs-fixture")

            def extract_vendor_policy(command, **_kwargs):
                output = Path(command[command.index("-o") + 1])
                extracted = output / "vendor" / "etc" / "selinux" / "vendor_sepolicy.cil"
                extracted.parent.mkdir(parents=True)
                extracted.write_text("(type vendor_sysfs_kgsl)\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="")

            with mock.patch.object(
                studio_core,
                "gettype",
                return_value="erofs",
            ), mock.patch.object(
                studio_core.subprocess,
                "run",
                side_effect=extract_vendor_policy,
            ) as run:
                first = studio_core._install_wk_manager_power_service(unpack, source)
                second = studio_core._install_wk_manager_power_service(unpack, source)

            daemon = system / "bin" / "wukong-system-powerd"
            service = system / "etc" / "init" / "wukong-system-powerd.rc"
            self.assertEqual(daemon.read_bytes(), bytes(elf))
            self.assertIn("user system", service.read_text(encoding="utf-8"))
            self.assertEqual(first["copied"], 2)
            self.assertEqual(second["copied"], 0)
            self.assertEqual(run.call_count, 2)
            extract_command = run.call_args.args[0]
            self.assertIn(str(vendor_image), extract_command)
            self.assertIn("-X", extract_command)
            self.assertIn("/etc/selinux/vendor_sepolicy.cil", extract_command)
            self.assertEqual(vendor_image.read_bytes(), b"vendor-erofs-fixture")
            self.assertFalse((unpack / "vendor_unpacked").exists())
            self.assertEqual(
                list(root.glob(".wkstudio-vendor-policy-*")),
                [],
            )
            self.assertIn("wukong_system_powerd", (selinux / "plat_sepolicy.cil").read_text(encoding="utf-8"))
            installed_policy = (selinux / "plat_sepolicy.cil").read_text(encoding="utf-8")
            for rule in studio_core.WK_MANAGER_ART_RUNTIME_POLICY_RULES:
                self.assertEqual(installed_policy.count(rule), 1)
            seapp = (selinux / "plat_seapp_contexts").read_text(encoding="utf-8")
            self.assertLess(seapp.index("name=com.wukong.manager"), seapp.index("domain=priv_app"))
            self.assertIn(
                "/dev/socket/wukong_system_power u:object_r:wukong_system_power_socket:s0",
                (selinux / "plat_file_contexts").read_text(encoding="utf-8"),
            )
            fs_config = (config / "system_fs_config").read_text(encoding="utf-8")
            self.assertIn("system/bin/wukong-system-powerd 0 2000 0755", fs_config)
            self.assertIn("system/etc/init/wukong-system-powerd.rc 0 0 0644", fs_config)
            contexts = (config / "system_file_contexts").read_text(encoding="utf-8")
            self.assertIn(
                "/system/bin/wukong-system-powerd u:object_r:wukong_system_powerd_exec:s0",
                contexts,
            )

    def test_wk_manager_power_policy_rejects_any_missing_patch_type(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "plat_sepolicy.cil"
            patch = root / "stark_plat_sepolicy.cil"
            policy.write_text(
                "(type wukong_manager_app)\n"
                "(type tmpfs)\n"
                "(type appdomain_tmpfs)\n"
                "(type privapp_data_file)\n"
                "(type system_file)\n",
                encoding="utf-8",
            )
            patch.write_text(
                "+(typetransition wukong_manager_app tmpfs file appdomain_tmpfs)\n"
                "+(allow wukong_manager_app appdomain_tmpfs (file (ioctl read write getattr map execute)))\n"
                "+(allowx wukong_manager_app appdomain_tmpfs (ioctl file ((range 0x7701 0x770b))))\n"
                "+(allow wukong_manager_app gpu_service (service_manager (find)))\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(studio_core.StudioError, "gpu_service"):
                studio_core._validate_wk_manager_power_policy_types(policy, patch)

    def test_wk_manager_power_policy_accepts_allow_target_typeattribute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "plat_sepolicy.cil"
            patch = root / "stark_plat_sepolicy.cil"
            policy.write_text(
                "(type wukong_manager_app)\n"
                "(type tmpfs)\n"
                "(type appdomain_tmpfs)\n"
                "(type privapp_data_file)\n"
                "(type system_file)\n"
                "(typeattribute sysfs_type)\n",
                encoding="utf-8",
            )
            patch.write_text(
                "+(typetransition wukong_manager_app tmpfs file appdomain_tmpfs)\n"
                "+(allow wukong_manager_app appdomain_tmpfs (file (ioctl read write getattr map execute)))\n"
                "+(allowx wukong_manager_app appdomain_tmpfs (ioctl file ((range 0x7701 0x770b))))\n"
                "+(allow wukong_manager_app sysfs_type (dir (read search)))\n",
                encoding="utf-8",
            )

            studio_core._validate_wk_manager_power_policy_types(policy, patch)

    def test_wk_manager_power_policy_accepts_vendor_symbols_from_stock_vendor_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "plat_sepolicy.cil"
            vendor_policy = root / "vendor_sepolicy.cil"
            patch = root / "stark_plat_sepolicy.cil"
            policy.write_text(
                "(type wukong_manager_app)\n"
                "(type tmpfs)\n"
                "(type appdomain_tmpfs)\n"
                "(type privapp_data_file)\n"
                "(type system_file)\n",
                encoding="utf-8",
            )
            vendor_policy.write_text(
                "(type vendor_sysfs_kgsl)\n"
                "(type vendor_sysfs_kgsl_gpuclk)\n",
                encoding="utf-8",
            )
            patch.write_text(
                "+(typetransition wukong_manager_app tmpfs file appdomain_tmpfs)\n"
                "+(allow wukong_manager_app appdomain_tmpfs (file (ioctl read write getattr map execute)))\n"
                "+(allowx wukong_manager_app appdomain_tmpfs (ioctl file ((range 0x7701 0x770b))))\n"
                "+(allow wukong_manager_app vendor_sysfs_kgsl (dir (read search)))\n"
                "+(allow wukong_manager_app vendor_sysfs_kgsl_gpuclk (file (read)))\n",
                encoding="utf-8",
            )

            studio_core._validate_wk_manager_power_policy_types(
                policy,
                patch,
                additional_policies=(vendor_policy,),
            )

    def test_wk_manager_gemini_patch_matches_register_settings_method_variants(self):
        method = (
            ".method private registerSettingsForOplusLocked(Landroid/content/ContentResolver;Landroid/database/ContentObserver;)V\n"
            "    .locals 3\n"
            "    invoke-static {}, Lcom/oplus/content/OplusFeatureConfigManager;->getInstacne()Lcom/oplus/content/OplusFeatureConfigManager;\n"
            "\n"
            "    move-result-object v0\n"
            "\n"
            "    const-string/jumbo v1, \"oplus.software.speech_assist_for_breeno\"\n"
            "\n"
            "    invoke-virtual {v0, v1}, Lcom/oplus/content/OplusFeatureConfigManager;->hasFeature(Ljava/lang/String;)Z\n"
            "\n"
            "    move-result v0\n"
            "\n"
            "    iput-boolean v0, p0, Lcom/android/server/policy/PhoneWindowManagerExtImpl;->mSpeechAsssistForBreeno:Z\n"
            "    return-void\n"
            ".end method\n"
        )

        patched = wk_manager_patcher._patch_gemini_button_in_register_settings(method)

        self.assertIn('const-string/jumbo v0, "gemini_button"', patched)
        self.assertIn("SettingsHelper;->getIntofSettings", patched)
        self.assertIn("iput-boolean v0, p0", patched)
        self.assertNotIn("oplus.software.speech_assist_for_breeno", patched)

    def test_wk_manager_gemini_patch_finds_register_settings_by_name(self):
        with tempfile.TemporaryDirectory() as temp:
            decoded = Path(temp)
            smali = decoded / "smali_classes2" / "com" / "android" / "server" / "policy" / "PhoneWindowManagerExtImpl.smali"
            smali.parent.mkdir(parents=True)
            smali.write_text(
                ".class public Lcom/android/server/policy/PhoneWindowManagerExtImpl;\n"
                ".super Ljava/lang/Object;\n"
                "\n"
                ".method private registerSettingsForOplusLocked(Landroid/content/ContentResolver;Landroid/database/ContentObserver;)V\n"
                "    .locals 3\n"
                "    invoke-static {}, Lcom/oplus/content/OplusFeatureConfigManager;->getInstacne()Lcom/oplus/content/OplusFeatureConfigManager;\n"
                "\n"
                "    move-result-object v0\n"
                "\n"
                "    const-string/jumbo v1, \"oplus.software.speech_assist_for_breeno\"\n"
                "\n"
                "    invoke-virtual {v0, v1}, Lcom/oplus/content/OplusFeatureConfigManager;->hasFeature(Ljava/lang/String;)Z\n"
                "\n"
                "    move-result v0\n"
                "\n"
                "    iput-boolean v0, p0, Lcom/android/server/policy/PhoneWindowManagerExtImpl;->mSpeechAsssistForBreeno:Z\n"
                "    return-void\n"
                ".end method\n",
                encoding="utf-8",
            )

            changed = wk_manager_patcher._edit_method_by_name(
                decoded,
                "com.android.server.policy.PhoneWindowManagerExtImpl",
                "registerSettingsForOplusLocked",
                '"gemini_button"',
                wk_manager_patcher._patch_gemini_button_in_register_settings,
            )

            self.assertTrue(changed)
            self.assertIn('"gemini_button"', smali.read_text(encoding="utf-8"))

    def test_mod_copy_normalizes_android_xml_but_preserves_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            xml = root / "feature.xml"
            apk = root / "fixture.apk"
            xml.write_bytes(b"<features>\r\n  <item/>\r\n</features>\r\n")
            apk.write_bytes(b"PK\r\nbinary\rpayload")

            self.assertTrue(studio_core._normalize_android_text_file_lf(xml))
            self.assertFalse(studio_core._normalize_android_text_file_lf(apk))
            self.assertEqual(xml.read_bytes(), b"<features>\n  <item/>\n</features>\n")
            self.assertEqual(apk.read_bytes(), b"PK\r\nbinary\rpayload")

    def test_global_props_mod_updates_my_product_and_keeps_vendor_protected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            product = unpack / "my_product_unpacked" / "my_product"
            vendor = unpack / "vendor_unpacked" / "vendor"
            product.mkdir(parents=True)
            vendor.mkdir(parents=True)
            product_prop = product / "build.prop"
            vendor_prop = vendor / "build.prop"
            product_prop.write_text(
                "persist.sys.timezone=Asia/Shanghai\n"
                "persist.sys.oplus.region=CN\n"
                "ro.product.locale=zh-CN\n",
                encoding="utf-8",
            )
            vendor_prop.write_text(
                "ro.vendor.oplus.camera.isSupportExplorer=0\n",
                encoding="utf-8",
            )
            result = studio_core.apply_selected_mods(
                ["Global_props"],
                unpack,
                {"soc": "86xx"},
                root,
            )
            self.assertEqual(result["modifiedPartitions"], ["my_product"])
            self.assertEqual(
                product_prop.read_text(encoding="utf-8"),
                "persist.sys.timezone=America/New_York\n"
                "persist.sys.oplus.region=US\n"
                "ro.product.locale=en-US\n",
            )
            self.assertEqual(
                vendor_prop.read_text(encoding="utf-8"),
                "ro.vendor.oplus.camera.isSupportExplorer=0\n",
            )

    def test_supported_mod_partitions_are_mutable_but_vendor_stays_passthrough(self):
        self.assertTrue(
            {"system", "system_ext", "my_product", "my_region", "my_stock"}.issubset(
                studio_core.MOD_PARTITIONS
            )
        )
        self.assertIn("vendor", studio_core.PASSTHROUGH_PARTITIONS)
        self.assertIn("vendor_dlkm", studio_core.PASSTHROUGH_PARTITIONS)
        for partition in studio_core.PASSTHROUGH_PARTITIONS:
            self.assertNotIn(partition, studio_core.MUTABLE_PARTITIONS)
            self.assertNotIn(partition, studio_core.MOD_PARTITIONS)
        with self.assertRaisesRegex(studio_core.StudioError, "Invalid debloat path"):
            studio_core.validate_debloat_paths(["vendor\\build.prop"])
        self.assertEqual(
            studio_core.validate_debloat_paths(["my_stock\\app\\Browser"]),
            ["my_stock\\app\\Browser"],
        )

    def test_stage_apply_mod_accepts_supported_non_system_partition(self):
        context = studio_core.BuildContext(
            job_id="multi-partition-mod",
            spec=studio_core.BuildSpec(romPath="fixture.zip", modNames=["Fixture"]),
            workspace=Path("workspace"),
            metadata={},
            device={},
        )
        with mock.patch.object(
            studio_core,
            "apply_selected_mods",
            return_value={"modifiedPartitions": ["system", "my_product"]},
        ):
            result = studio_core._stage_apply_mod(context)
        self.assertEqual(result["modifiedPartitions"], ["system", "my_product"])
        self.assertEqual(context.modified_partitions, {"system", "my_product"})

    def test_stage_apply_mod_detects_actual_passthrough_tree_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            vendor = workspace / "rom-unpack" / "vendor_unpacked" / "vendor"
            vendor.mkdir(parents=True)
            vendor_prop = vendor / "build.prop"
            vendor_prop.write_text("before\n", encoding="utf-8")
            context = studio_core.BuildContext(
                job_id="protected-partition-guard",
                spec=studio_core.BuildSpec(romPath="fixture.zip", modNames=["Fixture"]),
                workspace=workspace,
                metadata={},
                device={},
            )

            def mutate_vendor(*_args, **_kwargs):
                vendor_prop.write_text("after\n", encoding="utf-8")
                return {"modifiedPartitions": ["system"]}

            with mock.patch.object(
                studio_core,
                "apply_selected_mods",
                side_effect=mutate_vendor,
            ):
                with self.assertRaisesRegex(studio_core.StudioError, "actual MOD writes.*vendor"):
                    studio_core._stage_apply_mod(context)

    def test_block_ota_mod_removes_ota_lines_from_stock_features(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            stock_extension = (
                unpack
                / "my_stock_unpacked"
                / "my_stock"
                / "etc"
                / "extension"
            )
            stock_extension.mkdir(parents=True)
            feature_xml = stock_extension / "com.oplus.app-features.xml"
            feature_xml.write_text(
                "<extend_features>\n"
                "  <app_feature name=\"com.oplus.ota.print_log\" args=\"boolean:true\"/>\n"
                "  <app_feature name=\"com.oplus.system_update.keep\"/>\n"
                "  <app_feature name=\"com.oplus.RomUpdate.provider\"/>\n"
                "  <app_feature name=\"com.oplusos.sau\"/>\n"
                "  <app_feature name=\"com.android.launcher.DISABLE_OTA_ADD_BREENO_US_CARD\"/>\n"
                "</extend_features>\n",
                encoding="utf-8",
            )

            result = studio_core.apply_selected_mods(
                ["Block_ota"],
                unpack,
                {"soc": "86xx"},
                root,
            )
            self.assertEqual(result["modifiedPartitions"], ["my_stock"])
            self.assertEqual(result["stockOtaFeatureLines"], 4)
            content = feature_xml.read_text(encoding="utf-8")
            self.assertIn("com.oplus.system_update.keep", content)
            self.assertNotIn("com.oplusos.sau", content)
            self.assertNotIn("romupdate", content.lower())
            self.assertNotIn("ota", content.lower())

    def test_block_ota_is_listed_as_patch_only_mod(self):
        mod = next(mod for mod in studio_core.list_mods() if mod["name"] == "Block_ota")
        self.assertTrue(mod["ready"])
        self.assertTrue(mod["patchOnly"])
        self.assertEqual(mod["partitions"], [])
        self.assertIn("Block_ota", studio_core.preset_default_mods("lite"))

    def test_ai_global_removes_aiunit_only_for_coloros_1605(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "MOD_DIR", Path(temp) / "MOD"
        ):
            root = Path(temp)
            for version, should_remove in (("ColorOS_16.0.5", True), ("ColorOS_16.0.7", False)):
                mod_file = root / "MOD" / version / "Ai_global" / "my_stock" / "app" / "AiGlobal" / "AiGlobal.apk"
                mod_file.parent.mkdir(parents=True)
                mod_file.write_bytes(b"apk")

            for version, should_remove in (("ColorOS_16.0.5", True), ("ColorOS_16.0.7", False)):
                unpack = root / f"rom-unpack-{version}"
                stock = unpack / "my_stock_unpacked" / "my_stock"
                aiunit = stock / "app" / "AIUnit"
                aiunit.mkdir(parents=True)
                (aiunit / "AIUnit.apk").write_bytes(b"old")

                result = studio_core.apply_selected_mods(
                    ["Ai_global"],
                    unpack,
                    {"soc": "86xx"},
                    root / f"workspace-{version}",
                    version,
                )
                self.assertEqual(result["aiGlobalAiunitRemoved"], 1 if should_remove else 0)
                self.assertEqual(aiunit.exists(), not should_remove)

    def test_theme_cr_removes_duplicate_del_app_theme_space(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            stock = unpack / "my_stock_unpacked" / "my_stock"
            duplicate = stock / "del-app" / "KeKeThemeSpace"
            duplicate.mkdir(parents=True)
            (duplicate / "old.apk").write_bytes(b"old")
            (stock / "priv-app").mkdir(parents=True)

            result = studio_core.apply_selected_mods(
                ["Theme_cr"],
                unpack,
                {"soc": "86xx"},
                root,
            )
            self.assertEqual(result["themeCrRemoved"], 1)
            self.assertFalse(duplicate.exists())
            self.assertTrue(
                (stock / "priv-app" / "KeKeThemeSpace" / "KeKeThemeSpace.apk").is_file()
            )

    def test_fix_metis_is_lite_default_mod(self):
        self.assertIn("Fix_Metis", studio_core.LITE_DEFAULT_MODS)
        self.assertIn("Fix_Metis", studio_core.preset_default_mods("lite"))

    def test_wk_installer_is_lite_default_mod(self):
        self.assertIn("WK_Installer", studio_core.LITE_DEFAULT_MODS)
        self.assertIn("WK_Installer", studio_core.preset_default_mods("lite"))

    def test_build_branding_patches_display_version_and_market_name(self):
        with tempfile.TemporaryDirectory() as temp:
            unpack = Path(temp)
            manifest = unpack / "my_manifest_unpacked" / "my_manifest"
            product = unpack / "my_product_unpacked" / "my_product"
            manifest.mkdir(parents=True)
            product.mkdir(parents=True)
            manifest_prop = manifest / "build.prop"
            product_prop = product / "build.prop"
            manifest_prop.write_text(
                "ro.build.version.oplusrom.display=16.0.7\n"
                "ro.vendor.oplus.market.name=一加 Ace 5\n",
                encoding="utf-8",
            )
            product_prop.write_text(
                "ro.build.version.oplusrom.display=15.0\n"
                "ro.vendor.oplus.market.name=一加 Ace 5\n",
                encoding="utf-8",
            )

            result = studio_core.patch_build_branding(unpack, "Plus")

            self.assertEqual(
                result,
                {
                    "manifestDisplayVersion": 1,
                    "productDisplayVersion": 1,
                    "manifestBrand": 1,
                    "productBrand": 1,
                },
            )
            self.assertEqual(
                manifest_prop.read_text(encoding="utf-8"),
                "ro.build.version.oplusrom.display=16.0.7 | Plus | V3.4\n"
                "ro.vendor.oplus.market.name=OnePlus Ace 5\n",
            )
            self.assertEqual(
                product_prop.read_text(encoding="utf-8"),
                "ro.build.version.oplusrom.display=15.0 | Plus | V3.4\n"
                "ro.vendor.oplus.market.name=OnePlus Ace 5\n",
            )

    def test_custom_build_branding_uses_custom_edition(self):
        with tempfile.TemporaryDirectory() as temp:
            unpack = Path(temp)
            manifest = unpack / "my_manifest_unpacked" / "my_manifest"
            manifest.mkdir(parents=True)
            manifest_prop = manifest / "build.prop"
            manifest_prop.write_text(
                "ro.build.version.oplusrom.display=16.0.7 | Plus | V2.0\n",
                encoding="utf-8",
            )

            result = studio_core.patch_build_branding(unpack, "Custom")

            self.assertEqual(result["manifestDisplayVersion"], 1)
            self.assertEqual(
                manifest_prop.read_text(encoding="utf-8"),
                "ro.build.version.oplusrom.display=16.0.7 | Custom | V3.4\n",
            )

    def test_repack_brands_mutable_manifest_for_each_edition(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            manifest = (
                workspace
                / "rom-unpack"
                / "my_manifest_unpacked"
                / "my_manifest"
            )
            manifest.mkdir(parents=True)
            manifest_prop = manifest / "build.prop"
            manifest_prop.write_text(
                "ro.build.version.oplusrom.display=16.0.7\n",
                encoding="utf-8",
            )
            context = studio_core.BuildContext(
                job_id="job-both",
                spec=studio_core.BuildSpec(romPath="rom.zip", preset="lite"),
                workspace=workspace,
                metadata={},
                device={},
                modified_partitions={"system"},
            )

            with mock.patch.object(studio_core, "_run_command"), mock.patch.object(
                studio_core,
                "validate_rom_repack",
                return_value=True,
            ):
                lite = studio_core._stage_repack(context)
                self.assertEqual(
                    manifest_prop.read_text(encoding="utf-8"),
                    "ro.build.version.oplusrom.display=16.0.7 | Lite | V3.4\n",
                )
                context.spec = studio_core.BuildSpec(romPath="rom.zip", preset="resume")
                plus = studio_core._stage_repack(context)

            self.assertEqual(
                manifest_prop.read_text(encoding="utf-8"),
                "ro.build.version.oplusrom.display=16.0.7 | Plus | V3.4\n",
            )
            self.assertEqual(lite["buildBranding"]["manifestDisplayVersion"], 1)
            self.assertEqual(plus["buildBranding"]["manifestDisplayVersion"], 1)

    def test_repack_uses_selected_release_label_in_mutable_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            manifest = workspace / "rom-unpack" / "my_manifest_unpacked" / "my_manifest"
            manifest.mkdir(parents=True)
            manifest_prop = manifest / "build.prop"
            manifest_prop.write_text(
                "ro.build.version.oplusrom.display=16.0.7\n",
                encoding="utf-8",
            )
            context = studio_core.BuildContext(
                job_id="job-v4",
                spec=studio_core.BuildSpec(
                    romPath="rom.zip",
                    preset="lite",
                    modVersion="ColorOS_16.0.8",
                ),
                workspace=workspace,
                metadata={},
                device={},
                modified_partitions={"system"},
            )

            with mock.patch.object(studio_core, "_run_command"), mock.patch.object(
                studio_core,
                "validate_rom_repack",
                return_value=True,
            ):
                studio_core._stage_repack(context)

            self.assertEqual(
                manifest_prop.read_text(encoding="utf-8"),
                "ro.build.version.oplusrom.display=16.0.7 | Lite | V4.1\n",
            )

    def test_stage_repack_copies_passthrough_source_images(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "source_rom"
            source.mkdir()
            (source / "vendor.img").write_bytes(b"source-vendor")
            (source / "my_future.img").write_bytes(b"source-future")
            (source / "my_stock.img").write_bytes(b"source-stock")
            context = studio_core.BuildContext(
                job_id="fixture",
                spec=studio_core.BuildSpec(romPath="rom.zip"),
                workspace=workspace,
                metadata={},
                device={},
                modified_partitions={"system"},
            )

            with mock.patch.object(studio_core, "_run_command"), mock.patch.object(
                studio_core,
                "validate_rom_repack",
                return_value=True,
            ), mock.patch.object(
                studio_core,
                "source_dynamic_partition_names",
                return_value=["my_future", "my_stock", "system", "vendor"],
            ):
                result = studio_core._stage_repack(context)

            self.assertEqual((context.rom_repack / "vendor.img").read_bytes(), b"source-vendor")
            self.assertEqual((context.rom_repack / "my_stock.img").read_bytes(), b"source-stock")
            self.assertEqual(
                (context.rom_repack / "my_future.img").read_bytes(),
                b"source-future",
            )
            self.assertIn("vendor", result["passthroughPartitions"])
            self.assertIn("my_stock", result["passthroughPartitions"])
            self.assertIn("my_future", result["passthroughPartitions"])

    def test_static_firmware_images_are_not_dynamic_partitions(self):
        with tempfile.TemporaryDirectory() as temp:
            source_rom = Path(temp)
            for name in (
                "dsp.img",
                "dsp_a.img",
                "vm-bootsys.img",
                "vm-bootsys_b.img",
                "system.img",
            ):
                (source_rom / name).write_bytes(b"image")

            with mock.patch.object(
                studio_core,
                "partition_filesystem_type",
                return_value="ext4",
            ):
                partitions = studio_core.source_dynamic_partition_names(source_rom)

            self.assertEqual(partitions, ["system"])

    def test_static_firmware_images_are_staged_in_firmware_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = studio_core.BuildContext(
                job_id="static-firmware",
                spec=studio_core.BuildSpec(romPath="rom.zip"),
                workspace=root / "workspace",
                metadata={},
                device={},
            )
            context.source_rom.mkdir(parents=True)
            for name in studio_core.CORE_SOURCE_IMAGES | {
                "dsp.img",
                "dsp_a.img",
                "vm-bootsys.img",
                "vm-bootsys_b.img",
                "system.img",
            }:
                (context.source_rom / name).write_bytes(name.encode("ascii"))
            package_root = root / "package"

            with mock.patch.object(
                studio_core,
                "FLASH_ROOT",
                root / "missing-flash-template",
            ), mock.patch.object(
                studio_core,
                "partition_filesystem_type",
                return_value="ext4",
            ):
                studio_core._populate_shared_package_assets(context, package_root)

            firmware_files = {
                image.name for image in (package_root / "firmware-update").glob("*.img")
            }
            self.assertEqual(
                firmware_files,
                {"dsp.img", "dsp_a.img", "vm-bootsys.img", "vm-bootsys_b.img"},
            )

    def test_shared_package_cache_rebuilds_when_static_firmware_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = studio_core.BuildContext(
                job_id="stale-static-firmware-cache",
                spec=studio_core.BuildSpec(romPath="rom.zip"),
                workspace=root / "workspace",
                metadata={},
                device={},
            )
            context.source_rom.mkdir(parents=True)
            (context.source_rom / "dsp.img").write_bytes(b"dsp")
            shared = context.package_cache / "shared"
            (shared / "firmware-update").mkdir(parents=True)
            (shared / ".ready").write_text("ready\n", encoding="utf-8")

            def populate(_context, target_root):
                firmware = target_root / "firmware-update"
                firmware.mkdir(parents=True)
                (firmware / "dsp.img").write_bytes(b"dsp")
                return {"linked": 1, "copied": 0, "reused": 0}

            with mock.patch.object(
                studio_core,
                "_populate_shared_package_assets",
                side_effect=populate,
            ) as populate_assets:
                result = studio_core._ensure_shared_package_assets(context)

            self.assertFalse(result["reused"])
            populate_assets.assert_called_once_with(context, shared)
            self.assertTrue((shared / "firmware-update" / "dsp.img").is_file())

    def test_debloat_paths_reject_traversal(self):
        with self.assertRaisesRegex(studio_core.StudioError, "Invalid debloat path"):
            studio_core.validate_debloat_paths([r"system\..\outside"])

    def test_default_debloat_paths_read_shared_json_config(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "debloat.json"
            config.write_text(
                json.dumps({"version": 1, "default": [r"system\system\app\Browser"]}),
                encoding="utf-8",
            )
            with mock.patch.object(studio_core, "DEBLOAT_CONFIG_PATH", config):
                self.assertEqual(studio_core.default_debloat_paths(), [r"system\system\app\Browser"])
                self.assertEqual(studio_core.validate_debloat_paths(None), [r"system\system\app\Browser"])

    def test_delete_bloatware_resolves_catalog_paths_on_posix(self):
        with tempfile.TemporaryDirectory() as temp:
            rom_unpack = Path(temp) / "rom-unpack"
            browser = rom_unpack / "system_unpacked" / "system" / "system" / "app" / "Browser"
            browser.mkdir(parents=True)
            (browser / "Browser.apk").write_bytes(b"apk")

            result = studio_core.delete_bloatware(
                rom_unpack,
                [r"system\system\app\Browser"],
            )

            self.assertFalse(browser.exists())
            self.assertEqual(result["deleted"], 1)
            self.assertEqual(result["skipped"], 0)
            self.assertEqual(result["deletedPaths"], [r"system\system\app\Browser"])

    def test_debloat_stage_fails_when_no_requested_target_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            context = studio_core.BuildContext(
                job_id="debloat-zero",
                spec=studio_core.BuildSpec(
                    romPath="fixture.zip",
                    debloatPaths=[r"system\system\app\Missing"],
                ),
                workspace=Path(temp),
                metadata={},
                device={},
            )
            (context.rom_unpack / "system_unpacked" / "system").mkdir(parents=True)

            with self.assertRaisesRegex(studio_core.StudioError, "matched no files"):
                studio_core._stage_debloat(context)

    def test_shared_stark_mods_are_available_to_every_mod_version(self):
        with tempfile.TemporaryDirectory() as root:
            content = Path(root)
            version = content / "MOD" / "ColorOS_Test"
            (version / "Gapps" / "system").mkdir(parents=True)
            shared = content / "STARK"
            (shared / "WK_Manager" / "system").mkdir(parents=True)
            (shared / "WK_Installer" / "system_ext").mkdir(parents=True)

            mods = studio_core.list_mods("ColorOS_Test", mod_root=content / "MOD")

        by_name = {item["name"]: item for item in mods}
        self.assertTrue(by_name["WK_Manager"]["shared"])
        self.assertTrue(by_name["WK_Installer"]["shared"])
        self.assertFalse(by_name["Gapps"]["shared"])

    def test_refresh_plat_sepolicy_hash_repairs_bad_checksum_with_lf(self):
        with tempfile.TemporaryDirectory() as temp:
            unpack = Path(temp)
            selinux = unpack / "system_unpacked" / "system" / "system" / "etc" / "selinux"
            selinux.mkdir(parents=True)
            policy = selinux / "plat_sepolicy.cil"
            policy.write_text("(type system_file)\n", encoding="utf-8")
            checksum = selinux / "plat_sepolicy_and_mapping.sha256"
            checksum.write_bytes(b"bad-checksum\r\n")

            result = studio_core._refresh_plat_sepolicy_hash(unpack)

            digest = hashlib.sha256(policy.read_bytes()).hexdigest()
            self.assertEqual(result["sha256"], digest)
            self.assertEqual(result["profile"], "policy-only")
            self.assertEqual(checksum.read_bytes(), (digest + "\n").encode("ascii"))

    def test_fake_lock_injects_post_fs_data_block_and_repack_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack"
            system = unpack / "system_unpacked" / "system"
            config = unpack / "system_unpacked" / "config"
            (system / "system" / "bin").mkdir(parents=True)
            (system / "system" / "bin" / "sh").write_bytes(b"sh")
            (system / "system" / "etc" / "init" / "hw").mkdir(parents=True)
            init = system / "system" / "etc" / "init" / "hw" / "init.rc"
            init.write_text(
                "on post-fs-data\n"
                "    write /dev/null post-fs-data\n"
                "\n"
                "on boot\n"
                "    write /dev/null boot\n",
                encoding="utf-8",
            )
            selinux = system / "system" / "etc" / "selinux"
            selinux.mkdir(parents=True)
            (selinux / "plat_file_contexts").write_text(
                "/system/bin/sh u:object_r:shell_exec:s0\n",
                encoding="utf-8",
            )
            policy = selinux / "plat_sepolicy.cil"
            policy.write_text("(type system_file)\n", encoding="utf-8")
            checksum = selinux / "plat_sepolicy_and_mapping.sha256"
            checksum.write_text(
                hashlib.sha256(policy.read_bytes()).hexdigest() + "\n",
                encoding="utf-8",
            )
            config.mkdir()
            fs_config = config / "system_fs_config"
            fs_config.write_text(
                "/ 0 0 0755\n"
                "system 0 0 0755\n"
                "system/system 0 0 0755\n"
                "system/system/bin 0 0 0755\n"
                "system/system/bin/sh 0 2000 0755\n",
                encoding="utf-8",
            )
            file_contexts = config / "system_file_contexts"
            file_contexts.write_text(
                "/ u:object_r:system_file:s0\n"
                "/system/system/bin/sh u:object_r:shell_exec:s0\n",
                encoding="utf-8",
            )

            first = studio_core.apply_selected_mods(
                ["Fake_lock"],
                unpack,
                {"soc": "86xx"},
                root,
            )
            second = studio_core.apply_selected_mods(
                ["Fake_lock"],
                unpack,
                {"soc": "86xx"},
                root,
            )
            context = studio_core.BuildContext(
                job_id="fixture",
                spec=studio_core.BuildSpec(romPath="fixture.zip", modNames=["Fake_lock"]),
                workspace=root,
                metadata={"version_name": "fixture"},
                device={"soc": "86xx"},
            )
            with redirect_stdout(io.StringIO()):
                studio_core._stage_sync_configs(context)
                sync_repack_configs(unpack / "system_unpacked", "system")

            content = init.read_text(encoding="utf-8")
            self.assertEqual(content.count(studio_core.FAKE_LOCK_INIT_BLOCK_START), 1)
            self.assertLess(
                content.index("ro.boot.vbmeta.device_state locked"),
                content.index("on boot"),
            )
            self.assertIn("ro.secureboot.lockstate locked", content)
            self.assertIn("ro.bootloader OP5D2BL1-locked", content)
            self.assertIn("ro.product.brand_for_attestation OnePlus", content)
            self.assertIn("ro.product.manufacturer_for_attestation OnePlus", content)
            self.assertIn("ro.boot.vbmeta.invalidate_on_error yes", content)
            self.assertIn("ro.boot.vbmeta.device /dev/block/by-name/vbmeta_a", content)
            wk_binary = unpack / "system_unpacked" / "system" / "system" / "bin" / "wk"
            self.assertTrue(wk_binary.is_file())
            self.assertGreater(wk_binary.stat().st_size, 0)
            fs_config_content = fs_config.read_text(encoding="utf-8")
            self.assertIn("system/bin/wk 0 2000 0755", fs_config_content)
            self.assertIn("system/system/bin/wk 0 2000 0755", fs_config_content)
            contexts = file_contexts.read_text(encoding="utf-8")
            self.assertIn("/system/bin/wk u:object_r:wk_exec:s0", contexts)
            self.assertIn("/system/system/bin/wk u:object_r:wk_exec:s0", contexts)
            plat_contexts = (selinux / "plat_file_contexts").read_text(encoding="utf-8")
            self.assertIn("/system/bin/wk", plat_contexts)
            self.assertIn("/system/system/bin/wk", plat_contexts)
            self.assertIn(
                "(allow init wk_exec (file (read getattr map execute open execute_no_trans entrypoint)))",
                policy.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                checksum.read_text(encoding="utf-8"),
                hashlib.sha256(policy.read_bytes()).hexdigest() + "\n",
            )
            for path in (init, fs_config, file_contexts, policy, checksum):
                self.assertNotIn(b"\r", path.read_bytes(), str(path))
            self.assertEqual(first["mods"], ["Fake_lock"])
            self.assertEqual(second["mods"], ["Fake_lock"])

    def test_fix_noti_smali_patch_replaces_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            smali = (
                Path(temp)
                / "smali"
                / "com"
                / "android"
                / "server"
                / "notification"
                / "OplusNotificationManagerServiceExtImpl$NotificationUidObserver.smali"
            )
            smali.parent.mkdir(parents=True)
            smali.write_text(
                ".class public final Lfixture;\n"
                ".method private synthetic lambda$onUidGone$0(I)V\n"
                "    if-eqz v0, :cond_0\n"
                "    invoke-static {}, Lcom/android/server/notification/OplusNotificationManagerServiceExtImpl;->-$$Nest$sfgetARRAY_PKG_REMOVE_NOTIFICATION()[Ljava/lang/String;\n"
                "    return-void\n"
                ".end method\n",
                encoding="utf-8",
            )
            studio_core._patch_fix_noti_smali(Path(temp))
            content = smali.read_text(encoding="utf-8")
            self.assertNotIn("if-eqz v0,", content)
            self.assertIn("    nop\n\n    nop", content)

    def test_fix_noti_smali_patch_accepts_v1_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            smali = (
                Path(temp)
                / "smali"
                / "com"
                / "android"
                / "server"
                / "notification"
                / "OplusNotificationManagerServiceExtImpl$NotificationUidObserver.smali"
            )
            smali.parent.mkdir(parents=True)
            smali.write_text(
                ".class public final Lfixture;\n"
                ".method private synthetic lambda$onUidGone$0(I)V\n"
                "    if-eqz v1, :cond_0\n"
                "    invoke-static {}, Lcom/android/server/notification/OplusNotificationManagerServiceExtImpl;->-$$Nest$sfgetARRAY_PKG_REMOVE_NOTIFICATION()[Ljava/lang/String;\n"
                "    return-void\n"
                ".end method\n",
                encoding="utf-8",
            )
            studio_core._patch_fix_noti_smali(Path(temp))
            content = smali.read_text(encoding="utf-8")
            self.assertNotIn("if-eqz v1,", content)
            self.assertIn("    nop\n\n    nop", content)

    def test_jar_rewrite_preserves_original_entries_and_compression(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.jar"
            rebuilt = root / "rebuilt.jar"
            with zipfile.ZipFile(original, "w") as archive:
                archive.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
                archive.writestr(
                    "classes.dex",
                    b"original",
                    compress_type=zipfile.ZIP_STORED,
                )
            with zipfile.ZipFile(rebuilt, "w") as archive:
                archive.writestr(
                    "classes.dex",
                    b"patched",
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            studio_core._preserve_zip_entry_attributes(original, rebuilt)
            with zipfile.ZipFile(original, "r") as archive:
                self.assertEqual(archive.read("META-INF/MANIFEST.MF"), b"Manifest-Version: 1.0\n")
                self.assertEqual(archive.read("classes.dex"), b"patched")
                self.assertEqual(archive.getinfo("classes.dex").compress_type, zipfile.ZIP_STORED)

    def test_apktool_patch_reuses_matching_decoded_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jar = root / "oplus-services.jar"
            first_work = root / "Fix_noti"
            second_work = root / "WK_Manager" / "oplus-services"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("classes.dex", b"stock", compress_type=zipfile.ZIP_STORED)

            commands = []

            def fake_command(command, *, cwd=studio_core.ROOT_DIR):
                commands.append(command)
                if command[3] == "d":
                    decoded = Path(command[-1])
                    decoded.mkdir(parents=True)
                    with zipfile.ZipFile(jar) as archive:
                        (decoded / "classes.dex").write_bytes(archive.read("classes.dex"))
                elif command[3] == "b":
                    decoded = Path(command[4])
                    rebuilt = Path(command[-1])
                    with zipfile.ZipFile(rebuilt, "w") as archive:
                        archive.writestr("classes.dex", (decoded / "classes.dex").read_bytes())

            def patch(decoded: Path):
                dex = decoded / "classes.dex"
                dex.write_bytes(dex.read_bytes() + b"-patched")
                return {"patchedMethods": 1}

            with mock.patch.object(studio_core, "_run_command", side_effect=fake_command):
                first = studio_core._patch_jar_with_apktool(jar, first_work, patch)
                second = studio_core._patch_jar_with_apktool(
                    jar,
                    second_work,
                    patch,
                    reuse_decoded_from=first_work,
                )

            decode_commands = [command for command in commands if command[3] == "d"]
            self.assertEqual(len(decode_commands), 1)
            self.assertFalse(first["decodedReused"])
            self.assertTrue(second["decodedReused"])
            with zipfile.ZipFile(jar) as archive:
                self.assertEqual(archive.read("classes.dex"), b"stock-patched-patched")

    def test_wk_manager_reuses_fix_noti_decode_only_for_oplus_services(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reuse = root / "mod-tools" / "Fix_noti"
            calls = []

            def fake_patch(jar, work_dir, patcher, **kwargs):
                calls.append((jar.name, work_dir, kwargs.get("reuse_decoded_from")))
                return {"jar": jar.name, "patchedMethods": 0, "importedSmali": 0}

            with mock.patch.object(studio_core, "_patch_jar_with_apktool", side_effect=fake_patch):
                studio_core._patch_wk_manager_jars(root / "rom-unpack", root, reuse)

            self.assertEqual([call[0] for call in calls], ["framework.jar", "services.jar", "oplus-services.jar"])
            self.assertIsNone(calls[0][2])
            self.assertIsNone(calls[1][2])
            self.assertEqual(calls[2][2], reuse)

    def test_apply_mod_combines_fix_noti_with_wk_manager_oplus_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mods = [
                {"name": "Fix_noti", "partitions": []},
                {"name": "WK_Manager", "partitions": []},
            ]
            calls = []
            progress_events = []

            def fake_patch(jar, work_dir, patcher, **kwargs):
                calls.append((jar.name, work_dir, kwargs))
                callback = kwargs.get("status_callback")
                if callback:
                    callback(f"Giải mã {jar.name}")
                    callback(f"Đóng gói {jar.name}")
                return {
                    "jar": jar.name,
                    "patchedMethods": 0,
                    "importedSmali": 0,
                    "decodedReused": False,
                }

            with mock.patch.object(studio_core, "validate_mods", return_value=mods), mock.patch.object(
                studio_core, "_patch_jar_with_apktool", side_effect=fake_patch
            ), mock.patch.object(
                studio_core, "_patch_wk_manager_metrics_init_rc", return_value=0
            ), mock.patch.object(
                studio_core,
                "_install_wk_manager_power_service",
                return_value={"copied": 0, "copiedBytes": 0, "patched": 0},
            ), mock.patch.object(
                studio_core, "_refresh_plat_sepolicy_hash", return_value={"sha256": "fixture"}
            ):
                result = studio_core.apply_selected_mods(
                    ["Fix_noti", "WK_Manager"],
                    root / "rom-unpack",
                    None,
                    root,
                    progress_callback=progress_events.append,
                )

            self.assertEqual([call[0] for call in calls], ["framework.jar", "services.jar", "oplus-services.jar"])
            self.assertEqual(result["patched"], 1)
            self.assertEqual(result["mods"], ["Fix_noti", "WK_Manager"])
            self.assertEqual(progress_events[-1]["progress"], 100)
            self.assertTrue(any("oplus-services.jar" in event["progressMessage"] for event in progress_events))
            self.assertEqual(
                [event["progress"] for event in progress_events],
                sorted(event["progress"] for event in progress_events),
            )

    def test_wk_manager_is_visible_and_ready(self):
        mod = next(mod for mod in studio_core.list_mods() if mod["name"] == "WK_Manager")
        self.assertTrue(mod["ready"])
        self.assertEqual(studio_core.validate_mods(["WK_Manager"])[0]["name"], "WK_Manager")

    def test_inspect_small_fixture_rom(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "ROM_BUILD_DONE", Path(temp) / "out"
        ):
            rom = Path(temp) / "fixture.zip"
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=16.0.7.200(CN01)\n",
                )
                archive.writestr("payload.bin", b"fixture")
            result = studio_core.inspect_rom(rom, enforce_space=False)
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["device"]["product_name"], "PKG110")

    def test_preflight_rejects_missing_payload_and_corrupt_zip(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "ROM_BUILD_DONE", Path(temp) / "out"
        ):
            missing_payload = Path(temp) / "missing-payload.zip"
            with zipfile.ZipFile(missing_payload, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=fixture\n",
                )
            corrupt = Path(temp) / "corrupt.zip"
            corrupt.write_bytes(b"not a zip")
            self.assertTrue(any(
                "payload.bin is missing" in message
                for message in studio_core.inspect_rom(missing_payload, enforce_space=False)["errors"]
            ))
            self.assertIn(
                "ROM is not a valid ZIP file",
                studio_core.inspect_rom(corrupt, enforce_space=False)["errors"],
            )

    def test_apply_mod_target_requires_mod_selection(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "ROM_BUILD_DONE", Path(temp) / "out"
        ):
            rom = Path(temp) / "fixture.zip"
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "oplus_product_name=PKG110\noplus_version_name=fixture\n",
                )
                archive.writestr("payload.bin", b"fixture")
            result = studio_core.inspect_rom(
                rom,
                enforce_space=False,
                required_steps=["apply_mod"],
            )
            self.assertFalse(result["ok"])
            self.assertIn("Apply MOD step requires a valid MOD selection", result["errors"])

    def test_final_validator_rejects_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "invalid.zip"
            with zipfile.ZipFile(artifact, "w") as archive:
                archive.writestr("images/boot.img", b"x")
            with self.assertRaisesRegex(studio_core.StudioError, "missing images"):
                studio_core.validate_final_zip(artifact)

    def test_super_validator_rejects_truncated_sparse_chunk(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "super.img"
            header = struct.pack(
                "<I4H4I",
                0xED26FF3A,
                1,
                0,
                28,
                12,
                4096,
                2,
                1,
                0,
            )
            chunk = struct.pack("<2H2I", 0xCAC1, 0, 2, 12 + 8192)
            artifact.write_bytes(header + chunk + b"x" * 5000)
            with self.assertRaisesRegex(studio_core.StudioError, "Truncated sparse image"):
                studio_core.validate_super(artifact)

    def test_final_validator_rejects_manifest_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "invalid-hash.zip"
            images = sorted(studio_core.REQUIRED_IMAGES)
            with zipfile.ZipFile(artifact, "w", zipfile.ZIP_STORED) as archive:
                for name in images:
                    archive.writestr(f"images/{name}", name.encode("utf-8"))
                archive.writestr(
                    "wukong_md5_hashes.txt",
                    "\n".join(f"{'0' * 32}  {name}" for name in images) + "\n",
                )
            with mock.patch.object(
                studio_core,
                "_partition_names_from_sparse_stream",
                return_value={f"{name}_a" for name in studio_core.PARTITIONS},
            ), self.assertRaisesRegex(studio_core.StudioError, "hash mismatch"):
                studio_core.validate_final_zip(artifact, mode="deep")

    def test_final_validator_rejects_crc_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "invalid-crc.zip"
            images = sorted(studio_core.REQUIRED_IMAGES)
            with zipfile.ZipFile(artifact, "w", zipfile.ZIP_STORED) as archive:
                for name in images:
                    data = name.encode("utf-8")
                    archive.writestr(f"images/{name}", data)
                archive.writestr(
                    "wukong_md5_hashes.txt",
                    "\n".join(
                        f"{hashlib.md5(name.encode('utf-8')).hexdigest()}  {name}"
                        for name in images
                    )
                    + "\n",
                )
            with zipfile.ZipFile(artifact, "r") as archive:
                info = archive.getinfo("images/boot.img")
                data_offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
            with artifact.open("r+b") as handle:
                handle.seek(data_offset)
                original = handle.read(1)
                handle.seek(data_offset)
                handle.write(bytes([original[0] ^ 0xFF]))
            with mock.patch.object(
                studio_core,
                "_partition_names_from_sparse_stream",
                return_value={f"{name}_a" for name in studio_core.PARTITIONS},
            ), self.assertRaisesRegex(studio_core.StudioError, "corrupt"):
                studio_core.validate_final_zip(artifact, mode="deep")

    def test_fast_final_validator_skips_full_artifact_hash_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "fast.zip"
            images = sorted(studio_core.REQUIRED_IMAGES)
            with zipfile.ZipFile(artifact, "w", zipfile.ZIP_STORED) as archive:
                for name in images:
                    archive.writestr(f"images/{name}", name.encode("utf-8"))
                archive.writestr(
                    "wukong_md5_hashes.txt",
                    "\n".join(f"{'0' * 32}  {name}" for name in images) + "\n",
                )
            with mock.patch.object(
                studio_core,
                "_partition_names_from_sparse_stream",
                return_value={f"{name}_a" for name in studio_core.PARTITIONS},
            ), mock.patch.object(studio_core.hashlib, "md5") as md5:
                report = studio_core.validate_final_zip(artifact, mode="fast")

            md5.assert_not_called()
            self.assertEqual(report["validationMode"], "fast")
            self.assertFalse(report["crcVerified"])

    def test_fast_final_validator_rejects_missing_manifest_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "missing-manifest-entry.zip"
            images = sorted(studio_core.REQUIRED_IMAGES)
            with zipfile.ZipFile(artifact, "w", zipfile.ZIP_STORED) as archive:
                for name in images:
                    archive.writestr(f"images/{name}", name.encode("utf-8"))
                archive.writestr(
                    "wukong_md5_hashes.txt",
                    "\n".join(f"{'0' * 32}  {name}" for name in images[:-1]) + "\n",
                )
            with self.assertRaisesRegex(studio_core.StudioError, "missing artifact hashes"):
                studio_core.validate_final_zip(artifact, mode="fast")

    def test_fast_final_validator_rejects_duplicate_artifact_names(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "duplicate.zip"
            images = sorted(studio_core.REQUIRED_IMAGES)
            with zipfile.ZipFile(artifact, "w", zipfile.ZIP_STORED) as archive:
                for name in images:
                    archive.writestr(f"images/{name}", name.encode("utf-8"))
                archive.writestr("firmware-update/boot.img", b"duplicate")
                archive.writestr(
                    "wukong_md5_hashes.txt",
                    "\n".join(f"{'0' * 32}  {name}" for name in images) + "\n",
                )
            with self.assertRaisesRegex(studio_core.StudioError, "duplicate artifact name"):
                studio_core.validate_final_zip(artifact, mode="fast")

    def test_fast_final_validator_rejects_invalid_packaged_super_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "invalid-super.zip"
            images = sorted(studio_core.REQUIRED_IMAGES)
            with zipfile.ZipFile(artifact, "w", zipfile.ZIP_STORED) as archive:
                for name in images:
                    archive.writestr(f"images/{name}", name.encode("utf-8"))
                archive.writestr(
                    "wukong_md5_hashes.txt",
                    "\n".join(f"{'0' * 32}  {name}" for name in images) + "\n",
                )
            with mock.patch.object(
                studio_core,
                "_partition_names_from_sparse_stream",
                return_value=set(),
            ), self.assertRaisesRegex(studio_core.StudioError, "missing partitions"):
                studio_core.validate_final_zip(artifact, mode="fast")

    def test_failed_compression_never_publishes_partial_zip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_root = root / "package"
            package_root.mkdir()
            (package_root / "fixture.txt").write_text("fixture", encoding="utf-8")
            output = root / "out" / "fixture.zip"
            context = studio_core.BuildContext(
                job_id="job-1",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=root / "workspace",
                metadata={},
                device={},
            )

            def fail_package(command, _context):
                Path(command[-2]).write_bytes(b"partial")
                raise studio_core.StudioError("compression failed")

            with mock.patch.object(studio_core, "ROM_BUILD_DONE", output.parent), mock.patch.object(
                studio_core.shutil, "which", return_value="7z"
            ), mock.patch.object(studio_core, "_run_7z_package", side_effect=fail_package):
                with self.assertRaisesRegex(studio_core.StudioError, "compression failed"):
                    studio_core._compress_prepared_package(package_root, output, context)

            self.assertFalse(output.exists())
            self.assertEqual(list(output.parent.glob("*.partial")), [])

    def test_real_super_zip_and_final_validator_smoke(self):
        bin_dir = studio_core.BIN_ROOT / "Windows" / "AMD64"
        if not (bin_dir / "lpmake.exe").is_file() or not (bin_dir / "7z.exe").is_file():
            self.skipTest("Bundled lpmake or 7-Zip is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            partitions_dir = root / "partitions"
            package_root = root / "package"
            images_dir = package_root / "images"
            partitions_dir.mkdir()
            images_dir.mkdir(parents=True)
            partition_files = []
            for name in studio_core.PARTITIONS:
                image = partitions_dir / f"{name}.img"
                image.write_bytes(name.encode("ascii").ljust(4096, b"\0"))
                partition_files.append(str(image))
            super_size = 64 * 1024 * 1024
            super_img = images_dir / "super.img"
            self.assertTrue(
                super_tool.SuperPacker().pack(
                    str(super_img),
                    super_size,
                    "qti_dynamic_partitions",
                    24 * 1024 * 1024,
                    partition_files,
                    sparse=True,
                    is_ab=True,
                )
            )
            for name in studio_core.REQUIRED_IMAGES - {"super.img"}:
                (images_dir / name).write_bytes(name.encode("ascii"))
            manifest = package_root / "wukong_md5_hashes.txt"
            manifest.write_text(
                "".join(
                    f"{hashlib.md5(path.read_bytes()).hexdigest()}  {path.name}\n"
                    for path in sorted(images_dir.iterdir(), key=lambda item: item.name)
                ),
                encoding="utf-8",
            )
            output = root / "out" / "fixture.zip"
            context = studio_core.BuildContext(
                job_id="smoke-job",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=root / "workspace",
                metadata={},
                device={"SuperSize": super_size},
            )

            report = studio_core._compress_prepared_package(package_root, output, context)

            self.assertTrue(output.is_file())
            self.assertEqual(set(report["partitions"]), {f"{name}_a" for name in studio_core.PARTITIONS} | {f"{name}_b" for name in studio_core.PARTITIONS})
            with zipfile.ZipFile(output, "r") as archive:
                self.assertIsNone(archive.testzip())

    def test_package_copies_source_vendor_boot_without_patch_step(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (source / "vendor_boot.img").write_bytes(b"source-vendor-boot")
            (build / "super.img").write_bytes(b"super")
            context = studio_core.BuildContext(
                job_id="abcd1234",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )
            with mock.patch.object(studio_core, "ROOT_DIR", root), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", root / "out"
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=None
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": ["vendor_boot.img"]}
            ):
                result = studio_core._stage_package(context)
            with zipfile.ZipFile(result["outputZip"], "r") as archive:
                self.assertEqual(archive.read("images/vendor_boot.img"), b"source-vendor-boot")
                info = archive.read("info.txt").decode("utf-8").splitlines()
                self.assertEqual(info[3], "Lite")
                self.assertEqual(info[4], "V3.4")
            self.assertIn("Wukong_Lite_V3.4_fixture_China_Stable_abcd1234.zip", result["outputZip"])
            self.assertFalse(context.rom_build.exists())
            self.assertTrue(result["romBuildCleaned"])

    def test_package_custom_build_writes_custom_info_and_zip_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (source / "vendor_boot.img").write_bytes(b"source-vendor-boot")
            (build / "super.img").write_bytes(b"super")
            context = studio_core.BuildContext(
                job_id="abcd1234",
                spec=studio_core.BuildSpec(romPath="fixture.zip", preset="custom"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )
            with mock.patch.object(studio_core, "ROOT_DIR", root), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", root / "out"
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=None
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": ["vendor_boot.img"]}
            ):
                result = studio_core._stage_package(context)
            with zipfile.ZipFile(result["outputZip"], "r") as archive:
                info = archive.read("info.txt").decode("utf-8").splitlines()
                self.assertEqual(info[3], "Custom")
                self.assertEqual(info[4], "V3.4")
            self.assertIn("Wukong_Custom_V3.4_fixture_China_Stable_abcd1234.zip", result["outputZip"])

    def test_package_coloros_800_writes_v4_info_and_zip_name(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (source / "vendor_boot.img").write_bytes(b"source-vendor-boot")
            (build / "super.img").write_bytes(b"super")
            context = studio_core.BuildContext(
                job_id="abcd1234",
                spec=studio_core.BuildSpec(
                    romPath="fixture.zip",
                    preset="lite",
                    modVersion="ColorOS_16.0.8",
                ),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )
            with mock.patch.object(studio_core, "ROOT_DIR", root), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", root / "out"
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=None
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": ["vendor_boot.img"]}
            ):
                result = studio_core._stage_package(context)
            with zipfile.ZipFile(result["outputZip"], "r") as archive:
                info = archive.read("info.txt").decode("utf-8").splitlines()
                self.assertEqual(info[4], "V4.1")
            self.assertIn("Wukong_Lite_V4.1_fixture_China_Stable_abcd1234.zip", result["outputZip"])

    def test_package_moves_generated_super_and_preserves_source_images(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (source / "vendor_boot.img").write_bytes(b"source-vendor-boot")
            (build / "super.img").write_bytes(b"super")
            context = studio_core.BuildContext(
                job_id="abcd1234",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )
            with mock.patch.object(studio_core, "ROOT_DIR", root), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", root / "out"
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=None
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": ["vendor_boot.img"]}
            ):
                result = studio_core._stage_package(context)

            self.assertFalse((build / "super.img").exists())
            self.assertTrue((source / "vendor_boot.img").is_file())
            self.assertEqual(result["placedImages"]["super.img"], "moved")
            self.assertIn(result["placedImages"]["vendor_boot.img"], {"linked", "copied"})

    def test_reused_package_assets_skip_second_vbmeta_patch(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "source_rom"
            source.mkdir()
            header = bytearray(124)
            header[:4] = b"AVB0"
            for name in studio_core.VBMETA_IMAGE_NAMES:
                (source / name).write_bytes(header)
            context = studio_core.BuildContext(
                job_id="fixture",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={},
                device={},
                reuse_package_assets=True,
            )

            first = studio_core._stage_vbmeta(context)
            for name in studio_core.VBMETA_IMAGE_NAMES:
                studio_core._stage_generated_image(
                    context,
                    workspace / "Build" / name,
                    workspace / "ROM_build" / "images" / name,
                    "vbmeta image",
                    cache_name=name,
                )
            shutil.rmtree(workspace / "Build")
            with mock.patch.object(studio_core, "_run_command") as run_command:
                second = studio_core._stage_vbmeta(context)

            run_command.assert_not_called()
            self.assertFalse(first["vbmeta"]["vbmeta.img"]["reused"])
            self.assertTrue(second["vbmeta"]["vbmeta.img"]["reused"])

    def test_package_uses_7z_fast_compression_with_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            seven_zip = root / "7z.exe"
            seven_zip.write_bytes(b"fixture")
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img", "vendor_boot.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (build / "super.img").write_bytes(b"super")
            progress_events = []
            captured = {}
            context = studio_core.BuildContext(
                job_id="abcd1234",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
                progress_callback=progress_events.append,
            )

            def fake_7z(command, package_context, *, cwd=studio_core.ROOT_DIR):
                captured["command"] = command
                captured["context"] = package_context
                Path(command[-2]).write_bytes(b"zip")
                package_context.progress_callback({"progress": 42, "progressMessage": "ZIP 42%"})

            with mock.patch.object(studio_core, "ROOT_DIR", root), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", root / "out"
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=str(seven_zip)
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": []}
            ), mock.patch.object(
                studio_core, "_run_7z_package", side_effect=fake_7z
            ):
                result = studio_core._stage_package(context)

            self.assertIn("-mx1", captured["command"])
            self.assertIn("-bsp1", captured["command"])
            self.assertIs(captured["context"], context)
            self.assertEqual(progress_events[0]["progress"], 0)
            self.assertEqual(progress_events[1]["progress"], 42)
            self.assertEqual(result["progress"], 100)
            self.assertGreaterEqual(result["validation"]["compressionSeconds"], 0)
            self.assertGreaterEqual(result["validation"]["validationSeconds"], 0)
            self.assertEqual(result["validation"]["validationMode"], "fast")
            self.assertTrue(any(event["progress"] == 95 for event in progress_events))
            self.assertEqual(progress_events[-1]["progress"], 100)

    def test_async_package_stages_then_completes_in_background(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            jobs = root / ".wkstudio" / "jobs"
            packages = root / ".wkstudio" / "packages"
            output = root / "out"
            source.mkdir(parents=True)
            build.mkdir(parents=True)
            jobs.mkdir(parents=True)
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {"vbmeta.img", "vendor_boot.img"}:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (build / "super.img").write_bytes(b"super")
            context = studio_core.BuildContext(
                job_id="async1234",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )

            with mock.patch.dict(
                "os.environ", {"WUKONG_STUDIO_ASYNC_PACKAGE": "1"}, clear=False
            ), mock.patch.object(
                studio_core, "ROOT_DIR", root
            ), mock.patch.object(
                studio_core, "JOBS_DIR", jobs
            ), mock.patch.object(
                studio_core, "PACKAGE_STAGING_DIR", packages
            ), mock.patch.object(
                studio_core, "ROM_BUILD_DONE", output
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": []}
            ), mock.patch.object(
                studio_core.shutil, "which", return_value=None
            ):
                staged = studio_core._stage_package(context)
                task_file = Path(staged["taskFile"])
                staging_dir = Path(staged["stagingDir"])
                self.assertTrue(staged["packagingPending"])
                self.assertGreaterEqual(staged["stagingSeconds"], 0)
                self.assertTrue(task_file.is_file())
                self.assertTrue(staging_dir.is_dir())
                self.assertFalse(Path(staged["outputZip"]).exists())

                completed = studio_core.complete_package_task(task_file)

            self.assertTrue(Path(completed["outputZip"]).is_file())
            self.assertEqual(completed["timing"]["stagingSeconds"], staged["stagingSeconds"])
            self.assertGreaterEqual(completed["timing"]["compressionSeconds"], 0)
            self.assertGreaterEqual(completed["timing"]["validationSeconds"], 0)
            self.assertAlmostEqual(
                completed["timing"]["totalSeconds"],
                completed["timing"]["stagingSeconds"]
                + completed["timing"]["compressionSeconds"]
                + completed["timing"]["validationSeconds"],
                places=3,
            )
            self.assertEqual(completed["timing"]["validationMode"], "fast")
            self.assertFalse(staging_dir.exists())
            self.assertFalse(task_file.exists())

    def test_vendor_boot_stage_patches_header_and_repack_output(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "source_rom"
            source.mkdir()
            (source / "vendor_boot.img").write_bytes(b"vendor-boot")
            context = studio_core.BuildContext(
                job_id="vendor-boot",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={},
                device={},
            )

            def fake_run(command, *, cwd=studio_core.ROOT_DIR):
                if "unpack" in command:
                    unpacked = context.rom_unpack / "vendor_boot"
                    unpacked.mkdir(parents=True)
                    (unpacked / "header").write_text(
                        "vendor_boot header\n"
                        "androidboot.foo=bar androidboot.verifiedbootstate=orange\n",
                        encoding="utf-8",
                    )
                if "repack" in command:
                    context.build_dir.mkdir()
                    (context.build_dir / "vendor_boot.img").write_bytes(b"patched-vendor-boot")

            with mock.patch.object(studio_core, "_run_command", side_effect=fake_run):
                result = studio_core._stage_vendor_boot(context)

            header_line = (
                context.rom_unpack / "vendor_boot" / "header"
            ).read_text(encoding="utf-8").splitlines()[1]
            self.assertEqual(result["vendorBoot"], str(context.build_dir / "vendor_boot.img"))
            self.assertIn("androidboot.verifiedbootstate=green", header_line)
            self.assertNotIn("androidboot.verifiedbootstate=orange", header_line)
            self.assertEqual((context.build_dir / "vendor_boot.img").read_bytes(), b"patched-vendor-boot")

    def test_package_rejects_stock_vbmeta_for_modified_signed_partition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            source = workspace / "source_rom"
            build = workspace / "Build"
            repack = workspace / "rom-repack"
            source.mkdir(parents=True)
            build.mkdir()
            repack.mkdir()
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {
                "vbmeta.img",
                "vendor_boot.img",
            }:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            (build / "super.img").write_bytes(b"super")
            (repack / studio_core.PATCHED_VBMETA_MARKER).write_text(
                "my_product\n",
                encoding="utf-8",
            )
            context = studio_core.BuildContext(
                job_id="abcd1234",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )
            with mock.patch.object(studio_core, "ROOT_DIR", root):
                with self.assertRaisesRegex(studio_core.StudioError, "require the patch_vbmeta"):
                    studio_core._stage_package(context)

    def test_stage_vbmeta_patches_primary_vbmeta_only(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "source_rom"
            source.mkdir()
            header = bytearray(124)
            header[:4] = b"AVB0"
            for name in studio_core.VBMETA_IMAGE_NAMES:
                (source / name).write_bytes(header)
            context = studio_core.BuildContext(
                job_id="fixture",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={},
                device={},
            )

            result = studio_core._stage_vbmeta(context)

            self.assertEqual(set(result["vbmeta"]), set(studio_core.VBMETA_IMAGE_NAMES))
            for name in studio_core.VBMETA_IMAGE_NAMES:
                output = workspace / "Build" / name
                self.assertEqual(studio_core.validate_patched_vbmeta(output), 0x03)

    def test_package_keeps_stock_chained_vbmeta_images_for_modified_partitions(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            source = workspace / "source_rom"
            build = workspace / "Build"
            repack = workspace / "rom-repack"
            source.mkdir()
            build.mkdir()
            repack.mkdir()
            for name in set(studio_core.CORE_SOURCE_IMAGES) | {
                "vbmeta.img",
                "vendor_boot.img",
            }:
                (source / name).write_bytes(f"source-{name}".encode("utf-8"))
            header = bytearray(124)
            header[:4] = b"AVB0"
            header[120:124] = (3).to_bytes(4, "big")
            (build / "vbmeta.img").write_bytes(header)
            (build / "super.img").write_bytes(b"super")
            (repack / studio_core.PATCHED_VBMETA_MARKER).write_text(
                "vendor\n",
                encoding="utf-8",
            )
            context = studio_core.BuildContext(
                job_id="fixture",
                spec=studio_core.BuildSpec(romPath="fixture.zip"),
                workspace=workspace,
                metadata={"version_name": "fixture", "product_name": "PKG110"},
                device={"name": "Fixture", "product_name": "PKG110"},
            )
            with mock.patch.object(
                studio_core, "ROM_BUILD_DONE", workspace / "out"
            ), mock.patch.object(
                studio_core, "validate_super", return_value={"partitions": []}
            ), mock.patch.object(
                studio_core, "validate_final_zip", return_value={"images": []}
            ):
                result = studio_core._stage_package(context)
            with zipfile.ZipFile(result["outputZip"], "r") as archive:
                self.assertEqual(
                    archive.read("images/vbmeta_system.img"),
                    b"source-vbmeta_system.img",
                )
                self.assertEqual(
                    archive.read("images/vbmeta_vendor.img"),
                    b"source-vbmeta_vendor.img",
                )

    def test_extent_writer_splits_data_and_zero_uses_block_size(self):
        extents = [
            SimpleNamespace(start_block=1, num_blocks=1),
            SimpleNamespace(start_block=4, num_blocks=2),
        ]
        writer = RecordingWriter()
        _write_extents(writer, extents, 4, b"abcdefghijkl")
        self.assertEqual(writer.writes, [(4, b"abcd"), (16, b"efghijkl")])
        writer = RecordingWriter()
        _write_zero_extents(writer, [SimpleNamespace(start_block=2, num_blocks=3)], 4)
        self.assertEqual(writer.writes, [(8, b"\0" * 12)])

    def test_execute_build_fails_fast(self):
        events = []

        def fail(_context):
            raise studio_core.StudioError("stop here")

        handlers = {
            "inspect_rom": lambda _context: {},
            "debloat": fail,
            "package_zip": lambda _context: self.fail("package must not run"),
        }
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(
            studio_core, "inspect_rom", return_value={
                "ok": True,
                "metadata": {"version_name": "fixture", "product_name": "PKG110"},
                "device": {"product_name": "PKG110"},
            }
        ), mock.patch.object(
            studio_core, "plan_steps", return_value=list(handlers)
        ), mock.patch.dict(
            studio_core.STAGE_HANDLERS, handlers, clear=True
        ), mock.patch.object(
            studio_core, "JOBS_DIR", Path(temp) / ".wkstudio" / "jobs"
        ):
            with self.assertRaisesRegex(studio_core.StudioError, "stop here"):
                studio_core.execute_build(
                    "test-job",
                    studio_core.BuildSpec(romPath="fixture.zip"),
                    Path(temp),
                    events.append,
                )
        self.assertEqual(
            [(event.get("step"), event.get("status")) for event in events if event["type"] == "step"],
            [("inspect_rom", "running"), ("inspect_rom", "success"), ("debloat", "running"), ("debloat", "failed")],
        )

    def test_cli_sync_adapter_preserves_selinux_regex_rule(self):
        legacy = studio_core._load_legacy()
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            (unpacked / "system").mkdir()
            config = unpacked / "config"
            config.mkdir()
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            contexts = config / "system_file_contexts"
            contexts.write_text(
                "/ u:object_r:system_file:s0\n"
                "/system/bin(/.*)? u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                legacy.sync_partition_configs(str(unpacked), "system")
            self.assertIn("/system/bin(/.*)?", contexts.read_text(encoding="utf-8"))

    def test_cli_mod_text_normalizer_preserves_binary(self):
        legacy = studio_core._load_legacy()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            xml = root / "feature.xml"
            apk = root / "fixture.apk"
            xml.write_bytes(b"<features>\r\n  <item/>\r\n</features>\r\n")
            apk.write_bytes(b"PK\r\nbinary\rpayload")

            self.assertTrue(legacy.normalize_android_text_file_lf(str(xml)))
            self.assertFalse(legacy.normalize_android_text_file_lf(str(apk)))
            self.assertEqual(xml.read_bytes(), b"<features>\n  <item/>\n</features>\n")
            self.assertEqual(apk.read_bytes(), b"PK\r\nbinary\rpayload")

    def test_safe_sync_is_append_only_and_preserves_lost_found(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            data = unpacked / "system"
            binary = data / "bin"
            binary.mkdir(parents=True)
            (binary / "new_tool").write_bytes(b"tool")
            config = unpacked / "config"
            config.mkdir()
            fs_config = config / "system_fs_config"
            fs_config.write_text(
                "/ 0 0 0755\n"
                "system/ 0 0 0755\n"
                "system/lost+found 0 0 0755\n"
                "system/bin 0 0 0755\n",
                encoding="utf-8",
            )
            file_contexts = config / "system_file_contexts"
            file_contexts.write_text(
                "/ u:object_r:system_file:s0\n"
                "/system/bin(/.*)? u:object_r:system_file:s0\n",
                encoding="utf-8",
            )

            first = sync_partition_configs(unpacked, "system")
            second = sync_partition_configs(unpacked, "system")

            self.assertEqual(first["addedFs"], 1)
            self.assertEqual(first["addedFileContexts"], 1)
            self.assertEqual(second["addedFs"], 0)
            self.assertEqual(second["addedFileContexts"], 0)
            self.assertIn("system/lost+found 0 0 0755", fs_config.read_text(encoding="utf-8"))
            self.assertIn("/system/bin(/.*)?", file_contexts.read_text(encoding="utf-8"))

    def test_safe_sync_rejects_missing_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            (unpacked / "system").mkdir()
            with self.assertRaisesRegex(PartitionConfigError, "Missing fs_config"):
                sync_partition_configs(unpacked, "system")

    def test_validate_rom_repack_rejects_filesystem_conversion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            repack = root / "repack"
            source.mkdir()
            repack.mkdir()
            (source / "vendor_dlkm.img").write_bytes(b"\0" * 1080 + b"\x53\xef")
            (repack / "vendor_dlkm.img").write_bytes(b"\0" * 1024 + b"\xe2\xe1\xf5\xe0")
            self.assertFalse(studio_core.validate_rom_repack(repack, source))

    def test_erofs_repack_uses_legacy_mkfs_arguments(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir()
            config.mkdir()
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            output = unpacked / "system.img"
            tool = img_tool.ImageTool()
            with mock.patch.object(
                img_tool.time,
                "time",
                return_value=1788056000,
            ), mock.patch.object(img_tool, "run_command", return_value=0) as run:
                self.assertTrue(tool.repack_erofs(str(data), str(output)))
            command = run.call_args.args[0]
            self.assertIn("-zlz4hc,9", command)
            self.assertEqual(command[command.index("-T") + 1], "1788056000")
            self.assertIn("--mount-point", command)
            self.assertIn("--product-out", command)
            self.assertIn("--quiet", command)
            self.assertNotIn("-U", command)
            self.assertNotIn("-C", command)

    def test_erofs_unpack_suppresses_per_file_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "system.img"
            output = root / "unpacked"
            source.write_bytes(b"erofs")
            tool = img_tool.ImageTool()
            with mock.patch.object(tool, "detect_type", return_value="erofs"), mock.patch.object(
                img_tool,
                "run_command",
                return_value=0,
            ) as run:
                self.assertTrue(tool.unpack(str(source), str(output)))
            command = run.call_args.args[0]
            self.assertIn("-s", command)
            image_info = json.loads(
                (output / "config" / "system_image_info.json").read_text(encoding="utf-8")
            )
            self.assertEqual(image_info["filesystem"], "erofs")

    def test_erofs_repack_reuses_extracted_source_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir()
            config.mkdir()
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:rootfs:s0\n",
                encoding="utf-8",
            )
            (config / "system_fs_options").write_text(
                "mkfs.erofs options: -zlz4hc -C 16384 -T 0 "
                "-U 4ab76a33-86b2-5d6c-97d6-acf88c267bad "
                "--mount-point=/system old.img old-system\n",
                encoding="utf-8",
            )
            output = unpacked / "system.img"
            tool = img_tool.ImageTool()
            with mock.patch.object(
                img_tool.time,
                "time",
                return_value=1788056000,
            ), mock.patch.object(img_tool, "run_command", return_value=0) as run:
                self.assertTrue(tool.repack_erofs(str(data), str(output)))
            command = run.call_args.args[0]
            self.assertIn("-zlz4hc", command)
            self.assertIn("-C", command)
            self.assertEqual(command[command.index("-C") + 1], "16384")
            self.assertIn("-T", command)
            self.assertEqual(command[command.index("-T") + 1], "1788056000")
            self.assertIn("-U", command)
            self.assertEqual(
                command[command.index("-U") + 1],
                "4ab76a33-86b2-5d6c-97d6-acf88c267bad",
            )

    def test_real_erofs_round_trip_smoke(self):
        bin_dir = studio_core.BIN_ROOT / "Windows" / "AMD64"
        mkfs = bin_dir / "mkfs.erofs.exe"
        extractor = bin_dir / "extract.erofs.exe"
        if not mkfs.is_file() or not extractor.is_file():
            self.skipTest("Bundled EROFS binaries are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp) / "system_unpacked"
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir(parents=True)
            config.mkdir()
            (data / "fixture.txt").write_text("wukong-erofs-smoke\n", encoding="utf-8")
            (config / "system_fs_config").write_text(
                "/ 0 0 0755 capabilities=0x0\n"
                "system 0 0 0755 capabilities=0x0\n"
                "/lost+found 0 0 0755 capabilities=0x0\n"
                "system/fixture.txt 0 0 0644 capabilities=0x0\n",
                encoding="utf-8",
            )
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n"
                "/(.*) u:object_r:system_file:s0\n"
                "/system u:object_r:system_file:s0\n"
                "/system(/.*)? u:object_r:system_file:s0\n"
                "/system/lost.* u:object_r:system_file:s0\n"
                "/lost\\+found u:object_r:system_file:s0\n"
                "/system/fixture\\.txt u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            (config / "system_fs_options").write_text(
                "mkfs.erofs options: -zlz4hc,9 -T 0\n",
                encoding="utf-8",
            )
            write_partition_tree_fingerprint(unpacked, "system")
            output = Path(temp) / "system.img"

            self.assertTrue(img_tool.ImageTool().repack_erofs(str(data), str(output)))
            with mock.patch.dict(
                "os.environ", {"WUKONG_STUDIO_REPACK_AUDIT": "metadata"}, clear=False
            ):
                report = validate_repacked_partition(
                    unpacked,
                    "system",
                    output,
                    "erofs",
                    extract_erofs=extractor,
                )

            self.assertEqual(report["filesystem"], "erofs")
            self.assertEqual(report["audit"], "metadata")
            self.assertGreaterEqual(report["paths"], 2)

    def test_erofs_metadata_audit_does_not_extract_full_image(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp) / "system_unpacked"
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir(parents=True)
            config.mkdir()
            (data / "fixture.txt").write_text("fixture\n", encoding="utf-8")
            (config / "system_fs_config").write_text(
                "/ 0 0 0755\n"
                "system 0 0 0755\n"
                "system/fixture.txt 0 0 0644\n",
                encoding="utf-8",
            )
            (config / "system_file_contexts").write_text(
                "/system u:object_r:system_file:s0\n"
                "/system/fixture\\.txt u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            (config / "system_fs_options").write_text(
                "mkfs.erofs options: -zlz4hc -T 0\n", encoding="utf-8"
            )
            output = Path(temp) / "system.img"
            output.write_bytes(b"erofs")
            listing = (
                "Extract: type=DIR dataLayout=INLINE fsConfig=[/ 0 0 0755] "
                "seLabel=[u:object_r:system_file:s0]\n"
                "Extract: type=FILE dataLayout=PLAIN fsConfig=[/fixture.txt 0 0 0644] "
                "seLabel=[u:object_r:system_file:s0]\n"
            )

            with mock.patch.object(
                partition_config.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout=listing, stderr=""),
            ) as run:
                report = validate_repacked_partition(
                    unpacked,
                    "system",
                    output,
                    "erofs",
                    extract_erofs="extract.erofs",
                    full_audit=False,
                )

            self.assertEqual(report["audit"], "metadata")
            self.assertEqual(report["paths"], 2)
            self.assertEqual(run.call_count, 1)
            self.assertIn("-p", run.call_args.args[0])

    def test_erofs_metadata_audit_rejects_repacked_permissions_change(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp) / "system_unpacked"
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir(parents=True)
            config.mkdir()
            (data / "fixture.txt").write_text("fixture\n", encoding="utf-8")
            (config / "system_fs_config").write_text(
                "/ 0 0 0755\n"
                "system 0 0 0755\n"
                "system/fixture.txt 0 0 0644\n",
                encoding="utf-8",
            )
            (config / "system_file_contexts").write_text(
                "/system u:object_r:system_file:s0\n"
                "/system/fixture\\.txt u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            (config / "system_fs_options").write_text(
                "mkfs.erofs options: -zlz4hc -T 0\n", encoding="utf-8"
            )
            output = Path(temp) / "system.img"
            output.write_bytes(b"erofs")
            listing = (
                "Extract: type=DIR dataLayout=INLINE fsConfig=[/ 0 0 0755] "
                "seLabel=[u:object_r:system_file:s0]\n"
                "Extract: type=FILE dataLayout=PLAIN fsConfig=[/fixture.txt 0 0 0600] "
                "seLabel=[u:object_r:system_file:s0]\n"
            )

            with mock.patch.object(
                partition_config.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout=listing, stderr=""),
            ):
                with self.assertRaisesRegex(PartitionConfigError, "fs_config changed"):
                    validate_repacked_partition(
                        unpacked,
                        "system",
                        output,
                        "erofs",
                        extract_erofs="extract.erofs",
                        full_audit=False,
                    )

    def test_erofs_full_audit_remains_available(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp) / "system_unpacked"
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir(parents=True)
            config.mkdir()
            (config / "system_fs_config").write_text(
                "system 0 0 0755\n", encoding="utf-8"
            )
            (config / "system_file_contexts").write_text(
                "/system u:object_r:system_file:s0\n", encoding="utf-8"
            )
            (config / "system_fs_options").write_text(
                "mkfs.erofs options: -zlz4hc -T 0\n", encoding="utf-8"
            )
            output = Path(temp) / "system.img"
            output.write_bytes(b"erofs")

            with mock.patch.object(
                partition_config, "_validate_erofs_roundtrip", return_value={"paths": 1}
            ), mock.patch.object(
                partition_config, "_tree_profile", return_value={}
            ), mock.patch.object(
                partition_config, "_validate_config_roundtrip", return_value={"paths": 1}
            ), mock.patch.object(
                partition_config.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ) as run:
                report = validate_repacked_partition(
                    unpacked,
                    "system",
                    output,
                    "erofs",
                    extract_erofs="extract.erofs",
                    full_audit=True,
                )

            self.assertEqual(report["audit"], "full")
            self.assertIn("-x", run.call_args.args[0])

    def test_ext4_repack_uses_legacy_size_estimate(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            data = unpacked / "vendor_dlkm"
            config = unpacked / "config"
            data.mkdir()
            config.mkdir()
            (config / "vendor_dlkm_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "vendor_dlkm_file_contexts").write_text(
                "/ u:object_r:vendor_file:s0\n",
                encoding="utf-8",
            )
            (data / "payload.bin").write_bytes(b"x" * 1024 * 1024)
            output = unpacked / "vendor_dlkm.img"
            tool = img_tool.ImageTool()
            with mock.patch.object(img_tool, "run_command", return_value=0) as run:
                self.assertTrue(tool.repack_ext4(str(data), str(output)))
            mke2fs = run.call_args_list[0].args[0]
            self.assertEqual(mke2fs[-1], str((51 * 1024 * 1024) // 4096))

    def test_ext4_repack_legacy_command_has_no_source_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            data = unpacked / "vendor_dlkm"
            config = unpacked / "config"
            data.mkdir()
            config.mkdir()
            (config / "vendor_dlkm_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "vendor_dlkm_file_contexts").write_text(
                "/ u:object_r:vendor_file:s0\n",
                encoding="utf-8",
            )
            output = unpacked / "vendor_dlkm.img"
            tool = img_tool.ImageTool()
            with mock.patch.object(img_tool, "run_command", return_value=0) as run:
                self.assertTrue(tool.repack_ext4(str(data), str(output)))
            mke2fs = run.call_args_list[0].args[0]
            self.assertNotIn("-N", mke2fs)
            self.assertNotIn("-U", mke2fs)

    def test_ext4_repack_uses_recorded_source_size(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp)
            data = unpacked / "system"
            config = unpacked / "config"
            data.mkdir()
            config.mkdir()
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            (config / "system_image_info.json").write_text(
                json.dumps({"filesystem": "ext4", "sizeBytes": 64 * 1024 * 1024}),
                encoding="utf-8",
            )
            output = unpacked / "system.img"
            tool = img_tool.ImageTool()
            with mock.patch.object(img_tool, "run_command", return_value=0) as run:
                self.assertTrue(tool.repack_ext4(str(data), str(output)))
            mke2fs = run.call_args_list[0].args[0]
            self.assertEqual(mke2fs[-1], str((64 * 1024 * 1024) // 4096))

    def test_real_ext4_round_trip_smoke(self):
        bin_dir = studio_core.BIN_ROOT / "Windows" / "AMD64"
        if not (bin_dir / "mke2fs.exe").is_file() or not (bin_dir / "e2fsdroid.exe").is_file():
            self.skipTest("Bundled EXT4 binaries are unavailable")
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp) / "my_product_unpacked"
            data = unpacked / "my_product"
            config = unpacked / "config"
            data.mkdir(parents=True)
            config.mkdir()
            (data / "fixture.txt").write_text("wukong-ext4-smoke\n", encoding="utf-8")
            (config / "my_product_fs_config").write_text(
                "/ 0 0 0755\n"
                "/lost+found 0 0 0755\n"
                "my_product 0 0 0755\n"
                "my_product/fixture.txt 0 0 0644\n",
                encoding="utf-8",
            )
            (config / "my_product_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n"
                "/lost\\+found u:object_r:system_file:s0\n"
                "/my_product u:object_r:system_file:s0\n"
                "/my_product(/.*)? u:object_r:system_file:s0\n"
                "/my_product/fixture\\.txt u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            size = 64 * 1024 * 1024
            (config / "my_product_size.txt").write_text(f"{size}\n", encoding="ascii")
            (config / "my_product_image_info.json").write_text(
                json.dumps({"filesystem": "ext4", "sizeBytes": size}),
                encoding="utf-8",
            )
            write_partition_tree_fingerprint(unpacked, "my_product")
            output = Path(temp) / "my_product.img"

            self.assertTrue(img_tool.ImageTool().repack_ext4(str(data), str(output)))
            report = validate_repacked_partition(unpacked, "my_product", output, "ext4")

            self.assertEqual(report["filesystem"], "ext4")
            self.assertGreaterEqual(report["paths"], 2)

    def test_batch_repack_auto_preserves_each_partition_filesystem(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack_root = root / "rom-unpack"
            repack = root / "rom-repack"
            for partition, filesystem in (
                ("system", "erofs"),
                ("my_product", "ext4"),
                ("future_partition", "ext4"),
            ):
                unpacked = unpack_root / f"{partition}_unpacked"
                data = unpacked / partition
                config = unpacked / "config"
                data.mkdir(parents=True)
                config.mkdir()
                (data / "fixture.txt").write_text(partition, encoding="utf-8")
                (config / f"{partition}_fs_config").write_text(
                    "/ 0 0 0755\n", encoding="utf-8"
                )
                (config / f"{partition}_file_contexts").write_text(
                    "/ u:object_r:system_file:s0\n", encoding="utf-8"
                )
                (config / f"{partition}_image_info.json").write_text(
                    json.dumps({"filesystem": filesystem, "sizeBytes": 4096}),
                    encoding="utf-8",
                )

            commands = []

            def write_output(command, **_kwargs):
                commands.append(command)
                output = Path(command[5])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"repacked")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(batch_repack.subprocess, "run", side_effect=write_output):
                self.assertTrue(
                    batch_repack.batch_repack(
                        str(unpack_root),
                        str(repack),
                        img_format="auto",
                        validate_output=False,
                    )
                )

            formats = {
                Path(command[5]).stem: command[command.index("--format") + 1]
                for command in commands
            }
            self.assertEqual(formats, {"my_product": "ext4", "system": "erofs"})

    def test_batch_repack_legacy_trusts_img_tool_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack" / "system_unpacked"
            data = unpack / "system"
            config = unpack / "config"
            repack = root / "rom-repack"
            data.mkdir(parents=True)
            config.mkdir()
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            (data / "changed.txt").write_text("changed\n", encoding="utf-8")

            def create_wrong_format(*_args, **_kwargs):
                output = repack / "system.img"
                output.parent.mkdir(exist_ok=True)
                output.write_bytes(b"\0" * 1080 + b"\x53\xef")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(batch_repack.subprocess, "run", side_effect=create_wrong_format):
                self.assertTrue(
                    batch_repack.batch_repack(
                        str(root / "rom-unpack"),
                        str(repack),
                        validate_output=False,
                    )
                )

    def test_batch_repack_legacy_rebuilds_unchanged_partition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack" / "system_unpacked"
            data = unpack / "system"
            config = unpack / "config"
            repack = root / "rom-repack"
            data.mkdir(parents=True)
            config.mkdir()
            (data / "fixture.txt").write_text("fixture\n", encoding="utf-8")
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n",
                encoding="utf-8",
            )

            def write_output(*_args, **_kwargs):
                repack.mkdir(exist_ok=True)
                (repack / "system.img").write_bytes(b"rebuilt")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(batch_repack.subprocess, "run", side_effect=write_output) as run:
                self.assertTrue(
                    batch_repack.batch_repack(
                        str(root / "rom-unpack"),
                        str(repack),
                        validate_output=False,
                    )
                )
            run.assert_called_once()
            self.assertEqual((repack / "system.img").read_bytes(), b"rebuilt")

    def test_batch_repack_legacy_does_not_create_vbmeta_marker(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack = root / "rom-unpack" / "system_unpacked"
            data = unpack / "system"
            config = unpack / "config"
            repack = root / "rom-repack"
            data.mkdir(parents=True)
            config.mkdir()
            (data / "fixture.txt").write_text("fixture\n", encoding="utf-8")
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            (data / "changed.txt").write_text("changed\n", encoding="utf-8")

            def write_output(*_args, **_kwargs):
                repack.mkdir(exist_ok=True)
                (repack / "system.img").write_bytes(b"output")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(batch_repack.subprocess, "run", side_effect=write_output):
                self.assertTrue(
                    batch_repack.batch_repack(
                        str(root / "rom-unpack"),
                        str(repack),
                        validate_output=False,
                    )
                )
            self.assertFalse((repack / studio_core.PATCHED_VBMETA_MARKER).exists())

    def test_super_group_capacity_allows_expanded_mod_partition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "my_product.img"
            second = root / "system.img"
            first.write_bytes(b"x" * 16)
            second.write_bytes(b"x" * 8)
            report = super_tool.SuperPacker.validate_group_capacity(
                "qti_dynamic_partitions",
                24,
                [str(first), str(second)],
                is_ab=True,
            )
            self.assertEqual(report, {"slotA": 24, "slotB": 0})
            with self.assertRaisesRegex(ValueError, "exceeds capacity"):
                super_tool.SuperPacker.validate_group_capacity(
                    "qti_dynamic_partitions",
                    23,
                    [str(first), str(second)],
                    is_ab=True,
                )

    def test_super_pack_stops_when_sparse_conversion_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            partition = root / "system.img"
            partition.write_bytes(b"\x3a\xff\x26\xed" + b"invalid")
            sparse = mock.Mock()
            sparse.check.return_value = False
            with mock.patch("src.core.lpunpack.SparseImage", return_value=sparse), mock.patch.object(
                super_tool, "run_command", return_value=0
            ) as run:
                result = super_tool.SuperPacker().pack(
                    str(root / "super.img"),
                    1024 * 1024,
                    "qti_dynamic_partitions",
                    512 * 1024,
                    [str(partition)],
                    sparse=True,
                    is_ab=False,
                )
            self.assertFalse(result)
            run.assert_not_called()

    def test_real_lpmake_sparse_super_smoke(self):
        lpmake = studio_core.BIN_ROOT / "Windows" / "AMD64" / "lpmake.exe"
        if not lpmake.is_file():
            self.skipTest("Bundled lpmake is unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            system = root / "system.img"
            product = root / "my_product.img"
            system.write_bytes(b"system".ljust(4096, b"\0"))
            product.write_bytes(b"product".ljust(4096, b"\0"))
            output = root / "super.img"
            super_size = 32 * 1024 * 1024

            self.assertTrue(
                super_tool.SuperPacker().pack(
                    str(output),
                    super_size,
                    "qti_dynamic_partitions",
                    8 * 1024 * 1024,
                    [str(system), str(product)],
                    sparse=True,
                    is_ab=True,
                )
            )
            with output.open("rb") as stream:
                header = stream.read(28)
                _, _, _, _, _, block_size, total_blocks, _, _ = struct.unpack(
                    "<I4H4I", header
                )
                stream.seek(0)
                partitions = studio_core._partition_names_from_sparse_stream(
                    stream,
                    validate_full=True,
                )

            self.assertEqual(block_size * total_blocks, super_size)
            self.assertTrue({"system_a", "my_product_a"}.issubset(partitions))

    def test_modified_fec_partition_requires_fec_binary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "vendor_dlkm.img"
            source = root / "source-vendor_dlkm.img"
            output.write_bytes(b"x" * 4096)
            source.write_bytes(b"x" * 4096)
            profile = avb_footer.AvbHashtreeProfile(
                partition_size=8192,
                partition_name="vendor_dlkm",
                algorithm="NONE",
                hash_algorithm="sha256",
                salt="00" * 32,
                fec_num_roots=2,
                data_block_size=4096,
                flags=0,
                rollback_index=0,
                rollback_index_location=0,
                vbmeta_flags=0,
                properties=(),
            )
            with mock.patch.object(
                avb_footer,
                "read_avb_hashtree_profile",
                return_value=profile,
            ), mock.patch.object(
                avb_footer.shutil,
                "which",
                return_value=None,
            ):
                with self.assertRaisesRegex(avb_footer.AvbFooterError, "fec binary"):
                    avb_footer.restore_avb_footer(output, source)

    def test_validate_rom_unpack_requires_erofs_source_options(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            unpack = root / "unpack" / "system_unpacked"
            data = unpack / "system"
            config = unpack / "config"
            source.mkdir()
            data.mkdir(parents=True)
            config.mkdir()
            (source / "system.img").write_bytes(b"\0" * 1024 + b"\xe2\xe1\xf5\xe0")
            (config / "system_fs_config").write_text("/ 0 0 0755\n", encoding="utf-8")
            (config / "system_file_contexts").write_text(
                "/ u:object_r:system_file:s0\n",
                encoding="utf-8",
            )
            self.assertFalse(studio_core.validate_rom_unpack(root / "unpack", source))
            (config / "system_fs_options").write_text(
                "mkfs.erofs options: -zlz4hc -T 0 output.img source\n",
                encoding="utf-8",
            )
            write_partition_tree_fingerprint(unpack, "system")
            self.assertTrue(studio_core.validate_rom_unpack(root / "unpack", source))

    def test_partition_layout_analyzer_reads_json_and_reports_deltas(self):
        with tempfile.TemporaryDirectory() as temp:
            layout_path = Path(temp) / "lpdump.json"
            layout_path.write_text(
                json.dumps(
                    {
                        "metadata_max_size": 65536,
                        "metadata_slot_count": 3,
                        "block_devices": [
                            {"name": "super", "size": 16 * 1024**3, "first_sector": 2048}
                        ],
                        "group_table": [
                            {"name": "qti_dynamic_partitions_a", "maximum_size": 15 * 1024**3}
                        ],
                        "partition_table": [
                            {
                                "name": "system_a",
                                "group_name": "qti_dynamic_partitions_a",
                                "size": 6 * 1024**3,
                            },
                            {
                                "name": "my_company_a",
                                "group_name": "qti_dynamic_partitions_a",
                                "size": 1024**3,
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = studio_core.analyze_partition_layout(
                {
                    "product_name": "TEST110",
                    "name": "Test device",
                    "soc": "test",
                    "SuperSize": 16 * 1024**3,
                    "GroupSize": 15 * 1024**3,
                    "Partitions": ["my_company", "my_preload"],
                },
                layout_path,
            )
            self.assertEqual(result["mode"], "super-metadata")
            self.assertEqual(result["actual"]["superSize"], 16 * 1024**3)
            self.assertEqual(result["actual"]["groups"][0]["usedBytes"], 7 * 1024**3)
            self.assertEqual(result["comparison"]["missingConfiguredPartitions"], ["my_preload"])
            self.assertEqual(result["status"], "warning")

    def test_payload_stage_cache_reuses_extracted_images_by_rom_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "data"
            cache = runtime / "Cache" / "Payload"
            runtime.mkdir()
            (runtime / "settings.json").write_text(
                json.dumps({"stageCacheEnabled": True, "stageCacheMaxGb": 5}),
                encoding="utf-8",
            )
            rom = root / "fixture.zip"
            rom.write_bytes(b"rom-payload-fixture")

            def fake_extract(_command):
                source = current_context[0].source_rom
                source.mkdir(parents=True, exist_ok=True)
                for name in ["boot.img", "vbmeta.img", "vendor_boot.img", "system.img"]:
                    (source / name).write_bytes(name.encode("ascii"))

            first = studio_core.BuildContext(
                job_id="cache-first",
                spec=studio_core.BuildSpec(romPath=str(rom)),
                workspace=root / "first",
                metadata={"version_name": "fixture"},
                device={},
            )
            second = studio_core.BuildContext(
                job_id="cache-second",
                spec=studio_core.BuildSpec(romPath=str(rom)),
                workspace=root / "second",
                metadata={"version_name": "fixture"},
                device={},
            )
            current_context = [first]
            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime), mock.patch.object(
                studio_core, "STAGE_CACHE_ROOT", cache
            ), mock.patch.object(studio_core, "_run_command", side_effect=fake_extract) as run:
                first_result = studio_core._stage_extract_payload(first)
                current_context[0] = second
                second_result = studio_core._stage_extract_payload(second)

            self.assertFalse(first_result["cacheHit"])
            self.assertTrue(first_result["cacheStored"])
            self.assertTrue(second_result["cacheHit"])
            self.assertEqual(run.call_count, 1)
            self.assertTrue(studio_core.validate_source_rom(second.source_rom))

    def test_payload_cache_tampering_forces_fresh_extract(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "data"
            cache = runtime / "Cache" / "Payload"
            runtime.mkdir()
            (runtime / "settings.json").write_text(
                json.dumps({"stageCacheEnabled": True, "stageCacheMaxGb": 5}),
                encoding="utf-8",
            )
            rom = root / "fixture.zip"
            rom.write_bytes(b"rom-payload-fixture")
            contexts = [
                studio_core.BuildContext(
                    job_id=name,
                    spec=studio_core.BuildSpec(romPath=str(rom)),
                    workspace=root / name,
                    metadata={"version_name": "fixture"},
                    device={},
                )
                for name in ("first", "second")
            ]
            current = [contexts[0]]

            def fake_extract(_command):
                source = current[0].source_rom
                source.mkdir(parents=True, exist_ok=True)
                for name in ["boot.img", "vbmeta.img", "vendor_boot.img", "system.img"]:
                    (source / name).write_bytes(f"fresh-{name}".encode("ascii"))

            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime), mock.patch.object(
                studio_core, "STAGE_CACHE_ROOT", cache
            ), mock.patch.object(studio_core, "_run_command", side_effect=fake_extract) as run:
                first = studio_core._stage_extract_payload(contexts[0])
                (cache / first["cacheKey"] / "source_rom" / "system.img").write_bytes(b"tampered")
                current[0] = contexts[1]
                second = studio_core._stage_extract_payload(contexts[1])

            self.assertEqual(run.call_count, 2)
            self.assertFalse(second["cacheHit"])
            self.assertEqual((contexts[1].source_rom / "system.img").read_bytes(), b"fresh-system.img")

    def test_payload_extract_clears_partial_source_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = root / "data"
            runtime.mkdir()
            (runtime / "settings.json").write_text(
                json.dumps({"stageCacheEnabled": False}),
                encoding="utf-8",
            )
            rom = root / "fixture.zip"
            rom.write_bytes(b"rom")
            context = studio_core.BuildContext(
                job_id="fresh",
                spec=studio_core.BuildSpec(romPath=str(rom)),
                workspace=root / "workspace",
                metadata={},
                device={},
            )
            context.source_rom.mkdir(parents=True)
            (context.source_rom / "stale.img").write_bytes(b"stale")

            def fake_extract(_command):
                self.assertFalse((context.source_rom / "stale.img").exists())
                for name in ["boot.img", "vbmeta.img", "vendor_boot.img", "system.img"]:
                    (context.source_rom / name).write_bytes(name.encode("ascii"))

            with mock.patch.object(studio_core, "RUNTIME_DIR", runtime), mock.patch.object(
                studio_core, "_run_command", side_effect=fake_extract
            ):
                studio_core._stage_extract_payload(context)

    def test_batch_unpack_clears_partial_partition_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            target = root / "unpack"
            source.mkdir()
            (source / "system.img").write_bytes(b"system")
            stale = target / "system_unpacked" / "system" / "stale.txt"
            stale.parent.mkdir(parents=True)
            stale.write_text("stale", encoding="utf-8")

            def fake_run(_command, **_kwargs):
                self.assertFalse(stale.exists())
                return SimpleNamespace(returncode=0)

            with mock.patch.object(batch_unpack.subprocess, "run", side_effect=fake_run):
                self.assertTrue(batch_unpack.batch_unpack(str(source), str(target)))

    def test_partition_sync_only_regex_checks_new_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            unpacked = Path(temp) / "system_unpacked"
            data = unpacked / "system"
            config = unpacked / "config"
            (data / "app" / "Existing").mkdir(parents=True)
            (data / "app" / "Existing" / "base.apk").write_bytes(b"old")
            (data / "app" / "NewMod").mkdir(parents=True)
            (data / "app" / "NewMod" / "base.apk").write_bytes(b"new")
            config.mkdir()
            (config / "system_fs_config").write_text(
                "system 0 0 0755\nsystem/app 0 0 0755\n"
                "system/app/Existing 0 0 0755\nsystem/app/Existing/base.apk 0 0 0644\n",
                encoding="utf-8",
            )
            (config / "system_file_contexts").write_text(
                "/system/app/Existing(/.*)? u:object_r:system_file:s0\n",
                encoding="utf-8",
            )

            report = sync_partition_configs(unpacked, "system")

            self.assertEqual(report["addedFs"], 2)
            self.assertEqual(report["addedFileContexts"], 3)
            contexts = (config / "system_file_contexts").read_text(encoding="utf-8")
            self.assertIn("/system/app/NewMod", contexts)
            self.assertNotIn("/system/app/Existing/base\\.apk", contexts)

    def test_rom_sha256_memo_reuses_unchanged_file_without_reopening(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "fixture.zip"
            rom.write_bytes(b"rom-payload-fixture")
            context = studio_core.BuildContext(
                job_id="hash-memo",
                spec=studio_core.BuildSpec(romPath=str(rom)),
                workspace=root / "workspace",
                metadata={},
                device={},
            )
            studio_core._ROM_SHA256_MEMO.clear()

            first = studio_core._rom_sha256(context)
            with mock.patch.object(Path, "open", side_effect=AssertionError("ROM reopened")):
                second = studio_core._rom_sha256(context)

            self.assertEqual(first, second)

    def test_link_or_copy_required_reuses_existing_hardlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.img"
            destination = root / "destination.img"
            source.write_bytes(b"image")
            destination.hardlink_to(source)

            method = studio_core._link_or_copy_required(source, destination, "image")

            self.assertEqual(method, "reused")
            self.assertTrue(source.samefile(destination))

    def test_batch_repack_filters_to_selected_partitions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            unpack_root = root / "rom-unpack"
            repack = root / "rom-repack"
            for partition in ("system", "my_product"):
                unpacked = unpack_root / f"{partition}_unpacked"
                data = unpacked / partition
                config = unpacked / "config"
                data.mkdir(parents=True)
                config.mkdir()
                (data / "fixture.txt").write_text(partition, encoding="utf-8")
                (config / f"{partition}_fs_config").write_text(
                    "/ 0 0 0755\n",
                    encoding="utf-8",
                )
                (config / f"{partition}_file_contexts").write_text(
                    "/ u:object_r:system_file:s0\n",
                    encoding="utf-8",
                )

            def write_output(command, **_kwargs):
                output = Path(command[5])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"repacked")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(batch_repack.subprocess, "run", side_effect=write_output) as run:
                self.assertTrue(
                    batch_repack.batch_repack(
                        str(unpack_root),
                        str(repack),
                        validate_output=False,
                        partitions={"system"},
                    )
                )

            run.assert_called_once()
            self.assertTrue((repack / "system.img").is_file())
            self.assertFalse((repack / "my_product.img").exists())

    def test_selective_repack_rebuilds_only_modified_and_branded_partitions(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            context = studio_core.BuildContext(
                job_id="selective",
                spec=studio_core.BuildSpec(romPath="rom.zip", preset="resume"),
                workspace=workspace,
                metadata={},
                device={},
                selective_repack=True,
                modified_partitions={"system"},
            )
            commands = []

            with mock.patch.object(
                studio_core,
                "_run_command",
                side_effect=lambda command: commands.append(command),
            ), mock.patch.object(
                studio_core,
                "copy_passthrough_partition_images",
                return_value=[],
            ), mock.patch.object(
                studio_core,
                "validate_rom_repack",
                return_value=True,
            ):
                result = studio_core._stage_repack(context)

            command = commands[0]
            selected = set(command[command.index("--partitions") + 1 :])
            self.assertEqual(selected, {"system"})
            self.assertEqual(
                set(result["repackedPartitions"]),
                {"system"},
            )
            self.assertEqual(
                set(
                    (context.rom_repack / studio_core.PATCHED_VBMETA_MARKER)
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
                {"system"},
            )

    def test_selective_sync_only_scans_modified_partitions(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / "rom-unpack" / "system_unpacked").mkdir(parents=True)
            context = studio_core.BuildContext(
                job_id="selective-sync",
                spec=studio_core.BuildSpec(romPath="rom.zip", preset="resume"),
                workspace=workspace,
                metadata={},
                device={},
                selective_repack=True,
                modified_partitions={"system"},
            )

            def report(_unpacked, partition):
                return {
                    "partition": partition,
                    "scannedPaths": 1,
                    "addedFs": 0,
                    "addedFileContexts": 0,
                }

            with mock.patch.object(
                studio_core,
                "validate_no_unsafe_vendor_priv_app_sysfs",
                return_value={"checked": False},
            ), mock.patch.object(
                studio_core,
                "sync_partition_configs",
                side_effect=report,
            ) as sync:
                result = studio_core._stage_sync_configs(context)

            self.assertEqual(
                [call.args[1] for call in sync.call_args_list],
                ["system"],
            )
            self.assertEqual(
                [item["partition"] for item in result["partitions"]],
                ["system"],
            )

    def test_clear_repack_outputs_can_preserve_lite_partition_images(self):
        with tempfile.TemporaryDirectory() as temp:
            context = studio_core.BuildContext(
                job_id="both",
                spec=studio_core.BuildSpec(romPath="rom.zip", preset="both"),
                workspace=Path(temp),
                metadata={},
                device={},
            )
            context.rom_repack.mkdir()
            context.build_dir.mkdir()
            (context.rom_repack / "system.img").write_bytes(b"lite-system")
            (context.build_dir / "super.img").write_bytes(b"lite-super")

            studio_core._clear_repack_outputs(context, preserve_repacked=True)

            self.assertTrue((context.rom_repack / "system.img").is_file())
            self.assertFalse(context.build_dir.exists())

    def test_cached_md5_reuses_digest_for_hardlinked_package_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.img"
            linked = root / "linked.img"
            source.write_bytes(b"shared-image")
            linked.hardlink_to(source)
            context = studio_core.BuildContext(
                job_id="hashes",
                spec=studio_core.BuildSpec(romPath="rom.zip"),
                workspace=root / "workspace",
                metadata={},
                device={},
            )

            with mock.patch.object(studio_core, "_md5", wraps=studio_core._md5) as digest:
                first, first_hit = studio_core._cached_md5(context, source)
                second, second_hit = studio_core._cached_md5(context, linked)

            self.assertEqual(first, second)
            self.assertFalse(first_hit)
            self.assertTrue(second_hit)
            self.assertEqual(digest.call_count, 1)

    def test_single_build_stages_shared_assets_without_intermediate_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            context = studio_core.BuildContext(
                job_id="single",
                spec=studio_core.BuildSpec(romPath="rom.zip", preset="lite"),
                workspace=root / "workspace",
                metadata={},
                device={},
            )
            package_root = root / "package"
            package_root.mkdir()

            with mock.patch.object(
                studio_core,
                "_populate_shared_package_assets",
                return_value={"linked": 3, "copied": 0, "reused": 0},
            ) as populate, mock.patch.object(
                studio_core,
                "_ensure_shared_package_assets",
                side_effect=AssertionError("intermediate cache used"),
            ):
                result = studio_core._stage_shared_package_assets(context, package_root)

            populate.assert_called_once_with(context, package_root)
            self.assertFalse(result["cacheReused"])
            self.assertEqual(result["packageLinked"], 3)


if __name__ == "__main__":
    unittest.main()
