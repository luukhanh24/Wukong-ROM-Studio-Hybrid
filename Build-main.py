import os
import sys
import zipfile
import subprocess
import time
import shutil
import re
import json
import hashlib
from studio_paths import (
    CONFIG_ROOT,
    CONTENT_ROOT,
    COPY_IMAGE_ROOT,
    DATA_ROOT,
    DESKTOP_MODE,
    OUTPUT_ROOT,
    SCRIPT_ROOT,
)
from partition_config import (
    sync_all_partition_configs as safe_sync_all_partition_configs,
    sync_partition_configs as safe_sync_partition_configs,
)

# Ký tự cần escape trong file_contexts (regex format)
FC_SPECIAL_CHARS = re.compile(r'([.+\[\](){}^$|?*])')

def fc_escape(path):
    """Escape các ký tự đặc biệt regex trong đường dẫn file_contexts."""
    return FC_SPECIAL_CHARS.sub(r'\\\1', path)

def fc_unescape(path):
    """Unescape đường dẫn file_contexts về dạng bình thường."""
    return re.sub(r'\\(.)', r'\1', path)


def sanitize_version_name(value):
    """Keep metadata-derived workspace and ZIP names inside this project."""
    cleaned = str(value or "rom").strip().replace("\\", "_").replace("/", "_")
    cleaned = re.sub(r"[^A-Za-z0-9._()\-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip(" ._")
    return (cleaned or "rom")[:120]


def link_or_copy_file(src, dst):
    """Prefer a hardlink for large build assets; fall back to copy across volumes."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)
        return "linked"
    except OSError:
        shutil.copy2(src, dst)
        return "copied"

# ═══════════════════════════════════════════════════════════════
#  Build-main.py  —  MIO Kitchen ROM Build Orchestrator
# ═══════════════════════════════════════════════════════════════
#  Luồng xử lý:
#   1. Nhập đường dẫn ROM (.zip) + chọn MOD
#   2. Đọc metadata → lấy version_name → tạo thư mục phiên bản
#   3. Gọi payload_tool.py  → giải nén payload.bin  → source_rom/
#   4. Gọi batch_unpack.py  → unpack các partition  → rom-unpack/
#   5. Xóa bloatware + Áp dụng MOD
#   6. Đồng bộ fs_config & file_contexts
#   7. Batch repack: pack các partition thành .img
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR = str(SCRIPT_ROOT)
MOD_DIR = str(CONTENT_ROOT / "MOD")
DEBLOAT_CONFIG_PATH = str(CONFIG_ROOT / "debloat.json")
COPY_IMAGE_DIR = str(COPY_IMAGE_ROOT)
ROM_BUILD_DONE_DIR = str(OUTPUT_ROOT)
ROM_STUDIO_VERSION = "V3.4"
DEFAULT_BUILD_EDITION = "Plus"
VIRTUAL_MODS = {"Block_ota"}
SELINUX_HASH_MODS = {"Fake_lock", "WK_Manager"}
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
_DEBLOAT_LIST_CACHE = None

# Static firmware partitions that must never be packed into super.img.
# They belong in firmware-update/ of the final flashable ZIP instead, so the
# repack step moves them out of rom-repack before lpmake runs.
STATIC_FIRMWARE_PARTITIONS = {
    "dsp",
    "vm-bootsys",
    "vm-bootsys_a",
    "vm-bootsys_b",
}


def load_debloat_list():
    """Load shared debloat defaults used by both CLI and Studio UI."""
    global _DEBLOAT_LIST_CACHE
    if _DEBLOAT_LIST_CACHE is not None:
        return list(_DEBLOAT_LIST_CACHE)
    try:
        with open(DEBLOAT_CONFIG_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        values = payload.get("default") if isinstance(payload, dict) else payload
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError("debloat config must contain a string list")
        _DEBLOAT_LIST_CACHE = list(values)
    except Exception as exc:
        print(f"[!] Không thể đọc config debloat, dùng danh sách legacy: {exc}")
        _DEBLOAT_LIST_CACHE = list(DEBLOAT_LIST)
    return list(_DEBLOAT_LIST_CACHE)


def output_zip_name(version_name, build_edition=DEFAULT_BUILD_EDITION):
    edition = build_edition if build_edition in {"Lite", "Plus", "Custom"} else DEFAULT_BUILD_EDITION
    return f"Wukong_{edition}_{ROM_STUDIO_VERSION}_{sanitize_version_name(version_name)}_China_Stable.zip"


def normalize_android_text_file_lf(path):
    _, extension = os.path.splitext(path)
    if extension.lower() not in ANDROID_LF_TEXT_SUFFIXES and os.path.basename(path) != "build.prop":
        return False
    with open(path, "rb") as handle:
        original = handle.read()
    normalized = original.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if normalized == original:
        return False
    with open(path, "wb") as handle:
        handle.write(normalized)
    return True


def validate_no_unsafe_vendor_priv_app_sysfs(rom_unpack_dir):
    policy = os.path.join(
        rom_unpack_dir,
        "vendor_unpacked",
        "vendor",
        "etc",
        "selinux",
        "vendor_sepolicy.cil",
    )
    if not os.path.isfile(policy):
        return True
    unsafe = []
    with open(policy, "r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle.read().splitlines(), 1):
            stripped = line.strip()
            if UNSAFE_VENDOR_PRIV_APP_SYSFS_RE.match(stripped):
                unsafe.append((line_no, stripped))
    if unsafe:
        preview = "; ".join(f"{line_no}: {rule}" for line_no, rule in unsafe[:3])
        print(
            "[!] Unsafe vendor SELinux rules detected for priv_app_34_0 -> vendor_sysfs. "
            "These rules are known to break boot on Snapdragon 8 Elite."
        )
        print(f"[!] Remove them from: {policy}")
        print(f"[!] First matches: {preview}")
        return False
    return True


def write_text_lf(path, content, encoding="utf-8"):
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "wb") as handle:
        handle.write(normalized.encode(encoding))


def apply_stark_patch(source, destination):
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    if os.path.isfile(destination):
        with open(destination, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    else:
        lines = []
    added = removed = replaced = 0
    with open(source, "r", encoding="utf-8", errors="replace") as handle:
        instructions = handle.read().splitlines()
    for instruction in instructions:
        if not instruction.strip():
            continue
        operation = instruction[0] if instruction[0] in {"+", "-", "!"} else "="
        payload = instruction[1:] if operation in {"+", "-", "!"} else instruction
        normalized = payload.strip()
        if not normalized:
            continue
        if (
            os.path.basename(source) == "stark_vendor_sepolicy.cil"
            and normalized.startswith("(allow priv_app_34_0 vendor_sysfs_")
        ):
            raise RuntimeError(
                "Unsafe WK_Manager vendor SELinux rule blocked: priv_app_34_0 "
                "must not be granted vendor_sysfs access from vendor sepolicy"
            )
        if operation == "+":
            if not any(line.strip() == normalized for line in lines):
                insert_index = stark_xml_insert_index(os.path.basename(source), lines, normalized)
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
                raise RuntimeError(f"Stark upsert line has no '=': {source}: {payload}")
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
                raise RuntimeError(f"Stark replacement line has no '=': {source}: {payload}")
            key = payload.split("=", 1)[0].strip()
            matches = [
                index
                for index, line in enumerate(lines)
                if "=" in line and line.split("=", 1)[0].strip() == key
            ]
            if not matches:
                raise RuntimeError(f"Stark replacement key was not found: {source}: {key}")
            for index in matches:
                lines[index] = payload
                replaced += 1
    write_text_lf(destination, "\n".join(lines) + ("\n" if lines else ""))
    return {"added": added, "removed": removed, "replaced": replaced}


def stark_xml_insert_index(source_name, lines, normalized):
    if not source_name.endswith(".xml") or not normalized.startswith("<oplus-feature "):
        return None
    for index, line in enumerate(lines):
        if line.strip() == "</oplus-config>":
            return index
    return None


def stark_destination(partition_dst, rel_path):
    rel_dir = os.path.dirname(rel_path)
    filename = os.path.basename(rel_path)
    target_name = filename[len("stark_"):] if filename.startswith("stark_") else filename
    candidate = os.path.join(partition_dst, rel_dir, target_name)
    if os.path.isfile(candidate):
        return candidate
    matches = []
    for root, _dirs, files in os.walk(partition_dst):
        if target_name in files:
            matches.append(os.path.join(root, target_name))
    if len(matches) == 1:
        return matches[0]
    if not matches and os.path.isdir(os.path.dirname(candidate)):
        return candidate
    raise RuntimeError(
        f"Cannot resolve stark patch target for {rel_path}: found {len(matches)} candidates"
    )


def refresh_plat_sepolicy_hash(rom_unpack_dir):
    selinux_dir = os.path.join(
        rom_unpack_dir,
        "system_unpacked",
        "system",
        "system",
        "etc",
        "selinux",
    )
    policy = os.path.join(selinux_dir, "plat_sepolicy.cil")
    checksum = os.path.join(selinux_dir, "plat_sepolicy_and_mapping.sha256")
    if not os.path.isfile(policy):
        raise FileNotFoundError(f"SELinux policy is missing: {policy}")
    if not os.path.isfile(checksum):
        raise FileNotFoundError(f"SELinux checksum is missing: {checksum}")
    with open(policy, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()
    with open(checksum, "wb") as handle:
        handle.write((digest + "\n").encode("ascii"))
    return digest


def patch_product_display_version(prop_path, build_edition=DEFAULT_BUILD_EDITION):
    if not os.path.isfile(prop_path):
        return 0
    with open(prop_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    key = "ro.build.version.oplusrom.display"
    changed = 0
    for index, line in enumerate(lines):
        if not line.startswith(key + "="):
            continue
        base_value = line.split("=", 1)[1].split("|", 1)[0].strip()
        replacement = f"{key}={base_value} | {build_edition} | {ROM_STUDIO_VERSION}"
        if line != replacement:
            lines[index] = replacement
            changed += 1
    if changed:
        with open(prop_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
    return changed


def replace_oneplus_brand(prop_path):
    if not os.path.isfile(prop_path):
        return 0
    with open(prop_path, "r", encoding="utf-8", errors="replace") as handle:
        content = handle.read()
    updated = content.replace("一加", "OnePlus")
    if updated == content:
        return 0
    with open(prop_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    return content.count("一加")


def patch_build_branding(rom_unpack_dir, build_edition=DEFAULT_BUILD_EDITION):
    manifest_prop = os.path.join(
        rom_unpack_dir,
        "my_manifest_unpacked",
        "my_manifest",
        "build.prop",
    )
    product_prop = os.path.join(
        rom_unpack_dir,
        "my_product_unpacked",
        "my_product",
        "build.prop",
    )
    manifest_display_changed = patch_product_display_version(manifest_prop, build_edition)
    product_display_changed = patch_product_display_version(product_prop, build_edition)
    manifest_brand_changed = replace_oneplus_brand(manifest_prop)
    product_brand_changed = replace_oneplus_brand(product_prop)
    print(
        "[*] Build branding: "
        f"manifest_display={manifest_display_changed}, "
        f"product_display={product_display_changed}, "
        f"manifest_OnePlus={manifest_brand_changed}, "
        f"product_OnePlus={product_brand_changed}"
    )
    return {
        "manifestDisplayVersion": manifest_display_changed,
        "productDisplayVersion": product_display_changed,
        "manifestBrand": manifest_brand_changed,
        "productBrand": product_brand_changed,
    }

# ═══════════════════════════════════════════════════════════════
#  Danh sách bloatware cần xóa
#  Mỗi đường dẫn có dạng: <partition>\<đường dẫn bên trong>
#  Sẽ được map thành: rom-unpack/<partition>_unpacked/<đường dẫn>
# ═══════════════════════════════════════════════════════════════
def remove_stock_ota_feature_lines(rom_unpack_dir):
    feature_xml = os.path.join(
        rom_unpack_dir,
        "my_stock_unpacked",
        "my_stock",
        "etc",
        "extension",
        "com.oplus.app-features.xml",
    )
    if not os.path.isfile(feature_xml):
        return 0
    with open(feature_xml, "r", encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    kept = [line for line in lines if "ota" not in line.lower()]
    removed = len(lines) - len(kept)
    if removed:
        with open(feature_xml, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(kept) + ("\n" if kept else ""))
    return removed


DEBLOAT_LIST = [
    # ── my_product ──────────────────────────────────────────
    r"my_product\app\BaiduInput_U_Product",
    r"my_product\del-app\HeytapReader",
    r"my_product\del-app\SogouInput_U_Product_Del",
    r"my_product\etc\permissions\oplus.feature.control_cn_gms.xml",
    r"my_product\etc\permissions\oplus_google_cn_gms_features.xml",
    r"my_product\priv-app\GooglePlayServicesUpdater",

    # ── my_stock ────────────────────────────────────────────
    r"my_stock\app\Browser",
    r"my_stock\app\CarLink",
    r"my_stock\app\ChildrenSpace",
    r"my_stock\app\DigitalKeyFramework",
    r"my_stock\app\DigitalWellBeing",
    r"my_stock\app\OplusOperationManual",
    r"my_stock\app\OplusPhoneActivation",
    r"my_stock\app\OplusSecurityKeyboard",
    r"my_stock\app\TasWallet",
    r"my_stock\app\CloudService",
    r"my_stock\priv-app\OCar",
    r"my_stock\priv-app\HeyTapSpeechAssist",
    r"my_stock\priv-app\KeKeMarket",

    # ── my_stock (nằm trong my_stock_unpacked) ───────────
    r"my_stock\del-app\FinShellWallet",
    r"my_stock\del-app\Gamecenter",
    r"my_stock\del-app\Health",
    r"my_stock\del-app\KeKeUserCenterMember",
    r"my_stock\del-app\Music",
    r"my_stock\del-app\OPBreathMode",
    r"my_stock\del-app\OPCommunity",
    r"my_stock\del-app\OplusEmail",
    r"my_stock\del-app\OplusQuickGame",
    r"my_stock\del-app\OPPOStore",
    r"my_stock\del-app\SoftsimRedteaRoaming",
    r"my_stock\del-app\Tips",
    r"my_stock\del-app\UPTsmService",
    r"my_stock\del-app\BrowserVideo",
    r"my_stock\del-app\FamilyGuard",

    # ── Added by user request ──────────────────────────────
    r"my_product\app\OplusCamera",
    r"my_product\product_overlay",
    r"my_stock\app\ColorAccessibilityAssistant",
    r"my_stock\priv-app\OppoGallery2",
    r"system\system\framework\boot-apache-xml.vdex.fsv_meta",
    r"system\system\framework\boot.vdex",
    r"system\system\framework\boot.vdex.fsv_meta",
    r"system\system\framework\boot-apache-xml.vdex",
    r"system\system\framework\boot-framework.vdex.fsv_meta",
    r"system\system\framework\boot-framework.vdex",
    r"system\system\framework\services.jar.prof",
    r"system\system\framework\services.jar.prof.fsv_meta",
    r"system\system\framework\framework.jar.fsv_meta",
    r"system\system\framework\oplus-services.jar.fsv_meta",
    r"system\system\framework\oplus-services.jar.prof",
    r"system\system\framework\oplus-services.jar.prof.fsv_meta",
    r"system\system\framework\services.jar.fsv_meta",
    r"system\system\framework\arm\boot.vdex",
    r"system\system\framework\arm\boot.vdex.fsv_meta",
    r"system\system\framework\arm\boot.art",
    r"system\system\framework\arm\boot.art.fsv_meta",
    r"system\system\framework\arm\boot.oat",
    r"system\system\framework\arm\boot.oat.fsv_meta",
    r"system\system\framework\arm\boot-framework.oat.fsv_meta",
    r"system\system\framework\arm\boot-framework.vdex",
    r"system\system\framework\arm\boot-framework.vdex.fsv_meta",
    r"system\system\framework\arm\boot-framework.art",
    r"system\system\framework\arm\boot-framework.art.fsv_meta",
    r"system\system\framework\arm\boot-framework.oat",
    r"system\system\framework\arm64\boot.vdex.fsv_meta",
    r"system\system\framework\arm64\boot.art",
    r"system\system\framework\arm64\boot.art.fsv_meta",
    r"system\system\framework\arm64\boot.oat",
    r"system\system\framework\arm64\boot.oat.fsv_meta",
    r"system\system\framework\arm64\boot.vdex",
    r"system\system\framework\arm64\boot-framework.vdex.fsv_meta",
    r"system\system\framework\arm64\boot-framework.art",
    r"system\system\framework\arm64\boot-framework.art.fsv_meta",
    r"system\system\framework\arm64\boot-framework.oat",
    r"system\system\framework\arm64\boot-framework.oat.fsv_meta",
    r"system\system\framework\arm64\boot-framework.vdex",
    r"system\system\framework\ocomp\arm64\boot.vdex.fsv_meta",
    r"system\system\framework\ocomp\arm64\boot.art",
    r"system\system\framework\ocomp\arm64\boot.art.fsv_meta",
    r"system\system\framework\ocomp\arm64\boot.oat",
    r"system\system\framework\ocomp\arm64\boot.oat.fsv_meta",
    r"system\system\framework\ocomp\arm64\boot.vdex",
    r"system\system\framework\ocomp\arm64\boot-framework.vdex.fsv_meta",
    r"system\system\framework\ocomp\arm64\boot-framework.art",
    r"system\system\framework\ocomp\arm64\boot-framework.art.fsv_meta",
    r"system\system\framework\ocomp\arm64\boot-framework.oat",
    r"system\system\framework\ocomp\arm64\boot-framework.oat.fsv_meta",
    r"system\system\framework\ocomp\arm64\boot-framework.vdex",

]


def print_banner():
    banner = r"""
╔══════════════════════════════════════════════════════════╗
║              MIO KITCHEN - ROM BUILD MAIN                ║
║                    by KHANHSTARK                         ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_step(step_number, description):
    """In tiêu đề bước xử lý."""
    print(f"\n{'='*60}")
    print(f"  STEP {step_number}: {description}")
    print(f"{'='*60}")


def read_metadata_from_zip(zip_path):
    """
    Đọc file META-INF/com/android/metadata trong .zip,
    tìm dòng 'post-build' hoặc bất kỳ dòng nào chứa version_name
    và trả về (version_name, product_name).
    """
    metadata_path = "META-INF/com/android/metadata"

    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            # Tìm file metadata (có thể nằm ở vị trí hơi khác)
            found_path = None
            for name in z.namelist():
                if name.replace("\\", "/").endswith(metadata_path):
                    found_path = name
                    break

            if not found_path:
                print(f"[!] Không tìm thấy '{metadata_path}' trong file zip.")
                return None, None

            with z.open(found_path) as meta_file:
                content = meta_file.read().decode("utf-8", errors="replace")

            print(f"\n[*] Nội dung metadata:")
            print("-" * 40)

            version_name = None
            product_name = None
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                print(f"    {line}")

                # Tìm version_name
                if "version_name" in line.lower() and "=" in line:
                    version_name = line.split("=", 1)[1].strip()
                
                # Tìm product_name
                if "product_name" in line.lower() and "=" in line:
                    product_name = line.split("=", 1)[1].strip()

            print("-" * 40)
            return version_name, product_name

    except zipfile.BadZipFile:
        print(f"[!] Lỗi: '{zip_path}' không phải file zip hợp lệ.")
        return None, None
    except Exception as e:
        print(f"[!] Lỗi khi đọc metadata: {e}")
        return None, None


def run_payload_tool(zip_path, output_dir):
    """Gọi payload_tool.py để giải nén payload.bin vào output_dir."""
    payload_script = os.path.join(SCRIPT_DIR, "payload_tool.py")

    if not os.path.exists(payload_script):
        print(f"[!] Không tìm thấy script: {payload_script}")
        return False

    cmd = [
        sys.executable,
        payload_script,
        zip_path,
        "-o", output_dir,
    ]

    print(f"[*] Chạy lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        if result.returncode == 0:
            print(f"[✓] payload_tool.py hoàn thành thành công!")
            return True
        else:
            print(f"[!] payload_tool.py kết thúc với mã lỗi: {result.returncode}")
            return False
    except Exception as e:
        print(f"[!] Lỗi khi chạy payload_tool.py: {e}")
        return False


def run_batch_unpack(source_rom_dir, target_unpack_dir):
    """Gọi batch_unpack.py để unpack tất cả partition."""
    batch_script = os.path.join(SCRIPT_DIR, "batch_unpack.py")

    if not os.path.exists(batch_script):
        print(f"[!] Không tìm thấy script: {batch_script}")
        return False

    cmd = [
        sys.executable,
        batch_script,
        source_rom_dir,
        target_unpack_dir,
    ]

    print(f"[*] Chạy lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        if result.returncode == 0:
            print(f"[✓] batch_unpack.py hoàn thành thành công!")
            return True
        else:
            print(f"[!] batch_unpack.py kết thúc với mã lỗi: {result.returncode}")
            return False
    except Exception as e:
        print(f"[!] Lỗi khi chạy batch_unpack.py: {e}")
        return False


def clean_bloatware(rom_unpack_dir):
    r"""
    Xóa tất cả thư mục / file bloatware trong rom-unpack.
    Đường dẫn trong DEBLOAT_LIST có dạng: <partition>\<đường dẫn bên trong>
    Sẽ được map thành: rom_unpack_dir/<partition>_unpacked/<đường dẫn>
    """
    print(f"[*] Bắt đầu xóa bloatware...\n")

    deleted = 0
    skipped = 0

    for rel_path in load_debloat_list():
        # Tách partition (phần đầu) và đường dẫn còn lại
        parts = rel_path.replace("/", os.sep).replace("\\", os.sep).split(os.sep, 1)
        if len(parts) < 2:
            print(f"  [!] Đường dẫn không hợp lệ: {rel_path}")
            skipped += 1
            continue

        partition = parts[0]           # VD: my_product
        inner_path = parts[1]          # VD: app\BaiduInput_U_Product
        if partition in PASSTHROUGH_PARTITIONS:
            print(f"  [-] Skip passthrough partition: {partition}/{inner_path}")
            skipped += 1
            continue

        # Map sang thư mục _unpacked/<partition>/ do batch_unpack.py tạo
        full_path = os.path.join(rom_unpack_dir, f"{partition}_unpacked", partition, inner_path)

        if os.path.exists(full_path):
            try:
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                    print(f"  [✓] Đã xóa thư mục: {partition}/{inner_path}")
                else:
                    os.remove(full_path)
                    print(f"  [✓] Đã xóa file   : {partition}/{inner_path}")
                deleted += 1
            except Exception as e:
                print(f"  [!] Lỗi khi xóa '{full_path}': {e}")
                skipped += 1
        else:
            print(f"  [-] Không tồn tại : {partition}/{inner_path}")
            skipped += 1

    print(f"\n[*] Debloat xong: {deleted} đã xóa, {skipped} bỏ qua.")
    return deleted



def _legacy_sync_partition_configs(unpacked_dir, partition_name):
    """
    Đồng bộ _fs_config và _file_contexts với filesystem thực tế.
    - Thêm entry cho file/dir mới (MOD thêm vào)
    - Xóa entry cho file/dir đã bị xóa (debloat)
    """
    config_dir = os.path.join(unpacked_dir, "config")
    data_dir = os.path.join(unpacked_dir, partition_name)

    if not os.path.isdir(config_dir) or not os.path.isdir(data_dir):
        return

    fs_config_file = os.path.join(config_dir, f"{partition_name}_fs_config")
    file_contexts_file = os.path.join(config_dir, f"{partition_name}_file_contexts")

    if not os.path.isfile(fs_config_file) or not os.path.isfile(file_contexts_file):
        print(f"    [!] Config files không tồn tại cho {partition_name}")
        return

    # Xác định default context dựa trên tên partition
    default_context = "u:object_r:system_file:s0"
    if partition_name in ["vendor", "vendor_dlkm", "my_heytap", "my_stock"]:
        default_context = "u:object_r:vendor_file:s0"
    elif partition_name in ["odm", "my_company", "my_preload"]:
        default_context = "u:object_r:vendor_file:s0" # Thường là vendor_file hoặc odm_file
    elif partition_name == "system_ext":
        default_context = "u:object_r:system_file:s0"
    elif partition_name == "product":
        default_context = "u:object_r:system_file:s0"

    # ═══ 1. Thu thập tất cả đường dẫn thực tế ═══════════════════
    actual_paths = set()
    data_parent = os.path.dirname(data_dir)
    for root, dirs, files in os.walk(data_dir):
        rel = os.path.relpath(root, data_parent).replace("\\", "/")
        actual_paths.add(rel)
        for f in files:
            actual_paths.add(rel + "/" + f)
        # Symlinks
        for d in dirs:
            full = os.path.join(root, d)
            if os.path.islink(full):
                actual_paths.add(rel + "/" + d)

    # ═══ 2. Đọc & cập nhật fs_config ════════════════════════════
    with open(fs_config_file, "r", encoding="utf-8") as f:
        fs_lines = f.readlines()

    # Parse existing entries (path → full line)
    fs_existing = {}
    fs_header_lines = []
    for line in fs_lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 4:
            fs_existing[parts[0]] = stripped
        elif stripped == "/":
            fs_header_lines.append(stripped)

    # Tìm file mới cần thêm vào fs_config
    added_fs = 0
    removed_fs = 0

    # Thêm entry cho các path chưa có
    for path in sorted(actual_paths):
        if path not in fs_existing:
            full_path = os.path.join(data_parent, path.replace("/", os.sep))
            if os.path.islink(full_path):
                try:
                    target = os.readlink(full_path).replace("\\", "/")
                    fs_existing[path] = f"{path} 0 0 0644 {target}"
                except:
                    fs_existing[path] = f"{path} 0 0 0644"
            elif os.path.isdir(full_path):
                fs_existing[path] = f"{path} 0 0 0755"
            else:
                # Tự động gán quyền thực thi cho file trong các thư mục bin
                perm = "0644"
                if "/bin/" in path or "/xbin/" in path or path.endswith(".sh"):
                    perm = "0755"
                fs_existing[path] = f"{path} 0 0 {perm}"
            added_fs += 1

    # Xóa entry cho path không còn tồn tại
    paths_to_remove = []
    for path in fs_existing:
        if path in ("/", f"{partition_name}/", f"{partition_name}/lost+found"):
            continue
        if path not in actual_paths:
            paths_to_remove.append(path)
            removed_fs += 1

    for path in paths_to_remove:
        del fs_existing[path]

    # Ghi lại fs_config (sắp xếp)
    with open(fs_config_file, "w", encoding="utf-8", newline="\n") as f:
        # Giữ dòng / ở đầu
        f.write("/ 0 0 0755\n")
        for path in sorted(fs_existing):
            if fs_existing[path].startswith("/ "):
                continue
            f.write(fs_existing[path] + "\n")

    # ═══ 3. Đọc & cập nhật file_contexts ═════════════════════════
    with open(file_contexts_file, "r", encoding="utf-8") as f:
        fc_lines = f.readlines()

    # Parse existing entries
    # Format: /path u:object_r:type:s0
    fc_existing = {}
    
    # Ở đây default_context đã được xác định ở trên

    for line in fc_lines:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(None, 1)
        if len(parts) >= 2:
            fc_existing[parts[0]] = parts[1]
        elif stripped == "/":
            pass

    added_fc = 0
    removed_fc = 0
    added_fc_entries = []

    # Thêm entry cho các path chưa có
    for path in sorted(actual_paths):
        # file_contexts dùng format: /partition_name/sub/path
        fc_path = "/" + path

        # Escape các ký tự đặc biệt trong regex
        fc_path_escaped = fc_escape(fc_path)

        if fc_path_escaped not in fc_existing and fc_path not in fc_existing:
            # Thuật toán tìm context thông minh: 
            # 1. Tìm file cùng thư mục đã có context
            # 2. Nếu không có, tìm context của thư mục cha
            # 3. Cuối cùng mới dùng default_context
            parent_dir = fc_path_escaped.rsplit("/", 1)[0]
            matched_context = None
            
            # Ưu tiên các file cùng thư mục
            for existing_path, ctx in fc_existing.items():
                if existing_path.startswith(parent_dir + "/"):
                    matched_context = ctx
                    break
            
            # Thử tìm context của chính thư mục cha
            if not matched_context:
                matched_context = fc_existing.get(parent_dir)
            
            if not matched_context:
                # Hardcode một số trường hợp đặc biệt cho vendor
                if "/etc/init" in fc_path: matched_context = "u:object_r:vendor_configs_file:s0"
                elif "/bin/hw" in fc_path: matched_context = "u:object_r:hal_audio_default_exec:s0" # hoặc tổng quát hơn
                else: matched_context = default_context
                
            fc_existing[fc_path_escaped] = matched_context
            added_fc += 1
            added_fc_entries.append(f"{fc_path_escaped} {matched_context}")

    # Xóa entry cho path không còn tồn tại
    fc_paths_to_remove = []
    for fc_path in fc_existing:
        # Unescape để kiểm tra tồn tại
        clean_path = fc_unescape(fc_path).lstrip("/")
        if clean_path in ("", f"{partition_name}", f"{partition_name}/",
                          f"{partition_name}/lost+found"):
            continue
        if clean_path not in actual_paths:
            fc_paths_to_remove.append(fc_path)
            removed_fc += 1

    for fc_path in fc_paths_to_remove:
        del fc_existing[fc_path]

    # Ghi lại file_contexts (sắp xếp)
    with open(file_contexts_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"/ {default_context}\n")
        for fc_path in sorted(fc_existing):
            if fc_existing[fc_path] and fc_path != "/":
                f.write(f"{fc_path} {fc_existing[fc_path]}\n")

    if added_fs > 0 or removed_fs > 0 or added_fc > 0 or removed_fc > 0:
        print(f"    [✓] {partition_name}: fs_config(+{added_fs} -{removed_fs}) "
              f"file_contexts(+{added_fc} -{removed_fc})")
        if added_fc_entries:
            print(f"    [+] Added file_contexts:")
            for entry in added_fc_entries:
                print(f"        {entry}")
    else:
        print(f"    [-] {partition_name}: không có thay đổi")



def sync_partition_configs(unpacked_dir, partition_name):
    """Preserve extracted metadata and append entries for new MOD files."""
    return safe_sync_partition_configs(unpacked_dir, partition_name)


def sync_all_configs(rom_unpack_dir):
    if not validate_no_unsafe_vendor_priv_app_sysfs(rom_unpack_dir):
        return False
    return safe_sync_all_partition_configs(rom_unpack_dir)

    """
    Đồng bộ config cho TẤT CẢ partition trong rom-unpack.
    Chạy sau debloat + MOD để đảm bảo repack đúng.
    """
    print(f"[*] Đồng bộ fs_config & file_contexts cho tất cả partition...\n")

    for item in sorted(os.listdir(rom_unpack_dir)):
        if not item.endswith("_unpacked"):
            continue

        unpacked_dir = os.path.join(rom_unpack_dir, item)
        partition_name = item.replace("_unpacked", "")

        config_dir = os.path.join(unpacked_dir, "config")
        data_dir = os.path.join(unpacked_dir, partition_name)

        if os.path.isdir(config_dir) and os.path.isdir(data_dir):
            sync_partition_configs(unpacked_dir, partition_name)

    print(f"\n[*] Đồng bộ config hoàn tất.")


def select_mod_folder():
    r"""
    Liệt kê các thư mục MOD có trong \MOD và cho người dùng chọn.
    Trả về đường dẫn đầy đủ tới thư mục MOD đã chọn, hoặc None nếu bỏ qua.
    """
    if not os.path.isdir(MOD_DIR):
        print(f"[!] Thư mục MOD không tồn tại: {MOD_DIR}")
        return None

    mod_folders = sorted(set([
        d for d in os.listdir(MOD_DIR)
        if os.path.isdir(os.path.join(MOD_DIR, d))
    ]) | VIRTUAL_MODS)

    if not mod_folders:
        print("[!] Không tìm thấy MOD nào trong thư mục MOD/")
        return None

    print(f"\n[*] Danh sách MOD có sẵn:")
    print("-" * 40)
    for i, name in enumerate(mod_folders, 1):
        print(f"  {i}. {name}")
    print(f"  0. Bỏ qua (không áp dụng MOD)")
    print("-" * 40)

    while True:
        choice = input(f"[?] Chọn MOD (1-{len(mod_folders)}, 0 để bỏ qua): ").strip()
        if choice == "0":
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(mod_folders):
                selected = mod_folders[idx]
                selected_path = selected if selected in VIRTUAL_MODS else os.path.join(MOD_DIR, selected)
                print(f"[★] Đã chọn MOD: {selected}")
                return selected_path
            else:
                print("[!] Số không hợp lệ, thử lại.")
        except ValueError:
            print("[!] Vui lòng nhập số.")


def apply_mod(mod_path, rom_unpack_dir, device_db=None):
    """
    Copy tất cả file từ MOD/<tên mod>/<partition>/... 
    vào rom-unpack/<partition>_unpacked/...
    Ghi đè file đã tồn tại.
    """
    mod_name = os.path.basename(mod_path)
    print(f"[*] Áp dụng MOD: {mod_name}")
    print(f"[*] Nguồn : {mod_path}")
    print(f"[*] Đích  : {rom_unpack_dir}\n")

    copied = 0
    errors = 0
    soc = device_db.get("soc", "") if device_db else ""

    # Mỗi thư mục con cấp 1 trong MOD là tên partition
    partitions = sorted(os.listdir(mod_path)) if os.path.isdir(mod_path) else []
    for partition in partitions:
        partition_src = os.path.join(mod_path, partition)
        if not os.path.isdir(partition_src):
            continue

        # Logic lọc vendor theo SOC và ánh xạ tên phân vùng
        target_partition = partition
        if partition == "vendor_arm64":
            if soc and soc > "86xx":
                continue # Bỏ qua vendor_arm64 nếu SOC > 86xx
            target_partition = "vendor"
            print(f"  [+] Sử dụng vendor_arm64 → mapping thành vendor (SOC: {soc or 'N/A'})")
        elif partition == "vendor_aidl":
            if soc and soc < "87xx":
                continue # Bỏ qua vendor_aidl nếu SOC < 87xx
            target_partition = "vendor"
            print(f"  [+] Sử dụng vendor_aidl → mapping thành vendor (SOC: {soc or 'N/A'})")
        if target_partition in PASSTHROUGH_PARTITIONS:
            print(f"  [-] Skip passthrough partition: {target_partition}")
            continue

        # Map sang <target_partition>_unpacked/<target_partition> trong rom-unpack
        partition_dst = os.path.join(rom_unpack_dir, f"{target_partition}_unpacked", target_partition)

        if not os.path.exists(partition_dst):
            print(f"  [!] Partition đích không tồn tại: {partition}_unpacked  → bỏ qua")
            continue

        print(f"  [>>>] Partition: {partition}")

        # Duyệt tất cả file trong thư mục MOD partition
        for root, dirs, files in os.walk(partition_src):
            # Tính đường dẫn tương đối so với partition_src
            rel_root = os.path.relpath(root, partition_src)

            for filename in files:
                src_file = os.path.join(root, filename)
                if rel_root == ".":
                    dst_file = os.path.join(partition_dst, filename)
                else:
                    dst_file = os.path.join(partition_dst, rel_root, filename)

                if filename.startswith("stark_"):
                    try:
                        dst_file = stark_destination(partition_dst, os.path.join(rel_root, filename))
                        result = apply_stark_patch(src_file, dst_file)
                        rel_display = os.path.relpath(dst_file, rom_unpack_dir)
                        print(f"    [✓] patch {rel_display} {result}")
                        copied += sum(result.values())
                    except Exception as e:
                        print(f"    [!] Lỗi patch: {src_file} → {e}")
                        errors += 1
                    continue

                try:
                    # Tạo thư mục đích nếu chưa có
                    dst_dir = os.path.dirname(dst_file)
                    if not os.path.exists(dst_dir):
                        os.makedirs(dst_dir)

                    # Copy ghi đè
                    shutil.copy2(src_file, dst_file)
                    normalize_android_text_file_lf(dst_file)
                    # Hiển thị đường dẫn ngắn gọn
                    rel_display = os.path.relpath(dst_file, rom_unpack_dir)
                    print(f"    [✓] {rel_display}")
                    copied += 1
                except Exception as e:
                    print(f"    [!] Lỗi copy: {src_file} → {e}")
                    errors += 1

    if mod_name == "Block_ota":
        removed_ota = remove_stock_ota_feature_lines(rom_unpack_dir)
        if removed_ota:
            print(f"  [✓] Xóa {removed_ota} dòng chứa ota trong my_stock app-features.xml")
        else:
            print("  [-] Block_ota: không tìm thấy dòng chứa ota để xóa")

    print(f"\n[*] Áp dụng MOD xong: {copied} file đã copy, {errors} lỗi.")
    if mod_name in SELINUX_HASH_MODS:
        try:
            digest = refresh_plat_sepolicy_hash(rom_unpack_dir)
            print(f"  [✓] Refreshed plat_sepolicy_and_mapping.sha256: {digest}")
        except Exception as e:
            print(f"  [!] Failed to refresh plat_sepolicy_and_mapping.sha256: {e}")
            errors += 1

    return copied


def _run_framework_cooker_legacy(rom_unpack_dir, version_dir):
    """
    Step 6: Framework Cooker
    - Unpack framework.jar, services.jar, oplus-services.jar
    - Chạy framework-cooker.py, services-cooker.py, oplus-services-cooker.py
    - Repack lại các JAR
    - Copy JAR đã patch về vị trí ban đầu
    """
    # Danh sách các đường dẫn ứng viên cho thư mục framework
    candidates = [
        os.path.join(rom_unpack_dir, "system_unpacked", "system", "system", "framework"),
        os.path.join(rom_unpack_dir, "system_unpacked", "system", "framework"),
        os.path.join(rom_unpack_dir, "system_a_unpacked", "system", "system", "framework"),
        os.path.join(rom_unpack_dir, "system_a_unpacked", "system", "framework"),
    ]

    framework_src_dir = None
    for cand in candidates:
        if os.path.isdir(cand):
            framework_src_dir = cand
            print(f"  [✓] Tìm thấy thư mục framework tại: {cand}")
            break

    if not framework_src_dir:
        print(f"[!] Không tìm thấy thư mục framework trong các đường dẫn dự kiến.")
        return False

    # Thư mục cooker nằm trong version_dir
    cooker_dir = os.path.join(version_dir, "framework-cooker")

    # 3 file JAR cần xử lý
    jars = ["framework.jar", "services.jar", "oplus-services.jar"]
    failed = False

    # ── 6a: Unpack tất cả JAR ──────────────────────────────────
    print(f"\n[*] 6a. Unpack JAR files...")
    framework_tool = os.path.join(SCRIPT_DIR, "framework_tool.py")

    for jar_name in jars:
        jar_path = os.path.join(framework_src_dir, jar_name)
        if not os.path.isfile(jar_path):
            print(f"  [!] Không tìm thấy: {jar_path}")
            failed = True
            continue

        print(f"\n  [>>>] Unpack: {jar_name}")
        cmd = [
            sys.executable, framework_tool,
            "unpack", jar_path,
            "-o", cooker_dir,
        ]
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        if result.returncode != 0:
            print(f"  [!] Unpack {jar_name} thất bại (code={result.returncode})")
            failed = True

    # ── Tạo symlink framework-cooker tại SCRIPT_DIR ────────────
    # Các cooker script dùng đường dẫn tương đối "framework-cooker/..."
    # nên cần symlink từ SCRIPT_DIR/framework-cooker → version_dir/framework-cooker
    symlink_path = os.path.join(SCRIPT_DIR, "framework-cooker")
    symlink_created = False
    old_symlink_backup = None

    if os.path.isdir(cooker_dir):
        # Backup nếu đã tồn tại thư mục/symlink framework-cooker ở SCRIPT_DIR
        if os.path.exists(symlink_path) or os.path.islink(symlink_path):
            old_symlink_backup = symlink_path + "_backup_" + str(int(time.time()))
            print(f"  [*] Backup framework-cooker cũ → {os.path.basename(old_symlink_backup)}")
            os.rename(symlink_path, old_symlink_backup)

        try:
            # Tạo directory junction (hoạt động trên Windows không cần admin)
            if os.name == 'nt':
                cmd_link = f'mklink /J "{symlink_path}" "{cooker_dir}"'
                subprocess.run(cmd_link, shell=True, check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.symlink(cooker_dir, symlink_path)
            
            symlink_created = True
            print(f"  [✓] Đã tạo liên kết: framework-cooker → {cooker_dir}")
        except Exception as e:
            print(f"  [!] Không tạo được liên kết: {e}")
            print(f"  [*] Sử dụng trực tiếp cooker_dir trong các bước tiếp theo.")
            # Nếu không tạo được junction, ta sẽ cập nhật SCRIPT_DIR trong env cho các script?
            # Thực tế các script đang hardcode "framework-cooker/..."
            # Cách tốt nhất là copy và sau đó copy ngược lại nếu không dùng được junction.
            shutil.copytree(cooker_dir, symlink_path)
            symlink_created = "copy"

    # ── 6b: Chạy các cooker script ─────────────────────────────
    print(f"\n[*] 6b. Chạy cooker scripts để patch smali...")

    cooker_scripts = [
        ("framework-cooker.py", "Framework Cooker"),
        ("services-cooker.py", "Services Cooker"),
        ("oplus-services-cooker.py", "Oplus Services Cooker"),
    ]

    for script_name, display_name in cooker_scripts:
        script_path = os.path.join(SCRIPT_DIR, script_name)
        if not os.path.isfile(script_path):
            print(f"  [!] Không tìm thấy: {script_name}")
            failed = True
            continue

        print(f"\n  [>>>] Chạy {display_name}...")
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=SCRIPT_DIR,
            check=False
        )
        if result.returncode == 0:
            print(f"  [✓] {display_name} hoàn thành.")
        else:
            print(f"  [!] {display_name} kết thúc với mã lỗi: {result.returncode}")
            failed = True

    # ── 6c: Repack tất cả JAR ──────────────────────────────────
    print(f"\n[*] 6c. Repack JAR files...")

    # Liệt kê thư mục _unpack trong cooker_dir
    if os.path.isdir(cooker_dir):
        unpack_dirs = [
            d for d in os.listdir(cooker_dir)
            if os.path.isdir(os.path.join(cooker_dir, d)) and d.endswith("_unpack")
        ]
    else:
        unpack_dirs = []
        failed = True

    for unpack_name in sorted(unpack_dirs):
        unpack_path = os.path.join(cooker_dir, unpack_name)
        print(f"\n  [>>>] Repack: {unpack_name}")
        cmd = [
            sys.executable, framework_tool,
            "repack", unpack_path,
            "-o", cooker_dir,
        ]
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        if result.returncode != 0:
            print(f"  [!] Repack {unpack_name} thất bại (code={result.returncode})")
            failed = True

    # ── 6d: Dọn dẹp symlink ────────────────────────────────────
    if symlink_created:
        try:
            # Xóa junction / thư mục tạm
            if symlink_created == "copy":
                # Nếu là copy, ta phải copy ngược lại những gì đã sửa về cooker_dir
                print(f"  [*] Đang đồng bộ ngược các thay đổi từ copy tạm thời...")
                shutil.rmtree(cooker_dir)
                shutil.copytree(symlink_path, cooker_dir)
                shutil.rmtree(symlink_path)
            elif os.path.islink(symlink_path) or os.path.isdir(symlink_path):
                # Junction trên Windows cần xóa bằng rmdir
                if os.name == 'nt':
                     subprocess.run(f'rmdir "{symlink_path}"', shell=True,
                                   check=False, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                else:
                    os.remove(symlink_path)
                
                if os.path.exists(symlink_path):
                    shutil.rmtree(symlink_path, ignore_errors=True)
            print(f"  [✓] Đã dọn dẹp liên kết/thư mục tạm thời.")
        except:
            pass

        # Khôi phục backup nếu có
        if old_symlink_backup and os.path.exists(old_symlink_backup):
            os.rename(old_symlink_backup, symlink_path)
            print(f"  [✓] Đã khôi phục framework-cooker cũ.")

    print(f"\n[*] Framework Cooker hoàn thành!")
    return not failed


def copy_passthrough_partition_images(source_rom_dir, rom_repack_dir):
    if not source_rom_dir:
        return True
    if not os.path.isdir(source_rom_dir):
        print(f"[!] Source ROM directory missing for passthrough copy: {source_rom_dir}")
        return False
    os.makedirs(rom_repack_dir, exist_ok=True)
    copied = 0
    for partition in sorted(PASSTHROUGH_PARTITIONS):
        src = os.path.join(source_rom_dir, f"{partition}.img")
        if not os.path.isfile(src):
            continue
        link_or_copy_file(src, os.path.join(rom_repack_dir, f"{partition}.img"))
        copied += 1
        print(f"  [=] Passthrough copy: {partition}.img")
    print(f"[*] Passthrough partitions copied: {copied}")
    return True


def run_batch_repack(rom_unpack_dir, rom_repack_dir, source_rom_dir=None, img_format="erofs"):
    """Gọi batch_repack.py để repack tất cả partition thành .img."""
    batch_repack_script = os.path.join(SCRIPT_DIR, "batch_repack.py")

    if not os.path.exists(batch_repack_script):
        print(f"[!] Không tìm thấy script: {batch_repack_script}")
        return False

    cmd = [
        sys.executable,
        batch_repack_script,
        rom_unpack_dir,
        rom_repack_dir,
        "--format", img_format,
        "--skip-sync",
    ]
    print(f"[*] Chạy lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        if result.returncode == 0:
            if not copy_passthrough_partition_images(source_rom_dir, rom_repack_dir):
                return False
            print(f"[✓] batch_repack.py hoàn thành thành công!")
            return True
        else:
            print(f"[!] batch_repack.py kết thúc với mã lỗi: {result.returncode}")
            return False
    except Exception as e:
        print(f"[!] Lỗi khi chạy batch_repack.py: {e}")
        return False


def _legacy_apply_region_patches(rom_unpack_dir):
    """
    Step 8: Chỉnh sửa các file XML và build.prop để chuyển ROM sang global.
    """
    print(f"[*] Bắt đầu chỉnh sửa region / props...\n")
    patched = 0

    # ═══ 1. my_region: xóa dòng CN trong app-features.xml ═══════
    f1 = os.path.join(rom_unpack_dir, "my_region_unpacked", "my_region",
                      "etc", "extension", "com.oplus.app-features.xml")
    if os.path.isfile(f1):
        print(f"  [*] Patching: my_region app-features.xml")
        with open(f1, "r", encoding="utf-8") as f:
            lines = f.readlines()
        remove_lines = [
            'name="com.android.launcher.REGION_NAME" args="String:CN"',
            'name="com.android.launcher.CN_VERSION"',
        ]
        new_lines = []
        removed = 0
        for line in lines:
            if any(pat in line for pat in remove_lines):
                removed += 1
                continue
            new_lines.append(line)
        if removed > 0:
            with open(f1, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
            print(f"    [✓] Xóa {removed} dòng CN")
            patched += 1
        else:
            print(f"    [-] Không tìm thấy dòng CN hoặc đã xóa")
    else:
        print(f"  [!] Không tìm thấy: {f1}")

    # ═══ 2. my_manifest: đổi tên thương hiệu 一加 → OnePlus ════════
    f2 = os.path.join(rom_unpack_dir, "my_manifest_unpacked", "my_manifest",
                      "build.prop")
    if os.path.isfile(f2):
        print(f"  [*] Patching: my_manifest build.prop")
        with open(f2, "r", encoding="utf-8") as f:
            content = f.read()
        if "一加" in content:
            content = content.replace("一加", "OnePlus")
            with open(f2, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"    [✓] Đổi 一加 → OnePlus")
            patched += 1
        else:
            print(f"    [-] Không tìm thấy '一加' hoặc đã đổi")
    else:
        print(f"  [!] Không tìm thấy: {f2}")

    # ═══ 3. my_product: đổi timezone/region/locale ══════════════
    f3 = os.path.join(rom_unpack_dir, "my_product_unpacked", "my_product",
                      "build.prop")
    prop_replacements = {
        "persist.sys.timezone": "persist.sys.timezone=America/New_York",
        "persist.sys.oplus.region": "persist.sys.oplus.region=US",
        "ro.product.locale": "ro.product.locale=en-US",
        "persist.vendor.ims.disableDebugLogs": "persist.vendor.ims.disableDebugLogs=1",
        "persist.vendor.ims.disableADBLogs": "persist.vendor.ims.disableADBLogs=1",
        "persist.vendor.ims.disableQXDMLogs": "persist.vendor.ims.disableQXDMLogs=1",
        "persist.vendor.ims.disableIMSLogs": "persist.vendor.ims.disableIMSLogs=1",
        "persist.ims.disableDebugLogs": "persist.ims.disableDebugLogs=1",
        "persist.ims.disableADBLogs": "persist.ims.disableADBLogs=1",
        "persist.ims.disableQXDMLogs": "persist.ims.disableQXDMLogs=1",
        "persist.ims.disableIMSLogs": "persist.ims.disableIMSLogs=1",

    }
    if os.path.isfile(f3):
        print(f"  [*] Patching: my_product build.prop")
        with open(f3, "r", encoding="utf-8") as f:
            lines = f.readlines()
        changed = 0
        new_lines = []
        for line in lines:
            replaced = False
            for key, new_val in prop_replacements.items():
                if line.strip().startswith(key + "=") or line.strip() == key:
                    new_lines.append(new_val + "\n")
                    changed += 1
                    replaced = True
                    break
            if not replaced:
                new_lines.append(line)
        if changed > 0:
            with open(f3, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
            print(f"    [✓] Đổi {changed} properties")
            patched += 1
        else:
            print(f"    [-] Không tìm thấy properties cần đổi")
    else:
        print(f"  [!] Không tìm thấy: {f3}")

    # ═══ 4. my_stock: xóa dòng ota/update trong app-features.xml ═
    f4 = os.path.join(rom_unpack_dir, "my_stock_unpacked", "my_stock",
                      "etc", "extension", "com.oplus.app-features.xml")
    if os.path.isfile(f4):
        print(f"  [*] Patching: my_stock app-features.xml")
        with open(f4, "r", encoding="utf-8") as f:
            lines = f.readlines()
        new_lines = []
        removed = 0
        for line in lines:
            lower = line.lower()
            if "ota" in lower or "update" in lower:
                removed += 1
                continue
            new_lines.append(line)
        if removed > 0:
            with open(f4, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
            print(f"    [✓] Xóa {removed} dòng chứa ota/update")
            patched += 1
        else:
            print(f"    [-] Không tìm thấy dòng ota/update")
    else:
        print(f"  [!] Không tìm thấy: {f4}")

    # ═══ 5. system_ext: tắt debug logs ═════════════════════════
    f5 = os.path.join(rom_unpack_dir, "system_ext_unpacked", "system_ext",
                      "etc", "build.prop")
    log_replacements = {
        "persist.sys.log.main": "persist.sys.log.main=8|10",
        "persist.sys.log.radio": "persist.sys.log.radio=8|10",
        "persist.sys.log.event": "persist.sys.log.event=8|10",
        "persist.sys.log.kernel": "persist.sys.log.kernel=8|10",
        "persist.sys.log.tcpdump": "persist.sys.log.tcpdump=0",
    }
    if os.path.isfile(f5):
        print(f"  [*] Patching: system_ext build.prop")
        with open(f5, "r", encoding="utf-8") as f:
            lines = f.readlines()
        changed = 0
        new_lines = []
        for line in lines:
            replaced = False
            for key, new_val in log_replacements.items():
                if line.strip().startswith(key + "=") or line.strip() == key:
                    new_lines.append(new_val + "\n")
                    changed += 1
                    replaced = True
                    break
            if not replaced:
                new_lines.append(line)
        if changed > 0:
            with open(f5, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(new_lines)
            print(f"    [✓] Đổi {changed} log properties")
            patched += 1
        else:
            print(f"    [-] Không tìm thấy log properties")
    else:
        print(f"  [!] Không tìm thấy: {f5}")

    # ═══ 6. vendor: thêm camera props ═══════════════════════════
    f6 = os.path.join(rom_unpack_dir, "vendor_unpacked", "vendor",
                      "build.prop")
    vendor_props = [
        "ro.vendor.oplus.camera.isSupportExplorer=1",
        "ro.vendor.oplus.camera.isHasselbladCamera=1",
    ]
    if os.path.isfile(f6):
        print(f"  [*] Patching: vendor build.prop")
        with open(f6, "r", encoding="utf-8") as f:
            content = f.read()
        added = 0
        for prop in vendor_props:
            key = prop.split("=")[0]
            if key not in content:
                content = content.rstrip("\n") + "\n" + prop + "\n"
                added += 1
            else:
                print(f"    [-] Đã tồn tại: {key}")
        if added > 0:
            with open(f6, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"    [✓] Thêm {added} camera properties")
            patched += 1
    else:
        print(f"  [!] Không tìm thấy: {f6}")

    # ═══ 7. system: Kaorios Toolbox props ══════════════════════
    # Kiểm tra cả 2 đường dẫn có thể có của build.prop trong system
    f7_candidates = [
        os.path.join(rom_unpack_dir, "system_unpacked", "system", "system", "build.prop"),
        os.path.join(rom_unpack_dir, "system_unpacked", "system", "build.prop"),
        os.path.join(rom_unpack_dir, "system_a_unpacked", "system", "system", "build.prop"),
        os.path.join(rom_unpack_dir, "system_a_unpacked", "system", "build.prop"),
    ]
    
    f7 = None
    for cand in f7_candidates:
        if os.path.isfile(cand):
            f7 = cand
            break
            
    if f7:
        print(f"  [*] Patching: system build.prop (Kaorios Toolbox)")
        kaorios_props = "\n# Kaorios Toolbox\npersist.sys.kaorios=kousei\n# Leave the value after the = sign blank.\nro.control_privapp_permissions=\n"
        with open(f7, "r", encoding="utf-8") as f:
            content = f.read()
        
        if "persist.sys.kaorios" not in content:
            content = content.rstrip("\n") + "\n" + kaorios_props
            with open(f7, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            print(f"    [✓] Đã thêm Kaorios Toolbox properties")
            patched += 1
        else:
            print(f"    [-] Đã tồn tại Kaorios Toolbox properties")
    else:
        print(f"  [!] Không tìm thấy build.prop của system để patch Kaorios.")

    # ═══ 8. Audio effects patch (JamesDSP) ═════════════════════
    print(f"  [*] Patching audio effects (JamesDSP)...")
    
    def patch_audio_xml(file_path):
        if not os.path.isfile(file_path): return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            lib_entry = '        <library name="jdsp" path="libjamesdsp.so"/>'
            eff_entry = '        <effect name="jamesdsp" library="jdsp" uuid="f27317f4-c984-4de6-9a90-545759495bf2" type="f98765f4-c321-5de6-9a45-123459495ab2"/>'
            
            changed = False
            lines = content.splitlines()
            new_lines = []
            
            # Xóa dòng <apply effect="music_helper"/> và <apply effect="music_post_proc"/>
            for line in lines:
                if '<apply effect="music_helper"/>' in line or '<apply effect="music_post_proc"/>' in line:
                    changed = True
                    continue
                new_lines.append(line)
            lines = new_lines
            new_lines = []
            
            if lib_entry not in "\n".join(lines):
                for line in lines:
                    new_lines.append(line)
                    if "<libraries>" in line:
                        new_lines.append(lib_entry)
                        changed = True
                lines = new_lines
                new_lines = []
            
            if eff_entry not in "\n".join(lines):
                for line in lines:
                    new_lines.append(line)
                    if "<effects>" in line:
                        new_lines.append(eff_entry)
                        changed = True
            else:
                new_lines = lines

            if changed:
                with open(file_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(new_lines) + "\n")
                return True
        except: pass
        return False

    def patch_audio_conf(file_path):
        if not os.path.isfile(file_path): return False
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            lib_entry = '  jdsp {\n    path /vendor/lib/soundfx/libjamesdsp.so\n  }'
            eff_entry = '  jamesdsp {\n    library jdsp\n    uuid f27317f4-c984-4de6-9a90-545759495bf2\n    type f98765f4-c321-5de6-9a45-123459495ab2\n  }'
            
            changed = False
            lines = content.splitlines()
            new_lines = []
            
            if "jdsp {" not in "\n".join(lines):
                for line in lines:
                    new_lines.append(line)
                    if "libraries {" in line and not line.strip().startswith("#"):
                        new_lines.append(lib_entry)
                        changed = True
                lines = new_lines
                new_lines = []
            
            if "jamesdsp {" not in "\n".join(lines):
                for line in lines:
                    new_lines.append(line)
                    if "effects {" in line and not line.strip().startswith("#"):
                        new_lines.append(eff_entry)
                        changed = True
            else:
                new_lines = lines

            if changed:
                with open(file_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(new_lines) + "\n")
                return True
        except: pass
        return False

    xml_files_to_patch = ["audio_effects.xml", "audio_effects_config.xml", "audio_effects_config_stub.xml"]

    # odm/etc recursive
    odm_etc_dir = os.path.join(rom_unpack_dir, "odm_unpacked", "odm", "etc")
    if os.path.isdir(odm_etc_dir):
        for root, dirs, files in os.walk(odm_etc_dir):
            for file in files:
                if file in xml_files_to_patch:
                    f_path = os.path.join(root, file)
                    if patch_audio_xml(f_path):
                        print(f"    [✓] Patched: {os.path.relpath(f_path, rom_unpack_dir)}")
                        patched += 1

    # system/system/etc recursive
    sys_etc_candidates = [
        os.path.join(rom_unpack_dir, "system_unpacked", "system", "system", "etc"),
        os.path.join(rom_unpack_dir, "system_unpacked", "system", "etc"),
        os.path.join(rom_unpack_dir, "system_a_unpacked", "system", "system", "etc"),
    ]
    for sys_etc_dir in sys_etc_candidates:
        if os.path.isdir(sys_etc_dir):
            for root, dirs, files in os.walk(sys_etc_dir):
                for file in files:
                    if file in xml_files_to_patch:
                        f_path = os.path.join(root, file)
                        if patch_audio_xml(f_path):
                            print(f"    [✓] Patched: {os.path.relpath(f_path, rom_unpack_dir)}")
                            patched += 1
            break # Chỉ xử lý đường dẫn đầu tiên tìm thấy tồn tại

    # vendor/etc/audio recursive
    vendor_audio_dir = os.path.join(rom_unpack_dir, "vendor_unpacked", "vendor", "etc", "audio")
    if os.path.isdir(vendor_audio_dir):
        for root, dirs, files in os.walk(vendor_audio_dir):
            for file in files:
                f_path = os.path.join(root, file)
                if file in xml_files_to_patch:
                    if patch_audio_xml(f_path):
                        print(f"    [✓] Patched: {os.path.relpath(f_path, rom_unpack_dir)}")
                        patched += 1
                elif file == "audio_effects.conf":
                    if patch_audio_conf(f_path):
                        print(f"    [✓] Patched: {os.path.relpath(f_path, rom_unpack_dir)}")
                        patched += 1

    print(f"\n[*] Region/Props patch xong: {patched} file đã chỉnh sửa.")
    return patched


def run_super_repack(version_dir, rom_repack_dir, device_db, product_name=None):
    """
    Step 10: Repack Super Image
    - Copy extra partitions from copy-image to rom-repack
    - Run super_tool.py to create super.img
    """
    if not device_db:
        print("[!] Không có thông tin database để repack super.")
        return False

    print_step(10, "Repack Super Image")

    # 1. Copy extra partitions from /copy-image
    copy_image_root = COPY_IMAGE_DIR
    extra_partitions = device_db.get("Partitions", [])
    missing_extra_partitions = []
    
    if extra_partitions:
        print(f"[*] Copying extra partitions: {extra_partitions}")
        for part in extra_partitions:
            filename = f"{part}.img"
            src = os.path.join(copy_image_root, filename)
            dst = os.path.join(rom_repack_dir, filename)
            
            if os.path.exists(src):
                method = link_or_copy_file(src, dst)
                print(f"  [✓] {method.title()} (Root)   : {filename}")
            else:
                # Fallback: Find in \copy-image\product_name
                print(f"  [-] Missing in root path, searching in product folder...")
                if product_name:
                    product_folder_src = os.path.join(copy_image_root, product_name, filename)
                    if os.path.exists(product_folder_src):
                        method = link_or_copy_file(product_folder_src, dst)
                        print(f"  [✓] {method.title()} (Product): {product_name}/{filename}")
                    else:
                        print(f"  [!] Missing (Fatal) : {product_folder_src}")
                        missing_extra_partitions.append(filename)
                else:
                    print(f"  [!] Missing (Fatal) : {src}")
                    missing_extra_partitions.append(filename)

    if missing_extra_partitions:
        print(f"[!] Missing required extra partitions: {', '.join(missing_extra_partitions)}")
        return False

    # 2. Build output path in /version_name/Build
    build_dir = os.path.join(version_dir, "Build")
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)
    
    output_super = os.path.join(build_dir, "super.img")

    # 3. Move static firmware partitions out of rom-repack so they are never
    #    packed into super.img. They belong in firmware-update/ of the final ZIP.
    firmware_update_dir = os.path.join(version_dir, "firmware-update")
    os.makedirs(firmware_update_dir, exist_ok=True)
    moved_firmware = []
    for f in os.listdir(rom_repack_dir):
        if not f.endswith('.img'):
            continue
        stem = f[:-4]
        if stem in STATIC_FIRMWARE_PARTITIONS:
            src = os.path.join(rom_repack_dir, f)
            dst = os.path.join(firmware_update_dir, f)
            if os.path.exists(src):
                moved_firmware.append(f)
                if os.path.exists(dst):
                    os.remove(dst)
                shutil.move(src, dst)
                print("  [>] Moved static firmware out of super: " + f + " -> firmware-update/")
    if moved_firmware:
        print("[*] Static firmware moved to firmware-update: " + ", ".join(moved_firmware))

    # 4. Collect remaining .img files in rom_repack_dir for super packing
    partition_files = [
        os.path.join(rom_repack_dir, f) 
        for f in os.listdir(rom_repack_dir) 
        if f.endswith('.img')
    ]

    if not partition_files:
        print("[!] Error: No .img files found in rom-repack.")
        return False

    super_tool_script = os.path.join(SCRIPT_DIR, "super_tool.py")
    
    # 4. Chạy super_tool.py
    cmd = [
        sys.executable, super_tool_script,
        output_super,
        "--super-size", str(device_db["SuperSize"]),
        "--group-size", str(device_db["GroupSize"]),
        "--sparse",
        "--ab",
        "--partitions"
    ] + partition_files
    
    print(f"[*] Chạy lệnh: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
        if result.returncode == 0:
            print(f"\n[✓] Repack super thành công: {output_super}")
            return True
        else:
            print(f"\n[!] super_tool.py thất bại (code={result.returncode})")
            return False
    except Exception as e:
        print(f"\n[!] Lỗi khi chạy super_tool.py: {e}")
        return False


def run_extra_patches(version_dir, source_rom_dir, rom_unpack_dir):
    """
    Step 11: Extra Patches (vbmeta)
    - Patch vbmeta.img using vbmate-patch.py
    """
    print_step(11, "Extra Patches (vbmeta)")
    
    build_dir = os.path.join(version_dir, "Build")
    if not os.path.exists(build_dir):
        os.makedirs(build_dir)

    # ─── 1. Patch vbmeta.img ──────────────────────────────────
    vbmeta_patch_script = os.path.join(SCRIPT_DIR, "vbmate-patch.py")
    vbmeta_names = ["vbmeta.img"]
    if not os.path.isfile(vbmeta_patch_script):
        print(f"[!] Missing patch script: {vbmeta_patch_script}")
        return False

    for name in vbmeta_names:
        source = os.path.join(source_rom_dir, name)
        if not os.path.isfile(source):
            print(f"[!] Missing source vbmeta image: {source}")
            return False
        print(f"[*] Patching {name}...")
        cmd = [sys.executable, vbmeta_patch_script, source]
        result = subprocess.run(cmd, cwd=version_dir, check=False)
        if result.returncode != 0:
            print(f"[!] vbmate-patch.py failed for {name} (code={result.returncode})")
            return False

    missing_outputs = [
        name for name in vbmeta_names
        if not os.path.isfile(os.path.join(build_dir, name))
    ]
    if missing_outputs:
        print(f"[!] Thiếu artifact sau khi patch: {', '.join(missing_outputs)}")
        return False
    return True


def generate_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_7z_path():
    """Tìm đường dẫn tới binary 7z.exe."""
    # 1. Kiểm tra trong bin của project
    candidates = [
        os.path.join(SCRIPT_DIR, "bin", "Windows", "AMD64", "7z.exe"),
        os.path.join(SCRIPT_DIR, "bin", "Windows", "x86", "7z.exe"),
        # 2. Các đường dẫn cài đặt mặc định trên Windows
        "C:\\Program Files\\7-Zip\\7z.exe",
        "C:\\Program Files (x86)\\7-Zip\\7z.exe"
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    
    # 3. Thử gọi trực tiếp từ PATH
    try:
        subprocess.run(["7z", "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "7z"
    except:
        return None


def run_final_repack(version_dir, version_name, source_rom_dir, device_db, build_edition=DEFAULT_BUILD_EDITION):
    """
    Step 12: Final ROM Repack & Zipping
    - Collect build artifacts into /ROM_build
    - Patch info.txt
    - Generate MD5 hashes
    - Create final .zip package
    """
    print_step(12, "Final ROM Repack & Zipping")
    
    rom_build_dir = os.path.join(version_dir, "ROM_build")
    firmware_update_dir = os.path.join(rom_build_dir, "firmware-update")
    image_dir = os.path.join(rom_build_dir, "images")
    flash_script_dir = os.path.join(SCRIPT_DIR, "Flash_script")
    build_dir = os.path.join(version_dir, "Build")

    # 1. Tạo thư mục
    os.makedirs(rom_build_dir, exist_ok=True)
    os.makedirs(firmware_update_dir, exist_ok=True)
    os.makedirs(image_dir, exist_ok=True)

    # 2. Copy files từ Flash_script
    items_to_copy = [
        "Wukong_Flashing_Tool_Windows.bat",
        "wukong_md5_hashes.txt",
        "bin",
        "firmware-update",
        "image",
        "META-INF",
        "info.txt",
        "Wukong_Flashing_Tool_Linux.sh",
        "Wukong_Flashing_Tool_MacOS.sh"
    ]
    
    print("[*] Moving flash scripts and tools...")
    for item in items_to_copy:
        src = os.path.join(flash_script_dir, item)
        # Đổi tên folder 'image' thành 'images' ở đích nếu cần
        target_name = "images" if item == "image" else item
        dst = os.path.join(rom_build_dir, target_name)
        
        if os.path.exists(src):
            if os.path.isdir(src):
                if os.path.exists(dst): shutil.rmtree(dst)
                shutil.copytree(src, dst) # Scripts nên giữ lại bản gốc
            else:
                shutil.copy2(src, dst)

    # 3. Cập nhật info.txt
    info_file = os.path.join(rom_build_dir, "info.txt")
    if os.path.exists(info_file):
        print("[*] Updating info.txt...")
        with open(info_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        while len(lines) < 5: lines.append("\n")
        
        lines[0] = device_db.get("name", "Unknown Device") + "\n"
        lines[1] = version_name + "\n"
        lines[3] = build_edition + "\n"
        lines[4] = ROM_STUDIO_VERSION + "\n"
        
        with open(info_file, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)

    with open(os.path.join(rom_build_dir, "expected_product.txt"), "w", encoding="utf-8") as f:
        f.write(device_db.get("product_name", "") + "\n")

    # 4. Copy firmware files từ source_rom (có loại trừ)
    exclude_firmware = [
        "vendor_dlkm.img", "my_bigball.img", "my_carrier.img", "my_engineering.img",
        "my_heytap.img", "my_manifest.img", "my_product.img", "my_region.img",
        "my_stock.img", "odm.img", "product.img", "system.img", "system_dlkm.img",
        "system_ext.img", "vendor.img", "recovery.img", "vbmeta.img",
        "vbmeta_system.img", "vbmeta_vendor.img", "vendor_boot.img", "boot.img",
        "dtbo.img", "init_boot.img", "modem.img"
    ]
    
    print("[*] Moving firmware-update files (Saving space)...")
    for f in os.listdir(source_rom_dir):
        if f not in exclude_firmware and os.path.isfile(os.path.join(source_rom_dir, f)):
            shutil.move(os.path.join(source_rom_dir, f), os.path.join(firmware_update_dir, f))

    # Static firmware (e.g. dsp, vm-bootsys) must never live in super.img; if the
    # repack step already moved them into firmware-update, keep them there.
    for f in os.listdir(firmware_update_dir):
        if not f.endswith(".img"):
            continue
        stem = f[:-4]
        if stem in STATIC_FIRMWARE_PARTITIONS:
            print(f"  [OK] Static firmware preserved in firmware-update: {f}")

    # 5. Move images
    print("[*] Moving core images to /images (Saving space)...")
    from_source = [
        "recovery.img", "vbmeta_system.img", "vbmeta_vendor.img", "boot.img",
        "dtbo.img", "init_boot.img", "modem.img", "vendor_boot.img"
    ]
    for img in from_source:
        src = os.path.join(source_rom_dir, img)
        if os.path.exists(src):
            shutil.move(src, os.path.join(image_dir, img))

    from_build = [
        "vbmeta.img", "super.img"
    ]
    for img in from_build:
        src = os.path.join(build_dir, img)
        if os.path.exists(src):
            shutil.move(src, os.path.join(image_dir, img))

    # 6. Copy TWRP (Keep source to reuse)
    soc = device_db.get("soc", "86xx")
    twrp_src = os.path.join(SCRIPT_DIR, "TWRP", f"TWRP-{soc}.img")
    ofx_src = os.path.join(SCRIPT_DIR, "OFX", f"OrangeFox-{soc}.img")

    if os.path.exists(twrp_src):
        print(f"[*] Linking TWRP for SOC {soc}...")
        link_or_copy_file(twrp_src, os.path.join(image_dir, "TWRP.img"))
    elif os.path.exists(ofx_src):
        print(f"[*] TWRP not found, linking OrangeFox for SOC {soc}...")
        link_or_copy_file(ofx_src, os.path.join(image_dir, "OrangeFox.img"))
    else:
        print(f"[!] Warning: No TWRP or OrangeFox found for SOC {soc} (Paths: TWRP-{soc}.img, OrangeFox-{soc}.img)")

    required_images = [
        "recovery.img", "vbmeta.img", "vbmeta_system.img", "vbmeta_vendor.img",
        "boot.img", "dtbo.img", "init_boot.img", "modem.img",
        "vendor_boot.img", "super.img",
    ]
    missing_images = [name for name in required_images if not os.path.isfile(os.path.join(image_dir, name))]
    if missing_images:
        raise RuntimeError(f"Cannot package ROM: missing required images: {', '.join(missing_images)}")

    # 7. Tạo mã MD5 cho wukong_md5_hashes.txt (Sắp xếp A-Z theo từng thư mục)
    print("[*] Generating MD5 hashes (Sorted A-Z by folder)...")
    hash_file = os.path.join(rom_build_dir, "wukong_md5_hashes.txt")
    
    with open(hash_file, "w", encoding="utf-8", newline="\n") as f_hash:
        for folder in ["images", "firmware-update"]:
            target_f = os.path.join(rom_build_dir, folder)
            if os.path.isdir(target_f):
                # Lấy danh sách file và sắp xếp A-Z
                files = [f for f in os.listdir(target_f) if os.path.isfile(os.path.join(target_f, f))]
                files.sort(key=lambda x: x.lower())
                
                for filename in files:
                    file_p = os.path.join(target_f, filename)
                    md5 = generate_md5(file_p)
                    f_hash.write(f"{md5}  {filename}\n")

    # 8. Nén thư mục ROM_build và xuất vào /ROM_BUILD_DONE
    zip_filename = output_zip_name(version_name, build_edition)
    rom_build_done_dir = ROM_BUILD_DONE_DIR
    os.makedirs(rom_build_done_dir, exist_ok=True)
    zip_path = os.path.join(rom_build_done_dir, zip_filename)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    seven_zip = get_7z_path()
    if seven_zip:
        print(f"[*] Creating final ROM zip using 7zip: {zip_filename}...")
        # Lệnh 7z: a (add), -tzip (định dạng zip), -mx5 (nén bình thường)
        cmd = [seven_zip, "a", "-tzip", "-mx5", zip_path, os.path.join(rom_build_dir, "*")]
        try:
            subprocess.run(cmd, check=True)
            print(f"\n[✓] 7zip compression completed.")
        except Exception as e:
            print(f"[!] 7zip failed: {e}. Falling back to zipfile...")
            seven_zip = None

    if not seven_zip:
        print(f"[*] Creating final ROM zip using zipfile: {zip_filename}...")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(rom_build_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, rom_build_dir)
                    zipf.write(full_p, rel_p)

    print(f"\n[✓] ALL DONE! Final ROM saved at: {zip_path}")

    # 9. Dọn dẹp ROM_build và thư mục phiên bản để tiết kiệm dung lượng
    if os.path.isdir(rom_build_dir):
        print(f"[*] Cleaning up ROM_build directory: {rom_build_dir}")
        try:
            shutil.rmtree(rom_build_dir)
            print("  [✓] ROM_build cleanup completed.")
        except Exception as e:
            print(f"  [!] ROM_build cleanup failed: {e}")

    print(f"[*] Cleaning up build directory: {version_dir}")
    try:
        shutil.rmtree(version_dir)
        print("  [✓] Cleanup completed.")
    except Exception as e:
        print(f"  [!] Cleanup failed: {e}")

    return zip_path


def main():
    print_banner()

    # ─── STEP 0: Nhập đường dẫn ROM ───────────────────────────
    rom_paths = []
    if len(sys.argv) > 1:
        # Chấp nhận nhiều đường dẫn từ đối số dòng lệnh
        rom_paths = sys.argv[1:]
    else:
        while True:
            print(f"\n[?] Nhập đường dẫn file ROM thứ {len(rom_paths) + 1} (.zip):")
            path_input = input(">> ").strip().strip('"').strip("'")
            
            if path_input:
                if os.path.isfile(path_input):
                    rom_paths.append(path_input)
                    print(f"  [✓] Đã thêm: {os.path.basename(path_input)}")
                else:
                    print(f"  [!] Lỗi: Không tìm thấy file '{path_input}'")
            
            if not rom_paths:
                print("  [!] Bạn phải nhập ít nhất một đường dẫn ROM để bắt đầu.")
                continue

            cont = input("\n[?] Bạn có muốn nhập thêm ROM khác không? (y/n, mặc định: n): ").strip().lower()
            if cont != 'y':
                break

    if not rom_paths:
        print("[!] Không có đường dẫn ROM nào được nhập.")
        sys.exit(1)

    # ─── Chọn MOD (Dùng chung cho tất cả ROM trong lượt build này) ────────
    print(f"\n{'─'*60}")
    print(f"  CHỌN MOD ĐỂ ÁP DỤNG CHO TẤT CẢ ROM")
    print(f"{'─'*60}")
    selected_mod = select_mod_folder()
    
    # --- Upfront Config Check & Batch Confirmation ---
    valid_roms_info = []
    print(f"\n[*] Đang kiểm tra cấu hình cho {len(rom_paths)} bản ROM...")
    
    editable_devices_path = DATA_ROOT / "devices_sizes.json"
    devices_json_path = str(
        editable_devices_path
        if DESKTOP_MODE and editable_devices_path.is_file()
        else SCRIPT_ROOT / "devices_sizes.json"
    )
    all_devices_data = []
    if os.path.exists(devices_json_path):
        with open(devices_json_path, "r", encoding="utf-8") as f:
            try:
                all_devices_data = json.load(f)
            except:
                print(f"[!] Lỗi đọc devices_sizes.json")

    for rp in rom_paths:
        print(f"\n[*] Analyzing: {os.path.basename(rp)}...")
        v_name, p_name = read_metadata_from_zip(rp)
        d_db = None
        if p_name:
            for db in all_devices_data:
                if db.get("product_name") == p_name:
                    d_db = db
                    break
        
        if not d_db:
            print(f"    - Product Name: {p_name or 'Trống'}")
            print(f"    - [!] Kết quả: Hãy bổ xung thêm config cho '{p_name}' vào devices_sizes.json.")
            print(f"    - Trạng thái: SKIP")
        else:
            valid_roms_info.append({
                "zip_path": os.path.abspath(rp),
                "version_name": v_name,
                "product_name": p_name,
                "device_db": d_db
            })

    if not valid_roms_info:
        print("\n[!] Không có bản ROM nào đủ điều kiện để build (thiếu config hoặc lỗi metadata). Kết thúc.")
        sys.exit(0)

    print(f"\n{'─'*60}")
    print(f"  DANH SÁCH ROM SẼ BUILD ({len(valid_roms_info)} bản):")
    for i, info in enumerate(valid_roms_info, 1):
        print(f"  {i}. {os.path.basename(info['zip_path'])} -> {info['device_db'].get('name')}")
    print(f"{'─'*60}")
    
    confirm_all = input("\n[?] Bạn có muốn bắt đầu build toàn bộ các bản ROM trên không? (y/n, mặc định: y): ").strip().lower()
    if confirm_all == "n":
        print("[*] Hủy bỏ build.")
        sys.exit(0)

    # Duyệt qua từng ROM đã xác nhận để build tuần tự
    session_start = time.time()
    for idx, info in enumerate(valid_roms_info, 1):
        zip_path = info["zip_path"]
        version_name = info["version_name"]
        product_name = info["product_name"]
        device_db = info["device_db"]

        rom_start = time.time()
        print(f"\n\n{'='*80}")
        print(f"  ĐANG XỬ LÝ ROM {idx}/{len(valid_roms_info)}: {os.path.basename(zip_path)}")
        print(f"{'='*80}")
        
        print(f"[*] File ROM   : {zip_path}")
        print(f"[*] Thiết bị   : {device_db.get('name')}")
        print(f"[*] Super Size : {device_db.get('SuperSize')}")

        if not version_name:
            print("[!] Không tìm thấy version_name trong metadata.")
            version_name = input(f"[?] Nhập tên phiên bản cho {os.path.basename(zip_path)}: ").strip()
            if not version_name:
                version_name = os.path.splitext(os.path.basename(zip_path))[0]
                print(f"[*] Sử dụng tên file làm tên phiên bản: {version_name}")
        version_name = sanitize_version_name(version_name)

        # Tạo thư mục phiên bản
        version_dir = os.path.join(SCRIPT_DIR, version_name)
        if not os.path.exists(version_dir):
            os.makedirs(version_dir)
            print(f"[✓] Đã tạo thư mục phiên bản: {version_dir}")
        else:
            print(f"[*] Thư mục phiên bản đã tồn tại: {version_dir}")

        # ─── STEP 2: Giải nén payload.bin → source_rom ────────────
        print_step(2, "Giải nén payload.bin → source_rom")
        source_rom_dir = os.path.join(version_dir, "source_rom")

        if os.path.exists(source_rom_dir) and os.listdir(source_rom_dir):
            print(f"[*] Thư mục '{source_rom_dir}' đã có dữ liệu.")
            choice = input("[?] Bỏ qua bước này? (y/n, mặc định: y): ").strip().lower()
            if choice != "n":
                print("[*] Bỏ qua giải nén payload.")
            else:
                shutil.rmtree(source_rom_dir, ignore_errors=True)
                if not run_payload_tool(zip_path, source_rom_dir):
                    print("[!] Giải nén payload thất bại.")
                    continue
        else:
            if not run_payload_tool(zip_path, source_rom_dir):
                print("[!] Giải nén payload thất bại.")
                continue

        # ─── STEP 3: Unpack partitions → rom-unpack ───────────────
        print_step(3, "Unpack partitions → rom-unpack")
        rom_unpack_dir = os.path.join(version_dir, "rom-unpack")

        if os.path.exists(rom_unpack_dir) and os.listdir(rom_unpack_dir):
            print(f"[*] Thư mục '{rom_unpack_dir}' đã có dữ liệu.")
            choice = input("[?] Bỏ qua bước này? (y/n, mặc định: y): ").strip().lower()
            if choice != "n":
                print("[*] Bỏ qua unpack partitions.")
            else:
                shutil.rmtree(rom_unpack_dir, ignore_errors=True)
                if not run_batch_unpack(source_rom_dir, rom_unpack_dir):
                    print("[!] Unpack partitions thất bại.")
                    continue
        else:
            if not run_batch_unpack(source_rom_dir, rom_unpack_dir):
                print("[!] Unpack partitions thất bại.")
                continue

        # ─── STEP 4: Xóa bloatware ─────────────────────────────────
        print_step(4, "Xóa bloatware")
        clean_bloatware(rom_unpack_dir)

        # ─── STEP 5: Áp dụng MOD ──────────────────────────────────
        if selected_mod:
            print_step(5, f"Áp dụng MOD: {os.path.basename(selected_mod)}")
            apply_mod(selected_mod, rom_unpack_dir, device_db)
        else:
            print_step(5, "Áp dụng MOD")
            print("[*] Bỏ qua — không có MOD nào được chọn.")
        patch_build_branding(rom_unpack_dir, DEFAULT_BUILD_EDITION)

        # ─── STEP 6: Đồng bộ config (fs_config + file_contexts) ───
        print_step(6, "Đồng bộ fs_config & file_contexts")
        if sync_all_configs(rom_unpack_dir) is False:
            print("[!] Đồng bộ fs_config & file_contexts thất bại. Dừng build để tránh tạo ROM lỗi.")
            continue

        # ─── STEP 7: Batch Repack ─────────────────────────────────
        print_step(7, "Repack partitions → .img")
        rom_repack_dir = os.path.join(version_dir, "rom-repack")

        if os.path.exists(rom_repack_dir) and os.listdir(rom_repack_dir):
            print(f"[*] Thư mục '{rom_repack_dir}' đã có dữ liệu.")
            choice = input("[?] Bỏ qua bước này? (y/n, mặc định: y): ").strip().lower()
            if choice != "n":
                print("[*] Bỏ qua repack partitions.")
            else:
                shutil.rmtree(rom_repack_dir, ignore_errors=True)
                if not run_batch_repack(rom_unpack_dir, rom_repack_dir, source_rom_dir):
                    print("[!] Repack partitions thất bại.")
                    continue
        else:
            if not run_batch_repack(rom_unpack_dir, rom_repack_dir, source_rom_dir):
                print("[!] Repack partitions thất bại.")
                continue

        # ─── STEP 8: Super Repack ─────────────────────────────────
        if device_db:
            if not run_super_repack(version_dir, rom_repack_dir, device_db, product_name=product_name):
                print("[!] Repack super.img thất bại.")
                continue
        else:
            print("\n[*] Bỏ qua STEP 8: Không tìm thấy database thiết bị phù hợp.")

        # ─── STEP 9: Extra Patches ────────────────────────────────
        if not run_extra_patches(version_dir, source_rom_dir, rom_unpack_dir):
            print("[!] Patch vbmeta thất bại.")
            continue

        # ─── STEP 10: Final Repack & Zip ──────────────────────────
        zip_final = run_final_repack(version_dir, version_name, source_rom_dir, device_db)

        # ─── KẾT QUẢ ──────────────────────────────────────────────
        rom_duration = time.time() - rom_start
        mod_display = os.path.basename(selected_mod) if selected_mod else "(không)"
        
        print(f"\n{'='*60}")
        print(f"  ✅  BUILD ROM HOÀN THÀNH!")
        print(f"{'='*60}")
        print(f"  📦  ROM version : {version_name}")
        print(f"  🎨  MOD applied : {mod_display}")
        print(f"  ⏱️  Thời gian    : {int(rom_duration // 60)} phút {int(rom_duration % 60)} giây")
        print(f"  📁  Kết quả tại : {zip_final}")
        print(f"{'='*60}\n")
        
        # 10. Thông báo hoàn thành build ROM qua Telegram
        uploader_script = os.path.join(SCRIPT_DIR, "Uploader.py")
        if os.path.exists(uploader_script):
            print(f"[*] Đang gửi thông báo kết quả qua Telegram: {os.path.basename(zip_final)}")
            subprocess.Popen([sys.executable, uploader_script, zip_final, str(rom_duration)], 
                             creationflags=subprocess.CREATE_NEW_CONSOLE)
        
        print(f"[✓] Đã xử lý xong ROM {idx}/{len(valid_roms_info)}.")

    total_duration = time.time() - session_start
    print(f"\n{'='*80}")
    print(f"  🎉 TẤT CẢ {len(valid_roms_info)} NHIỆM VỤ ĐÃ HOÀN THÀNH!")
    print(f"  ⏱️ Tổng thời gian: {int(total_duration // 60)} phút {int(total_duration % 60)} giây")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
