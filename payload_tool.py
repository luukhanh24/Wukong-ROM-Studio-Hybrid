import os
import sys
import zipfile
import argparse
import time

# Add the src directory to sys.path to allow imports from core
sys.path.append(os.getcwd())

from src.core.payload_extract import extract_partitions_from_payload

def main():
    parser = argparse.ArgumentParser(description="Extract payload.bin from ROM zip and unpack it")
    parser.add_argument("zip_path", help="Path to the ROM .zip file")
    parser.add_argument("-o", "--output", default="source_rom", help="Output directory (default: source_rom)")
    parser.add_argument("-t", "--threads", type=int, default=os.cpu_count() or 4, help="Number of threads for extraction")
    
    args = parser.parse_args()
    
    zip_path = os.path.abspath(args.zip_path)
    output_dir = os.path.abspath(args.output)
    
    if not os.path.exists(zip_path):
        print(f"[!] Error: File {zip_path} not found.")
        return 1

    print(f"[*] Extracting payload from {os.path.basename(zip_path)}...")
    start_time = time.time()
    
    try:
        with open(zip_path, "rb") as f:
            with zipfile.ZipFile(f, "r") as z:
                # Find payload.bin in the zip
                payload_file = None
                for name in z.namelist():
                    if name.endswith("payload.bin"):
                        payload_file = name
                        break
                
                if not payload_file:
                    print("[!] Error: payload.bin not found in the zip file.")
                    return 1
                
                print(f"[*] Found payload: {payload_file}")
                
                # Use the core extraction logic directly from the zip handle
                with z.open(payload_file, "r") as zf:
                    print(f"[*] Unpacking partitions to '{args.output}'...")
                    extract_partitions_from_payload(
                        zf,
                        partitions_name=[], # Empty means extract all
                        out_dir=output_dir,
                        max_workers=args.threads
                    )
                    
        end_time = time.time()
        print(f"[*] SUCCESS: All partitions unpacked to {output_dir}")
        print(f"[*] Time taken: {end_time - start_time:.2f} seconds.")
        return 0
        
    except Exception as e:
        print(f"[!] An error occurred: {e}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
