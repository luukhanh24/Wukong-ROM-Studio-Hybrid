from __future__ import annotations

import copy
import html
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from partition_config import (
    PartitionConfigError,
    read_partition_tree_fingerprint,
    sync_all_partition_configs,
    sync_partition_configs,
    validate_partition_configs,
)
from avb_footer import AvbFooterError, has_avb_footer, read_avb_hashtree_profile
from studio_env import load_local_env
from studio_paths import (
    BIN_ROOT,
    CONFIG_ROOT,
    CONTENT_ROOT,
    DATA_ROOT,
    DESKTOP_MODE,
    FLASH_ROOT,
    INSTALL_ROOT,
    JOBS_ROOT,
    OFX_ROOT,
    OUTPUT_ROOT,
    PACKAGE_STAGING_ROOT,
    SCRIPT_ROOT,
    STARK_ROOT,
    TWRP_ROOT,
    WORKSPACE_ROOT,
    platform_bin_dir,
    platform_tool_path,
)
from src.core.utils import gettype
from wukong.catalog import LITE_DEFAULT_MODS, PLUS_DEFAULT_EXCLUDED_MODS, SHARED_MOD_NAMES
from wukong.pipeline import DEFAULT_PIPELINE_STEPS, PIPELINE_STEP_DEFINITIONS


ROOT_DIR = SCRIPT_ROOT
RUNTIME_DIR = DATA_ROOT
JOBS_DIR = JOBS_ROOT
PACKAGE_STAGING_DIR = PACKAGE_STAGING_ROOT
ROM_BUILD_DONE = OUTPUT_ROOT
CONFIG_DIR = CONFIG_ROOT
DEBLOAT_CONFIG_PATH = CONFIG_DIR / "debloat.json"
DEVICE_CATALOG_TEMPLATE_PATH = ROOT_DIR / "devices_sizes.json"
DEVICE_CATALOG_PATH = RUNTIME_DIR / "devices_sizes.json" if DESKTOP_MODE else DEVICE_CATALOG_TEMPLATE_PATH
DEVICE_CATALOG_BACKUP_DIR = INSTALL_ROOT / "Backups" / "devices"
DEVICE_CATALOG_LOCK = threading.RLock()
STAGE_CACHE_ROOT = RUNTIME_DIR / "Cache" / "Payload"
STAGE_CACHE_LOCK = threading.RLock()
ROM_SHA256_MEMO_LOCK = threading.RLock()
_ROM_SHA256_MEMO: dict[tuple[str, int, int, int], str] = {}
ROM_SHA256_MEMO_LIMIT = 64
MOD_DIR = CONTENT_ROOT / "MOD"
DEFAULT_MOD_VERSION = "ColorOS_16.0.7"
PLATFORM_BIN_DIR = platform_bin_dir(BIN_ROOT)
APKTOOL_JAR = PLATFORM_BIN_DIR / "apktool_3.0.2.jar"
APKTOOL_DECODE_MARKER_NAME = "decoded-source.json"
WK_MANAGER_STARK_DIR = STARK_ROOT
WORKSPACE_MARKER_NAME = ".wkstudio-workspace.json"
WORKSPACE_MARKER_KIND = "wukong-rom-studio-workspace"
WORKSPACE_PIPELINE_VERSION = 21
ROM_STUDIO_VERSION = "V3.4"
MOD_VERSION_STUDIO_VERSIONS = {
    "ColorOS_16.0.8": "V4.1",
    "ColorOS_16.0.9": "V5.0",
}
STUDIO_VERSION_RE = re.compile(r"^V[0-9]+(?:\.[0-9]+){1,3}$", re.IGNORECASE)
MOD_VERSION_ALIASES = {
    "ColorOS_700": "ColorOS_16.0.7",
    "ColorOS_800": "ColorOS_16.0.8",
}
PATCHED_VBMETA_MARKER = ".requires-patched-vbmeta"
VBMETA_IMAGE_NAMES = ("vbmeta.img",)
VENDOR_BOOT_PATCH_ARGS = (
    "androidboot.vbmeta.device_state=locked",
    "androidboot.vbmeta.avb_version=1.0",
    "androidboot.vbmeta.hash_alg=sha256",
    "androidboot.vbmeta.size=4096",
    "androidboot.verifiedbootstate=green",
)
RESERVED_WORKSPACE_NAMES = {
    ".wkstudio",
    "__pycache__",
    "bin",
    "copy-image",
    "flash_script",
    "mod",
    "ofx",
    "platform_external_avb-master",
    "rom_build_done",
    "src",
    "stark",
    "studio_static",
    "tests",
    "twrp",
}
RESUME_DEFAULT_MODS: list[str] = []
BLOCKED_MODS: dict[str, str] = {}
PROTECTED_DEBLOAT_PATHS = {
    r"system_ext\app\NotificationCenter".lower(),
    r"system_ext\priv-app\Settings".lower(),
    r"system_ext\priv-app\SystemUI".lower(),
    r"system_ext\priv-app\OplusLauncher".lower(),
}
PATCH_ONLY_MODS = {
    "Block_ota": "Remove lines containing ota, romupdate or com.oplusos.sau from my_stock app-features.xml",
}
BLOCK_OTA_FEATURE_KEYWORDS = ("ota", "romupdate", "com.oplusos.sau")
THEME_CR_REMOVE_PATHS = [r"my_stock\del-app\KeKeThemeSpace"]
AI_GLOBAL_COLOROS_1605_REMOVE_PATHS = [r"my_stock\app\AIUnit"]
SELINUX_HASH_MODS = {"Fake_lock", "WK_Manager"}
FAKE_LOCK_INIT_BLOCK_START = "    # WK_STUDIO_FAKE_LOCK_BEGIN"
FAKE_LOCK_INIT_BLOCK_END = "    # WK_STUDIO_FAKE_LOCK_END"
FAKE_LOCK_LEGACY_INIT_MARKER = "    # wk needs init context for readonly boot property updates; make sure"
WK_MANAGER_METRICS_INIT_BLOCK_START = "# WK_STUDIO_WK_MANAGER_METRICS_BEGIN"
WK_MANAGER_METRICS_INIT_BLOCK_END = "# WK_STUDIO_WK_MANAGER_METRICS_END"
FAKE_LOCK_FS_CONFIG = {
    "system/bin/wk": "system/bin/wk 0 2000 0755",
    "system/system/bin/wk": "system/system/bin/wk 0 2000 0755",
}
FAKE_LOCK_FILE_CONTEXTS = {
    "/system/bin/wk": "/system/bin/wk u:object_r:wk_exec:s0",
    "/system/system/bin/wk": "/system/system/bin/wk u:object_r:wk_exec:s0",
}
ANDROID_LF_TEXT_SUFFIXES = {
    ".cil",
    ".conf",
    ".config",
    ".prop",
    ".rc",
    ".sh",
    ".txt",
    ".xml",
}
UNSAFE_VENDOR_PRIV_APP_SYSFS_RE = re.compile(
    r"^\(allow\s+priv_app_34_0\s+vendor_sysfs_(?:kgsl|kgsl_gpuclk|graphics)\s+"
    r"\((?:dir|file|lnk_file)\s+\([^)]+\)\)\)$"
)

PARTITIONS = [
    "my_bigball",
    "my_carrier",
    "my_company",
    "my_engineering",
    "my_heytap",
    "my_manifest",
    "my_preload",
    "my_product",
    "my_region",
    "my_stock",
    "odm",
    "product",
    "system",
    "system_dlkm",
    "system_ext",
    "vendor",
    "vendor_dlkm",
]
PASSTHROUGH_PARTITIONS = {
    "my_bigball",
    "my_carrier",
    "my_engineering",
    "my_heytap",
    "odm",
    "product",
    "system_dlkm",
    "vendor",
    "vendor_dlkm",
}
MUTABLE_PARTITIONS = tuple(name for name in PARTITIONS if name not in PASSTHROUGH_PARTITIONS)
MOD_PARTITIONS = set(MUTABLE_PARTITIONS)
REQUIRED_IMAGES = {
    "boot.img",
    "dtbo.img",
    "init_boot.img",
    "modem.img",
    "recovery.img",
    "super.img",
    "vbmeta.img",
    "vbmeta_system.img",
    "vbmeta_vendor.img",
    "vendor_boot.img",
}
CORE_SOURCE_IMAGES = {
    "recovery.img",
    "vbmeta_system.img",
    "vbmeta_vendor.img",
    "boot.img",
    "dtbo.img",
    "init_boot.img",
    "modem.img",
}
DYNAMIC_SOURCE_IMAGES = {f"{name}.img" for name in PARTITIONS}
EXCLUDED_FIRMWARE = DYNAMIC_SOURCE_IMAGES | CORE_SOURCE_IMAGES | {
    "vbmeta.img",
    "vendor_boot.img",
}

STEP_DEFINITIONS = list(PIPELINE_STEP_DEFINITIONS)
STEP_ORDER = [step[0] for step in STEP_DEFINITIONS]
STEP_LABELS = {step[0]: step[1] for step in STEP_DEFINITIONS}
DEFAULT_STEPS = set(DEFAULT_PIPELINE_STEPS)
PLUS_DEFAULT_STEPS: set[str] = set()
ZIP_COMPRESSION_LEVEL = "1"
ZIP_COMPRESSION_LABEL = "fast"
ZIP_PROGRESS_RE = re.compile(r"(?<!\d)(100|[1-9]?\d)%")


@dataclass
class BuildSpec:
    romPath: str
    modName: str | None = None
    modNames: list[str] = field(default_factory=list)
    modVersion: str = DEFAULT_MOD_VERSION
    debloatPaths: list[str] | None = None
    preset: str = "lite"
    enabledSteps: list[str] = field(default_factory=list)
    resumeFromJobId: str | None = None
    notifyTelegram: bool = False
    romSha256: str | None = None
    specFingerprint: str | None = None
    resumePreset: str | None = None

    def selected_mod_names(self) -> list[str]:
        names = self.modNames or ([self.modName] if self.modName else [])
        return list(dict.fromkeys(name for name in names if name))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BuildSpec":
        preset = str(payload.get("preset", "lite")).lower()
        if preset == "standard":
            preset = "lite"
        mod_version = normalize_mod_version(payload.get("modVersion"))
        raw_mod_names = payload.get("modNames")
        if raw_mod_names is None:
            raw_mod_names = (
                [payload["modName"]]
                if payload.get("modName")
                else preset_default_mods(preset, mod_version)
            )
        if not isinstance(raw_mod_names, list):
            raw_mod_names = [raw_mod_names]
        # Empty MOD lists for Plus/Lite presets mean "use preset defaults", not
        # "skip every MOD". Custom builds may still pass an explicit empty list
        # only when apply_mod is intentionally omitted from enabledSteps.
        if (
            isinstance(raw_mod_names, list)
            and not [str(name).strip() for name in raw_mod_names if str(name).strip()]
            and preset in {"lite", "plus", "resume", "both"}
            and not payload.get("modName")
        ):
            try:
                raw_mod_names = preset_default_mods(preset, mod_version)
            except StudioError:
                raw_mod_names = []
        raw_debloat_paths = payload.get("debloatPaths")
        if raw_debloat_paths is not None and not isinstance(raw_debloat_paths, list):
            raw_debloat_paths = []
        return cls(
            romPath=str(payload.get("romPath", "")).strip(),
            modName=(str(payload["modName"]).strip() if payload.get("modName") else None),
            modNames=[str(name).strip() for name in raw_mod_names if str(name).strip()],
            modVersion=mod_version,
            debloatPaths=(
                [str(path).strip() for path in raw_debloat_paths if str(path).strip()]
                if raw_debloat_paths is not None
                else None
            ),
            preset=preset,
            enabledSteps=[str(step) for step in payload.get("enabledSteps", [])],
            resumeFromJobId=payload.get("resumeFromJobId"),
            notifyTelegram=bool(payload.get("notifyTelegram", False)),
            romSha256=(str(payload.get("romSha256") or "").strip() or None),
            specFingerprint=(str(payload.get("specFingerprint") or "").strip() or None),
            resumePreset=(str(payload.get("resumePreset") or "").strip().lower() or None),
        )


@dataclass
class StepResult:
    step: str
    status: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class BuildContext:
    job_id: str
    spec: BuildSpec
    workspace: Path
    metadata: dict[str, Any]
    device: dict[str, Any]
    output_zip: Path | None = None
    output_zips: list[Path] = field(default_factory=list)
    package_tasks: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    reuse_package_assets: bool = False
    defer_package_notifications: bool = False
    selective_repack: bool = False
    modified_partitions: set[str] = field(default_factory=set)
    file_hash_cache: dict[tuple[int, int, int, int], str] = field(default_factory=dict)
    progress_callback: Callable[[dict[str, Any]], None] | None = field(default=None, repr=False, compare=False)

    @property
    def source_rom(self) -> Path:
        return self.workspace / "source_rom"

    @property
    def rom_unpack(self) -> Path:
        return self.workspace / "rom-unpack"

    @property
    def rom_repack(self) -> Path:
        return self.workspace / "rom-repack"

    @property
    def build_dir(self) -> Path:
        return self.workspace / "Build"

    @property
    def rom_build(self) -> Path:
        return self.workspace / "ROM_build"

    @property
    def package_cache(self) -> Path:
        return self.workspace / "package-cache"


class StudioError(RuntimeError):
    pass


def build_edition_name(spec: "BuildSpec") -> str:
    preset = "lite" if spec.preset == "standard" else spec.preset
    if preset == "resume" and spec.resumePreset:
        preset = spec.resumePreset
    if preset == "custom":
        return "Custom"
    if preset in {"resume", "plus", "both"}:
        return "Plus"
    return "Lite"


def default_studio_version(mod_version: str | None) -> str:
    normalized = normalize_mod_version(mod_version)
    return MOD_VERSION_STUDIO_VERSIONS.get(normalized, ROM_STUDIO_VERSION)


def normalize_studio_version(value: Any, fallback: str = ROM_STUDIO_VERSION) -> str:
    candidate = str(value or "").strip().upper()
    if not STUDIO_VERSION_RE.fullmatch(candidate):
        return fallback
    return candidate


def studio_version_settings() -> dict[str, str]:
    settings_path = RUNTIME_DIR / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        settings = {}
    raw_versions = settings.get("studioVersions")
    if not isinstance(raw_versions, dict):
        return {}
    versions: dict[str, str] = {}
    for raw_mod_version, raw_studio_version in raw_versions.items():
        try:
            mod_version = normalize_mod_version(raw_mod_version)
        except StudioError:
            continue
        versions[mod_version] = normalize_studio_version(
            raw_studio_version,
            default_studio_version(mod_version),
        )
    return versions


def studio_version_name(spec: "BuildSpec") -> str:
    return studio_version_settings().get(
        normalize_mod_version(spec.modVersion),
        default_studio_version(spec.modVersion),
    )


def output_zip_name(version_name: str, spec: "BuildSpec", suffix: str = "") -> str:
    version = sanitize_version_name(version_name)
    edition = build_edition_name(spec)
    studio_version = studio_version_name(spec)
    return f"Wukong_{edition}_{studio_version}_{version}_China_Stable{suffix}.zip"


def _load_legacy() -> Any:
    module_name = "wukong_legacy_build_main"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, ROOT_DIR / "Build-main.py")
    if spec is None or spec.loader is None:
        raise StudioError("Cannot load Build-main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def device_catalog_path() -> Path:
    """Return the writable catalog path used by the current runtime mode."""
    return DEVICE_CATALOG_PATH


def _device_catalog_read_path() -> Path:
    if DEVICE_CATALOG_PATH.is_file():
        return DEVICE_CATALOG_PATH
    if DEVICE_CATALOG_TEMPLATE_PATH.is_file():
        return DEVICE_CATALOG_TEMPLATE_PATH
    return DEVICE_CATALOG_PATH


def _device_field(device: dict[str, Any], *names: str) -> Any:
    fields = {str(key).casefold(): value for key, value in device.items()}
    for name in names:
        key = name.casefold()
        if key in fields:
            return fields[key]
    return None


def _device_text(value: Any, field_name: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise StudioError(f"{field_name} phải là chuỗi")
    normalized = value.strip()
    if not normalized:
        raise StudioError(f"{field_name} không được để trống")
    if len(normalized) > max_length or any(ord(character) < 32 for character in normalized):
        raise StudioError(f"{field_name} không hợp lệ")
    return normalized


def _device_size(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise StudioError(f"{field_name} phải là số nguyên")
    if isinstance(value, int):
        normalized = value
    elif isinstance(value, str) and value.strip().isdigit():
        normalized = int(value.strip())
    else:
        raise StudioError(f"{field_name} phải là số nguyên")
    if normalized <= 0 or normalized > 1024 * 1024**3:
        raise StudioError(f"{field_name} nằm ngoài giới hạn hỗ trợ")
    if normalized % 4096:
        raise StudioError(f"{field_name} phải căn chỉnh theo 4096 byte")
    return normalized


def normalize_device_catalog(devices: Any) -> list[dict[str, Any]]:
    if not isinstance(devices, list):
        raise StudioError("Danh mục thiết bị phải là một mảng JSON")

    normalized_devices: list[dict[str, Any]] = []
    product_names: set[str] = set()
    for index, raw_device in enumerate(devices, start=1):
        if not isinstance(raw_device, dict):
            raise StudioError(f"Thiết bị #{index} phải là một object JSON")

        product_name = _device_text(
            _device_field(raw_device, "product_name", "productName"),
            "product_name",
            max_length=64,
        )
        if not re.fullmatch(r"[A-Za-z0-9._-]+", product_name):
            raise StudioError("product_name chỉ được chứa chữ, số, dấu chấm, gạch dưới hoặc gạch ngang")
        product_key = product_name.casefold()
        if product_key in product_names:
            raise StudioError(f"product_name bị trùng: {product_name}")
        product_names.add(product_key)

        name = _device_text(_device_field(raw_device, "name"), "name", max_length=120)
        soc = _device_text(_device_field(raw_device, "soc"), "soc", max_length=48)
        super_size = _device_size(_device_field(raw_device, "SuperSize", "superSize"), "SuperSize")
        group_size = _device_size(_device_field(raw_device, "GroupSize", "groupSize"), "GroupSize")
        if group_size > super_size:
            raise StudioError("GroupSize không được lớn hơn SuperSize")

        raw_partitions = _device_field(raw_device, "Partitions", "partitions")
        if raw_partitions is None:
            raw_partitions = []
        if not isinstance(raw_partitions, list):
            raise StudioError("Partitions phải là một mảng")
        partitions: list[str] = []
        partition_names: set[str] = set()
        for raw_partition in raw_partitions:
            partition = _device_text(raw_partition, "Partition", max_length=64)
            if not re.fullmatch(r"[A-Za-z0-9._-]+", partition):
                raise StudioError(f"Tên phân vùng không hợp lệ: {partition}")
            partition_key = partition.casefold()
            if partition_key in partition_names:
                raise StudioError(f"Phân vùng bị trùng trong {product_name}: {partition}")
            partition_names.add(partition_key)
            partitions.append(partition)

        normalized_devices.append(
            {
                "product_name": product_name,
                "name": name,
                "soc": soc,
                "SuperSize": super_size,
                "GroupSize": group_size,
                "Partitions": partitions,
            }
        )
    return normalized_devices


def load_devices() -> list[dict[str, Any]]:
    with DEVICE_CATALOG_LOCK:
        path = _device_catalog_read_path()
        try:
            with path.open("r", encoding="utf-8") as handle:
                return normalize_device_catalog(json.load(handle))
        except (OSError, json.JSONDecodeError) as exc:
            raise StudioError(f"Không thể đọc danh mục thiết bị {path}: {exc}") from exc


def save_devices(devices: Any) -> list[dict[str, Any]]:
    normalized = normalize_device_catalog(devices)
    target = DEVICE_CATALOG_PATH
    with DEVICE_CATALOG_LOCK:
        target.parent.mkdir(parents=True, exist_ok=True)
        source = _device_catalog_read_path()
        if source.is_file():
            DEVICE_CATALOG_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            shutil.copy2(source, DEVICE_CATALOG_BACKUP_DIR / f"devices_sizes-{timestamp}.json")

        temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(normalized, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

        backups = sorted(DEVICE_CATALOG_BACKUP_DIR.glob("devices_sizes-*.json"), reverse=True)
        for stale_backup in backups[25:]:
            stale_backup.unlink(missing_ok=True)
    return normalized


def _align_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def _partition_size_from_extents(partition: dict[str, Any]) -> int:
    extents = partition.get("extents") or []
    total_sectors = 0
    for extent in extents:
        match = re.match(r"\s*(\d+)\s*\.\.\s*(\d+)", str(extent))
        if match:
            total_sectors += int(match.group(2)) - int(match.group(1)) + 1
    return total_sectors * 512 if total_sectors else int(partition.get("size") or 0)


def _normalize_layout_info(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise StudioError("Metadata layout phải là một object JSON")
    if isinstance(raw.get("layout"), dict):
        raw = raw["layout"]

    block_devices = raw.get("block_devices") or raw.get("blockDevices") or []
    groups = raw.get("group_table") or raw.get("groups") or []
    partitions = raw.get("partition_table") or raw.get("partitions") or []
    if not isinstance(block_devices, list) or not isinstance(groups, list) or not isinstance(partitions, list):
        raise StudioError("Metadata super không chứa block device, group hoặc partition hợp lệ")

    normalized_groups = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        normalized_groups.append(
            {
                "name": str(group.get("name") or "default"),
                "maximumSize": int(group.get("maximum_size") or group.get("maximumSize") or 0),
                "flags": str(group.get("flags") or "none"),
            }
        )
    normalized_partitions = []
    for partition in partitions:
        if not isinstance(partition, dict):
            continue
        normalized_partitions.append(
            {
                "name": str(partition.get("name") or ""),
                "groupName": str(partition.get("group_name") or partition.get("groupName") or "default"),
                "size": _partition_size_from_extents(partition),
                "attributes": str(partition.get("attributes") or ""),
            }
        )
    normalized_blocks = []
    for block in block_devices:
        if not isinstance(block, dict):
            continue
        normalized_blocks.append(
            {
                "name": str(block.get("name") or "super"),
                "size": int(block.get("size") or 0),
                "firstSector": int(block.get("first_sector") or block.get("firstSector") or 0),
                "alignment": int(block.get("alignment") or 0),
                "blockSize": int(block.get("block_size") or block.get("blockSize") or 4096),
            }
        )
    if not normalized_blocks:
        raise StudioError("Không tìm thấy block device super trong metadata")
    return {
        "metadataVersion": str(raw.get("metadata_version") or raw.get("metadataVersion") or "unknown"),
        "metadataMaxSize": int(raw.get("metadata_max_size") or raw.get("metadataMaxSize") or 0),
        "metadataSlotCount": int(raw.get("metadata_slot_count") or raw.get("metadataSlotCount") or 0),
        "blockDevices": normalized_blocks,
        "groups": normalized_groups,
        "partitions": normalized_partitions,
    }


def _parse_layout_text(content: str) -> dict[str, Any]:
    metadata_max = re.search(r"Metadata max size:\s*(\d+)", content, re.IGNORECASE)
    metadata_slots = re.search(r"Metadata slot count:\s*(\d+)", content, re.IGNORECASE)
    block_matches = re.findall(
        r"Partition name:\s*([^\r\n]+).*?First sector:\s*(\d+).*?Size:\s*(\d+)\s*bytes",
        content,
        re.IGNORECASE | re.DOTALL,
    )
    group_section = content.split("Group table:", 1)[-1] if "Group table:" in content else content
    group_matches = re.findall(
        r"Name:\s*([^\r\n]+).*?Maximum size:\s*(\d+)",
        group_section,
        re.IGNORECASE | re.DOTALL,
    )
    partition_section = content.split("Partition table:", 1)[-1]
    if "Super partition layout:" in partition_section:
        partition_section = partition_section.split("Super partition layout:", 1)[0]
    partition_matches = re.findall(
        r"Name:\s*([^\r\n]+).*?Group:\s*([^\r\n]+).*?Extents:\s*(.*?)(?=\n-+|\Z)",
        partition_section,
        re.IGNORECASE | re.DOTALL,
    )
    raw = {
        "metadata_max_size": int(metadata_max.group(1)) if metadata_max else 0,
        "metadata_slot_count": int(metadata_slots.group(1)) if metadata_slots else 0,
        "block_devices": [
            {"name": name.strip(), "first_sector": int(first), "size": int(size)}
            for name, first, size in block_matches
        ],
        "group_table": [
            {"name": name.strip(), "maximum_size": int(size)}
            for name, size in group_matches
        ],
        "partition_table": [
            {
                "name": name.strip(),
                "group_name": group.strip(),
                "extents": [line.strip() for line in extents.splitlines() if ".." in line],
            }
            for name, group, extents in partition_matches
        ],
    }
    return _normalize_layout_info(raw)


def read_partition_layout_source(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise StudioError(f"Không tìm thấy nguồn phân tích layout: {source}")
    suffix = source.suffix.casefold()
    if suffix == ".img":
        try:
            from src.core.lpunpack import get_info

            return _normalize_layout_info(get_info(str(source)))
        except SystemExit as exc:
            raise StudioError("Không thể đọc metadata logical partition từ super image") from exc
        except Exception as exc:
            raise StudioError(f"Không thể phân tích super image: {exc}") from exc
    if source.stat().st_size > 32 * 1024 * 1024:
        raise StudioError("File lpdump text/JSON vượt quá giới hạn 32 MiB")
    content = source.read_text(encoding="utf-8", errors="replace")
    if suffix == ".json" or content.lstrip().startswith("{"):
        try:
            return _normalize_layout_info(json.loads(content))
        except json.JSONDecodeError as exc:
            raise StudioError(f"JSON layout không hợp lệ: {exc}") from exc
    return _parse_layout_text(content)


def analyze_partition_layout(
    device: dict[str, Any],
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    configured = normalize_device_catalog([device])[0]
    super_size = int(configured["SuperSize"])
    group_size = int(configured["GroupSize"])
    configured_reserve = super_size - group_size
    warnings: list[str] = []
    errors: list[str] = []
    if configured_reserve < 4 * 1024**2:
        warnings.append("Khoảng dự phòng giữa SuperSize và GroupSize nhỏ hơn 4 MiB")
    if configured_reserve > 1024**3:
        warnings.append("Khoảng dự phòng lớn hơn 1 GiB; cần xác nhận đây là chủ ý")

    result: dict[str, Any] = {
        "mode": "catalog",
        "sourcePath": str(Path(source_path).resolve()) if source_path else None,
        "configured": {
            "productName": configured["product_name"],
            "name": configured["name"],
            "soc": configured["soc"],
            "superSize": super_size,
            "groupSize": group_size,
            "reserveBytes": configured_reserve,
            "partitions": configured["Partitions"],
        },
        "actual": None,
        "warnings": warnings,
        "errors": errors,
        "score": 100,
        "status": "healthy",
    }
    if not source_path:
        result["score"] = 85 if warnings else 95
        result["status"] = "warning" if warnings else "catalog-only"
        return result

    layout = read_partition_layout_source(source_path)
    result["mode"] = "super-metadata"
    block = max(layout["blockDevices"], key=lambda item: int(item["size"]))
    actual_super = int(block["size"])
    group_usage: dict[str, int] = {}
    for partition in layout["partitions"]:
        group_name = partition["groupName"]
        group_usage[group_name] = group_usage.get(group_name, 0) + int(partition["size"])
    groups = []
    for group in layout["groups"]:
        maximum = int(group["maximumSize"])
        used = group_usage.get(group["name"], 0)
        groups.append(
            {
                **group,
                "usedBytes": used,
                "freeBytes": max(0, maximum - used) if maximum else 0,
                "usagePercent": round(used * 100 / maximum, 2) if maximum else 0,
            }
        )
        if maximum and used > maximum:
            errors.append(f"Group {group['name']} vượt giới hạn {used - maximum} byte")
    actual_group = max((int(group["maximumSize"]) for group in groups), default=0)
    actual_partition_names = {partition["name"].removesuffix("_a").removesuffix("_b") for partition in layout["partitions"]}
    missing = [name for name in configured["Partitions"] if name not in actual_partition_names]
    if actual_super != super_size:
        warnings.append(f"SuperSize catalog lệch {actual_super - super_size:+d} byte so với image")
    if actual_group and actual_group != group_size:
        warnings.append(f"GroupSize catalog lệch {actual_group - group_size:+d} byte so với metadata")
    if missing:
        warnings.append("Thiếu logical partition bổ sung: " + ", ".join(missing))

    total_used = sum(int(partition["size"]) for partition in layout["partitions"])
    safety_headroom = max(512 * 1024**2, int(total_used * 0.08))
    recommended_group = min(
        max(0, actual_super - max(4 * 1024**2, int(block["firstSector"]) * 512)),
        _align_up(total_used + safety_headroom, 1024**2),
    )
    score = max(0, 100 - len(warnings) * 10 - len(errors) * 35)
    result.update(
        {
            "actual": {
                **layout,
                "superSize": actual_super,
                "groupSize": actual_group,
                "metadataReserveBytes": int(block["firstSector"]) * 512,
                "totalPartitionBytes": total_used,
                "groups": groups,
            },
            "comparison": {
                "superDeltaBytes": actual_super - super_size,
                "groupDeltaBytes": actual_group - group_size if actual_group else None,
                "missingConfiguredPartitions": missing,
            },
            "recommendation": {
                "superSize": actual_super,
                "minimumGroupSize": recommended_group,
                "safetyHeadroomBytes": safety_headroom,
            },
            "warnings": warnings,
            "errors": errors,
            "score": score,
            "status": "error" if errors else "warning" if warnings else "healthy",
        }
    )
    return result


def find_device(product_name: str | None) -> dict[str, Any] | None:
    if not product_name:
        return None
    return next((device for device in load_devices() if device.get("product_name") == product_name), None)


def sanitize_version_name(value: str | None, fallback: str = "rom") -> str:
    raw = (value or fallback).strip()
    raw = raw.replace("\\", "_").replace("/", "_")
    raw = re.sub(r"[^A-Za-z0-9._()\-]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip(" ._")
    if not raw or raw in {".", ".."}:
        raw = fallback
    return raw[:120]


def _validate_project_workspace_path(workspace: Path, *, root: Path | None = None) -> Path:
    project_root = (root or (WORKSPACE_ROOT if DESKTOP_MODE else ROOT_DIR)).resolve()
    resolved = workspace.resolve()
    if resolved.parent != project_root or resolved == project_root:
        raise StudioError(f"Workspace must be a direct child of project root: {resolved}")
    if resolved.name.casefold() in RESERVED_WORKSPACE_NAMES:
        raise StudioError(f"Workspace name is reserved by the project: {resolved.name}")
    return resolved


def workspace_for_version(
    version_name: str | None,
    *,
    fallback: str = "rom",
    root: Path | None = None,
) -> Path:
    project_root = (root or (WORKSPACE_ROOT if DESKTOP_MODE else ROOT_DIR)).resolve()
    workspace = project_root / sanitize_version_name(version_name, fallback=fallback)
    return _validate_project_workspace_path(workspace, root=project_root)


def _workspace_marker_path(workspace: Path) -> Path:
    return workspace / WORKSPACE_MARKER_NAME


def _read_workspace_marker(workspace: Path) -> dict[str, Any]:
    return json.loads(_workspace_marker_path(workspace).read_text(encoding="utf-8"))


def is_managed_workspace(workspace: Path, *, root: Path | None = None) -> bool:
    try:
        resolved = _validate_project_workspace_path(workspace, root=root)
        payload = _read_workspace_marker(resolved)
    except (StudioError, OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("kind") == WORKSPACE_MARKER_KIND
        and payload.get("versionName") == resolved.name
    )


def is_resume_compatible_workspace(
    workspace: Path,
    *,
    root: Path | None = None,
    rom_sha256: str | None = None,
    spec_fingerprint: str | None = None,
) -> bool:
    try:
        resolved = _validate_project_workspace_path(workspace, root=root)
        payload = _read_workspace_marker(resolved)
    except (StudioError, OSError, json.JSONDecodeError):
        return False
    compatible = (
        payload.get("kind") == WORKSPACE_MARKER_KIND
        and payload.get("versionName") == resolved.name
        and payload.get("pipelineVersion") == WORKSPACE_PIPELINE_VERSION
    )
    if rom_sha256 is not None:
        compatible = compatible and payload.get("romSha256") == rom_sha256
    if spec_fingerprint is not None:
        compatible = compatible and payload.get("specFingerprint") == spec_fingerprint
    return compatible


def claim_workspace(
    workspace: Path,
    job_id: str,
    version_name: str,
    *,
    root: Path | None = None,
    rom_sha256: str | None = None,
    spec_fingerprint: str | None = None,
) -> Path:
    resolved = _validate_project_workspace_path(workspace, root=root)
    if resolved.exists():
        if not resolved.is_dir():
            raise StudioError(f"Workspace path is not a directory: {resolved}")
        if not is_managed_workspace(resolved, root=root):
            raise StudioError(
                f"Workspace already exists and is not managed by Studio: {resolved}"
            )
    else:
        resolved.mkdir(parents=False)
    _write_json_atomic(
        _workspace_marker_path(resolved),
        {
            "kind": WORKSPACE_MARKER_KIND,
            "versionName": resolved.name,
            "jobId": job_id,
            "pipelineVersion": WORKSPACE_PIPELINE_VERSION,
            "romSha256": rom_sha256,
            "specFingerprint": spec_fingerprint,
        },
    )
    return resolved


def prepare_workspace(
    workspace: Path,
    job_id: str,
    version_name: str,
    *,
    resume: bool,
    root: Path | None = None,
    rom_sha256: str | None = None,
    spec_fingerprint: str | None = None,
) -> Path:
    resolved = _validate_project_workspace_path(workspace, root=root)
    if resume:
        if not is_resume_compatible_workspace(
            resolved,
            root=root,
            rom_sha256=rom_sha256,
            spec_fingerprint=spec_fingerprint,
        ):
            raise StudioError(f"Resume workspace is unavailable or uses an outdated pipeline: {resolved}")
    elif resolved.exists():
        if not is_managed_workspace(resolved, root=root):
            raise StudioError(
                f"Workspace already exists and is not managed by Studio: {resolved}"
            )
        shutil.rmtree(resolved)
    resolved.mkdir(parents=False, exist_ok=True)
    _write_json_atomic(
        _workspace_marker_path(resolved),
        {
            "kind": WORKSPACE_MARKER_KIND,
            "versionName": sanitize_version_name(version_name),
            "jobId": job_id,
            "pipelineVersion": WORKSPACE_PIPELINE_VERSION,
            "romSha256": rom_sha256,
            "specFingerprint": spec_fingerprint,
        },
    )
    return resolved


def cleanup_workspace(
    workspace: Path,
    *,
    root: Path | None = None,
    expected_job_id: str | None = None,
) -> bool:
    resolved = _validate_project_workspace_path(workspace, root=root)
    if not resolved.exists():
        return False
    if not is_managed_workspace(resolved, root=root):
        raise StudioError(f"Refusing to clean unmanaged workspace: {resolved}")
    if expected_job_id is not None:
        try:
            owner = str(_read_workspace_marker(resolved).get("jobId") or "")
        except (OSError, json.JSONDecodeError) as exc:
            raise StudioError(f"Cannot verify workspace ownership: {resolved}") from exc
        if owner != expected_job_id:
            raise StudioError(
                f"Refusing to clean workspace owned by another job: {owner or 'unknown'}"
            )
    shutil.rmtree(resolved)
    return True


def read_rom_metadata(rom_path: str | Path) -> dict[str, Any]:
    path = Path(rom_path).resolve()
    metadata_suffix = "META-INF/com/android/metadata"
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            metadata_name = next(
                (name for name in names if name.replace("\\", "/").endswith(metadata_suffix)),
                None,
            )
            if not metadata_name:
                raise StudioError(f"Missing {metadata_suffix}")
            content = archive.read(metadata_name).decode("utf-8", errors="replace")
            payload_name = next((name for name in names if name.endswith("payload.bin")), None)
    except zipfile.BadZipFile as exc:
        raise StudioError("ROM is not a valid ZIP file") from exc

    metadata: dict[str, str | None] = {
        "version_name": None,
        "product_name": None,
        "payload_name": payload_name,
    }
    for line in content.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lower()
        if "version_name" in key:
            metadata["version_name"] = value.strip()
        elif "product_name" in key:
            metadata["product_name"] = value.strip()
    metadata["version_name"] = sanitize_version_name(
        metadata["version_name"], fallback=path.stem
    )
    return metadata


def _required_rom_version_name(rom_path: Path) -> str:
    metadata_suffix = "META-INF/com/android/metadata"
    try:
        with zipfile.ZipFile(rom_path, "r") as archive:
            metadata_name = next(
                (
                    name
                    for name in archive.namelist()
                    if name.replace("\\", "/").endswith(metadata_suffix)
                ),
                None,
            )
            if not metadata_name:
                raise StudioError(f"Missing {metadata_suffix}")
            content = archive.read(metadata_name).decode("utf-8", errors="replace")
    except zipfile.BadZipFile as exc:
        raise StudioError("ROM is not a valid ZIP file") from exc
    except (OSError, RuntimeError) as exc:
        raise StudioError(f"Cannot read ROM ZIP: {exc}") from exc

    version_name = ""
    for line in content.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if "version_name" in key.strip().lower():
            version_name = value.strip()
    if not version_name:
        raise StudioError("ROM metadata does not contain version_name")
    if version_name in {".", ".."} or any(char in version_name for char in ("/", "\\", "\0")):
        raise StudioError("ROM metadata version_name contains an unsafe path component")
    return version_name


def _rom_rename_path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve())).casefold()


def _rom_rename_entry(rom_path: str | Path) -> dict[str, Any]:
    source = Path(rom_path).expanduser().resolve()
    entry: dict[str, Any] = {
        "sourcePath": str(source),
        "sourceName": source.name,
        "versionName": None,
        "targetPath": None,
        "targetName": None,
        "status": "error",
        "warning": None,
        "error": None,
    }
    try:
        if not source.is_file():
            raise StudioError("ROM ZIP does not exist")
        if source.suffix.casefold() != ".zip":
            raise StudioError("ROM must be a .zip file")
        version_name = _required_rom_version_name(source)
        sanitized = sanitize_version_name(version_name, fallback="rom")
        if sanitized.casefold() in {
            "con",
            "prn",
            "aux",
            "nul",
            *(f"com{index}" for index in range(1, 10)),
            *(f"lpt{index}" for index in range(1, 10)),
        }:
            raise StudioError("ROM metadata version_name is reserved by Windows")
        target = source.with_name(f"{sanitized}.zip")
        entry.update(
            {
                "versionName": version_name,
                "targetPath": str(target),
                "targetName": target.name,
                "status": (
                    "unchanged"
                    if source.name.casefold() == target.name.casefold()
                    else "ready"
                ),
                "warning": (
                    "version_name was normalized for a safe Windows filename"
                    if sanitized != version_name
                    else None
                ),
            }
        )
    except StudioError as exc:
        entry["error"] = str(exc)
    return entry


def preview_rom_renames(rom_paths: Iterable[str | Path]) -> dict[str, Any]:
    entries = [_rom_rename_entry(path) for path in rom_paths]
    target_groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if entry["targetPath"]:
            target_groups.setdefault(
                _rom_rename_path_key(Path(entry["targetPath"])), []
            ).append(entry)

    for group in target_groups.values():
        if len(group) <= 1:
            continue
        for entry in group:
            entry["status"] = "error"
            entry["error"] = "Multiple ROM ZIP files resolve to the same target filename"

    moving_source_keys = {
        _rom_rename_path_key(Path(entry["sourcePath"]))
        for entry in entries
        if entry["status"] == "ready"
    }
    for entry in entries:
        if entry["status"] != "ready":
            continue
        target = Path(entry["targetPath"])
        if target.exists() and _rom_rename_path_key(target) not in moving_source_keys:
            entry["status"] = "error"
            entry["error"] = f"Target ZIP already exists: {target.name}"

    error_count = sum(entry["status"] == "error" for entry in entries)
    ready_count = sum(entry["status"] == "ready" for entry in entries)
    unchanged_count = sum(entry["status"] == "unchanged" for entry in entries)
    return {
        "entries": entries,
        "total": len(entries),
        "ready": ready_count,
        "unchanged": unchanged_count,
        "errors": error_count,
        "canApply": error_count == 0 and ready_count > 0,
    }


def _unique_rom_rename_temp(source: Path, index: int) -> Path:
    attempt = 0
    while True:
        suffix = f"{os.getpid()}-{time.time_ns()}-{index}-{attempt}"
        candidate = source.with_name(f".{source.name}.wkrename-{suffix}.tmp")
        if not candidate.exists():
            return candidate
        attempt += 1


def apply_rom_renames(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    requested = list(entries)
    if not requested:
        raise StudioError("No ROM ZIP files were selected")
    sources = [str(entry.get("sourcePath") or "") for entry in requested]
    preview = preview_rom_renames(sources)
    if preview["errors"]:
        first_error = next(
            entry["error"] for entry in preview["entries"] if entry["error"]
        )
        raise StudioError(first_error)

    for expected, actual in zip(requested, preview["entries"], strict=True):
        expected_target = str(expected.get("targetPath") or "")
        if not expected_target or _rom_rename_path_key(Path(expected_target)) != _rom_rename_path_key(
            Path(actual["targetPath"])
        ):
            raise StudioError("ROM rename preview is stale; run preview again")

    moving = [entry for entry in preview["entries"] if entry["status"] == "ready"]
    staged: list[tuple[Path, Path, Path]] = []
    finalized: list[tuple[Path, Path, Path]] = []
    try:
        for index, entry in enumerate(moving):
            source = Path(entry["sourcePath"])
            target = Path(entry["targetPath"])
            temporary = _unique_rom_rename_temp(source, index)
            source.rename(temporary)
            staged.append((source, temporary, target))
        for record in staged:
            source, temporary, target = record
            if target.exists():
                raise StudioError(f"Target ZIP appeared during rename: {target.name}")
            temporary.rename(target)
            finalized.append(record)
    except Exception as exc:
        for _source, temporary, target in reversed(finalized):
            if target.exists() and not temporary.exists():
                target.rename(temporary)
        for source, temporary, _target in reversed(staged):
            if temporary.exists() and not source.exists():
                temporary.rename(source)
        if isinstance(exc, StudioError):
            raise
        raise StudioError(f"Could not rename ROM ZIP files: {exc}") from exc

    results = []
    for entry in preview["entries"]:
        result = dict(entry)
        if result["status"] == "ready":
            result["status"] = "renamed"
        results.append(result)
    return {
        "entries": results,
        "total": len(results),
        "renamed": len(moving),
        "unchanged": preview["unchanged"],
    }


def _mod_special_actions(name: str) -> list[str]:
    actions = []
    if name in PATCH_ONLY_MODS:
        actions.append(PATCH_ONLY_MODS[name])
    if name == "Fix_noti":
        actions.append("Patch oplus-services.jar with apktool")
    if name == "Global_props":
        actions.append("Upsert US timezone, region and locale properties")
    if name == "Ai_global":
        actions.append("ColorOS 16.0.5 only: remove my_stock app AIUnit")
    if name == "Theme_cr":
        actions.append("Remove duplicate my_stock del-app KeKeThemeSpace before packaging")
    if name == "WK_Manager":
        actions.append("Patch framework.jar, services.jar and oplus-services.jar with apktool")
        actions.append("Import STARK smali into framework.jar")
        actions.append("Inject read-only GPU metric chmod hooks into existing init.rc")
        actions.append("Allow WukongManager priv-app metric reads via platform SELinux")
    if name == "Fake_lock":
        actions.append("Inject wk commands into init.rc on post-fs-data")
        actions.append("Force wk executable permission and SELinux repack context")
    if name in SELINUX_HASH_MODS:
        actions.append("Refresh platform SELinux checksum using detected stock profile")
    return actions


def list_mod_versions(*, mod_root: Path | None = None) -> list[str]:
    root = (mod_root or MOD_DIR).resolve()
    if not root.is_dir():
        return []
    return sorted(
        (path.name for path in root.iterdir() if path.is_dir()),
        key=str.lower,
    )


def normalize_mod_version(value: Any = None, *, mod_root: Path | None = None) -> str:
    root = (mod_root or MOD_DIR).resolve()
    version = str(value or DEFAULT_MOD_VERSION).strip()
    if not version or Path(version).name != version or version in {".", ".."}:
        raise StudioError(f"Invalid MOD version: {version}")
    version = MOD_VERSION_ALIASES.get(version, version)
    collection_dir = root / version
    if collection_dir.is_dir():
        return version
    if version == DEFAULT_MOD_VERSION and root.is_dir():
        return version
    raise StudioError(f"MOD version does not exist: {version}")


def _mod_collection_dir(mod_version: str | None = None, *, mod_root: Path | None = None) -> Path:
    root = (mod_root or MOD_DIR).resolve()
    version = normalize_mod_version(mod_version, mod_root=root)
    collection_dir = root / version
    return collection_dir if collection_dir.is_dir() else root


def list_mods(mod_version: str | None = None, *, mod_root: Path | None = None) -> list[dict[str, Any]]:
    root = (mod_root or MOD_DIR).resolve()
    shared_root = (
        ((CONTENT_ROOT / "STARK").resolve() if (CONTENT_ROOT / "STARK").is_dir() else STARK_ROOT.resolve())
        if mod_root is None
        else root.parent / "STARK"
    )
    version = normalize_mod_version(mod_version, mod_root=root)
    collection_dir = _mod_collection_dir(version, mod_root=root)
    results = []
    seen = set()
    sources = [(collection_dir, False), (shared_root, True)]
    for source_root, shared in sources:
        if source_root.is_dir():
            for mod_dir in sorted(path for path in source_root.iterdir() if path.is_dir()):
                if shared and mod_dir.name not in SHARED_MOD_NAMES:
                    continue
                if mod_dir.name in seen:
                    continue
                patch_only = mod_dir.name in PATCH_ONLY_MODS
                directories = sorted(path.name for path in mod_dir.iterdir() if path.is_dir())
                compatible = [name for name in directories if name in MOD_PARTITIONS]
                skipped = [name for name in directories if name not in MOD_PARTITIONS]
                root_files = sorted(path.name for path in mod_dir.iterdir() if path.is_file())
                blocked_reason = BLOCKED_MODS.get(mod_dir.name)
                results.append(
                    {
                        "name": mod_dir.name,
                        "version": version,
                        "valid": bool(compatible) or patch_only,
                        "ready": (bool(compatible) or patch_only) and not blocked_reason,
                        "blockedReason": blocked_reason,
                        "partitions": compatible,
                        "patchOnly": patch_only,
                        "shared": shared,
                        "skippedDirectories": skipped,
                        "rootFiles": root_files,
                        "specialActions": _mod_special_actions(mod_dir.name),
                    }
                )
                seen.add(mod_dir.name)
    for name in sorted(PATCH_ONLY_MODS):
        if name in seen:
            continue
        blocked_reason = BLOCKED_MODS.get(name)
        results.append(
            {
                "name": name,
                "version": version,
                "valid": True,
                "ready": not blocked_reason,
                "blockedReason": blocked_reason,
                "partitions": [],
                "patchOnly": True,
                "shared": False,
                "skippedDirectories": [],
                "rootFiles": [],
                "specialActions": _mod_special_actions(name),
            }
        )
    return sorted(results, key=lambda mod: mod["name"].lower())


def validate_mod(mod_name: str | None, mod_version: str | None = None) -> dict[str, Any] | None:
    if not mod_name:
        return None
    candidate = next((mod for mod in list_mods(mod_version) if mod["name"] == mod_name), None)
    if candidate is None:
        raise StudioError(f"MOD does not exist: {mod_name}")
    if not candidate["valid"]:
        raise StudioError(f"MOD has no supported partition folders: {mod_name}")
    return candidate


def validate_mods(
    mod_names: Iterable[str] | None,
    *,
    allow_blocked: bool = False,
    mod_version: str | None = None,
) -> list[dict[str, Any]]:
    results = []
    for name in dict.fromkeys(mod_names or []):
        mod = validate_mod(name, mod_version)
        if mod is None:
            continue
        if mod.get("blockedReason") and not allow_blocked:
            raise StudioError(str(mod["blockedReason"]))
        results.append(mod)
    return results


def preset_default_mods(
    preset: str,
    mod_version: str | None = None,
    *,
    mod_root: Path | None = None,
) -> list[str]:
    normalized = "lite" if preset == "standard" else preset
    mods = list_mods(mod_version, mod_root=mod_root)
    if normalized == "lite":
        return [name for name in LITE_DEFAULT_MODS if any(mod["name"] == name for mod in mods)]
    if normalized in {"resume", "plus", "both"}:
        return [
            mod["name"]
            for mod in mods
            if mod["name"] not in PLUS_DEFAULT_EXCLUDED_MODS
        ]
    return []


def default_debloat_paths() -> list[str]:
    try:
        payload = json.loads(DEBLOAT_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudioError(f"Cannot load debloat config: {DEBLOAT_CONFIG_PATH}") from exc
    values = payload.get("default") if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise StudioError("Debloat config must contain a string list")
    return list(values)


def validate_debloat_paths(paths: Iterable[str] | None) -> list[str]:
    values = default_debloat_paths() if paths is None else list(paths)
    normalized = []
    for value in values:
        path = str(value).strip().replace("/", "\\")
        parts = [part for part in path.split("\\") if part]
        if (
            len(parts) < 2
            or parts[0] not in MUTABLE_PARTITIONS
            or any(part in {".", ".."} for part in parts)
            or Path(path).is_absolute()
        ):
            raise StudioError(f"Invalid debloat path: {value}")
        clean = "\\".join(parts)
        if clean.lower() in PROTECTED_DEBLOAT_PATHS:
            continue
        if clean not in normalized:
            normalized.append(clean)
    return normalized


def _required_binary_paths() -> list[Path]:
    return [
        platform_tool_path("extract.erofs", BIN_ROOT),
        platform_tool_path("mkfs.erofs", BIN_ROOT),
        platform_tool_path("lpmake", BIN_ROOT),
        platform_tool_path("magiskboot", BIN_ROOT),
        platform_tool_path("cpio", BIN_ROOT),
    ]


def inspect_rom(
    rom_path: str | Path,
    mod_name: str | None = None,
    *,
    mod_names: Iterable[str] | None = None,
    mod_version: str | None = None,
    debloat_paths: Iterable[str] | None = None,
    enforce_space: bool = True,
    required_steps: Iterable[str] | None = None,
) -> dict[str, Any]:
    path = Path(rom_path).expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    metadata: dict[str, Any] = {}
    device = None
    mod = None
    mods: list[dict[str, Any]] = []
    selected_mod_version = DEFAULT_MOD_VERSION
    requested_steps = set(required_steps or [])
    selected_mod_names = list(dict.fromkeys(mod_names or ([mod_name] if mod_name else [])))
    try:
        selected_mod_version = normalize_mod_version(mod_version)
    except StudioError as exc:
        errors.append(str(exc))

    if not path.is_file():
        errors.append("ROM ZIP does not exist")
    elif path.suffix.lower() != ".zip":
        errors.append("ROM must be a .zip file")
    else:
        try:
            metadata = read_rom_metadata(path)
            if not metadata.get("payload_name"):
                errors.append("payload.bin is missing from ROM ZIP")
            device = find_device(metadata.get("product_name"))
            if device is None:
                errors.append(f"Unsupported product: {metadata.get('product_name') or 'unknown'}")
        except (OSError, StudioError) as exc:
            errors.append(str(exc))

    try:
        mods = validate_mods(
            selected_mod_names,
            allow_blocked="apply_mod" not in requested_steps,
            mod_version=selected_mod_version,
        )
        mod = mods[0] if mods else None
    except StudioError as exc:
        errors.append(str(exc))
    if "apply_mod" in requested_steps and not mods:
        errors.append("Apply MOD step requires a valid MOD selection")
    if mods and "apply_mod" not in requested_steps:
        warnings.append("Selected MODs will be skipped because Apply MOD is disabled")
    if "debloat" in requested_steps:
        try:
            validate_debloat_paths(debloat_paths)
        except StudioError as exc:
            errors.append(str(exc))
    jar_patch_mods = {"Fix_noti", "WK_Manager"}.intersection(selected_mod_names)
    if "apply_mod" in requested_steps and jar_patch_mods:
        if not APKTOOL_JAR.is_file():
            errors.append(f"Missing apktool dependency: {APKTOOL_JAR}")
        if not shutil.which("java"):
            errors.append("Java is required to patch selected JAR MODs")
    if (
        "apply_mod" in requested_steps
        and "WK_Manager" in selected_mod_names
        and not WK_MANAGER_STARK_DIR.is_dir()
    ):
        errors.append(f"Missing WK_Manager STARK smali directory: {WK_MANAGER_STARK_DIR}")

    missing_bins = [str(path) for path in _required_binary_paths() if not path.is_file()]
    if missing_bins:
        errors.append("Missing required build binaries")
    ROM_BUILD_DONE.mkdir(parents=True, exist_ok=True)
    if not os.access(ROM_BUILD_DONE, os.W_OK):
        errors.append(f"Output directory is not writable: {ROM_BUILD_DONE}")

    disk_root = WORKSPACE_ROOT if DESKTOP_MODE else ROOT_DIR
    disk_root.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(disk_root)
    required_free = (path.stat().st_size * 3 + 10 * 1024**3) if path.is_file() else 0
    if required_free and disk.free < required_free:
        message = (
            f"Low disk space: need {required_free / 1024**3:.1f} GiB, "
            f"available {disk.free / 1024**3:.1f} GiB"
        )
        if enforce_space:
            errors.append(message)
        else:
            warnings.append(message)

    return {
        "ok": not errors,
        "path": str(path),
        "size": path.stat().st_size if path.is_file() else 0,
        "metadata": metadata,
        "device": device,
        "mod": mod,
        "mods": mods,
        "modVersion": selected_mod_version,
        "errors": errors,
        "warnings": warnings,
        "missingBinaries": missing_bins,
        "disk": {
            "free": disk.free,
            "total": disk.total,
            "required": required_free,
        },
    }


def validate_source_rom(source_rom: Path) -> bool:
    required = {"boot.img", "vbmeta.img", "vendor_boot.img", "system.img"}
    return source_rom.is_dir() and all((source_rom / name).is_file() for name in required)


def validate_rom_unpack(rom_unpack: Path, source_rom: Path | None = None) -> bool:
    if not rom_unpack.is_dir():
        return False
    expected = [
        name
        for name in MUTABLE_PARTITIONS
        if source_rom is None or (source_rom / f"{name}.img").is_file()
    ]
    if not expected:
        return False
    try:
        for name in expected:
            filesystem_type = (
                partition_filesystem_type(source_rom / f"{name}.img")
                if source_rom is not None
                else None
            )
            if source_rom is not None and filesystem_type is None:
                return False
            validate_partition_configs(
                rom_unpack / f"{name}_unpacked",
                name,
                filesystem_type,
            )
    except PartitionConfigError:
        return False
    return True


def partition_filesystem_type(path: Path) -> str | None:
    image_type = gettype(str(path))
    if image_type == "erofs":
        return "erofs"
    if image_type == "ext":
        return "ext4"
    return None


def _ext4_repack_profile(path: Path) -> dict[str, Any] | None:
    try:
        from src.core import ext4

        with path.open("rb") as handle:
            volume = ext4.Volume(handle)
            lost_found = volume.root.get_inode("lost+found")
            return {
                "size": path.stat().st_size,
                "uuid": str(volume.uuid),
                "inodes": volume.superblock.s_inodes_count,
                "lostFound": (
                    lost_found.inode.i_uid,
                    lost_found.inode.i_gid,
                    lost_found.inode.i_mode,
                ),
            }
    except (OSError, ext4.Ext4Error):
        return None


def validate_rom_repack(rom_repack: Path, source_rom: Path | None = None) -> bool:
    if not rom_repack.is_dir():
        return False
    expected = [
        name
        for name in PARTITIONS
        if source_rom is None or (source_rom / f"{name}.img").is_file()
    ]
    if not expected:
        return False
    for name in expected:
        output = rom_repack / f"{name}.img"
        if not output.is_file() or output.stat().st_size <= 0:
            return False
        output_type = gettype(str(output))
        if output_type not in {"erofs", "ext", "sparse"}:
            return False
        if source_rom is not None:
            source_type = gettype(str(source_rom / f"{name}.img"))
            if source_type in {"erofs", "ext", "sparse"} and output_type != source_type:
                return False
    return True


def _read_sparse_prefix(
    stream: Any,
    wanted: int = 8 * 1024 * 1024,
    *,
    validate_full: bool = False,
) -> bytes:
    def read_exact(size: int, label: str) -> bytes:
        data = stream.read(size)
        if len(data) != size:
            raise StudioError(f"Truncated sparse image {label}")
        return data

    header = stream.read(28)
    if len(header) != 28:
        raise StudioError("Short sparse image header")
    magic, _, _, file_header_size, chunk_header_size, block_size, total_blocks, chunks, _ = struct.unpack(
        "<I4H4I", header
    )
    if magic != 0xED26FF3A:
        raise StudioError("super.img is not Android sparse format")
    if file_header_size > 28:
        read_exact(file_header_size - 28, "file header")
    result = bytearray()
    raw_position = 0
    for _ in range(chunks):
        chunk_header = read_exact(chunk_header_size, "chunk header")
        chunk_type, _, chunk_size, total_size = struct.unpack("<2H2I", chunk_header[:12])
        raw_length = chunk_size * block_size
        data_length = total_size - chunk_header_size
        take = max(0, min(raw_position + raw_length, wanted) - raw_position)
        if chunk_type == 0xCAC1:
            if data_length != raw_length:
                raise StudioError("Sparse RAW chunk has an invalid data length")
            remaining = data_length
            captured = 0
            while remaining:
                data = read_exact(min(8 * 1024**2, remaining), "RAW chunk")
                if captured < take:
                    amount = min(take - captured, len(data))
                    result.extend(data[:amount])
                    captured += amount
                remaining -= len(data)
        elif chunk_type == 0xCAC2:
            if data_length != 4:
                raise StudioError("Sparse FILL chunk has an invalid data length")
            pattern = read_exact(data_length, "FILL chunk")
            if take:
                result.extend((pattern * ((take + len(pattern) - 1) // len(pattern)))[:take])
        elif chunk_type == 0xCAC3:
            if data_length != 0:
                raise StudioError("Sparse DONT_CARE chunk has unexpected data")
            result.extend(b"\0" * take)
        elif chunk_type == 0xCAC4:
            if data_length != 4:
                raise StudioError("Sparse CRC32 chunk has an invalid data length")
            read_exact(data_length, "CRC32 chunk")
        else:
            raise StudioError(f"Unsupported sparse chunk type: 0x{chunk_type:04x}")
        raw_position += raw_length
        if not validate_full and raw_position >= wanted:
            break
    if validate_full:
        expected_raw_size = total_blocks * block_size
        if raw_position != expected_raw_size:
            raise StudioError(
                f"Sparse image raw size mismatch: {raw_position} != {expected_raw_size}"
            )
        if stream.read(1):
            raise StudioError("Sparse image contains trailing data")
    return bytes(result)


def _partition_names_from_sparse_stream(stream: Any, *, validate_full: bool = False) -> set[str]:
    from src.core.lpunpack import LpUnpack

    prefix = _read_sparse_prefix(stream, validate_full=validate_full)
    unpacker = object.__new__(LpUnpack)
    unpacker._fd = io.BytesIO(prefix)
    metadata = unpacker._read_metadata()
    return {partition.name for partition in metadata.partitions}


def validate_super(super_img: Path, device: dict[str, Any] | None = None) -> dict[str, Any]:
    if not super_img.is_file() or super_img.stat().st_size <= 4096:
        raise StudioError("super.img is missing or too small")
    with super_img.open("rb") as stream:
        header = stream.read(28)
        if len(header) != 28:
            raise StudioError("Short sparse image header")
        _, _, _, _, _, block_size, total_blocks, _, _ = struct.unpack("<I4H4I", header)
        stream.seek(0)
        partitions = _partition_names_from_sparse_stream(stream, validate_full=True)
    raw_size = block_size * total_blocks
    if device and int(device.get("SuperSize") or 0) not in {0, raw_size}:
        raise StudioError(
            f"super.img raw size does not match device config: {raw_size} != {device['SuperSize']}"
        )
    expected = {f"{name}_a" for name in PARTITIONS}
    if device:
        expected.update(f"{name}_a" for name in device.get("Partitions", []))
    missing = sorted(expected - partitions)
    if missing:
        raise StudioError(f"super.img is missing logical partitions: {', '.join(missing)}")
    return {"partitions": sorted(partitions), "missing": missing, "rawSize": raw_size}


def normalize_zip_validation_mode(value: Any) -> str:
    return "deep" if str(value or "").strip().lower() == "deep" else "fast"


def validate_final_zip(
    zip_path: Path,
    device: dict[str, Any] | None = None,
    mode: str = "fast",
) -> dict[str, Any]:
    if not zip_path.is_file():
        raise StudioError("Output ZIP was not created")
    validation_mode = normalize_zip_validation_mode(mode)
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            infos = archive.infolist()
            names = {item.filename.replace("\\", "/") for item in infos}
            images = {
                Path(name).name
                for name in names
                if name.startswith("images/") and not name.endswith("/")
            }
            artifacts = {
                Path(name).name
                for name in names
                if name.startswith(("images/", "firmware-update/")) and not name.endswith("/")
            }
            missing = sorted(REQUIRED_IMAGES - images)
            if missing:
                raise StudioError(f"Output ZIP is missing images: {', '.join(missing)}")
            try:
                manifest = archive.read("wukong_md5_hashes.txt").decode(
                    "utf-8", errors="replace"
                )
            except KeyError as exc:
                raise StudioError("Output ZIP is missing wukong_md5_hashes.txt") from exc
            listed: dict[str, str] = {}
            for line_number, raw_line in enumerate(manifest.splitlines(), start=1):
                line = raw_line.strip()
                if not line:
                    continue
                match = re.fullmatch(r"([0-9a-fA-F]{32})\s{2}(.+)", line)
                if not match:
                    raise StudioError(f"Manifest contains invalid syntax at line {line_number}")
                name = match.group(2).strip()
                if name in listed:
                    raise StudioError(f"Manifest contains duplicate artifact: {name}")
                listed[name] = match.group(1).lower()
            unlisted = sorted(artifacts - set(listed))
            if unlisted:
                raise StudioError(f"Manifest is missing artifact hashes: {', '.join(unlisted)}")
            unknown = sorted(set(listed) - artifacts)
            if unknown:
                raise StudioError(f"Manifest lists missing artifacts: {', '.join(unknown)}")

            artifact_infos: dict[str, zipfile.ZipInfo] = {}
            for info in infos:
                normalized = info.filename.replace("\\", "/")
                if info.is_dir() or not normalized.startswith(("images/", "firmware-update/")):
                    continue
                name = Path(normalized).name
                if name in artifact_infos:
                    raise StudioError(f"Output ZIP contains duplicate artifact name: {name}")
                if info.file_size <= 0:
                    raise StudioError(f"Output ZIP contains empty artifact: {name}")
                if info.compress_size < 0 or info.header_offset < 0:
                    raise StudioError(f"Output ZIP contains invalid artifact metadata: {name}")
                artifact_infos[name] = info

            if validation_mode == "deep":
                artifact_entries = set(artifact_infos.values())
                for info in infos:
                    if info.is_dir() or info.filename.replace("\\", "/") == "wukong_md5_hashes.txt":
                        continue
                    digest = hashlib.md5() if info in artifact_entries else None
                    with archive.open(info) as stream:
                        while chunk := stream.read(8 * 1024**2):
                            if digest is not None:
                                digest.update(chunk)
                    if digest is not None:
                        name = Path(info.filename.replace("\\", "/")).name
                        if digest.hexdigest() != listed[name]:
                            raise StudioError(f"Artifact hash mismatch: {name}")
            with archive.open("images/super.img") as stream:
                partitions = _partition_names_from_sparse_stream(stream)
    except StudioError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise StudioError("Output ZIP is corrupt") from exc

    expected = {f"{name}_a" for name in PARTITIONS}
    if device:
        expected.update(f"{name}_a" for name in device.get("Partitions", []))
    missing_partitions = sorted(expected - partitions)
    if missing_partitions:
        raise StudioError(
            f"Packaged super.img is missing partitions: {', '.join(missing_partitions)}"
        )
    return {
        "entries": len(infos),
        "images": sorted(images),
        "partitions": sorted(partitions),
        "size": zip_path.stat().st_size,
        "validationMode": validation_mode,
        "crcVerified": validation_mode == "deep",
    }


def _marker_path(workspace: Path, step: str) -> Path:
    return workspace / ".studio-markers" / f"{step}.json"


def _write_marker(workspace: Path, result: StepResult, spec: BuildSpec | None = None) -> None:
    marker = _marker_path(workspace, result.step)
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    if spec is not None:
        payload["romSha256"] = spec.romSha256
        payload["specFingerprint"] = spec.specFingerprint
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _has_marker(workspace: Path, step: str, spec: BuildSpec | None = None) -> bool:
    marker = _marker_path(workspace, step)
    if not marker.is_file():
        return False
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("status") != "success":
        return False
    if spec is not None:
        if spec.romSha256 is not None and payload.get("romSha256") != spec.romSha256:
            return False
        if spec.specFingerprint is not None and payload.get("specFingerprint") != spec.specFingerprint:
            return False
        if spec.preset == "resume" and (payload.get("details") or {}).get("phase") == "Lite":
            return False
    return True


def plan_steps(spec: BuildSpec, workspace: Path | None = None) -> list[str]:
    preset = "lite" if spec.preset == "standard" else spec.preset
    resume_requested = preset == "resume"
    if resume_requested and spec.resumePreset:
        preset = spec.resumePreset
    if preset == "plus":
        preset = "resume"
    preset = preset if preset in {"lite", "resume", "custom", "both"} else "lite"
    explicit_targets = preset == "custom" or bool(spec.enabledSteps)
    if explicit_targets:
        selected = set(spec.enabledSteps)
    else:
        selected = set(DEFAULT_STEPS)
        if preset in {"resume", "both"}:
            selected.update(PLUS_DEFAULT_STEPS)
        if spec.selected_mod_names():
            selected.add("apply_mod")
    if spec.notifyTelegram:
        selected.add("notify_telegram")
    if "notify_telegram" in selected:
        selected.add("package_zip")

    if workspace and resume_requested:
        validators: dict[str, Callable[[], bool]] = {
            "extract_payload": lambda: validate_source_rom(workspace / "source_rom"),
            "unpack_partitions": lambda: validate_rom_unpack(
                workspace / "rom-unpack", workspace / "source_rom"
            ),
            "repack_partitions": lambda: validate_rom_repack(
                workspace / "rom-repack", workspace / "source_rom"
            ),
            "repack_super": lambda: (workspace / "Build" / "super.img").is_file(),
        }
        for step in STEP_ORDER:
            if step in {"inspect_rom", "package_zip", "notify_telegram"}:
                continue
            if step not in selected:
                continue
            validator = validators.get(step)
            if _has_marker(workspace, step, spec) and (validator is None or validator()):
                selected.remove(step)
                continue
            break

    return [step for step in STEP_ORDER if step in selected]


def _run_command(command: list[str], *, cwd: Path = ROOT_DIR) -> None:
    print(f"[*] CMD: {' '.join(command)}", flush=True)
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise StudioError(f"Command failed with exit code {result.returncode}: {command[0]}")


def _emit_progress(context: BuildContext, progress: int, message: str = "") -> None:
    if not context.progress_callback:
        return
    context.progress_callback(
        {
            "progress": max(0, min(100, int(progress))),
            "progressMessage": message,
        }
    )


def _run_7z_package(command: list[str], context: BuildContext, *, cwd: Path = ROOT_DIR) -> None:
    print(f"[*] CMD: {' '.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None
    buffer = ""
    last_progress = -1

    def handle_record(record: str) -> None:
        nonlocal last_progress
        text = record.strip()
        if not text:
            return
        match = None
        for match in ZIP_PROGRESS_RE.finditer(text):
            pass
        if match:
            progress = max(0, min(100, int(match.group(1))))
            if progress != last_progress:
                last_progress = progress
                _emit_progress(context, round(progress * 0.9), f"ZIP {progress}%")
                print(f"[*] ZIP progress: {progress}%", flush=True)
            return
        print(text, flush=True)

    try:
        while True:
            chunk = process.stdout.read(1)
            if chunk == "":
                break
            if chunk in "\r\n":
                handle_record(buffer)
                buffer = ""
            else:
                buffer += chunk
        handle_record(buffer)
    finally:
        process.stdout.close()
    return_code = process.wait()
    if return_code != 0:
        raise StudioError(f"Command failed with exit code {return_code}: {command[0]}")
    _emit_progress(context, 90, "ZIP 100% · chuẩn bị hậu kiểm")
    if last_progress != 100:
        print("[*] ZIP progress: 100%", flush=True)


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise StudioError(f"Unsafe relative path: {value}")
    return path


def _write_text_lf(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode(encoding))


def _normalize_android_text_file_lf(path: Path) -> bool:
    if path.suffix.lower() not in ANDROID_LF_TEXT_SUFFIXES and path.name != "build.prop":
        return False
    original = path.read_bytes()
    normalized = original.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized == original:
        return False
    path.write_bytes(normalized)
    return True


def validate_no_unsafe_vendor_priv_app_sysfs(rom_unpack: Path) -> dict[str, Any]:
    policy = rom_unpack / "vendor_unpacked" / "vendor" / "etc" / "selinux" / "vendor_sepolicy.cil"
    if not policy.is_file():
        return {"checked": False, "reason": "vendor_sepolicy.cil not unpacked"}
    unsafe: list[tuple[int, str]] = []
    for line_no, line in enumerate(policy.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        stripped = line.strip()
        if UNSAFE_VENDOR_PRIV_APP_SYSFS_RE.match(stripped):
            unsafe.append((line_no, stripped))
    if unsafe:
        preview = "; ".join(f"{line_no}: {rule}" for line_no, rule in unsafe[:3])
        raise StudioError(
            "Unsafe vendor SELinux rules detected for priv_app_34_0 -> vendor_sysfs. "
            "These rules are known to break boot on Snapdragon 8 Elite. "
            f"Remove them from {policy}. First matches: {preview}"
        )
    return {"checked": True, "path": str(policy), "unsafeRules": 0}


def _partition_destination(
    rom_unpack: Path,
    partition: str,
    device: dict[str, Any] | None,
) -> tuple[str, Path] | None:
    target_partition = partition
    soc = str((device or {}).get("soc", ""))
    if partition == "vendor_arm64":
        if soc and soc > "86xx":
            return None
        target_partition = "vendor"
    elif partition == "vendor_aidl":
        if soc and soc < "87xx":
            return None
        target_partition = "vendor"
    if target_partition in PASSTHROUGH_PARTITIONS:
        return None
    destination = rom_unpack / f"{target_partition}_unpacked" / target_partition
    return (target_partition, destination) if destination.is_dir() else None


def apply_stark_patch(source: Path, destination: Path) -> dict[str, int]:
    if not source.is_file():
        raise StudioError(f"Stark patch file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = destination.read_text(encoding="utf-8", errors="replace") if destination.is_file() else ""
    lines = original.splitlines()
    added = removed = replaced = 0

    for instruction in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if not instruction.strip():
            continue
        operation = instruction[0] if instruction[0] in {"+", "-", "!"} else "="
        payload = instruction[1:] if operation in {"+", "-", "!"} else instruction
        normalized = payload.strip()
        if not normalized:
            continue
        if (
            source.name == "stark_vendor_sepolicy.cil"
            and normalized.startswith("(allow priv_app_34_0 vendor_sysfs_")
        ):
            raise StudioError(
                "Unsafe WK_Manager vendor SELinux rule blocked: priv_app_34_0 "
                "must not be granted vendor_sysfs access from vendor sepolicy"
            )
        if operation == "+":
            if not any(line.strip() == normalized for line in lines):
                insert_index = _stark_xml_insert_index(source.name, lines, normalized)
                if insert_index is None:
                    lines.append(payload)
                else:
                    lines.insert(insert_index, payload)
                added += 1
        elif operation == "-":
            retained = [line for line in lines if line.strip() != normalized]
            removed += len(lines) - len(retained)
            lines = retained
        elif operation == "!":
            if "=" not in payload:
                raise StudioError(f"Stark upsert line has no '=': {source.name}: {payload}")
            key = payload.split("=", 1)[0].strip()
            matches = [
                index
                for index, line in enumerate(lines)
                if "=" in line and line.split("=", 1)[0].strip() == key
            ]
            if matches:
                for index in matches:
                    if lines[index] != payload:
                        lines[index] = payload
                        replaced += 1
            else:
                lines.append(payload)
                added += 1
        else:
            if "=" not in payload:
                raise StudioError(f"Stark replacement line has no '=': {source.name}: {payload}")
            key = payload.split("=", 1)[0].strip()
            matches = [
                index
                for index, line in enumerate(lines)
                if "=" in line and line.split("=", 1)[0].strip() == key
            ]
            if not matches:
                raise StudioError(f"Stark replacement key was not found: {source.name}: {key}")
            for index in matches:
                lines[index] = payload
                replaced += 1

    _write_text_lf(destination, "\n".join(lines) + ("\n" if lines else ""))
    return {"added": added, "removed": removed, "replaced": replaced}


def _stark_xml_insert_index(source_name: str, lines: list[str], normalized: str) -> int | None:
    if not source_name.endswith(".xml") or not normalized.startswith("<oplus-feature "):
        return None
    for index, line in enumerate(lines):
        if line.strip() == "</oplus-config>":
            return index
    return None


def _patch_product_display_version(path: Path, edition: str, studio_version: str) -> int:
    if not path.is_file():
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    changed = 0
    key = "ro.build.version.oplusrom.display"
    for index, line in enumerate(lines):
        if not line.startswith(f"{key}="):
            continue
        value = line.split("=", 1)[1].split("|", 1)[0].strip()
        replacement = f"{key}={value} | {edition} | {studio_version}"
        if line != replacement:
            lines[index] = replacement
            changed += 1
    if changed:
        _write_text_lf(path, "\n".join(lines) + "\n")
    return changed


def _replace_oneplus_brand(path: Path) -> int:
    if not path.is_file():
        return 0
    content = path.read_text(encoding="utf-8", errors="replace")
    updated = content.replace("一加", "OnePlus")
    if updated == content:
        return 0
    _write_text_lf(path, updated)
    return content.count("一加")


def remove_stock_ota_feature_lines(rom_unpack: Path) -> int:
    feature_xml = (
        rom_unpack
        / "my_stock_unpacked"
        / "my_stock"
        / "etc"
        / "extension"
        / "com.oplus.app-features.xml"
    )
    if not feature_xml.is_file():
        return 0
    lines = feature_xml.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [
        line
        for line in lines
        if not any(keyword in line.lower() for keyword in BLOCK_OTA_FEATURE_KEYWORDS)
    ]
    removed = len(lines) - len(kept)
    if removed:
        _write_text_lf(feature_xml, "\n".join(kept) + ("\n" if kept else ""))
    return removed


def patch_build_branding(
    rom_unpack: Path,
    edition: str,
    studio_version: str = ROM_STUDIO_VERSION,
) -> dict[str, int]:
    manifest_prop = rom_unpack / "my_manifest_unpacked" / "my_manifest" / "build.prop"
    product_prop = rom_unpack / "my_product_unpacked" / "my_product" / "build.prop"
    return {
        "manifestDisplayVersion": _patch_product_display_version(
            manifest_prop,
            edition,
            studio_version,
        ),
        "productDisplayVersion": _patch_product_display_version(
            product_prop,
            edition,
            studio_version,
        ),
        "manifestBrand": _replace_oneplus_brand(manifest_prop),
        "productBrand": _replace_oneplus_brand(product_prop),
    }


def _stark_destination(partition_destination: Path, relative: Path) -> Path:
    filename = relative.name.removeprefix("stark_")
    candidate = partition_destination / relative.parent / filename
    if candidate.is_file():
        return candidate
    matches = list(partition_destination.rglob(filename))
    if len(matches) == 1:
        return matches[0]
    if not matches and candidate.parent.is_dir():
        return candidate
    raise StudioError(
        f"Cannot resolve stark patch target for {relative}: found {len(matches)} candidates"
    )


def _preserve_zip_entry_attributes(original: Path, rebuilt: Path) -> None:
    temporary = original.with_name(f"{original.name}.studio-tmp")
    with zipfile.ZipFile(original, "r") as original_zip, zipfile.ZipFile(rebuilt, "r") as rebuilt_zip:
        original_infos = {info.filename: info for info in original_zip.infolist()}
        with zipfile.ZipFile(temporary, "w") as output:
            written = set()
            for rebuilt_info in rebuilt_zip.infolist():
                info = copy.copy(rebuilt_info)
                previous = original_infos.get(info.filename)
                if previous:
                    info.compress_type = previous.compress_type
                    info.comment = previous.comment
                    info.extra = previous.extra
                    info.internal_attr = previous.internal_attr
                    info.external_attr = previous.external_attr
                    info.create_system = previous.create_system
                    info.date_time = previous.date_time
                output.writestr(info, rebuilt_zip.read(rebuilt_info.filename))
                written.add(info.filename)
            for original_info in original_zip.infolist():
                if original_info.filename not in written:
                    output.writestr(copy.copy(original_info), original_zip.read(original_info.filename))
    temporary.replace(original)


def _patch_fix_noti_smali(decoded: Path) -> None:
    candidates = list(
        decoded.rglob("OplusNotificationManagerServiceExtImpl$NotificationUidObserver.smali")
    )
    if len(candidates) != 1:
        raise StudioError(
            "Fix_noti could not locate exactly one NotificationUidObserver smali file"
        )
    path = candidates[0]
    content = path.read_text(encoding="utf-8")
    method_match = re.search(
        r"(?ms)^\.method private synthetic lambda\$onUidGone\$0\(I\)V\b.*?^\.end method$",
        content,
    )
    if not method_match:
        raise StudioError("Fix_noti target method lambda$onUidGone$0(I)V was not found")
    method = method_match.group(0)
    anchor = (
        "invoke-static {}, "
        "Lcom/android/server/notification/OplusNotificationManagerServiceExtImpl;"
        "->-$$Nest$sfgetARRAY_PKG_REMOVE_NOTIFICATION()[Ljava/lang/String;"
    )
    anchor_index = method.find(anchor)
    if anchor_index < 0:
        raise StudioError("Fix_noti anchor invoke-static was not found")
    before_anchor = method[:anchor_index]
    after_anchor = method[anchor_index:]
    branches = list(
        re.finditer(r"(?m)^([ \t]*)if-eqz v[01],[ \t]*:[A-Za-z0-9_]+[ \t]*$", before_anchor)
    )
    if not branches:
        if re.search(r"(?m)^[ \t]*nop\s*\n[ \t]*nop\s*$", before_anchor):
            return
        raise StudioError("Fix_noti target if-eqz branch was not found")
    branch = branches[-1]
    indent = branch.group(1)
    patched_before = (
        before_anchor[: branch.start()]
        + f"{indent}nop\n\n{indent}nop"
        + before_anchor[branch.end() :]
    )
    _write_text_lf(path, content.replace(method, patched_before + after_anchor, 1))


def _patch_jar_with_apktool(
    jar: Path,
    work_dir: Path,
    patcher: Callable[[Path], Any],
    *,
    reuse_decoded_from: Path | None = None,
    status_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    if not jar.is_file():
        raise StudioError(f"JAR patch target is missing: {jar}")
    if not APKTOOL_JAR.is_file():
        raise StudioError(f"apktool dependency is missing: {APKTOOL_JAR}")
    work_dir.mkdir(parents=True, exist_ok=True)
    decoded = work_dir / "decoded"
    rebuilt = work_dir / "rebuilt.jar"
    if rebuilt.exists():
        rebuilt.unlink()
    with zipfile.ZipFile(jar, "r") as archive:
        before_profile = {info.filename: info.compress_type for info in archive.infolist()}
    jar_hash = _file_sha256(jar)
    decoded_reused = False
    if reuse_decoded_from is not None:
        reuse_marker = reuse_decoded_from / APKTOOL_DECODE_MARKER_NAME
        reuse_decoded = reuse_decoded_from / "decoded"
        try:
            marker = json.loads(reuse_marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            marker = {}
        if (
            reuse_decoded.is_dir()
            and marker.get("jar") == jar.name
            and marker.get("sha256") == jar_hash
        ):
            decoded = reuse_decoded
            decoded_reused = True

    decode_started = time.perf_counter()
    if decoded_reused:
        if status_callback:
            status_callback(f"Tái sử dụng decode {jar.name}")
    else:
        if decoded.exists():
            shutil.rmtree(decoded)
        if status_callback:
            status_callback(f"Giải mã {jar.name}")
        _run_command(["java", "-jar", str(APKTOOL_JAR), "d", "-f", str(jar), "-o", str(decoded)])
    decode_seconds = time.perf_counter() - decode_started

    patch_started = time.perf_counter()
    report = patcher(decoded)
    patch_seconds = time.perf_counter() - patch_started
    for generated in (decoded / "build", decoded / "dist"):
        if generated.exists():
            shutil.rmtree(generated)
    if status_callback:
        status_callback(f"Đóng gói {jar.name}")
    build_started = time.perf_counter()
    _run_command(["java", "-jar", str(APKTOOL_JAR), "b", str(decoded), "-o", str(rebuilt)])
    build_seconds = time.perf_counter() - build_started
    preserve_started = time.perf_counter()
    _preserve_zip_entry_attributes(jar, rebuilt)
    preserve_seconds = time.perf_counter() - preserve_started
    with zipfile.ZipFile(jar, "r") as archive:
        after_profile = {info.filename: info.compress_type for info in archive.infolist()}
    changed = {
        name
        for name, compress_type in before_profile.items()
        if after_profile.get(name) != compress_type
    }
    if changed:
        raise StudioError(f"JAR compression profile changed unexpectedly: {', '.join(sorted(changed))}")
    final_hash = _file_sha256(jar)
    _write_json_atomic(
        decoded.parent / APKTOOL_DECODE_MARKER_NAME,
        {"jar": jar.name, "sha256": final_hash},
    )
    details = dict(report) if isinstance(report, dict) else {}
    details.update(
        {
            "jar": jar.name,
            "decodedReused": decoded_reused,
            "decodeSeconds": round(decode_seconds, 3),
            "patchSeconds": round(patch_seconds, 3),
            "buildSeconds": round(build_seconds, 3),
            "preserveSeconds": round(preserve_seconds, 3),
            "totalSeconds": round(
                decode_seconds + patch_seconds + build_seconds + preserve_seconds,
                3,
            ),
        }
    )
    return details


def _patch_wk_manager_jars(
    rom_unpack: Path,
    workspace: Path,
    oplus_reuse_work_dir: Path | None = None,
    status_callback: Callable[[str], None] | None = None,
    include_fix_noti: bool = False,
) -> list[dict[str, Any]]:
    from wk_manager_patcher import (
        WkManagerPatchError,
        patch_framework_decoded,
        patch_oplus_services_decoded,
        patch_services_decoded,
    )

    framework_dir = rom_unpack / "system_unpacked" / "system" / "system" / "framework"
    def patch_oplus_services(decoded: Path) -> dict[str, Any]:
        report = patch_oplus_services_decoded(decoded)
        if include_fix_noti:
            _patch_fix_noti_smali(decoded)
            report = {**report, "fixNotiPatched": 1}
        return report

    patchers: list[tuple[str, Callable[[Path], dict[str, Any]]]] = [
        (
            "framework.jar",
            lambda decoded: patch_framework_decoded(decoded, WK_MANAGER_STARK_DIR),
        ),
        ("services.jar", patch_services_decoded),
        ("oplus-services.jar", patch_oplus_services),
    ]
    reports = []
    for jar_name, patcher in patchers:
        try:
            report = _patch_jar_with_apktool(
                framework_dir / jar_name,
                workspace / "mod-tools" / "WK_Manager" / Path(jar_name).stem,
                patcher,
                reuse_decoded_from=(
                    oplus_reuse_work_dir if jar_name == "oplus-services.jar" else None
                ),
                status_callback=status_callback,
            )
        except WkManagerPatchError as exc:
            raise StudioError(f"WK_Manager {jar_name} patch failed: {exc}") from exc
        reports.append(report)
    return reports


def _fake_lock_init_body(mod_dir: Path) -> list[str]:
    source = mod_dir / "system" / "system" / "etc" / "init" / "hw" / "stark_init.rc"
    if not source.is_file():
        raise StudioError(f"Fake_lock init patch is missing: {source}")
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.startswith("+"):
            raise StudioError(f"Fake_lock init patch contains an invalid line: {line}")
        value = line[1:]
        if value == "on post-fs-data":
            continue
        lines.append(value)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or not any("/system/bin/wk" in line for line in lines):
        raise StudioError("Fake_lock init patch contains no wk commands")
    return lines


def _remove_fake_lock_init_block(lines: list[str]) -> list[str]:
    if FAKE_LOCK_INIT_BLOCK_START in lines:
        start = lines.index(FAKE_LOCK_INIT_BLOCK_START)
        try:
            end = lines.index(FAKE_LOCK_INIT_BLOCK_END, start + 1)
        except ValueError as exc:
            raise StudioError("Fake_lock init block marker is incomplete") from exc
        return lines[:start] + lines[end + 1 :]
    if FAKE_LOCK_LEGACY_INIT_MARKER in lines:
        start = lines.index(FAKE_LOCK_LEGACY_INIT_MARKER)
        end = start + 1
        while end < len(lines) and (not lines[end] or lines[end][0].isspace()):
            end += 1
        return lines[:start] + lines[end:]
    return lines


def _remove_marked_init_block(
    lines: list[str],
    start_marker: str,
    end_marker: str,
    label: str,
) -> list[str]:
    if start_marker not in lines:
        return lines
    start = lines.index(start_marker)
    try:
        end = lines.index(end_marker, start + 1)
    except ValueError as exc:
        raise StudioError(f"{label} init block marker is incomplete") from exc
    return lines[:start] + lines[end + 1 :]


def _patch_fake_lock_init_rc(rom_unpack: Path, mod_dir: Path) -> int:
    target = (
        rom_unpack
        / "system_unpacked"
        / "system"
        / "system"
        / "etc"
        / "init"
        / "hw"
        / "init.rc"
    )
    if not target.is_file():
        raise StudioError(f"Fake_lock init.rc target is missing: {target}")
    original = target.read_text(encoding="utf-8", errors="replace")
    lines = _remove_fake_lock_init_block(original.splitlines())
    try:
        trigger = lines.index("on post-fs-data")
    except ValueError:
        if lines and lines[-1]:
            lines.append("")
        lines.append("on post-fs-data")
        trigger = len(lines) - 1
    block = [
        FAKE_LOCK_INIT_BLOCK_START,
        *_fake_lock_init_body(mod_dir),
        FAKE_LOCK_INIT_BLOCK_END,
        "",
    ]
    lines[trigger + 1 : trigger + 1] = block
    updated = "\n".join(lines).rstrip() + "\n"
    if updated == original:
        return 0
    _write_text_lf(target, updated)
    return 1


def _wk_manager_metrics_init_body(mod_dir: Path) -> list[str]:
    source = mod_dir / "system" / "system" / "etc" / "init" / "hw" / "stark_init.rc"
    if not source.is_file():
        raise StudioError(f"WK_Manager metrics init patch is missing: {source}")
    lines = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.startswith("+"):
            raise StudioError(f"WK_Manager metrics init patch contains an invalid line: {line}")
        lines.append(line[1:])
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or not any("kgsl-3d0" in line for line in lines):
        raise StudioError("WK_Manager metrics init patch contains no KGSL metric commands")
    return lines


def _patch_wk_manager_metrics_init_rc(rom_unpack: Path, mod_dir: Path) -> int:
    target = (
        rom_unpack
        / "system_unpacked"
        / "system"
        / "system"
        / "etc"
        / "init"
        / "hw"
        / "init.rc"
    )
    if not target.is_file():
        raise StudioError(f"WK_Manager init.rc target is missing: {target}")
    legacy_standalone_rc = target.parent.parent / "wukong_manager_metrics.rc"
    legacy_removed = 0
    if legacy_standalone_rc.is_file():
        legacy_standalone_rc.unlink()
        legacy_removed = 1
    original = target.read_text(encoding="utf-8", errors="replace")
    lines = _remove_marked_init_block(
        original.splitlines(),
        WK_MANAGER_METRICS_INIT_BLOCK_START,
        WK_MANAGER_METRICS_INIT_BLOCK_END,
        "WK_Manager metrics",
    )
    if lines and lines[-1]:
        lines.append("")
    lines.extend(
        [
            WK_MANAGER_METRICS_INIT_BLOCK_START,
            *_wk_manager_metrics_init_body(mod_dir),
            WK_MANAGER_METRICS_INIT_BLOCK_END,
            "",
        ]
    )
    updated = "\n".join(lines).rstrip() + "\n"
    if updated == original:
        return legacy_removed
    _write_text_lf(target, updated)
    return 1 + legacy_removed


def _upsert_config_entries(path: Path, entries: dict[str, str]) -> int:
    if not path.is_file():
        raise StudioError(f"Fake_lock repack config is missing: {path}")
    original = path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()
    changed = 0
    remaining = dict(entries)
    updated = []
    for line in lines:
        parts = line.split(None, 1)
        key = parts[0] if parts else ""
        replacement = remaining.pop(key, None)
        if replacement is None:
            updated.append(line)
            continue
        updated.append(replacement)
        changed += int(line != replacement)
    for key in entries:
        if key in remaining:
            updated.append(entries[key])
            changed += 1
    content = "\n".join(updated) + "\n"
    if content != original:
        _write_text_lf(path, content)
    return changed


def _sync_fake_lock_repack_configs(rom_unpack: Path) -> dict[str, int]:
    config = rom_unpack / "system_unpacked" / "config"
    return {
        "fsConfig": _upsert_config_entries(
            config / "system_fs_config",
            FAKE_LOCK_FS_CONFIG,
        ),
        "fileContexts": _upsert_config_entries(
            config / "system_file_contexts",
            FAKE_LOCK_FILE_CONTEXTS,
        ),
    }


def _plat_sepolicy_paths(rom_unpack: Path) -> tuple[Path, Path, Path]:
    selinux = rom_unpack / "system_unpacked" / "system" / "system" / "etc" / "selinux"
    return selinux, selinux / "plat_sepolicy.cil", selinux / "plat_sepolicy_and_mapping.sha256"


def _refresh_plat_sepolicy_hash(rom_unpack: Path) -> dict[str, str]:
    _, policy, checksum = _plat_sepolicy_paths(rom_unpack)
    if not policy.is_file():
        raise StudioError(f"SELinux policy is missing: {policy}")
    if not checksum.is_file():
        raise StudioError(f"SELinux checksum is missing: {checksum}")
    digest = hashlib.sha256(policy.read_bytes()).hexdigest()
    checksum.write_bytes((digest + "\n").encode("ascii"))
    if checksum.read_bytes() != (digest + "\n").encode("ascii"):
        raise StudioError(f"Failed to refresh SELinux checksum: {checksum}")
    return {
        "sha256": digest,
        "profile": "policy-only",
        "input": str(policy),
    }


def apply_selected_mods(
    mod_names: Iterable[str],
    rom_unpack: Path,
    device: dict[str, Any] | None,
    workspace: Path,
    mod_version: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    version = normalize_mod_version(mod_version)
    mods = validate_mods(mod_names, mod_version=version)
    copied = patched = copied_bytes = 0
    applied = []
    stock_ota_feature_lines = 0
    theme_cr_removed = 0
    ai_global_aiunit_removed = 0
    jar_reports: list[dict[str, Any]] = []
    modified_partitions: set[str] = set()
    fix_noti_selected = False
    wk_manager_mod_dir: Path | None = None
    last_progress = -1

    def emit_progress(progress: int, message: str) -> None:
        nonlocal last_progress
        if not progress_callback:
            return
        last_progress = max(last_progress, max(0, min(100, int(progress))))
        progress_callback(
            {
                "progress": last_progress,
                "progressMessage": message,
            }
        )

    total_mods = max(1, len(mods))
    for index, mod in enumerate(mods, start=1):
        emit_progress(int((index - 1) * 35 / total_mods), f"MOD {index}/{len(mods)} · {mod['name']}")
        mod_dir = (STARK_ROOT if mod.get("shared") else _mod_collection_dir(version)) / mod["name"]
        for partition in mod["partitions"]:
            destination_info = _partition_destination(rom_unpack, partition, device)
            if not destination_info:
                continue
            target_partition, partition_destination = destination_info
            partition_source = mod_dir / partition
            for source in partition_source.rglob("*"):
                if not source.is_file():
                    continue
                relative = _safe_relative_path(str(source.relative_to(partition_source)))
                if source.name.startswith("stark_"):
                    if (
                        mod["name"] in {"Fake_lock", "WK_Manager"}
                        and relative.as_posix() == "system/etc/init/hw/stark_init.rc"
                    ):
                        continue
                    target = _stark_destination(partition_destination, relative)
                    result = apply_stark_patch(source, target)
                    changes = sum(result.values())
                    patched += changes
                    if changes:
                        modified_partitions.add(target_partition)
                    continue
                target = partition_destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                _normalize_android_text_file_lf(target)
                copied += 1
                copied_bytes += source.stat().st_size
                modified_partitions.add(target_partition)
        if mod["name"] == "Fix_noti":
            fix_noti_selected = True
        if mod["name"] == "WK_Manager":
            wk_manager_mod_dir = mod_dir
        if mod["name"] == "Fake_lock":
            patched += _patch_fake_lock_init_rc(rom_unpack, mod_dir)
            _sync_fake_lock_repack_configs(rom_unpack)
            modified_partitions.add("system")
        if mod["name"] == "Block_ota":
            removed = remove_stock_ota_feature_lines(rom_unpack)
            stock_ota_feature_lines += removed
            patched += removed
            if removed:
                modified_partitions.add("my_stock")
        if mod["name"] == "Ai_global" and version == "ColorOS_16.0.5":
            result = delete_bloatware(rom_unpack, AI_GLOBAL_COLOROS_1605_REMOVE_PATHS)
            ai_global_aiunit_removed += int(result["deleted"])
            patched += int(result["deleted"])
            modified_partitions.update(result["modifiedPartitions"])
        if mod["name"] == "Theme_cr":
            result = delete_bloatware(rom_unpack, THEME_CR_REMOVE_PATHS)
            theme_cr_removed += int(result["deleted"])
            patched += int(result["deleted"])
            modified_partitions.update(result["modifiedPartitions"])
        applied.append(mod["name"])

    jar_progress = 35

    def emit_jar_progress(message: str) -> None:
        nonlocal jar_progress
        jar_progress = min(94, jar_progress + 8)
        emit_progress(jar_progress, message)

    fix_noti_work_dir = workspace / "mod-tools" / "Fix_noti"
    combined_fix_noti = fix_noti_selected and wk_manager_mod_dir is not None
    if fix_noti_selected and not combined_fix_noti:
        jar = rom_unpack / "system_unpacked" / "system" / "system" / "framework" / "oplus-services.jar"
        report = _patch_jar_with_apktool(
            jar,
            fix_noti_work_dir,
            _patch_fix_noti_smali,
            status_callback=emit_jar_progress,
        )
        jar_reports.append({"mod": "Fix_noti", **report})
        patched += 1
        modified_partitions.add("system")
    if wk_manager_mod_dir is not None:
        reports = _patch_wk_manager_jars(
            rom_unpack,
            workspace,
            fix_noti_work_dir,
            emit_jar_progress,
            include_fix_noti=combined_fix_noti,
        )
        jar_reports.extend({"mod": "WK_Manager", **report} for report in reports)
        patched += sum(int(report.get("patchedMethods", 0)) for report in reports)
        patched += sum(int(report.get("importedSmali", 0)) for report in reports)
        if combined_fix_noti:
            patched += 1
        patched += _patch_wk_manager_metrics_init_rc(rom_unpack, wk_manager_mod_dir)
        modified_partitions.add("system")
    sepolicy_hash = None
    if SELINUX_HASH_MODS.intersection(applied):
        sepolicy_hash = _refresh_plat_sepolicy_hash(rom_unpack)
        modified_partitions.add("system")
    emit_progress(100, "Đã áp dụng xong MOD")
    if not copied and not patched:
        raise StudioError("Selected MODs did not copy or patch any files")
    return {
        "mods": applied,
        "modVersion": version,
        "copied": copied,
        "copiedBytes": copied_bytes,
        "patched": patched,
        "stockOtaFeatureLines": stock_ota_feature_lines,
        "themeCrRemoved": theme_cr_removed,
        "aiGlobalAiunitRemoved": ai_global_aiunit_removed,
        "jarReports": jar_reports,
        "platSepolicyHash": sepolicy_hash,
        "modifiedPartitions": sorted(modified_partitions),
    }


def delete_bloatware(rom_unpack: Path, paths: Iterable[str] | None) -> dict[str, Any]:
    deleted = skipped = 0
    modified_partitions: set[str] = set()
    for relative in validate_debloat_paths(paths):
        partition, inner = relative.split("\\", 1)
        target = rom_unpack / f"{partition}_unpacked" / partition / Path(inner)
        unpacked_partition = (rom_unpack / f"{partition}_unpacked" / partition).resolve()
        resolved = target.resolve()
        if unpacked_partition not in resolved.parents:
            raise StudioError(f"Debloat target escaped partition workspace: {relative}")
        if not resolved.exists():
            skipped += 1
            continue
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
        deleted += 1
        modified_partitions.add(partition)
    return {
        "deleted": deleted,
        "skipped": skipped,
        "modifiedPartitions": sorted(modified_partitions),
    }


def _stage_cache_options() -> tuple[bool, int]:
    settings_path = RUNTIME_DIR / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        settings = {}
    enabled = bool(settings.get("stageCacheEnabled", True))
    try:
        maximum_gb = max(5, min(int(settings.get("stageCacheMaxGb", 40)), 500))
    except (TypeError, ValueError):
        maximum_gb = 40
    return enabled, maximum_gb * 1024**3


def _zip_validation_mode() -> str:
    configured = os.environ.get("WUKONG_STUDIO_ZIP_VALIDATION_MODE", "").strip()
    if configured:
        return normalize_zip_validation_mode(configured)
    settings_path = RUNTIME_DIR / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        settings = {}
    return normalize_zip_validation_mode(settings.get("zipValidationMode"))


def _tree_stats(path: Path) -> tuple[int, int]:
    files = size = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        files += 1
        size += item.stat().st_size
    return files, size


def _tree_size(path: Path) -> int:
    return _tree_stats(path)[1]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_rom_inventory(root: Path) -> list[dict[str, Any]]:
    files = sorted(
        (item for item in root.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(root).as_posix(),
    )
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
        for path in files
    ]


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def stage_cache_status() -> dict[str, Any]:
    enabled, maximum_bytes = _stage_cache_options()
    entries = []
    total_bytes = 0
    if STAGE_CACHE_ROOT.is_dir():
        for entry in STAGE_CACHE_ROOT.iterdir():
            manifest_path = entry / "manifest.json"
            source = entry / "source_rom"
            if not entry.is_dir() or not manifest_path.is_file() or not source.is_dir():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            size = int(manifest.get("bytes") or _tree_size(source))
            total_bytes += size
            entries.append(
                {
                    "key": entry.name,
                    "versionName": manifest.get("versionName"),
                    "romName": manifest.get("romName"),
                    "bytes": size,
                    "files": int(manifest.get("files") or 0),
                    "hits": int(manifest.get("hits") or 0),
                    "createdAt": manifest.get("createdAt"),
                    "lastUsedAt": manifest.get("lastUsedAt"),
                }
            )
    entries.sort(key=lambda item: str(item.get("lastUsedAt") or ""), reverse=True)
    return {
        "enabled": enabled,
        "root": str(STAGE_CACHE_ROOT),
        "maximumBytes": maximum_bytes,
        "totalBytes": total_bytes,
        "entryCount": len(entries),
        "totalHits": sum(int(item["hits"]) for item in entries),
        "entries": entries,
    }


def clear_stage_cache() -> dict[str, Any]:
    with STAGE_CACHE_LOCK:
        if STAGE_CACHE_ROOT.exists():
            shutil.rmtree(STAGE_CACHE_ROOT)
        STAGE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return stage_cache_status()


def _prune_stage_cache(maximum_bytes: int, *, keep_key: str) -> None:
    status = stage_cache_status()
    total = int(status["totalBytes"])
    if total <= maximum_bytes:
        return
    for entry in reversed(status["entries"]):
        if entry["key"] == keep_key:
            continue
        target = STAGE_CACHE_ROOT / str(entry["key"])
        if target.is_dir():
            shutil.rmtree(target)
            total -= int(entry["bytes"])
        if total <= maximum_bytes:
            break


def rom_sha256(path_value: str | Path) -> str:
    path = Path(path_value)
    stat = path.stat()
    identity = (
        str(path.resolve()).casefold(),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )
    with ROM_SHA256_MEMO_LOCK:
        cached = _ROM_SHA256_MEMO.get(identity)
    if cached is not None:
        return cached

    total = max(1, stat.st_size)
    processed = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024**2):
            digest.update(chunk)
            processed += len(chunk)
    value = digest.hexdigest()
    with ROM_SHA256_MEMO_LOCK:
        _ROM_SHA256_MEMO[identity] = value
        while len(_ROM_SHA256_MEMO) > ROM_SHA256_MEMO_LIMIT:
            _ROM_SHA256_MEMO.pop(next(iter(_ROM_SHA256_MEMO)))
    return value


def _rom_sha256(context: BuildContext) -> str:
    path = Path(context.spec.romPath)
    stat = path.stat()
    identity = (
        str(path.resolve()).casefold(),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        int(stat.st_ctime_ns),
    )
    with ROM_SHA256_MEMO_LOCK:
        cached = _ROM_SHA256_MEMO.get(identity)
    if cached is not None:
        if context.progress_callback:
            context.progress_callback(
                {
                    "progress": 20,
                    "progressMessage": "Reused ROM SHA-256 from this session",
                }
            )
        return cached
    value = rom_sha256(path)
    if context.progress_callback:
        context.progress_callback(
            {"progress": 20, "progressMessage": "ROM SHA-256 ready"}
        )
    return value


def _restore_payload_cache(context: BuildContext, cache_key: str) -> dict[str, Any] | None:
    entry = STAGE_CACHE_ROOT / cache_key
    source = entry / "source_rom"
    manifest_path = entry / "manifest.json"
    if not manifest_path.is_file() or not validate_source_rom(source):
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("schemaVersion") != 2
        or manifest.get("key") != cache_key
        or manifest.get("inventory") != _source_rom_inventory(source)
    ):
        return None
    if context.source_rom.exists():
        shutil.rmtree(context.source_rom)
    materialized = _link_or_copy_tree(source, context.source_rom)
    if not validate_source_rom(context.source_rom):
        shutil.rmtree(context.source_rom, ignore_errors=True)
        return None
    manifest["hits"] = int(manifest.get("hits") or 0) + 1
    manifest["lastUsedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _write_json_atomic(manifest_path, manifest)
    return {
        "cacheHit": True,
        "cacheKey": cache_key,
        "cacheBytes": int(manifest.get("bytes") or 0),
        "cacheLinked": materialized["linked"],
        "cacheCopied": materialized["copied"],
    }


def _store_payload_cache(context: BuildContext, cache_key: str, maximum_bytes: int) -> dict[str, Any]:
    STAGE_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    target = STAGE_CACHE_ROOT / cache_key
    staging = STAGE_CACHE_ROOT / f".{cache_key}.{context.job_id}.tmp"
    with STAGE_CACHE_LOCK:
        if staging.exists():
            shutil.rmtree(staging)
        source = staging / "source_rom"
        materialized = _link_or_copy_tree(context.source_rom, source)
        files, size = _tree_stats(source)
        inventory = _source_rom_inventory(source)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _write_json_atomic(
            staging / "manifest.json",
            {
                "schemaVersion": 2,
                "key": cache_key,
                "romName": Path(context.spec.romPath).name,
                "versionName": context.metadata.get("version_name"),
                "bytes": size,
                "files": files,
                "inventory": inventory,
                "hits": 0,
                "createdAt": now,
                "lastUsedAt": now,
            },
        )
        if target.exists():
            shutil.rmtree(target)
        os.replace(staging, target)
        _prune_stage_cache(maximum_bytes, keep_key=cache_key)
    return {
        "cacheHit": False,
        "cacheStored": True,
        "cacheKey": cache_key,
        "cacheBytes": size,
        "cacheLinked": materialized["linked"],
        "cacheCopied": materialized["copied"],
    }


def _stage_extract_payload(context: BuildContext) -> dict[str, Any]:
    cache_enabled, cache_maximum = _stage_cache_options()
    cache_key = _rom_sha256(context) if cache_enabled else ""
    if cache_enabled:
        try:
            cached = _restore_payload_cache(context, cache_key)
            if cached is not None:
                print(f"[*] Reused payload cache {cache_key[:12]}", flush=True)
                return {"sourceRom": str(context.source_rom), **cached}
        except (OSError, StudioError, json.JSONDecodeError) as exc:
            print(f"[!] Payload cache restore skipped: {exc}", flush=True)
    if context.source_rom.exists():
        shutil.rmtree(context.source_rom)
    context.source_rom.mkdir(parents=True, exist_ok=True)
    _run_command(
        [sys.executable, str(ROOT_DIR / "payload_tool.py"), context.spec.romPath, "-o", str(context.source_rom)]
    )
    if not validate_source_rom(context.source_rom):
        raise StudioError("Payload extraction did not produce required source images")
    cache_details: dict[str, Any] = {"cacheHit": False, "cacheStored": False}
    if cache_enabled:
        try:
            cache_details = _store_payload_cache(context, cache_key, cache_maximum)
        except (OSError, StudioError) as exc:
            print(f"[!] Payload cache store skipped: {exc}", flush=True)
            cache_details["cacheError"] = str(exc)
    return {"sourceRom": str(context.source_rom), **cache_details}


def _stage_unpack(context: BuildContext) -> dict[str, Any]:
    _run_command(
        [sys.executable, str(ROOT_DIR / "batch_unpack.py"), str(context.source_rom), str(context.rom_unpack)]
    )
    if not validate_rom_unpack(context.rom_unpack, context.source_rom):
        raise StudioError("Partition unpack did not produce all expected directories")
    return {"romUnpack": str(context.rom_unpack)}


def _stage_debloat(context: BuildContext) -> dict[str, Any]:
    return delete_bloatware(context.rom_unpack, context.spec.debloatPaths)


def _stage_apply_mod(context: BuildContext) -> dict[str, Any]:
    mod_names = context.spec.selected_mod_names()
    if not mod_names:
        return {"skipped": True}
    details = apply_selected_mods(
        mod_names,
        context.rom_unpack,
        context.device,
        context.workspace,
        context.spec.modVersion,
        context.progress_callback,
    )
    context.modified_partitions.update(details.get("modifiedPartitions") or [])
    return details


def _sync_selected_partition_configs(
    rom_unpack: Path,
    partitions: Iterable[str],
) -> list[dict[str, Any]]:
    reports = []
    for part_name in sorted(set(partitions)):
        unpacked = rom_unpack / f"{part_name}_unpacked"
        if not unpacked.is_dir():
            raise StudioError(f"Missing unpacked partition for metadata sync: {part_name}")
        print(f"[*] Sync metadata: {part_name}", flush=True)
        report = sync_partition_configs(unpacked, part_name)
        reports.append(report)
        print(
            f"    [OK] {part_name}: scanned={report['scannedPaths']} "
            f"fs_config(+{report['addedFs']}) "
            f"file_contexts(+{report['addedFileContexts']})",
            flush=True,
        )
    return reports


def _stage_sync_configs(context: BuildContext) -> dict[str, Any]:
    vendor_sepolicy_guard = validate_no_unsafe_vendor_priv_app_sysfs(context.rom_unpack)
    reports = (
        _sync_selected_partition_configs(context.rom_unpack, context.modified_partitions)
        if context.selective_repack
        else sync_all_partition_configs(context.rom_unpack)
    )
    return {"partitions": reports, "vendorSepolicyGuard": vendor_sepolicy_guard}


def copy_passthrough_partition_images(source_rom: Path, rom_repack: Path) -> list[str]:
    rom_repack.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in PARTITIONS:
        if name not in PASSTHROUGH_PARTITIONS:
            continue
        source = source_rom / f"{name}.img"
        if not source.is_file():
            continue
        _link_or_copy_required(source, rom_repack / source.name, "passthrough partition")
        copied.append(name)
    return copied


def _stage_repack(context: BuildContext) -> dict[str, Any]:
    branding = patch_build_branding(
        context.rom_unpack,
        build_edition_name(context.spec),
        studio_version_name(context.spec),
    )
    if branding["manifestDisplayVersion"] or branding["manifestBrand"]:
        context.modified_partitions.add("my_manifest")
    if branding["productDisplayVersion"] or branding["productBrand"]:
        context.modified_partitions.add("my_product")
    command = [
        sys.executable,
        str(ROOT_DIR / "batch_repack.py"),
        str(context.rom_unpack),
        str(context.rom_repack),
        "--format",
        "auto",
        "--skip-sync",
    ]
    repacked_partitions = sorted(context.modified_partitions) if context.selective_repack else []
    if context.selective_repack:
        if not repacked_partitions:
            raise StudioError("Selective repack has no modified partitions")
        for part_name in repacked_partitions:
            (context.rom_repack / f"{part_name}.img").unlink(missing_ok=True)
        command.extend(["--partitions", *repacked_partitions])
    _run_command(command)
    passthrough = copy_passthrough_partition_images(context.source_rom, context.rom_repack)
    if not validate_rom_repack(context.rom_repack, context.source_rom):
        raise StudioError("Partition repack did not produce all expected images")
    if not repacked_partitions:
        repacked_partitions = sorted(
            name for name in MUTABLE_PARTITIONS if (context.rom_repack / f"{name}.img").is_file()
        )
    if repacked_partitions:
        context.rom_repack.mkdir(parents=True, exist_ok=True)
        _write_text_lf(
            context.rom_repack / PATCHED_VBMETA_MARKER,
            "\n".join(repacked_partitions) + "\n",
        )
    reused_partitions = sorted(
        name
        for name in MUTABLE_PARTITIONS
        if name not in repacked_partitions and (context.rom_repack / f"{name}.img").is_file()
    )
    return {
        "romRepack": str(context.rom_repack),
        "buildBranding": branding,
        "passthroughPartitions": passthrough,
        "repackedPartitions": repacked_partitions,
        "reusedPartitions": reused_partitions,
    }


def _stage_super(context: BuildContext) -> dict[str, Any]:
    if not _load_legacy().run_super_repack(
        str(context.workspace),
        str(context.rom_repack),
        context.device,
        product_name=context.metadata.get("product_name"),
    ):
        raise StudioError("super.img repack failed")
    details = validate_super(context.build_dir / "super.img", context.device)
    marker = context.rom_repack / PATCHED_VBMETA_MARKER
    if marker.is_file():
        details["requiresPatchedVbmeta"] = True
        details["modifiedPartitions"] = [
            line.strip()
            for line in marker.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        details["warning"] = (
            "Do not flash this intermediate super.img before patching vbmeta.img"
        )
    return details


def _vbmeta_flags(path: Path) -> int | None:
    try:
        with path.open("rb") as handle:
            header = handle.read(124)
    except OSError:
        return None
    if len(header) < 124 or header[:4] != b"AVB0":
        return None
    return struct.unpack(">I", header[120:124])[0]


def validate_patched_vbmeta(path: Path) -> int:
    flags = _vbmeta_flags(path)
    if flags is None:
        raise StudioError(f"Invalid vbmeta image: {path.name}")
    if flags & 0x03 != 0x03:
        raise StudioError(
            f"Patched vbmeta flags are missing for {path.name}: 0x{flags:08x}"
        )
    return flags


def _stage_vbmeta(context: BuildContext) -> dict[str, Any]:
    context.build_dir.mkdir(parents=True, exist_ok=True)
    patched = {}
    for name in VBMETA_IMAGE_NAMES:
        cached = _package_cache_image(context, name)
        if context.reuse_package_assets and cached.is_file():
            patched[name] = {
                "path": str(cached),
                "flags": f"0x{validate_patched_vbmeta(cached):08x}",
                "reused": True,
            }
            continue
        source = context.source_rom / name
        if not source.is_file():
            raise StudioError(f"Source {name} is missing")
        _run_command(
            [sys.executable, str(ROOT_DIR / "vbmate-patch.py"), str(source)],
            cwd=context.workspace,
        )
        output = context.build_dir / name
        if not output.is_file():
            raise StudioError(f"Patched {name} was not created")
        patched[name] = {
            "path": str(output),
            "flags": f"0x{validate_patched_vbmeta(output):08x}",
            "reused": False,
        }
    return {"vbmeta": patched}


def _patch_vendor_boot_header(header: Path) -> dict[str, Any]:
    if not header.is_file():
        raise StudioError(f"vendor_boot header was not created: {header}")
    lines = header.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        raise StudioError("vendor_boot header does not contain a bootargs line")

    tokens = lines[1].split()
    changed_args: list[str] = []
    for arg in VENDOR_BOOT_PATCH_ARGS:
        key = arg.split("=", 1)[0]
        replaced = False
        for index, token in enumerate(tokens):
            if token == arg:
                replaced = True
                break
            if token.startswith(f"{key}="):
                tokens[index] = arg
                replaced = True
                changed_args.append(arg)
                break
        if not replaced:
            tokens.append(arg)
            changed_args.append(arg)

    if changed_args:
        lines[1] = " ".join(tokens)
        _write_text_lf(header, "\n".join(lines) + "\n")
    return {"header": str(header), "changedArgs": changed_args}


def _stage_vendor_boot(context: BuildContext) -> dict[str, Any]:
    cached = _package_cache_image(context, "vendor_boot.img")
    if context.reuse_package_assets and cached.is_file():
        return {"vendorBoot": str(cached), "reused": True}
    source = context.source_rom / "vendor_boot.img"
    if not source.is_file():
        raise StudioError("Source vendor_boot.img is missing")

    tool = ROOT_DIR / "vendor_boot_tool.py"
    if not tool.is_file():
        raise StudioError("vendor_boot_tool.py is missing")

    _run_command(
        [
            sys.executable,
            str(tool),
            "unpack",
            "--source",
            str(context.source_rom),
            "--unpack",
            str(context.rom_unpack),
        ],
        cwd=ROOT_DIR,
    )
    header_details = _patch_vendor_boot_header(context.rom_unpack / "vendor_boot" / "header")
    _run_command(
        [
            sys.executable,
            str(tool),
            "repack",
            "--source",
            str(context.source_rom),
            "--unpack",
            str(context.rom_unpack),
            "--build",
            str(context.build_dir),
        ],
        cwd=ROOT_DIR,
    )

    output = context.build_dir / "vendor_boot.img"
    if not output.is_file():
        raise StudioError("Patched vendor_boot.img was not created")
    return {"vendorBoot": str(output), "reused": False, **header_details}


def _copy_required(source: Path, destination: Path, label: str) -> None:
    if not source.is_file():
        raise StudioError(f"Missing required {label}: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _replace_existing_file(path: Path) -> None:
    if path.exists() or path.is_symlink():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def _link_or_copy_required(source: Path, destination: Path, label: str) -> str:
    if not source.is_file():
        raise StudioError(f"Missing required {label}: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        try:
            if source.samefile(destination):
                return "reused"
        except OSError:
            pass
    _replace_existing_file(destination)
    try:
        os.link(source, destination)
        return "linked"
    except OSError:
        shutil.copy2(source, destination)
        return "copied"


def _move_required(source: Path, destination: Path, label: str) -> str:
    if not source.is_file():
        raise StudioError(f"Missing required {label}: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _replace_existing_file(destination)
    shutil.move(str(source), str(destination))
    return "moved"


def _link_or_copy_tree(source: Path, destination: Path, *, skip_names: set[str] | None = None) -> dict[str, int]:
    if not source.is_dir():
        raise StudioError(f"Missing required directory: {source.name}")
    skip_names = skip_names or set()
    linked = copied = reused = 0
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        if any(part in skip_names for part in relative.parts):
            continue
        target = destination / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            method = _link_or_copy_required(item, target, item.name)
            if method == "linked":
                linked += 1
            elif method == "reused":
                reused += 1
            else:
                copied += 1
    return {"linked": linked, "copied": copied, "reused": reused}


def _package_cache_image(context: BuildContext, name: str) -> Path:
    return context.package_cache / "images" / name


def _populate_shared_package_assets(context: BuildContext, target_root: Path) -> dict[str, int]:
    image_cache = target_root / "images"
    firmware_cache = target_root / "firmware-update"
    image_cache.mkdir(parents=True, exist_ok=True)
    firmware_cache.mkdir(parents=True, exist_ok=True)

    linked = copied = reused = 0
    flash_template = FLASH_ROOT
    for item in [
        "Wukong_Flashing_Tool_Windows.bat",
        "Wukong_Flashing_Tool_Linux.sh",
        "Wukong_Flashing_Tool_MacOS.sh",
        "META-INF",
        "bin",
    ]:
        source = flash_template / item
        destination = target_root / item
        if source.is_dir():
            result = _link_or_copy_tree(source, destination)
            linked += int(result["linked"])
            copied += int(result["copied"])
            reused += int(result["reused"])
        elif source.is_file():
            method = _link_or_copy_required(source, destination, item)
            linked += int(method == "linked")
            copied += int(method == "copied")
            reused += int(method == "reused")

    for source in context.source_rom.glob("*.img"):
        if source.name not in EXCLUDED_FIRMWARE:
            method = _link_or_copy_required(source, firmware_cache / source.name, "firmware image")
            linked += int(method == "linked")
            copied += int(method == "copied")
            reused += int(method == "reused")
    for name in CORE_SOURCE_IMAGES:
        method = _link_or_copy_required(context.source_rom / name, image_cache / name, "source image")
        linked += int(method == "linked")
        copied += int(method == "copied")
        reused += int(method == "reused")

    return {"linked": linked, "copied": copied, "reused": reused}


def _ensure_shared_package_assets(context: BuildContext) -> dict[str, int | bool]:
    cache_root = context.package_cache / "shared"
    marker = cache_root / ".ready"
    if marker.is_file():
        return {"reused": True, "linked": 0, "copied": 0, "existing": 0}

    if cache_root.exists():
        shutil.rmtree(cache_root)
    details = _populate_shared_package_assets(context, cache_root)

    marker.write_text("ready\n", encoding="utf-8")
    return {
        "reused": False,
        "linked": details["linked"],
        "copied": details["copied"],
        "existing": details["reused"],
    }


def _stage_shared_package_assets(context: BuildContext, rom_build: Path) -> dict[str, int | bool]:
    if not context.reuse_package_assets:
        result = _populate_shared_package_assets(context, rom_build)
        return {
            "cacheReused": False,
            "cacheLinked": 0,
            "cacheCopied": 0,
            "cacheExisting": 0,
            "packageLinked": int(result["linked"]),
            "packageCopied": int(result["copied"]),
            "packageReused": int(result["reused"]),
        }
    details = _ensure_shared_package_assets(context)
    shared = context.package_cache / "shared"
    result = _link_or_copy_tree(shared, rom_build, skip_names={".ready"})
    return {
        "cacheReused": bool(details["reused"]),
        "cacheLinked": int(details["linked"]),
        "cacheCopied": int(details["copied"]),
        "cacheExisting": int(details["existing"]),
        "packageLinked": int(result["linked"]),
        "packageCopied": int(result["copied"]),
        "packageReused": int(result["reused"]),
    }


def _cached_or_build_image(context: BuildContext, name: str) -> Path | None:
    build = context.build_dir / name
    if build.is_file():
        return build
    cached = _package_cache_image(context, name)
    if cached.is_file():
        return cached
    return None


def _stage_generated_image(
    context: BuildContext,
    source: Path,
    destination: Path,
    label: str,
    *,
    cache_name: str | None = None,
) -> str:
    if context.reuse_package_assets and cache_name:
        cache_path = _package_cache_image(context, cache_name)
        if source.is_file() and source.resolve() != cache_path.resolve():
            _move_required(source, cache_path, label)
        elif not cache_path.is_file():
            raise StudioError(f"Missing required {label}: {source.name}")
        return _link_or_copy_required(cache_path, destination, label)
    return _move_required(source, destination, label)


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_md5(context: BuildContext, path: Path) -> tuple[str, bool]:
    stat = path.stat()
    if int(stat.st_nlink) <= 1:
        return _md5(path), False
    identity = (
        int(stat.st_dev),
        int(stat.st_ino),
        int(stat.st_size),
        int(stat.st_mtime_ns),
    )
    cached = context.file_hash_cache.get(identity)
    if cached is not None:
        return cached, True
    digest = _md5(path)
    context.file_hash_cache[identity] = digest
    return digest, False


def _async_packaging_enabled() -> bool:
    return os.environ.get("WUKONG_STUDIO_ASYNC_PACKAGE", "").strip() == "1"


def _package_task_key(context: BuildContext) -> str:
    edition = re.sub(r"[^a-z0-9]+", "-", build_edition_name(context.spec).lower()).strip("-")
    return f"{len(context.package_tasks) + 1:02d}-{edition or 'rom'}"


def _spec_payload(spec: BuildSpec) -> dict[str, Any]:
    return {
        "romPath": spec.romPath,
        "modName": spec.modName,
        "modNames": spec.selected_mod_names(),
        "modVersion": spec.modVersion,
        "debloatPaths": spec.debloatPaths,
        "preset": spec.preset,
        "enabledSteps": spec.enabledSteps,
        "resumeFromJobId": spec.resumeFromJobId,
        "notifyTelegram": spec.notifyTelegram,
        "romSha256": spec.romSha256,
        "specFingerprint": spec.specFingerprint,
        "resumePreset": spec.resumePreset,
    }


def build_spec_fingerprint(spec: BuildSpec) -> str:
    payload = {
        "modNames": spec.selected_mod_names(),
        "modVersion": spec.modVersion,
        "debloatPaths": spec.debloatPaths,
        "preset": "lite" if spec.preset == "standard" else spec.preset,
        "enabledSteps": spec.enabledSteps,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _compress_prepared_package(
    package_root: Path,
    zip_path: Path,
    context: BuildContext,
) -> dict[str, Any]:
    ROM_BUILD_DONE.mkdir(parents=True, exist_ok=True)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    partial_path = zip_path.with_name(f"{zip_path.name}.{context.job_id}.partial")
    partial_path.unlink(missing_ok=True)
    bundled_seven_zip = platform_tool_path("7z", BIN_ROOT)
    seven_zip = shutil.which("7z") or shutil.which("7zz") or str(bundled_seven_zip)
    validation_mode = _zip_validation_mode()
    _emit_progress(context, 0, f"Đang đóng gói ZIP · {ZIP_COMPRESSION_LABEL} (-mx{ZIP_COMPRESSION_LEVEL})")
    compression_started = time.perf_counter()
    try:
        if Path(seven_zip).is_file() or shutil.which(seven_zip):
            _run_7z_package(
                [
                    seven_zip,
                    "a",
                    "-tzip",
                    f"-mx{ZIP_COMPRESSION_LEVEL}",
                    "-bsp1",
                    str(partial_path),
                    str(package_root / "*"),
                ],
                context,
            )
        else:
            files = [file for file in package_root.rglob("*") if file.is_file()]
            total = max(1, len(files))
            with zipfile.ZipFile(partial_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for index, file in enumerate(files, start=1):
                    archive.write(file, file.relative_to(package_root))
                    archive_progress = int(index * 100 / total)
                    _emit_progress(context, round(archive_progress * 0.9), f"ZIP {archive_progress}%")
        compression_seconds = time.perf_counter() - compression_started
        validation_message = (
            "Đang kiểm tra CRC toàn phần"
            if validation_mode == "deep"
            else "Đang xác thực nhanh ZIP"
        )
        _emit_progress(context, 95, validation_message)
        validation_started = time.perf_counter()
        validation = validate_final_zip(partial_path, context.device, mode=validation_mode)
        validation_seconds = time.perf_counter() - validation_started
        _emit_progress(context, 99, "Hậu kiểm ZIP đã đạt")
        os.replace(partial_path, zip_path)
        _emit_progress(context, 100, "ZIP đã xác thực")
        return {
            **validation,
            "validationMode": validation_mode,
            "compressionSeconds": round(compression_seconds, 3),
            "validationSeconds": round(validation_seconds, 3),
        }
    finally:
        partial_path.unlink(missing_ok=True)


def _stage_package(context: BuildContext) -> dict[str, Any]:
    staging_started = time.perf_counter()
    async_packaging = _async_packaging_enabled()
    task_key = _package_task_key(context) if async_packaging else ""
    package_root = (
        PACKAGE_STAGING_DIR / context.job_id / task_key
        if async_packaging
        else context.rom_build
    )
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True)
    staging = _stage_shared_package_assets(context, package_root)
    image_dir = package_root / "images"
    firmware_dir = package_root / "firmware-update"
    image_dir.mkdir(parents=True, exist_ok=True)
    firmware_dir.mkdir(parents=True, exist_ok=True)

    requires_patched_vbmeta = (context.rom_repack / PATCHED_VBMETA_MARKER).is_file()
    placed_images: dict[str, str] = {}
    for name in VBMETA_IMAGE_NAMES:
        patched = _cached_or_build_image(context, name)
        if requires_patched_vbmeta and not (patched and patched.is_file()):
            raise StudioError(
                "Modified dynamic partitions require the patch_vbmeta step; "
                f"cannot package stock {name}"
            )
        if patched and patched.is_file():
            validate_patched_vbmeta(patched)
            placed_images[name] = _stage_generated_image(
                context,
                patched,
                image_dir / name,
                "vbmeta image",
                cache_name=name,
            )
        else:
            placed_images[name] = _link_or_copy_required(
                context.source_rom / name,
                image_dir / name,
                "vbmeta image",
            )
    vendor_boot_source = _cached_or_build_image(context, "vendor_boot.img")
    if vendor_boot_source and vendor_boot_source.is_file():
        placed_images["vendor_boot.img"] = _stage_generated_image(
            context,
            vendor_boot_source,
            image_dir / "vendor_boot.img",
            "vendor_boot image",
            cache_name="vendor_boot.img",
        )
    else:
        placed_images["vendor_boot.img"] = _link_or_copy_required(
            context.source_rom / "vendor_boot.img",
            image_dir / "vendor_boot.img",
            "vendor_boot image",
        )
    placed_images["super.img"] = _stage_generated_image(
        context,
        context.build_dir / "super.img",
        image_dir / "super.img",
        "super image",
    )

    soc = context.device.get("soc", "86xx")
    twrp = TWRP_ROOT / f"TWRP-{soc}.img"
    orangefox = OFX_ROOT / f"OrangeFox-{soc}.img"
    if twrp.is_file():
        placed_images["TWRP.img"] = _link_or_copy_required(twrp, image_dir / "TWRP.img", "TWRP image")
    elif orangefox.is_file():
        placed_images["OrangeFox.img"] = _link_or_copy_required(orangefox, image_dir / "OrangeFox.img", "OrangeFox image")

    info = package_root / "info.txt"
    template_info = FLASH_ROOT / "info.txt"
    lines = (
        template_info.read_text(encoding="utf-8", errors="replace").splitlines()
        if template_info.is_file()
        else []
    )
    while len(lines) < 2:
        lines.append("")
    while len(lines) < 5:
        lines.append("")
    lines[0] = context.device.get("name", "Unknown Device")
    lines[1] = context.metadata["version_name"]
    lines[3] = build_edition_name(context.spec)
    lines[4] = studio_version_name(context.spec)
    with info.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")
    _write_text_lf(
        package_root / "expected_product.txt",
        str(context.metadata.get("product_name", "")) + "\n",
    )

    manifest_hash_hits = manifest_hash_misses = 0
    manifest = package_root / "wukong_md5_hashes.txt"
    with manifest.open("w", encoding="utf-8", newline="\n") as handle:
        for folder in (image_dir, firmware_dir):
            for file in sorted(folder.iterdir(), key=lambda path: path.name.lower()):
                if file.is_file():
                    digest, cache_hit = _cached_md5(context, file)
                    manifest_hash_hits += int(cache_hit)
                    manifest_hash_misses += int(not cache_hit)
                    handle.write(f"{digest}  {file.name}\n")

    validate_super(image_dir / "super.img", context.device)
    missing_images = sorted(REQUIRED_IMAGES - {path.name for path in image_dir.iterdir() if path.is_file()})
    if missing_images:
        raise StudioError(f"Cannot package ZIP, missing images: {', '.join(missing_images)}")

    ROM_BUILD_DONE.mkdir(parents=True, exist_ok=True)
    zip_path = ROM_BUILD_DONE / output_zip_name(
        context.metadata["version_name"],
        context.spec,
        f"_{context.job_id[:8]}",
    )
    context.output_zip = zip_path
    if zip_path not in context.output_zips:
        context.output_zips.append(zip_path)
    staging_seconds = round(time.perf_counter() - staging_started, 3)
    if async_packaging:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        task_file = JOBS_DIR / f"{context.job_id}.{task_key}.package.json"
        task = {
            "jobId": context.job_id,
            "taskId": task_key,
            "stagingDir": str(package_root),
            "outputZip": str(zip_path),
            "spec": _spec_payload(context.spec),
            "metadata": context.metadata,
            "device": context.device,
            "startedAt": context.started_at,
            "notifyTelegram": context.defer_package_notifications,
            "stagingSeconds": staging_seconds,
        }
        task_file.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        task["taskFile"] = str(task_file)
        context.package_tasks.append(task)
        return {
            "outputZip": str(zip_path),
            "outputZips": [str(path) for path in context.output_zips],
            "progress": 0,
            "progressMessage": "ZIP queued in background",
            "packagingPending": True,
            "taskId": task_key,
            "taskFile": str(task_file),
            "stagingDir": str(package_root),
            "stagingSeconds": staging_seconds,
            "staging": staging,
            "placedImages": placed_images,
            "manifestHashHits": manifest_hash_hits,
            "manifestHashMisses": manifest_hash_misses,
        }

    details = _compress_prepared_package(package_root, zip_path, context)
    timing = {
        "stagingSeconds": staging_seconds,
        "compressionSeconds": float(details.get("compressionSeconds") or 0),
        "validationSeconds": float(details.get("validationSeconds") or 0),
        "validationMode": details.get("validationMode") or _zip_validation_mode(),
    }
    timing["totalSeconds"] = round(
        timing["stagingSeconds"]
        + timing["compressionSeconds"]
        + timing["validationSeconds"],
        3,
    )
    if package_root.exists():
        shutil.rmtree(package_root)
    return {
        "outputZip": str(zip_path),
        "outputZips": [str(path) for path in context.output_zips],
        "progress": 100,
        "progressMessage": "ZIP 100%",
        "validation": details,
        "timing": timing,
        **timing,
        "romBuildCleaned": True,
        "staging": staging,
        "placedImages": placed_images,
        "manifestHashHits": manifest_hash_hits,
        "manifestHashMisses": manifest_hash_misses,
    }


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.2f} GB"


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _local_datetime(timezone_name: str, timestamp: float | None = None) -> datetime:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Bangkok":
            zone = timezone(timedelta(hours=7))
        else:
            zone = datetime.now().astimezone().tzinfo or timezone.utc
    return datetime.now(zone) if timestamp is None else datetime.fromtimestamp(timestamp, zone)


def _telegram_locale() -> str:
    configured = os.environ.get("WUKONG_TELEGRAM_LOCALE", "").strip().lower()
    if configured in {"vi", "en"}:
        return configured
    try:
        settings = json.loads((RUNTIME_DIR / "settings.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "vi"
    return "en" if settings.get("locale") == "en" else "vi"


def _telegram_text(value: Any, maximum: int = 700) -> str:
    text = str(value or "-").strip() or "-"
    if len(text) > maximum:
        text = text[: maximum - 1].rstrip() + "…"
    return html.escape(text)


def _utc_offset_label(value: datetime) -> str:
    offset = value.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _format_telegram_notification(
    context: BuildContext,
    finished: datetime,
    timezone_name: str,
    locale: str,
) -> str:
    artifact = context.output_zip
    if artifact is None:
        raise StudioError("Output ZIP is unavailable")
    edition = build_edition_name(context.spec)
    studio_version = studio_version_name(context.spec)
    mod_names = context.spec.selected_mod_names()
    planned_steps = plan_steps(context.spec)
    debloat_enabled = "debloat" in planned_steps
    debloat_count = 0
    if debloat_enabled:
        try:
            debloat_count = len(
                context.spec.debloatPaths
                if context.spec.debloatPaths is not None
                else default_debloat_paths()
            )
        except (OSError, StudioError, json.JSONDecodeError):
            debloat_count = 0
    started = _local_datetime(timezone_name, context.started_at)
    size = artifact.stat().st_size if artifact.is_file() else 0
    device_name = context.device.get("name") or "Unknown device"
    product_name = context.metadata.get("product_name") or context.device.get("product_name") or "-"
    soc = context.device.get("soc") or "-"
    version_name = context.metadata.get("version_name") or Path(context.spec.romPath).stem
    source_name = Path(context.spec.romPath).name
    mods = ", ".join(mod_names) if mod_names else ("Không có" if locale == "vi" else "None")
    offset = _utc_offset_label(finished)
    start_text = started.strftime("%d/%m/%Y %H:%M:%S")
    finish_text = finished.strftime("%d/%m/%Y %H:%M:%S")
    duration = _format_duration(finished.timestamp() - context.started_at)

    if locale == "en":
        debloat = f"Enabled · {debloat_count} entries" if debloat_enabled else "Disabled"
        lines = [
            "✅ <b>ROM BUILD COMPLETED</b>",
            f"<blockquote><b>Wukong {edition} {studio_version}</b>\n<code>{_telegram_text(version_name, 300)}</code></blockquote>",
            "📱 <b>Device &amp; ROM</b>",
            f"• Device: <b>{_telegram_text(device_name, 200)}</b>",
            f"• Product: <code>{_telegram_text(product_name, 100)}</code>",
            f"• SoC profile: <code>{_telegram_text(soc, 100)}</code>",
            f"• Source ROM: <code>{_telegram_text(source_name, 300)}</code>",
            f"• MOD base: <code>{_telegram_text(context.spec.modVersion, 160)}</code>",
            "",
            "🧩 <b>Build configuration</b>",
            f"• Edition: <b>{_telegram_text(edition, 80)}</b>",
            f"• Selected MODs: <b>{len(mod_names)}</b>",
            f"• MOD list: {_telegram_text(mods)}",
            f"• Debloat: {_telegram_text(debloat, 120)}",
            "",
            "📦 <b>Validated artifact</b>",
            f"• File: <code>{_telegram_text(artifact.name, 350)}</code>",
            f"• Size: <code>{_format_bytes(size)}</code>",
            f"• Path: <code>{_telegram_text(artifact, 700)}</code>",
            "• Validation: ✅ ZIP CRC · Manifest · super.img layout",
            "",
            "⏱ <b>Timing</b>",
            f"• Started: <code>{start_text}</code>",
            f"• Finished: <code>{finish_text}</code>",
            f"• Duration: <code>{duration}</code>",
            f"• Timezone: <code>{_telegram_text(timezone_name, 100)} ({offset})</code>",
            "",
            f"🆔 <b>Job:</b> <code>{_telegram_text(context.job_id, 100)}</code>",
            "<i>Wukong ROM Studio · Automated build report</i>",
        ]
    else:
        debloat = f"Đã bật · {debloat_count} mục" if debloat_enabled else "Đã tắt"
        lines = [
            "✅ <b>BUILD ROM HOÀN TẤT</b>",
            f"<blockquote><b>Wukong {edition} {studio_version}</b>\n<code>{_telegram_text(version_name, 300)}</code></blockquote>",
            "📱 <b>Thiết bị &amp; ROM</b>",
            f"• Thiết bị: <b>{_telegram_text(device_name, 200)}</b>",
            f"• Product: <code>{_telegram_text(product_name, 100)}</code>",
            f"• Hồ sơ SoC: <code>{_telegram_text(soc, 100)}</code>",
            f"• ROM nguồn: <code>{_telegram_text(source_name, 300)}</code>",
            f"• Nền MOD: <code>{_telegram_text(context.spec.modVersion, 160)}</code>",
            "",
            "🧩 <b>Cấu hình build</b>",
            f"• Phiên bản: <b>{_telegram_text(edition, 80)}</b>",
            f"• MOD đã chọn: <b>{len(mod_names)}</b>",
            f"• Danh sách MOD: {_telegram_text(mods)}",
            f"• Debloat: {_telegram_text(debloat, 120)}",
            "",
            "📦 <b>Artifact đã xác thực</b>",
            f"• File: <code>{_telegram_text(artifact.name, 350)}</code>",
            f"• Dung lượng: <code>{_format_bytes(size)}</code>",
            f"• Đường dẫn: <code>{_telegram_text(artifact, 700)}</code>",
            "• Kiểm tra: ✅ ZIP CRC · Manifest · cấu trúc super.img",
            "",
            "⏱ <b>Thời gian</b>",
            f"• Bắt đầu: <code>{start_text}</code>",
            f"• Hoàn tất: <code>{finish_text}</code>",
            f"• Tổng thời gian: <code>{duration}</code>",
            f"• Múi giờ: <code>{_telegram_text(timezone_name, 100)} ({offset})</code>",
            "",
            f"🆔 <b>Job:</b> <code>{_telegram_text(context.job_id, 100)}</code>",
            "<i>Wukong ROM Studio · Báo cáo build tự động</i>",
        ]
    return "\n".join(lines)


def _stage_notify(context: BuildContext) -> dict[str, Any]:
    load_local_env(override=True)
    token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("WUKONG_TELEGRAM_CHAT_ID", "").strip()
    timezone_name = os.environ.get("WUKONG_TELEGRAM_TIMEZONE", "Asia/Bangkok").strip() or "Asia/Bangkok"
    finished = _local_datetime(timezone_name)
    finished_at = finished.isoformat(timespec="seconds")
    if not token or not chat_id:
        message = "Telegram environment variables are not configured"
        print(f"[!] {message}", flush=True)
        return {"notified": False, "warning": message, "finishedAt": finished_at}
    if not context.output_zip or not context.output_zip.is_file():
        message = "Output ZIP is unavailable"
        print(f"[!] Telegram notification skipped: {message}", flush=True)
        return {"notified": False, "warning": message, "finishedAt": finished_at}
    import requests

    timeout = int(os.environ.get("WUKONG_TELEGRAM_TIMEOUT", "10") or "10")
    parse_mode = "HTML"
    artifacts = [context.output_zip]
    locale = _telegram_locale()
    message = _format_telegram_notification(context, finished, timezone_name, locale)
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code == 403:
            warning = (
                "Telegram rejected the configured chat. Open the bot, send /start, "
                "then run python configure_telegram.py to refresh WUKONG_TELEGRAM_CHAT_ID."
            )
        else:
            label = f"HTTP {status_code}" if status_code else type(exc).__name__
            warning = f"Telegram notification failed: {label}"
        print(f"[!] {warning}", flush=True)
        return {
            "notified": False,
            "warning": warning,
            "statusCode": status_code,
            "artifacts": [str(path) for path in artifacts],
            "finishedAt": finished_at,
        }
    return {
        "notified": True,
        "artifacts": [str(path) for path in artifacts],
        "finishedAt": finished_at,
        "locale": locale,
    }


def complete_package_task(
    task_file: str | Path,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    path = Path(task_file).resolve()
    if path.parent != JOBS_DIR.resolve() or not path.name.endswith(".package.json"):
        raise StudioError(f"Invalid package task file: {path}")
    task = json.loads(path.read_text(encoding="utf-8"))
    package_root = Path(task["stagingDir"]).resolve()
    package_base = (PACKAGE_STAGING_DIR / str(task["jobId"])).resolve()
    if package_base not in package_root.parents:
        raise StudioError(f"Package staging escaped job directory: {package_root}")
    if not package_root.is_dir():
        raise StudioError(f"Package staging is missing: {package_root}")
    zip_path = Path(task["outputZip"]).resolve()
    if zip_path.parent != ROM_BUILD_DONE.resolve():
        raise StudioError(f"Package output path is invalid: {zip_path}")

    callback = event_callback or (lambda payload: None)
    context = BuildContext(
        job_id=str(task["jobId"]),
        spec=BuildSpec.from_dict(task["spec"]),
        workspace=package_base,
        metadata=dict(task["metadata"]),
        device=dict(task["device"]),
        output_zip=zip_path,
        output_zips=[zip_path],
        started_at=float(task.get("startedAt") or time.time()),
    )
    phase = build_edition_name(context.spec)

    def emit_progress(details: dict[str, Any]) -> None:
        callback(
            {
                "type": "step",
                "step": "package_zip",
                "status": "running",
                "details": {
                    **details,
                    "taskId": task["taskId"],
                    "phase": phase,
                    "outputZip": str(zip_path),
                },
            }
        )

    context.progress_callback = emit_progress
    validation = _compress_prepared_package(package_root, zip_path, context)
    timing = {
        "stagingSeconds": round(float(task.get("stagingSeconds") or 0), 3),
        "compressionSeconds": round(float(validation.get("compressionSeconds") or 0), 3),
        "validationSeconds": round(float(validation.get("validationSeconds") or 0), 3),
        "validationMode": validation.get("validationMode") or _zip_validation_mode(),
    }
    timing["totalSeconds"] = round(
        timing["stagingSeconds"]
        + timing["compressionSeconds"]
        + timing["validationSeconds"],
        3,
    )
    notify_details = None
    if task.get("notifyTelegram"):
        callback(
            {
                "type": "step",
                "step": "notify_telegram",
                "status": "running",
                "details": {"taskId": task["taskId"], "phase": phase},
            }
        )
        notify_details = _stage_notify(context)
        callback(
            {
                "type": "step",
                "step": "notify_telegram",
                "status": "success",
                "details": {
                    **notify_details,
                    "taskId": task["taskId"],
                    "phase": phase,
                },
            }
        )
    shutil.rmtree(package_root)
    try:
        package_base.rmdir()
    except OSError:
        pass
    path.unlink(missing_ok=True)
    return {
        "taskId": task["taskId"],
        "phase": phase,
        "outputZip": str(zip_path),
        "validation": validation,
        "timing": timing,
        "notification": notify_details,
    }


STAGE_HANDLERS: dict[str, Callable[[BuildContext], dict[str, Any]]] = {
    "inspect_rom": lambda context: {"preflight": True},
    "extract_payload": _stage_extract_payload,
    "unpack_partitions": _stage_unpack,
    "debloat": _stage_debloat,
    "apply_mod": _stage_apply_mod,
    "sync_configs": _stage_sync_configs,
    "repack_partitions": _stage_repack,
    "repack_super": _stage_super,
    "patch_vbmeta": _stage_vbmeta,
    "patch_vendor_boot": _stage_vendor_boot,
    "package_zip": _stage_package,
    "notify_telegram": _stage_notify,
}


DUAL_SHARED_STEPS = {"inspect_rom", "extract_payload", "unpack_partitions", "debloat"}
DUAL_PHASE_STEPS = {
    "apply_mod",
    "sync_configs",
    "repack_partitions",
    "repack_super",
    "patch_vbmeta",
    "patch_vendor_boot",
    "package_zip",
}


def _run_build_step(
    context: BuildContext,
    step: str,
    workspace: Path,
    callback: Callable[[dict[str, Any]], None],
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    label = STEP_LABELS[step]
    message = f"{phase} - {label}" if phase else ""
    started = time.time()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    running_payload = {
        "type": "step",
        "step": step,
        "status": "running",
        "details": {"startedAt": started_at, "phase": phase},
    }
    if message:
        running_payload["message"] = message
    callback(running_payload)
    print(f"\n=== {message or label} ===", flush=True)
    previous_progress_callback = context.progress_callback

    def emit_step_progress(details: dict[str, Any]) -> None:
        payload = {
            "type": "step",
            "step": step,
            "status": "running",
            "details": details,
        }
        if details.get("progressMessage"):
            payload["message"] = str(details["progressMessage"])
        callback(payload)

    context.progress_callback = emit_step_progress
    try:
        details = STAGE_HANDLERS[step](context)
    except Exception as exc:
        callback(
            {
                "type": "step",
                "step": step,
                "status": "failed",
                "message": str(exc),
                "details": {
                    "startedAt": started_at,
                    "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "durationSeconds": round(time.time() - started, 3),
                    "phase": phase,
                },
            }
        )
        raise
    finally:
        context.progress_callback = previous_progress_callback
    details = {
        **details,
        "startedAt": started_at,
        "finishedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "durationSeconds": round(time.time() - started, 3),
        "phase": phase,
    }
    result = StepResult(step=step, status="success", message=message, details=details)
    _write_marker(workspace, result, context.spec)
    callback({"type": "step", **asdict(result)})
    return details


def _clear_repack_outputs(context: BuildContext, *, preserve_repacked: bool = False) -> None:
    if context.rom_repack.exists() and not preserve_repacked:
        shutil.rmtree(context.rom_repack)
    if context.build_dir.exists():
        shutil.rmtree(context.build_dir)


def _lite_spec(spec: BuildSpec) -> BuildSpec:
    selected = spec.selected_mod_names()
    defaults = preset_default_mods("lite", spec.modVersion)
    return replace(
        spec,
        preset="lite",
        modName=None,
        modNames=[name for name in defaults if not selected or name in selected],
    )


def _plus_delta_spec(spec: BuildSpec) -> BuildSpec:
    selected = spec.selected_mod_names()
    lite_mods = set(_lite_spec(spec).modNames)
    available_plus = preset_default_mods("resume", spec.modVersion)
    plus_mods = [
        name
        for name in available_plus
        if name not in lite_mods and (not selected or name in selected)
    ]
    return replace(spec, preset="resume", modName=None, modNames=plus_mods)


def _execute_both_build(
    job_id: str,
    spec: BuildSpec,
    workspace: Path,
    callback: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    steps = plan_steps(spec, workspace)
    preflight = inspect_rom(
        spec.romPath,
        spec.modName,
        mod_names=spec.selected_mod_names() or preset_default_mods("both", spec.modVersion),
        mod_version=spec.modVersion,
        debloat_paths=spec.debloatPaths,
        required_steps=steps,
    )
    if not preflight["ok"]:
        raise StudioError("; ".join(preflight["errors"]))
    context = BuildContext(
        job_id=job_id,
        spec=spec,
        workspace=workspace,
        metadata=preflight["metadata"],
        device=preflight["device"],
        reuse_package_assets=True,
        defer_package_notifications=(
            _async_packaging_enabled() and "notify_telegram" in steps
        ),
    )
    callback({"type": "plan", "steps": steps})
    async_packaging = _async_packaging_enabled()
    both_packaged = False
    try:
        for step in [step for step in steps if step in DUAL_SHARED_STEPS]:
            _run_build_step(context, step, workspace, callback)

        phase_steps = [step for step in steps if step in DUAL_PHASE_STEPS]
        context.spec = _lite_spec(spec)
        for step in phase_steps:
            if step in PLUS_DEFAULT_STEPS:
                continue
            _run_build_step(context, step, workspace, callback, phase="Lite")
            if (
                step == "package_zip"
                and "notify_telegram" in steps
                and not _async_packaging_enabled()
            ):
                _run_build_step(context, "notify_telegram", workspace, callback, phase="Lite")

        context.spec = _plus_delta_spec(spec)
        context.selective_repack = True
        context.modified_partitions.clear()
        for step in phase_steps:
            if step == "repack_partitions":
                _clear_repack_outputs(context, preserve_repacked=True)
            _run_build_step(context, step, workspace, callback, phase="Plus")
            if step == "package_zip":
                both_packaged = len(context.output_zips) >= 2
                if "notify_telegram" in steps and not _async_packaging_enabled():
                    _run_build_step(context, "notify_telegram", workspace, callback, phase="Plus")
    finally:
        if both_packaged and not async_packaging:
            cleanup_workspace(workspace, expected_job_id=job_id)
            print(f"[*] Cleaned workspace after validated Lite + Plus package: {workspace}", flush=True)
    result = {
        "outputZip": str(context.output_zip) if context.output_zip else None,
        "outputZips": [str(path) for path in context.output_zips],
        "packageTasks": context.package_tasks,
        "workspace": str(workspace),
        "workspaceCleaned": both_packaged and not async_packaging,
        "steps": steps,
    }
    return result


def execute_build(
    job_id: str,
    spec: BuildSpec,
    workspace: Path,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    callback = event_callback or (lambda payload: None)
    effective_preset = "lite" if spec.preset == "standard" else spec.preset
    if effective_preset == "resume" and spec.resumePreset:
        effective_preset = spec.resumePreset
    if effective_preset == "both":
        return _execute_both_build(job_id, spec, workspace, callback)
    planned_steps = plan_steps(spec, workspace)
    preflight = inspect_rom(
        spec.romPath,
        spec.modName,
        mod_names=spec.selected_mod_names(),
        mod_version=spec.modVersion,
        debloat_paths=spec.debloatPaths,
        required_steps=planned_steps,
    )
    if not preflight["ok"]:
        raise StudioError("; ".join(preflight["errors"]))
    context = BuildContext(
        job_id=job_id,
        spec=spec,
        workspace=workspace,
        metadata=preflight["metadata"],
        device=preflight["device"],
        defer_package_notifications=(
            _async_packaging_enabled() and "notify_telegram" in planned_steps
        ),
    )
    steps = planned_steps
    callback({"type": "plan", "steps": steps})
    async_packaging = _async_packaging_enabled()
    package_completed = False
    try:
        for step in steps:
            if step == "notify_telegram" and _async_packaging_enabled():
                continue
            _run_build_step(context, step, workspace, callback)
            if step == "package_zip":
                package_completed = True
    finally:
        if package_completed and not async_packaging:
            cleanup_workspace(workspace, expected_job_id=job_id)
            print(f"[*] Cleaned workspace after validated package: {workspace}", flush=True)
    result = {
        "outputZip": str(context.output_zip) if context.output_zip else None,
        "outputZips": [str(path) for path in context.output_zips],
        "packageTasks": context.package_tasks,
        "workspace": str(workspace),
        "workspaceCleaned": package_completed and not async_packaging,
        "steps": steps,
    }
    return result
