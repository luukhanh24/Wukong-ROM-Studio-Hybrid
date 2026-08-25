import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from wukong.catalog import MODIFIABLE_PARTITIONS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# List of partitions to unpack as requested
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
    "vendor_dlkm"
]
MUTABLE_PARTITIONS = [part for part in PARTITIONS if part in MODIFIABLE_PARTITIONS]


def _partition_workers(task_count):
    configured = os.environ.get("WUKONG_PARTITION_WORKERS", "").strip()
    if configured:
        try:
            return max(1, min(int(configured), task_count))
        except ValueError:
            print(f"[!] Invalid WUKONG_PARTITION_WORKERS={configured!r}; using automatic value.")
    return max(1, min(2, os.cpu_count() or 1, task_count))


def batch_unpack(source_rom_dir, target_unpack_dir):
    source_rom_dir = os.path.abspath(source_rom_dir)
    target_unpack_dir = os.path.abspath(target_unpack_dir)
    
    if not os.path.exists(source_rom_dir):
        print(f"[!] Error: Source directory '{source_rom_dir}' does not exist.")
        return False

    if not os.path.exists(target_unpack_dir):
        os.makedirs(target_unpack_dir)

    print(f"[*] Starting batch unpack from '{source_rom_dir}' to '{target_unpack_dir}'...")
    start_time = time.time()
    
    tasks = []
    for part in MUTABLE_PARTITIONS:
        img_path = os.path.join(source_rom_dir, f"{part}.img")
        
        if os.path.exists(img_path):
            # Each partition gets its own subfolder to avoid config file conflicts
            # Example: rom-unpack/system_unpacked/
            out_subdir = os.path.join(target_unpack_dir, f"{part}_unpacked")
            if os.path.exists(out_subdir):
                shutil.rmtree(out_subdir)
            
            tasks.append((part, img_path, out_subdir))
        else:
            print(f"[-] Skip: {part}.img not found.")

    def unpack_one(task):
        part, img_path, out_subdir = task
        started = time.perf_counter()
        print(f"\n[>>>] Unpacking partition: {part}", flush=True)
        cmd = [
            sys.executable,
            os.path.join(SCRIPT_DIR, "img_tool.py"),
            "unpack",
            img_path,
            out_subdir,
        ]
        try:
            result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
            return part, result.returncode == 0, time.perf_counter() - started, None
        except Exception as exc:
            return part, False, time.perf_counter() - started, exc

    success_count = 0
    fail_count = 0
    workers = _partition_workers(len(tasks)) if tasks else 1
    print(f"[*] Partition workers: {workers} (override: WUKONG_PARTITION_WORKERS)", flush=True)
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="wukong-unpack") as pool:
        futures = [pool.submit(unpack_one, task) for task in tasks]
        for future in as_completed(futures):
            part, success, elapsed, error = future.result()
            if success:
                success_count += 1
                print(f"    [OK] {part}: {elapsed:.1f}s", flush=True)
            else:
                fail_count += 1
                detail = f": {error}" if error else ""
                print(f"[!] img_tool.py failed for {part}{detail} ({elapsed:.1f}s)", flush=True)

    end_time = time.time()
    print(f"\n{'='*50}")
    print(f"[*] Batch Unpack Finished!")
    print(f"[*] Success: {success_count}")
    print(f"[*] Failed: {fail_count}")
    print(f"[*] Total time: {end_time - start_time:.2f} seconds.")
    print(f"{'='*50}")
    return success_count > 0 and fail_count == 0

if __name__ == "__main__":
    # Check if paths are provided in CLI, otherwise use defaults
    src = sys.argv[1] if len(sys.argv) > 1 else "source-rom"
    dst = sys.argv[2] if len(sys.argv) > 2 else "rom-unpack"
    
    raise SystemExit(0 if batch_unpack(src, dst) else 1)
