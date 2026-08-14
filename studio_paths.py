from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


DESKTOP_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_path(
    environ: Mapping[str, str],
    key: str,
    fallback: Path,
) -> Path:
    value = str(environ.get(key, "")).strip()
    return Path(value).expanduser().resolve() if value else fallback.resolve()


@dataclass(frozen=True)
class StudioPaths:
    source_root: Path
    desktop_mode: bool
    install_root: Path
    app_root: Path
    script_root: Path
    data_root: Path
    content_root: Path
    workspace_root: Path
    output_root: Path
    temp_root: Path
    log_root: Path
    jobs_root: Path
    package_staging_root: Path
    bin_root: Path
    config_root: Path
    flash_root: Path
    stark_root: Path
    web_root: Path
    mod_root: Path
    twrp_root: Path
    ofx_root: Path
    copy_image_root: Path

    def ensure_writable_layout(self) -> None:
        for path in (
            self.data_root,
            self.data_root / "Jobs",
            self.data_root / "Secrets",
            self.content_root,
            self.workspace_root,
            self.output_root,
            self.temp_root,
            self.temp_root / "Packages",
            self.temp_root / "Downloads",
            self.temp_root / "Extraction",
            self.log_root,
            self.log_root / "crash",
            self.install_root / "Updates",
            self.install_root / "Backups",
            self.jobs_root,
            self.package_staging_root,
        ):
            path.mkdir(parents=True, exist_ok=True)


def build_paths(
    environ: Mapping[str, str] | None = None,
    *,
    source_root: Path | None = None,
) -> StudioPaths:
    values = environ if environ is not None else os.environ
    source = (source_root or Path(__file__).resolve().parent).resolve()
    desktop_mode = str(values.get("WUKONG_STUDIO_DESKTOP_MODE", "")).strip().lower() in DESKTOP_TRUE_VALUES

    if desktop_mode:
        install = _env_path(
            values,
            "WUKONG_STUDIO_INSTALL_ROOT",
            Path(r"C:\WukongROMStudio"),
        )
        app = _env_path(values, "WUKONG_STUDIO_APP_ROOT", install / "Runtime")
        data = _env_path(values, "WUKONG_STUDIO_DATA_ROOT", install / "Data")
        content = _env_path(values, "WUKONG_STUDIO_CONTENT_ROOT", install / "Content")
        workspace = _env_path(values, "WUKONG_STUDIO_WORKSPACE_ROOT", install / "Workspace")
        output = _env_path(values, "WUKONG_STUDIO_OUTPUT_ROOT", install / "ROM_BUILD_DONE")
        temp = _env_path(values, "WUKONG_STUDIO_TEMP_ROOT", install / "Temp")
        logs = _env_path(values, "WUKONG_STUDIO_LOG_ROOT", install / "Logs")
        script_root = app / "Scripts"
        jobs_root = data / "Jobs"
        package_root = temp / "Packages"
        bin_root = app / "Bin"
        config_root = app / "Config"
        flash_root = app / "Flash_script"
        stark_root = app / "STARK"
        web_root = app / "Web"
    else:
        install = source
        app = source
        data = source / ".wkstudio"
        content = _env_path(values, "WUKONG_STUDIO_CONTENT_ROOT", source)
        workspace = source
        output = source / "ROM_BUILD_DONE"
        temp = data
        logs = data
        script_root = source
        jobs_root = data / "jobs"
        package_root = data / "packages"
        bin_root = source / "bin"
        config_root = source / "config"
        flash_root = source / "Flash_script"
        stark_root = source / "STARK"
        web_root = source / "studio_static"

    return StudioPaths(
        source_root=source,
        desktop_mode=desktop_mode,
        install_root=install,
        app_root=app,
        script_root=script_root.resolve(),
        data_root=data.resolve(),
        content_root=content.resolve(),
        workspace_root=workspace.resolve(),
        output_root=output.resolve(),
        temp_root=temp.resolve(),
        log_root=logs.resolve(),
        jobs_root=jobs_root.resolve(),
        package_staging_root=package_root.resolve(),
        bin_root=bin_root.resolve(),
        config_root=config_root.resolve(),
        flash_root=flash_root.resolve(),
        stark_root=stark_root.resolve(),
        web_root=web_root.resolve(),
        mod_root=(content / "MOD").resolve(),
        twrp_root=(content / "TWRP").resolve(),
        ofx_root=(content / "OFX").resolve(),
        copy_image_root=(content / "copy-image").resolve(),
    )


def platform_bin_dir(
    bin_root: Path | None = None,
    *,
    system: str | None = None,
    machine: str | None = None,
) -> Path:
    host_system = system or platform.system()
    host_machine = machine or platform.machine()
    if host_system == "Windows":
        architecture = "AMD64" if host_machine in {"AMD64", "x86_64"} else "x86"
    else:
        architecture = host_machine
    root = Path(bin_root) if bin_root is not None else PATHS.bin_root
    return (root / host_system / architecture).resolve()


def platform_tool_path(
    name: str,
    bin_root: Path | None = None,
    *,
    system: str | None = None,
    machine: str | None = None,
) -> Path:
    host_system = system or platform.system()
    suffix = ".exe" if host_system == "Windows" and not name.casefold().endswith(".jar") else ""
    return platform_bin_dir(
        bin_root,
        system=host_system,
        machine=machine,
    ) / f"{name}{suffix}"


PATHS = build_paths()

SOURCE_ROOT = PATHS.source_root
DESKTOP_MODE = PATHS.desktop_mode
INSTALL_ROOT = PATHS.install_root
APP_ROOT = PATHS.app_root
SCRIPT_ROOT = PATHS.script_root
DATA_ROOT = PATHS.data_root
CONTENT_ROOT = PATHS.content_root
WORKSPACE_ROOT = PATHS.workspace_root
OUTPUT_ROOT = PATHS.output_root
TEMP_ROOT = PATHS.temp_root
LOG_ROOT = PATHS.log_root
JOBS_ROOT = PATHS.jobs_root
PACKAGE_STAGING_ROOT = PATHS.package_staging_root
BIN_ROOT = PATHS.bin_root
CONFIG_ROOT = PATHS.config_root
FLASH_ROOT = PATHS.flash_root
STARK_ROOT = PATHS.stark_root
WEB_ROOT = PATHS.web_root
MOD_ROOT = PATHS.mod_root
TWRP_ROOT = PATHS.twrp_root
OFX_ROOT = PATHS.ofx_root
COPY_IMAGE_ROOT = PATHS.copy_image_root
