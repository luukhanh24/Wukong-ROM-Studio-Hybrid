import os
import sys
import subprocess
import platform
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.append(SCRIPT_DIR)

from studio_paths import TEMP_ROOT, platform_bin_dir

def run_command(cmd):
    """Utility to run shell commands and print output."""
    print(f"Executing: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    try:
        # Define TMP environment variable for lpmake on Windows
        env = os.environ.copy()
        if platform.system() == 'Windows':
            temp_dir = TEMP_ROOT / "lpmake"
            temp_dir.mkdir(parents=True, exist_ok=True)
            env['TMP'] = str(temp_dir)
            env['TEMP'] = str(temp_dir)

        result = subprocess.run(cmd, check=True, text=True, env=env)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        return e.returncode
    except FileNotFoundError:
        print(f"Error: Command not found. Make sure lpmake is in the 'bin' folder.")
        return 127

class SuperPacker:
    def __init__(self):
        self.bin_path = str(platform_bin_dir())
        self.bin_base = os.path.dirname(self.bin_path)

    def get_bin(self, name):
        ext = '.exe' if platform.system() == 'Windows' else ''
        return os.path.join(self.bin_path, name + ext)

    @staticmethod
    def validate_group_capacity(group_name, group_size, partition_files, is_ab=False):
        slot_a = []
        slot_b = []
        for part_path in partition_files:
            if not os.path.isfile(part_path):
                continue
            base_name = os.path.basename(part_path).rsplit('.', 1)[0]
            if base_name.endswith('_b'):
                continue
            clean_name = base_name[:-2] if base_name.endswith('_a') else base_name
            slot_a.append((clean_name, os.path.getsize(part_path)))
            if is_ab:
                b_img = os.path.join(os.path.dirname(part_path), f"{clean_name}_b.img")
                if os.path.isfile(b_img):
                    slot_b.append((clean_name, os.path.getsize(b_img)))
        for slot_name, partitions in [('a', slot_a), ('b', slot_b)]:
            total = sum(size for _name, size in partitions)
            if total > group_size:
                largest = ", ".join(
                    f"{name}={size}" for name, size in sorted(
                        partitions, key=lambda item: item[1], reverse=True
                    )[:5]
                )
                raise ValueError(
                    f"Dynamic group {group_name}_{slot_name} exceeds capacity: "
                    f"{total} > {group_size} bytes. Largest: {largest}"
                )
        return {
            "slotA": sum(size for _name, size in slot_a),
            "slotB": sum(size for _name, size in slot_b),
        }

    def unsparse_if_needed(self, part_path):
        """Ensure an image is raw before it is passed to lpmake."""
        try:
            # Check magic first to avoid unnecessary imports
            with open(part_path, 'rb') as f:
                magic = f.read(4)
                if magic != b'\x3a\xff\x26\xed':
                    return True
            
            # It is sparse, try to unsparse
            from src.core.lpunpack import SparseImage
            with open(part_path, 'rb') as f:
                s_img = SparseImage(f)
                if s_img.check():
                    print(f"[*] Sparse image detected: {os.path.basename(part_path)}. Converting to raw...")
                    unsparse_file = s_img.unsparse()
                    f.close() # Close before replacing
                    
                    # Replace sparse with raw
                    if os.path.exists(unsparse_file):
                        # Ensure we don't have permission issues on Windows
                        if os.path.exists(part_path):
                            os.remove(part_path)
                        os.rename(unsparse_file, part_path)
                        print(f"    [✓] Converted to raw: {os.path.basename(part_path)}")
                        return True
                print(f"    [!] Sparse validation failed: {os.path.basename(part_path)}")
        except Exception as e:
             print(f"    [!] Unsparse failed for {os.path.basename(part_path)}: {e}")
        return False

    def pack(self, output_img, super_size, group_name, group_size, partition_files, sparse=False, is_ab=False):
        """Construct and run lpmake command."""
        lpmake_bin = self.get_bin('lpmake')
        
        # Check and unsparse images before getting sizes
        for i in range(len(partition_files)):
            if os.path.exists(partition_files[i]):
                if not self.unsparse_if_needed(partition_files[i]):
                    print(f"[!] Refusing to build super with invalid sparse image: {partition_files[i]}")
                    return False

        try:
            capacity = self.validate_group_capacity(
                group_name,
                group_size,
                partition_files,
                is_ab=is_ab,
            )
        except ValueError as exc:
            print(f"[!] {exc}")
            return False
        print(
            f"[*] Dynamic group usage: slot_a={capacity['slotA']}/{group_size}, "
            f"slot_b={capacity['slotB']}/{group_size}"
        )
        
        # Normalize output path
        output_img = output_img.replace('\\', '/')
        
        # Base command
        metadata_slots = '3' if is_ab else '2'
        
        cmd = [
            lpmake_bin,
            '--metadata-size', '65536',
            '--super-name', 'super',
            '--metadata-slots', metadata_slots,
            '--device', f'super:{super_size}'
        ]
        
        if sparse:
            cmd.append('--sparse')

        if not is_ab:
            # A-Only logic
            cmd.extend(['--group', f'{group_name}:{group_size}'])
            for part_path in partition_files:
                if not os.path.exists(part_path): continue
                part_name = os.path.basename(part_path).rsplit('.', 1)[0]
                part_size = os.path.getsize(part_path)
                # Normalize path for lpmake
                norm_path = part_path.replace('\\', '/')
                cmd.extend(['--partition', f'{part_name}:readonly:{part_size}:{group_name}'])
                cmd.extend(['--image', f'{part_name}={norm_path}'])
        else:
            # A/B logic
            # Group A
            cmd.extend(['--group', f'{group_name}_a:{group_size}'])
            for part_path in partition_files:
                if not os.path.exists(part_path): continue
                # Handle cases where user provides 'system.img' or 'system_a.img'
                base_name = os.path.basename(part_path).rsplit('.', 1)[0]
                if base_name.endswith('_a'):
                    clean_name = base_name[:-2]
                elif base_name.endswith('_b'):
                    continue # Skip _b for now, we process by base name
                else:
                    clean_name = base_name

                part_size = os.path.getsize(part_path)
                # Normalize path for lpmake
                norm_path = part_path.replace('\\', '/')
                cmd.extend(['--partition', f'{clean_name}_a:readonly:{part_size}:{group_name}_a'])
                cmd.extend(['--image', f'{clean_name}_a={norm_path}'])

            # Group B
            cmd.extend(['--group', f'{group_name}_b:{group_size}'])
            for part_path in partition_files:
                if not os.path.exists(part_path): continue
                base_name = os.path.basename(part_path).rsplit('.', 1)[0]
                if base_name.endswith('_a'):
                    clean_name = base_name[:-2]
                elif base_name.endswith('_b'):
                    continue
                else:
                    clean_name = base_name
                
                # Check if a _b.img exists in the same directory
                parent_dir = os.path.dirname(part_path)
                b_img_path = os.path.join(parent_dir, f"{clean_name}_b.img")
                
                if os.path.exists(b_img_path):
                    b_size = os.path.getsize(b_img_path)
                    # Normalize path for lpmake
                    norm_path_b = b_img_path.replace('\\', '/')
                    cmd.extend(['--partition', f'{clean_name}_b:readonly:{b_size}:{group_name}_b'])
                    cmd.extend(['--image', f'{clean_name}_b={norm_path_b}'])
                else:
                    # Create empty placeholder for slot B
                    cmd.extend(['--partition', f'{clean_name}_b:readonly:0:{group_name}_b'])

        cmd.extend(['--out', output_img])
        
        print(f"[*] Repacking Super (A/B={is_ab}) | Group: {group_name}")
        if run_command(cmd) == 0:
            print(f"[*] SUCCESS: Super image created at {output_img}")
            return True
        else:
            print("[!] lpmake failed.")
            return False

def main():
    packer = SuperPacker()
    
    # Simple interactive input if no arguments provided
    if len(sys.argv) == 1:
        print("=== MIO-KITCHEN Super Repack Tool ===")
        output_img = input("Enter output super image path (e.g., super_new.img): ") or "super_new.img"
        super_size = input("Enter Super partition size (in bytes): ")
        group_name = "qti_dynamic_partitions"
        group_size = input(f"Enter Group size for '{group_name}' (in bytes): ")
        
        img_dir = input("Enter directory containing partition images (.img): ")
        if not os.path.isdir(img_dir):
            print("[!] Invalid directory.")
            return
            
        partition_files = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.endswith('.img')]
        print(f"[*] Found {len(partition_files)} partition(s): {[os.path.basename(f) for f in partition_files]}")
        
        sparse_in = input("Use sparse format? (y/n, default: n): ").lower()
        sparse = True if sparse_in == 'y' else False
        
        ab_in = input("Is this an A/B device? (y/n, default: y): ").lower()
        is_ab = False if ab_in == 'n' else True
        
        if not packer.pack(output_img, super_size, group_name, group_size, partition_files, sparse, is_ab):
            sys.exit(1)
    else:
        # CLI Argument usage
        parser = argparse.ArgumentParser(description="Repack partitions into super.img")
        parser.add_argument("output", help="Output super.img path")
        parser.add_argument("--super-size", required=True, type=int, help="Super size in bytes")
        parser.add_argument("--group-size", required=True, type=int, help="Group size in bytes")
        parser.add_argument("--partitions", nargs='+', required=True, help="List of .img files to include")
        parser.add_argument("--group-name", default="qti_dynamic_partitions", help="Dynamic group name (default: qti_dynamic_partitions)")
        parser.add_argument("--sparse", action="store_true", help="Output sparse image")
        parser.add_argument("--ab", action="store_true", help="Enable A/B partitioning (creates _a and _b slots)")
        
        args = parser.parse_args()
        if not packer.pack(args.output, args.super_size, args.group_name, args.group_size, args.partitions, args.sparse, args.ab):
            sys.exit(1)

if __name__ == "__main__":
    main()
