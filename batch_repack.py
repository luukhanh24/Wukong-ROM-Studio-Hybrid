import os
import subprocess
import sys
import argparse
import time
import re
import json
from partition_config import (
    sync_partition_configs as safe_sync_partition_configs,
    validate_repacked_partition,
)
from studio_paths import platform_bin_dir
from wukong.catalog import MODIFIABLE_PARTITIONS

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(line_buffering=True, errors="replace")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MUTABLE_PARTITIONS = set(MODIFIABLE_PARTITIONS)

# Ký tự cần escape trong file_contexts (regex format)
FC_SPECIAL_CHARS = re.compile(r'([.+\[\](){}^$|?*])')

def fc_escape(path):
    """Escape các ký tự đặc biệt regex trong đường dẫn file_contexts."""
    return FC_SPECIAL_CHARS.sub(r'\\\1', path)

def fc_unescape(path):
    """Unescape đường dẫn file_contexts về dạng bình thường."""
    return re.sub(r'\\(.)', r'\1', path)


def find_version_unpack_dir():
    """Tự tìm thư mục rom-unpack có dữ liệu _unpacked."""
    default = os.path.join(SCRIPT_DIR, "rom-unpack")
    if os.path.isdir(default):
        if any(d.endswith("_unpacked") for d in os.listdir(default)): return default
    for item in sorted(os.listdir(SCRIPT_DIR), reverse=True):
        candidate = os.path.join(SCRIPT_DIR, item, "rom-unpack")
        if os.path.isdir(candidate):
            if any(d.endswith("_unpacked") for d in os.listdir(candidate)): return candidate
    return default


def _legacy_sync_configs(unpacked_dir, part_name):
    """
    Đồng bộ _fs_config và _file_contexts với filesystem thực tế.
    - Sửa lỗi repack system.img do sai lệch đường dẫn và quyền hạn.
    """
    config_dir = os.path.join(unpacked_dir, "config")
    data_dir = os.path.join(unpacked_dir, part_name)

    if not os.path.isdir(data_dir):
        possible = [d for d in os.listdir(unpacked_dir) if os.path.isdir(os.path.join(unpacked_dir, d)) and d not in ["config", "work"]]
        if possible: data_dir = os.path.join(unpacked_dir, possible[0])
        else: return []

    fs_config_file = os.path.join(config_dir, f"{part_name}_fs_config")
    file_contexts_file = os.path.join(config_dir, f"{part_name}_file_contexts")
    if not os.path.isfile(fs_config_file) or not os.path.isfile(file_contexts_file): return []

    # --- 1. Detect Defaults ---
    default_uid, default_gid, default_ctx = "0", "0", "u:object_r:system_file:s0"
    
    # Phân vùng vendor thường dùng các UID/GID khác
    is_vendor_related = any(x in part_name.lower() for x in ["vendor", "odm", "product", "my_"])
    if is_vendor_related:
        default_ctx = "u:object_r:vendor_file:s0"
        if "vendor" in part_name.lower() or "odm" in part_name.lower():
            default_gid = "2000" # shell/vendor group
    
    # Thử lấy default từ sytem/build.prop hoặc các file có sẵn
    if os.path.exists(fs_config_file):
        with open(fs_config_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and (parts[0] == "/" or parts[0] == f"{part_name}/"):
                    default_uid, default_gid = parts[1], parts[2]
                    break
    if os.path.exists(file_contexts_file):
        with open(file_contexts_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and (parts[0] == "/" or parts[0] == f"/{part_name}(/.*)?"):
                    default_ctx = parts[1]
                    break

    # --- 2. Scan Filesystem & Fix Spaces ---
    actual_data = {}
    for root, dirs, files in os.walk(data_dir):
        for name in files + dirs:
            if ' ' in name:
                old_p = os.path.join(root, name)
                new_n = name.replace(' ', '_')
                new_p = os.path.join(root, new_n)
                if not os.path.exists(new_p):
                    os.rename(old_p, new_p)
                    print(f"    [sync] Fix space: {name} -> {new_n}")

        rel = os.path.relpath(root, os.path.dirname(data_dir)).replace("\\", "/").rstrip("/")
        actual_data[rel] = {'type': 'dir'}
        for f in files:
            cl_f = f.replace(' ', '_')
            p = (rel + "/" + cl_f).replace("//", "/")
            full_p = os.path.join(root, cl_f)
            if os.path.islink(full_p):
                try: actual_data[p] = {'type': 'link', 'target': os.readlink(full_p).replace("\\", "/")}
                except: pass
            else: actual_data[p] = {'type': 'file'}
        for d in dirs:
            cl_d = d.replace(' ', '_')
            p = (rel + "/" + cl_d).replace("//", "/")
            full_p = os.path.join(root, cl_d)
            if os.path.islink(full_p):
                try: actual_data[p] = {'type': 'link', 'target': os.readlink(full_p).replace("\\", "/")}
                except: pass

    # --- 3. Sync fs_config ---
    with open(fs_config_file, "r", encoding="utf-8") as f:
        fs_existing = {l.split()[0].rstrip("/"): l.strip() for l in f if l.strip() and l.split()}
    
    new_fs = {}
    new_fs["/"] = fs_existing.get("/", f"/ {default_uid} {default_gid} 0755")
    
    added_fs = 0
    for path in sorted(actual_data.keys()):
        if path == "": continue
        p_cl = path.rstrip("/")
        if p_cl in fs_existing:
            new_fs[p_cl] = fs_existing[p_cl]
        else:
            info = actual_data[path]
            if info['type'] == 'dir':
                new_fs[p_cl] = f"{path}/ {default_uid} {default_gid} 0755"
            elif info['type'] == 'link':
                new_fs[p_cl] = f"{path} {default_uid} {default_gid} 0644 {info['target']}"
            else:
                exec_list = ["bin/", "xbin/", "sbin/"]
                perm = "0755" if any(x in path for x in exec_list) or path.endswith(".sh") else "0644"
                new_fs[p_cl] = f"{path} {default_uid} {default_gid} {perm}"
            added_fs += 1

    with open(fs_config_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_fs.pop("/") + "\n")
        for p in sorted(new_fs): f.write(new_fs[p] + "\n")

    # --- 4. Update file_contexts ---
    with open(file_contexts_file, "r", encoding="utf-8") as f:
        fc_existing = {l.split(None, 1)[0]: l.split(None, 1)[1].strip() for l in f if l.strip() and len(l.split(None, 1))>=2}
    
    added_fc = 0
    added_fc_entries = []
    for path in sorted(actual_data.keys()):
        fc_p = "/" + path
        esc_p = fc_escape(fc_p)
        
        # Nếu đã có regex khớp với file này thì không thêm nữa
        found = False
        if esc_p in fc_existing or fc_p in fc_existing:
            found = True
        else:
            # Check simple regex
            for pattern in fc_existing:
                if pattern.endswith("(/.*)?"):
                    base = pattern[:-6]
                    if fc_p.startswith(base):
                        found = True
                        break
        
        if not found:
            # Thuật toán kế thừa context
            parent_dir = esc_p.rsplit("/", 1)[0]
            current_ctx = None
            
            # 1. Thử tìm các file cùng thư mục để lấy context tương ứng
            for existing_p, ctx in fc_existing.items():
                if existing_p.startswith(parent_dir + "/"):
                    current_ctx = ctx
                    break
            
            # 2. Nếu không có, lấy context của chính thư mục cha
            if not current_ctx:
                current_ctx = fc_existing.get(parent_dir)
            
            # 3. Nếu vẫn không có, sử dụng default dựa trên tên file/đường dẫn
            if not current_ctx:
                current_ctx = default_ctx
                if "/bin/" in fc_p: 
                    current_ctx = "u:object_r:vendor_file:s0" if is_vendor_related else "u:object_r:system_file:s0"
                elif "/etc/init" in fc_p:
                    current_ctx = "u:object_r:vendor_configs_file:s0" if is_vendor_related else "u:object_r:system_file:s0"
            
            fc_existing[esc_p] = current_ctx
            added_fc += 1
            added_fc_entries.append(f"{esc_p} {current_ctx}")

    with open(file_contexts_file, "w", encoding="utf-8", newline="\n") as f:
        # Ghi dòng gốc đầu tiên
        if "/" in fc_existing:
            f.write(f"/ {fc_existing.pop('/')}\n")
        
        # Ghi các dòng còn lại (đã sắp xếp)
        for p in sorted(fc_existing):
            f.write(f"{p} {fc_existing[p]}\n")

    if added_fs or added_fc:
        print(f"    [OK] {part_name}: Synced config (+{added_fs + added_fc} items)")
    
    return added_fc_entries


def sync_configs(unpacked_dir, part_name):
    """Append metadata for new files without rewriting extracted SELinux rules."""
    report = safe_sync_partition_configs(unpacked_dir, part_name)
    return report["addedFileContextEntries"]


def _extract_erofs_binary():
    suffix = ".exe" if os.name == "nt" else ""
    return str(platform_bin_dir() / f"extract.erofs{suffix}")


def _partition_filesystem(unpacked_dir, part_name, requested_format):
    if requested_format != "auto":
        return requested_format
    info_path = os.path.join(unpacked_dir, "config", f"{part_name}_image_info.json")
    try:
        with open(info_path, "r", encoding="utf-8") as handle:
            filesystem = str(json.load(handle).get("filesystem") or "").lower()
    except (OSError, ValueError, AttributeError):
        filesystem = ""
    return filesystem if filesystem in {"erofs", "ext4"} else "erofs"


def batch_repack(
    unpack_dir,
    repack_dir,
    img_format="erofs",
    sync_metadata=True,
    validate_output=True,
    partitions=None,
):
    unpack_dir = os.path.abspath(unpack_dir)
    repack_dir = os.path.abspath(repack_dir)
    if not os.path.exists(unpack_dir):
        print(f"[!] Error: Unpack directory does not exist: {unpack_dir}")
        return False
    if not os.path.exists(repack_dir): os.makedirs(repack_dir)

    selected_partitions = set(partitions) if partitions is not None else None
    if selected_partitions is not None and not selected_partitions.issubset(MUTABLE_PARTITIONS):
        unsupported = ", ".join(sorted(selected_partitions.difference(MUTABLE_PARTITIONS)))
        raise ValueError(f"Protected or unsupported partitions cannot be repacked: {unsupported}")
    print(f"[*] Starting batch repack to '{repack_dir}'...")
    if selected_partitions is not None:
        print(f"[*] Selected partitions: {', '.join(sorted(selected_partitions))}")
    success_count = 0
    fail_count = 0
    failed_partitions = []

    for item in os.listdir(unpack_dir):
        item_path = os.path.join(unpack_dir, item)
        if os.path.isdir(item_path) and item.endswith("_unpacked"):
            part_name = item.replace("_unpacked", "")
            if part_name not in MUTABLE_PARTITIONS:
                print(f"[-] Skip protected or passthrough partition: {part_name}")
                continue
            if selected_partitions is not None and part_name not in selected_partitions:
                print(f"[-] Reuse existing repack: {part_name}")
                continue
            data_dir = os.path.join(item_path, part_name)
            if not os.path.exists(data_dir):
                subdirs = [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d)) and d not in ["config", "work"]]
                if subdirs: data_dir = os.path.join(item_path, subdirs[0])
                else: continue

            output_img = os.path.join(repack_dir, f"{part_name}.img")
            partition_format = _partition_filesystem(item_path, part_name, img_format)
            
            print(f"\n[>>>] Repacking partition: {part_name}", flush=True)
            cmd = [
                sys.executable,
                "-u",
                os.path.join(SCRIPT_DIR, "img_tool.py"),
                "repack",
                data_dir,
                output_img,
                "--format",
                partition_format,
            ]
            
            try:
                added_fcs = sync_configs(item_path, part_name) if sync_metadata else []
                result = subprocess.run(cmd, cwd=SCRIPT_DIR)
                if result.returncode == 0:
                    if validate_output:
                        validation = validate_repacked_partition(
                            item_path,
                            part_name,
                            output_img,
                            partition_format,
                            extract_erofs=_extract_erofs_binary(),
                        )
                        print(
                            f"    [OK] Validation: {validation.get('audit', 'full')} "
                            f"({validation.get('paths', 0)} paths)",
                            flush=True,
                        )
                    success_count += 1
                    if added_fcs:
                        print(f"    [+] Added file_contexts for {part_name}:")
                        for entry in added_fcs:
                            print(f"        {entry}")
                else:
                    fail_count += 1
                    failed_partitions.append(f"{part_name} (exit {result.returncode})")
                    print(f"[!] Repack command failed for {part_name}: exit code {result.returncode}", flush=True)
                    print(f"    Command: {' '.join(cmd)}", flush=True)
            except Exception as exc:
                print(f"[!] Repack failed for {part_name}: {exc}")
                fail_count += 1
                failed_partitions.append(f"{part_name} ({type(exc).__name__}: {exc})")

    print(f"\n[*] Finished! Success: {success_count}, Failed: {fail_count}")
    if failed_partitions:
        print("[!] Failed partitions:")
        for part in failed_partitions:
            print(f"    - {part}")
    return success_count > 0 and fail_count == 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("unpack_dir", nargs='?')
    parser.add_argument("repack_dir", nargs='?')
    parser.add_argument("--format", choices=['auto', 'ext4', 'erofs'], default='auto')
    parser.add_argument("--skip-sync", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    parser.add_argument("--partitions", nargs="+", help="Only repack the selected partitions")
    args = parser.parse_args()
    unpack = args.unpack_dir if args.unpack_dir else find_version_unpack_dir()
    repack = args.repack_dir if args.repack_dir else os.path.join(os.path.dirname(unpack), "rom-repack")
    raise SystemExit(
        0
        if batch_repack(
            unpack,
            repack,
            args.format,
            not args.skip_sync,
            not args.skip_validation,
            args.partitions,
        )
        else 1
    )
