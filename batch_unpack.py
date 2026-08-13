import os
import shutil
import subprocess
import sys
import time

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
MUTABLE_PARTITIONS = [part for part in PARTITIONS if part not in PASSTHROUGH_PARTITIONS]

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
    
    success_count = 0
    fail_count = 0

    for part in MUTABLE_PARTITIONS:
        img_path = os.path.join(source_rom_dir, f"{part}.img")
        
        if os.path.exists(img_path):
            # Each partition gets its own subfolder to avoid config file conflicts
            # Example: rom-unpack/system_unpacked/
            out_subdir = os.path.join(target_unpack_dir, f"{part}_unpacked")
            if os.path.exists(out_subdir):
                shutil.rmtree(out_subdir)
            
            print(f"\n[>>>] Unpacking partition: {part}")
            
            # Call img_tool.py for each image
            cmd = [
                sys.executable, 
                os.path.join(SCRIPT_DIR, "img_tool.py"),
                "unpack", 
                img_path, 
                out_subdir
            ]
            
            try:
                result = subprocess.run(cmd, cwd=SCRIPT_DIR, check=False)
                if result.returncode == 0:
                    success_count += 1
                else:
                    print(f"[!] img_tool.py failed for {part}")
                    fail_count += 1
            except Exception as e:
                print(f"[!] Error running img_tool.py for {part}: {e}")
                fail_count += 1
        else:
            print(f"[-] Skip: {part}.img not found.")

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
