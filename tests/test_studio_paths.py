import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from studio_paths import build_paths, platform_tool_path


class StudioPathsTests(unittest.TestCase):
    def test_image_tool_uses_desktop_bin_root_not_scripts_working_directory(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            install = Path(temp) / "WukongROMStudio"
            runtime = install / "Runtime"
            scripts = runtime / "Scripts"
            scripts.mkdir(parents=True)
            env = os.environ.copy()
            dependency_paths = [
                entry
                for entry in sys.path
                if entry and Path(entry).name.casefold() == "site-packages"
            ]
            env.update(
                {
                    "PYTHONPATH": os.pathsep.join(
                        [str(project_root), *dependency_paths]
                    ),
                    "PYTHONSAFEPATH": "1",
                    "WUKONG_STUDIO_DESKTOP_MODE": "1",
                    "WUKONG_STUDIO_INSTALL_ROOT": str(install),
                    "WUKONG_STUDIO_APP_ROOT": str(runtime),
                }
            )
            bootstrap = (
                "import sys; "
                f"sys.path[:0] = {[str(project_root), *dependency_paths]!r}; "
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-P",
                    "-c",
                    bootstrap + "from img_tool import ImageTool; print(ImageTool().bin_path)",
                ],
                cwd=scripts,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            actual = Path(result.stdout.strip().splitlines()[-1])
            self.assertEqual(
                tuple(part.lower() for part in actual.parts[-4:]),
                ("runtime", "bin", "windows", "amd64"),
            )

    def test_super_and_vendor_boot_tools_use_desktop_bin_root(self):
        project_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            install = Path(temp) / "WukongROMStudio"
            runtime = install / "Runtime"
            scripts = runtime / "Scripts"
            scripts.mkdir(parents=True)
            env = os.environ.copy()
            env.update(
                {
                    "PYTHONPATH": str(project_root),
                    "WUKONG_STUDIO_DESKTOP_MODE": "1",
                    "WUKONG_STUDIO_INSTALL_ROOT": str(install),
                    "WUKONG_STUDIO_APP_ROOT": str(runtime),
                }
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from super_tool import SuperPacker; "
                        "from vendor_boot_tool import VendorBootTool; "
                        "print(SuperPacker().bin_path); "
                        "print(VendorBootTool().bin_path)"
                    ),
                ],
                cwd=scripts,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

            paths = [Path(line) for line in result.stdout.strip().splitlines()[-2:]]
            for path in paths:
                self.assertEqual(
                    tuple(part.lower() for part in path.parts[-4:]),
                    ("runtime", "bin", "windows", "amd64"),
                )

    def test_desktop_paths_are_isolated_under_install_root(self):
        with tempfile.TemporaryDirectory() as temp:
            install = Path(temp) / "WukongROMStudio"
            runtime = install / "Runtime"
            paths = build_paths(
                {
                    "WUKONG_STUDIO_DESKTOP_MODE": "1",
                    "WUKONG_STUDIO_INSTALL_ROOT": str(install),
                    "WUKONG_STUDIO_APP_ROOT": str(runtime),
                    "WUKONG_STUDIO_DATA_ROOT": str(install / "Data"),
                    "WUKONG_STUDIO_CONTENT_ROOT": str(install / "Content"),
                    "WUKONG_STUDIO_WORKSPACE_ROOT": str(install / "Workspace"),
                    "WUKONG_STUDIO_OUTPUT_ROOT": str(install / "ROM_BUILD_DONE"),
                    "WUKONG_STUDIO_TEMP_ROOT": str(install / "Temp"),
                    "WUKONG_STUDIO_LOG_ROOT": str(install / "Logs"),
                },
                source_root=Path(temp) / "legacy-source",
            )

            self.assertTrue(paths.desktop_mode)
            self.assertEqual(paths.script_root, (runtime / "Scripts").resolve())
            self.assertEqual(paths.bin_root, (runtime / "Bin").resolve())
            self.assertEqual(paths.mod_root, (install / "Content" / "MOD").resolve())
            for path in (
                paths.data_root,
                paths.content_root,
                paths.workspace_root,
                paths.output_root,
                paths.temp_root,
                paths.log_root,
            ):
                self.assertTrue(path.is_relative_to(install.resolve()))

            paths.ensure_writable_layout()
            self.assertTrue((install / "Data" / "Secrets").is_dir())
            self.assertTrue((install / "Temp" / "Extraction").is_dir())
            self.assertTrue((install / "Logs" / "crash").is_dir())

    def test_source_mode_keeps_legacy_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            paths = build_paths({}, source_root=source)
            self.assertFalse(paths.desktop_mode)
            self.assertEqual(paths.data_root, (source / ".wkstudio").resolve())
            self.assertEqual(paths.workspace_root, source.resolve())
            self.assertEqual(paths.web_root, (source / "studio_static").resolve())

    def test_source_mode_can_override_private_content_root(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            content = Path(temp) / "private-content"
            paths = build_paths(
                {"WUKONG_STUDIO_CONTENT_ROOT": str(content)},
                source_root=source,
            )
            self.assertFalse(paths.desktop_mode)
            self.assertEqual(paths.content_root, content.resolve())
            self.assertEqual(paths.mod_root, (content / "MOD").resolve())

    def test_source_mode_can_persist_control_plane_state_outside_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            state = root / "persistent"
            paths = build_paths(
                {
                    "WUKONG_STUDIO_DATA_ROOT": str(state / "Data"),
                    "WUKONG_STUDIO_WORKSPACE_ROOT": str(state / "Workspace"),
                    "WUKONG_STUDIO_OUTPUT_ROOT": str(state / "Output"),
                    "WUKONG_STUDIO_TEMP_ROOT": str(state / "Temp"),
                    "WUKONG_STUDIO_LOG_ROOT": str(state / "Logs"),
                },
                source_root=source,
            )

            self.assertEqual((state / "Data").resolve(), paths.data_root)
            self.assertEqual((state / "Workspace").resolve(), paths.workspace_root)
            self.assertEqual((state / "Output").resolve(), paths.output_root)
            self.assertEqual((state / "Temp").resolve(), paths.temp_root)
            self.assertEqual((state / "Logs").resolve(), paths.log_root)
            self.assertEqual((state / "Temp" / "packages").resolve(), paths.package_staging_root)

    def test_linux_tool_paths_are_platform_specific_and_not_windows_hard_coded(self):
        root = Path("tool-root").resolve()
        self.assertEqual(
            platform_tool_path("apktool_3.0.2.jar", root, system="Linux", machine="x86_64"),
            root / "Linux" / "x86_64" / "apktool_3.0.2.jar",
        )
        self.assertEqual(
            platform_tool_path("lpmake", root, system="Linux", machine="x86_64"),
            root / "Linux" / "x86_64" / "lpmake",
        )


if __name__ == "__main__":
    unittest.main()
