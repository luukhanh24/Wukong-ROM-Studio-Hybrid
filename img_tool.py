import os
import sys
import subprocess
import platform
import logging
import argparse
import time
import shlex
import json

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(errors="replace")

# Resolve imports and binaries from the script/runtime layout, not the caller's cwd.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.append(SCRIPT_DIR)

from src.core.utils import gettype, simg2img, img2simg, formats
from src.core.imgextractor import Extractor
from src.core.lpunpack import unpack as lpunpack_func, SparseImage as LP_SparseImage
from studio_paths import platform_bin_dir

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_command(cmd, shell=False):
    """Utility to run shell commands and print output."""
    print(f"Executing: {' '.join(cmd) if isinstance(cmd, list) else cmd}", flush=True)
    try:
        process = subprocess.Popen(
            cmd,
            text=True,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            errors="replace",
        )
        if process.stdout:
            with process.stdout:
                for line in process.stdout:
                    print(line.rstrip(), flush=True)
        return_code = process.wait()
        if return_code != 0:
            print(f"Error executing command: exit code {return_code}", flush=True)
        return return_code
    except FileNotFoundError:
        print(f"Error: Command not found. Make sure the binaries in 'bin' are present.")
        return 127

class ImageTool:
    def __init__(self):
        self.bin_path = str(platform_bin_dir())
        self.bin_base = os.path.dirname(self.bin_path)

        if not os.path.exists(self.bin_path):
            print(f"Warning: Binary path {self.bin_path} does not exist.")

    def get_bin(self, name):
        """Get the absolute path to a binary in the project's bin folder."""
        ext = '.exe' if platform.system() == 'Windows' else ''
        return os.path.join(self.bin_path, name + ext)

    def detect_type(self, path):
        """Detect the image type using MIO-KITCHEN's utility."""
        return gettype(path)

    @staticmethod
    def _write_image_info(out_dir, name, filesystem, size_bytes):
        config_dir = os.path.join(out_dir, "config")
        os.makedirs(config_dir, exist_ok=True)
        path = os.path.join(config_dir, f"{name}_image_info.json")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {"filesystem": filesystem, "sizeBytes": int(size_bytes)},
                handle,
                indent=2,
            )
            handle.write("\n")

    @staticmethod
    def _read_image_info(config_dir, name):
        path = os.path.join(config_dir, f"{name}_image_info.json")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            return {}

    def unpack(self, img_path, out_dir):
        """Unpack various image types."""
        img_path = os.path.abspath(img_path)
        out_dir = os.path.abspath(out_dir)
        if not os.path.isfile(img_path):
            print(f"[!] Input image not found: {img_path}")
            return False
        
        img_type = self.detect_type(img_path)
        print(f"[*] Detected image type: {img_type}")

        if img_type == 'sparse':
            print("[*] Converting sparse image to raw...")
            # We use LP_SparseImage for convenience as it has an unsparse method
            with open(img_path, 'rb') as f:
                s_img = LP_SparseImage(f)
                if s_img.check():
                    raw_img = s_img.unsparse()
                    img_path = raw_img
                    img_type = self.detect_type(img_path)
                    print(f"[*] Converted to raw: {img_path}")
                else:
                    print("[!] Sparse check failed.")
                    return False

        if img_type == 'ext':
            print(f"[*] Extracting EXT4 image: {img_path}")
            extractor = Extractor()
            # The Extractor.main expects (target, output_dir, work, target_type)
            # work directory is used for config files
            extractor.main(img_path, out_dir, out_dir, target_type='img')
            self._write_image_info(
                out_dir,
                os.path.basename(img_path).rsplit('.', 1)[0],
                "ext4",
                os.path.getsize(img_path),
            )
            print(f"[*] Extraction complete. Files in: {out_dir}")
            return True
            
        elif img_type == 'erofs':
            print(f"[*] Extracting EROFS image: {img_path}")
            # MIO-KITCHEN uses: extract.erofs -i <img_src> -o <out_dir> -x
            # The -x flag extracts fs_config and file_contexts into config/
            extract_bin = self.get_bin('extract.erofs')
            
            if not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)
                
            # Point -o directly to out_dir. 
            # extract.erofs will create subfolders: {out_dir}/{img_name} and {out_dir}/config
            cmd = [extract_bin, '-i', img_path, '-o', out_dir, '-x', '-s']
            if run_command(cmd) == 0:
                # The actual extracted files are in out_dir/<img_name>
                img_name = os.path.basename(img_path).rsplit('.', 1)[0]
                self._write_image_info(out_dir, img_name, "erofs", os.path.getsize(img_path))
                # Note: extract.erofs might normalize the name (e.g., odm.img -> odm)
                print(f"[*] EROFS extraction complete.")
                print(f"[*] Files are in: {os.path.join(out_dir, img_name)}")
                print(f"[*] Configs are in: {os.path.join(out_dir, 'config')}")
                return True
            else:
                print("[!] EROFS extraction failed.")
                return False

        elif img_type == 'super':
            print(f"[*] Unpacking Super Image (LP): {img_path}")
            # lpunpack_func(file, out, parts=None)
            lpunpack_func(img_path, out_dir)
            print(f"[*] Super image unpacked to: {out_dir}")
            return True
            
        else:
            print(f"[!] Extraction for type '{img_type}' is not implemented in this script.")
            print("    Check 'src/core/' for specific handlers (e.g., rsceutil.py, payload_extract.py).")
            return False

    def repack_ext4(self, in_dir, out_img, size_mb=None):
        """Repack a directory into an EXT4 image using mke2fs and e2fsdroid."""
        in_dir = os.path.abspath(in_dir)
        out_img = os.path.abspath(out_img)
        name = os.path.basename(in_dir)
        
        # Look for config files generated during unpack
        # Structure: <out_dir>/config and <out_dir>/<partition>
        # in_dir is <out_dir>/<partition>
        out_dir = os.path.dirname(in_dir)
        config_dir = os.path.join(out_dir, "config")

        fs_config = os.path.join(config_dir, f"{name}_fs_config")
        file_contexts = os.path.join(config_dir, f"{name}_file_contexts")
        
        print(f"[*] Repacking {in_dir} to {out_img}...")
        
        if not os.path.exists(fs_config) or not os.path.exists(file_contexts):
            print(f"[!] Warning: Config files not found in {config_dir}")
            print(f"    Expected: {fs_config} and {file_contexts}")
            print("    Repack will proceed with dummy/default permissions which might break the system.")
            # We could generate dummies or exit. Let's try to proceed but warn.
        
        image_info = self._read_image_info(config_dir, name)
        source_size_bytes = int(image_info.get("sizeBytes") or 0)

        # Calculate size if no exact source size was recorded during unpack.
        if not size_mb and source_size_bytes <= 0:
            total_size = 0
            for root, dirs, files in os.walk(in_dir):
                for f in files:
                    total_size += os.path.getsize(os.path.join(root, f))
            # Heuristic: folder size + ~50MB buffer + 15% overhead (more safe for vendor)
            size_mb = int((total_size * 1.15) / (1024 * 1024)) + 50
            print(f"[*] Estimated size: {size_mb} MB")
        
        size_bytes = size_mb * 1024 * 1024 if size_mb else source_size_bytes
        blocks = (size_bytes + 4095) // 4096

        mke2fs_bin = self.get_bin('mke2fs')
        e2fsdroid_bin = self.get_bin('e2fsdroid')

        # 1. Create empty image
        print(f"[*] Phase 1: Creating empty ext4 image...")
        cmd_mk = [
            mke2fs_bin,
            '-O', '^has_journal,^metadata_csum,extent,huge_file,^flex_bg,^64bit,uninit_bg,dir_nlink,extra_isize',
            '-L', name,
            '-I', '256',
            '-M', f'/{name}',
            '-m', '0',
            '-t', 'ext4',
            '-b', '4096',
            out_img,
            str(blocks)
        ]
        if run_command(cmd_mk) != 0:
            print("[!] mke2fs failed.")
            return False

        # 2. Add files and permissions
        print(f"[*] Phase 2: Writing files and security contexts...")
        cmd_e2 = [e2fsdroid_bin, '-e']
        
        if os.path.exists(file_contexts):
            cmd_e2 += ['-S', file_contexts]
        if os.path.exists(fs_config):
            cmd_e2 += ['-C', fs_config]
            
        cmd_e2 += ['-a', f'/{name}', '-f', in_dir, out_img]
        
        if run_command(cmd_e2) != 0:
            print("[!] e2fsdroid failed.")
            return False
        else:
            print(f"[*] SUCCESS: Image created at {out_img}")
            return True

    def repack_erofs(self, in_dir, out_img, compress='lz4hc', level=9):
        """Repack a directory into an EROFS image using mkfs.erofs."""
        in_dir = os.path.normpath(os.path.abspath(in_dir))
        out_img = os.path.normpath(os.path.abspath(out_img))
        name = os.path.basename(in_dir)
        work = os.path.dirname(in_dir)
        
        # Look for config files
        config_dir = os.path.join(work, "config")
        fs_config = os.path.join(config_dir, f"{name}_fs_config")
        file_contexts = os.path.join(config_dir, f"{name}_file_contexts")
        fs_options = os.path.join(config_dir, f"{name}_fs_options")
        
        print(f"[*] Repacking {in_dir} to EROFS {out_img}...")
        
        mkfs_bin = self.get_bin('mkfs.erofs')
        
        # Build command based on mkerofs from src/tkui/tool.py
        # mkfs.erofs -z<compress>,<level> -T <UTC> --mount-point=/<name> 
        # --product-out=<work> --fs-config-file=<fs_config> --file-contexts=<file_contexts> 
        # <out_img> <in_dir>/
        
        profile = self._read_erofs_profile(fs_options)
        cmd = [mkfs_bin]
        if profile:
            cmd.extend(profile)
        else:
            cmd.extend([f'-z{compress},{level}', '-T', str(int(time.time()))])
        if '--quiet' not in cmd:
            cmd.append('--quiet')
        cmd.extend(['--mount-point', f'/{name}', '--product-out', work])
        
        if os.path.exists(fs_config):
            cmd.extend(['--fs-config-file', fs_config])
        if os.path.exists(file_contexts):
            cmd.extend(['--file-contexts', file_contexts])
            
        cmd.extend([out_img, in_dir + os.sep])
        
        if run_command(cmd) == 0:
            print(f"[*] SUCCESS: EROFS Image created at {out_img}")
            return True
        else:
            print("[!] mkfs.erofs failed.")
            return False

    @staticmethod
    def _read_erofs_profile(fs_options):
        """Reuse filesystem layout options emitted by extract.erofs."""
        if not os.path.isfile(fs_options):
            return []
        with open(fs_options, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
        options_line = next((line for line in lines if "mkfs.erofs options:" in line), "")
        if not options_line:
            return []
        tokens = shlex.split(options_line.split("mkfs.erofs options:", 1)[1].strip(), posix=False)
        profile = []
        options_with_value = {"-C", "-T", "-U", "-L"}
        value_prefixes = ("-b", "-m", "-x", "-z", "-E")
        long_prefixes = (
            "--async-queue-limit=",
            "--fsalignblks=",
            "--max-extent-bytes=",
            "--root-xattr-isize=",
            "--zD",
            "--ZI",
            "--zfeature-bits=",
        )
        standalone = {
            "--all-root",
            "--all-time",
            "--hard-dereference",
            "--ignore-mtime",
            "--mkfs-time",
            "--preserve-mtime",
        }
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token in options_with_value and index + 1 < len(tokens):
                profile.extend([token, tokens[index + 1]])
                index += 2
                continue
            if token.startswith(value_prefixes) or token.startswith(long_prefixes) or token in standalone:
                profile.append(token)
            index += 1
        return profile

def main():
    parser = argparse.ArgumentParser(description="Image Unpack/Repack Script (Powered by MIO-KITCHEN)")
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Unpack parser
    unpack_parser = subparsers.add_parser("unpack", help="Unpack an image")
    unpack_parser.add_argument("input", help="Path to the .img or super file")
    unpack_parser.add_argument("output", help="Directory to extract files into")

    # Repack parser
    repack_parser = subparsers.add_parser("repack", help="Repack a directory into an image")
    repack_parser.add_argument("input", help="Directory containing the files to repack")
    repack_parser.add_argument("output", help="Path for the new .img file")
    repack_parser.add_argument("--format", choices=['ext4', 'erofs'], default='ext4', help="Image format (default: ext4)")
    repack_parser.add_argument("--size", type=int, help="Fixed size in MB (for ext4 only)")
    repack_parser.add_argument("--compress", default='lz4hc', help="Compression for erofs (default: lz4hc)")
    repack_parser.add_argument("--level", type=int, default=9, help="Compression level for erofs (0-9, default: 9)")

    args = parser.parse_args()

    if not args.action:
        parser.print_help()
        return 1

    tool = ImageTool()
    
    if args.action == "unpack":
        return 0 if tool.unpack(args.input, args.output) else 1
    elif args.action == "repack":
        if args.format == 'erofs':
            return 0 if tool.repack_erofs(args.input, args.output, args.compress, args.level) else 1
        else:
            return 0 if tool.repack_ext4(args.input, args.output, args.size) else 1
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
