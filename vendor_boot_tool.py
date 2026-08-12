#!/usr/bin/env python3
"""
vendor_boot_tool.py - Vendor Boot Unpack/Repack Tool
Tham khảo cách làm của MIO Kitchen (src/tkui/tool.py: unpack_boot, repack_boot)
"""
import os
import subprocess
import platform
import shutil
import sys
import argparse
import struct
import logging

from studio_paths import platform_bin_dir

# ────────────────────────────────────────────────────────────────
# Hằng số: magic header để nhận dạng định dạng nén (giống MIO Kitchen utils.py)
# ────────────────────────────────────────────────────────────────
COMPRESSION_FORMATS = [
    (b'\x1f\x8b', "gzip"),
    (b'\x1f\x9e', "gzip"),
    (b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03', "zopfli"),
    (b'\x02\x21\x4c\x18', "lz4_legacy"),
    (b'\x03\x21\x4c\x18', 'lz4'),
    (b'\x04\x22\x4d\x18', 'lz4'),
    (b'\x02!L\x18', 'lz4_lg'),
    (b'\xfd7zXZ', 'lzma'),
    (b'\x5d\x00', 'lzma'),
    (b']\x00\x00\x00\x04\xff\xff\xff\xff\xff\xff\xff\xff', 'lzma'),
    (b'BZh', "bzip2"),
    (b'\x28\xb5\x2f\xfd', 'zstd'),
]


def gettype(file_path):
    """
    Nhận dạng loại file dựa trên magic bytes.
    Modelled after MIO Kitchen src/core/utils.py → gettype()
    """
    if not os.path.isfile(file_path):
        return "unknown"
    try:
        with open(file_path, 'rb') as f:
            header = f.read(16)  # Đọc đủ bytes cho phép so sánh
    except Exception:
        return "unknown"

    for magic, desc in COMPRESSION_FORMATS:
        if header[:len(magic)] == magic:
            return desc
    return "unknown"


class VendorBootTool:
    """
    Tool unpack/repack vendor_boot.img theo cách MIO Kitchen:
      - Dùng magiskboot để unpack/repack boot image
      - Dùng magiskboot decompress/compress cho ramdisk
      - Dùng cpio -i/-o để extract/tạo cpio archive
      - Hỗ trợ busybox nếu có (giống MIO Kitchen dùng busybox ash)
    """

    def __init__(self):
        self.system = platform.system()
        self.machine = platform.machine()
        self.script_dir = os.path.dirname(os.path.abspath(__file__))

        self.bin_path = str(platform_bin_dir())

        self.magiskboot = self._resolve_bin('magiskboot')
        self.cpio_tool = self._resolve_bin('cpio')
        self.busybox = self._resolve_bin('busybox')

    # ─── Helpers ───────────────────────────────────────────────

    def _resolve_bin(self, name):
        """Tìm binary trong bin path, fallback ra system PATH."""
        ext = '.exe' if self.system == 'Windows' else ''
        path = os.path.join(self.bin_path, name + ext)
        return path if os.path.isfile(path) else name

    def _call(self, cmd, cwd=None, capture=False):
        """
        Chạy lệnh, in output realtime (giống MIO Kitchen call()).
        Trả về returncode.
        """
        # Lọc bỏ phần tử rỗng trong cmd (giống MIO Kitchen: cmd = [i for i in cmd if i])
        cmd = [c for c in cmd if c]
        print(f"[*] CMD: {' '.join(cmd)}")

        conf = subprocess.CREATE_NO_WINDOW if self.system == 'Windows' else 0
        try:
            if capture:
                proc = subprocess.run(
                    cmd, cwd=cwd,
                    capture_output=True, text=True,
                    creationflags=conf
                )
                return proc
            else:
                proc = subprocess.Popen(
                    cmd, cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=conf
                )
                for line in iter(proc.stdout.readline, b""):
                    try:
                        text = line.decode("utf-8").strip()
                    except Exception:
                        text = line.decode("gbk", errors="replace").strip()
                    if text:
                        print(f"    {text}")
                proc.wait()
                return proc.returncode
        except FileNotFoundError:
            print(f"[!] Binary not found: {cmd[0]}")
            return 2
        except Exception as e:
            print(f"[!] Error running command: {e}")
            return 2

    # ─── UNPACK ────────────────────────────────────────────────

    def unpack(self, source_dir, unpack_root):
        """
        Unpack vendor_boot.img theo flow MIO Kitchen:
          1. magiskboot unpack -h vendor_boot.img
          2. Nhận dạng compression format của ramdisk.cpio → lưu vào file 'comp'
          3. Nếu có compression → decompress bằng magiskboot decompress
          4. Extract ramdisk content bằng cpio -i -d
        """
        source_img = os.path.abspath(os.path.join(source_dir, "vendor_boot.img"))
        if not os.path.isfile(source_img):
            print(f"[!] Error: {source_img} not found.")
            return False

        # Chuẩn bị thư mục unpack
        unpack_dir = os.path.join(unpack_root, "vendor_boot")
        if os.path.exists(unpack_dir):
            shutil.rmtree(unpack_dir)
        os.makedirs(unpack_dir)

        # ── Step 1: magiskboot unpack ──────────────────────────
        # MIO Kitchen: os.chdir(work + name) rồi call(['magiskboot', 'unpack', '-h', boot])
        # boot là đường dẫn tuyệt đối, không cần copy file
        print(f"[*] Step 1: Unpacking vendor_boot.img...")
        os.chdir(unpack_dir)
        ret = self._call([self.magiskboot, 'unpack', '-h', source_img], cwd=unpack_dir)
        os.chdir(self.script_dir)

        if ret != 0:
            print(f"[!] Unpack vendor_boot.img failed (code={ret})")
            shutil.rmtree(unpack_dir, ignore_errors=True)
            return False

        # Liệt kê file sau khi unpack
        generated = os.listdir(unpack_dir)
        print(f"[*] Generated files: {generated}")

        # ── Step 2: Xử lý ramdisk (detect + decompress) ───────
        # MIO Kitchen: comp = gettype(f"{work}/{name}/ramdisk.cpio")
        ramdisk_cpio = os.path.join(unpack_dir, "ramdisk.cpio")
        if not os.path.isfile(ramdisk_cpio):
            print(f"[!] ramdisk.cpio not found after unpack. Files: {generated}")
            return False

        comp = gettype(ramdisk_cpio)
        print(f"[*] Step 2: Ramdisk compression format: {comp}")

        # Lưu format vào file 'comp' (giống MIO Kitchen)
        comp_file = os.path.join(unpack_dir, "comp")
        with open(comp_file, "w", encoding="utf-8") as f:
            f.write(comp)

        if comp != "unknown":
            # MIO Kitchen flow:
            #   os.rename("ramdisk.cpio", "ramdisk.cpio.comp")
            #   call(["magiskboot", "decompress", "ramdisk.cpio.comp", "ramdisk.cpio"])
            ramdisk_comp = ramdisk_cpio + ".comp"
            os.rename(ramdisk_cpio, ramdisk_comp)

            print(f"[*] Decompressing ramdisk ({comp})...")
            ret = self._call(
                [self.magiskboot, 'decompress', ramdisk_comp, ramdisk_cpio],
                cwd=unpack_dir
            )
            if ret != 0:
                print("[!] Failed to decompress ramdisk.")
                # Khôi phục file gốc
                if os.path.exists(ramdisk_comp) and not os.path.exists(ramdisk_cpio):
                    os.rename(ramdisk_comp, ramdisk_cpio)
                return False
        else:
            print("[*] Ramdisk is raw/uncompressed.")

        # ── Step 3: Extract ramdisk content ────────────────────
        # MIO Kitchen: call(['cpio', '-i', '-d', '-F', 'ramdisk.cpio', '-D', 'ramdisk'])
        ramdisk_dir = os.path.join(unpack_dir, "ramdisk")
        if not os.path.exists(ramdisk_dir):
            os.makedirs(ramdisk_dir)

        print(f"[*] Step 3: Extracting ramdisk content...")
        os.chdir(unpack_dir)
        ret = self._call(
            [self.cpio_tool, '-i', '-d', '-F', 'ramdisk.cpio', '-D', 'ramdisk'],
            cwd=unpack_dir
        )
        os.chdir(self.script_dir)

        if ret != 0:
            print(f"[!] cpio extract returned code {ret}")
            return False

        # ── Kiểm tra kết quả ──────────────────────────────────
        final_files = os.listdir(unpack_dir)
        expected = ["header", "ramdisk.cpio", "ramdisk", "comp"]
        missing = [f for f in expected if f not in final_files]
        if missing:
            print(f"[!] Missing expected items: {missing}")
            return False

        print(f"[✓] SUCCESS: vendor_boot unpacked to {unpack_dir}")
        print(f"    Files: {final_files}")
        return True

    # ─── REPACK ────────────────────────────────────────────────

    def repack(self, unpack_root, build_dir, source_dir):
        """
        Repack vendor_boot.img theo flow MIO Kitchen:
          1. Tạo ramdisk-new.cpio từ thư mục ramdisk/ bằng cpio hoặc busybox
          2. Nén ramdisk nếu comp != unknown (magiskboot compress=<fmt>)
          3. Đổi tên thành ramdisk.cpio
          4. magiskboot repack vendor_boot.img
          5. Copy new-boot.img → Build/vendor_boot.img
        """
        unpack_dir = os.path.abspath(os.path.join(unpack_root, "vendor_boot"))
        if not os.path.isdir(unpack_dir):
            print(f"[!] Error: Unpack directory not found: {unpack_dir}")
            return False

        ramdisk_dir = os.path.join(unpack_dir, "ramdisk")
        comp_file = os.path.join(unpack_dir, "comp")

        # Tìm vendor_boot.img gốc từ source_dir (không copy vào unpack)
        # MIO Kitchen: boot = findfile(f"{name}.img", work)
        vendor_boot_img = os.path.abspath(os.path.join(source_dir, "vendor_boot.img"))
        if not os.path.isfile(vendor_boot_img):
            print(f"[!] Error: vendor_boot.img not found at {vendor_boot_img}")
            print(f"    (magiskboot repack cần file gốc)")
            return False

        # ── Step 1: Tạo ramdisk-new.cpio ──────────────────────
        if os.path.isdir(ramdisk_dir):
            print(f"[*] Step 1: Repacking ramdisk/ → ramdisk-new.cpio ...")
            os.chdir(unpack_dir)

            # MIO Kitchen dùng: busybox ash -c "find | sed 1d | cpio -H newc -R 0:0 -o -F ../ramdisk-new.cpio"
            cpio_out = os.path.abspath(os.path.join(unpack_dir, "ramdisk-new.cpio"))

            # Thử dùng busybox trước (giống MIO Kitchen)
            use_busybox = os.path.isfile(self.busybox)
            if use_busybox:
                # Trên Windows, busybox ash coi \ là ký tự escape, cần chuyển sang /
                cpio_rel = os.path.relpath(cpio_out, ramdisk_dir).replace("\\", "/")
                cpio_bin = self.cpio_tool.replace("\\", "/")
                shell_cmd = f'find | sed 1d | "{cpio_bin}" -H newc -R 0:0 -o -F {cpio_rel}'
                ret = self._call(
                    [self.busybox, 'ash', '-c', shell_cmd],
                    cwd=ramdisk_dir
                )
            else:
                # Fallback: dùng cpio trực tiếp
                # Tạo danh sách file
                file_list = []
                for root, dirs, files in os.walk(ramdisk_dir):
                    for d in dirs:
                        rel = os.path.relpath(os.path.join(root, d), ramdisk_dir)
                        file_list.append(rel.replace("\\", "/"))
                    for f in files:
                        rel = os.path.relpath(os.path.join(root, f), ramdisk_dir)
                        file_list.append(rel.replace("\\", "/"))
                file_list.sort()
                input_data = "\n".join(file_list) + "\n"

                ret = self._call(
                    [self.cpio_tool, '-o', '-H', 'newc', '-F', cpio_out],
                    cwd=ramdisk_dir
                )
                # Nếu cpio cần stdin, dùng subprocess trực tiếp
                if ret != 0 or not os.path.isfile(cpio_out) or os.path.getsize(cpio_out) == 0:
                    print("[*] Retrying cpio with stdin pipe...")
                    conf = subprocess.CREATE_NO_WINDOW if self.system == 'Windows' else 0
                    try:
                        proc = subprocess.run(
                            [self.cpio_tool, '-o', '-H', 'newc', '-F', cpio_out],
                            input=input_data, text=True,
                            cwd=ramdisk_dir, check=True,
                            creationflags=conf
                        )
                        ret = proc.returncode
                    except Exception as e:
                        print(f"[!] cpio pipe failed: {e}")
                        ret = 1

            os.chdir(self.script_dir)

            if ret != 0 or not os.path.isfile(cpio_out):
                print("[!] Failed to create ramdisk-new.cpio")
                return False

            # ── Step 2: Nén ramdisk nếu cần ───────────────────
            comp = "unknown"
            if os.path.isfile(comp_file):
                with open(comp_file, "r", encoding="utf-8") as f:
                    comp = f.read().strip()

            print(f"[*] Step 2: Compression format: {comp}")
            os.chdir(unpack_dir)

            if comp != "unknown":
                # MIO Kitchen: call(['magiskboot', f'compress={comp}', 'ramdisk-new.cpio'])
                print(f"[*] Compressing ramdisk-new.cpio with {comp}...")
                ret = self._call(
                    [self.magiskboot, f'compress={comp}', 'ramdisk-new.cpio'],
                    cwd=unpack_dir
                )
                if ret != 0:
                    print("[!] Failed to compress ramdisk, using uncompressed.")
                    # Xóa file nén lỗi nếu có
                    if os.path.isfile(os.path.join(unpack_dir, "ramdisk-new.cpio")):
                        pass  # Keep uncompressed version
                else:
                    # MIO Kitchen: xóa ramdisk.cpio cũ, đổi tên file nén
                    ramdisk_cpio = os.path.join(unpack_dir, "ramdisk.cpio")
                    if os.path.exists(ramdisk_cpio):
                        os.remove(ramdisk_cpio)

                    # Xác định extension của file nén
                    # MIO Kitchen: if comp == 'gzip': comp = 'gz'
                    # File sẽ được tạo với tên: ramdisk-new.cpio.<comp>
                    comp_ext = comp
                    if comp == 'gzip':
                        comp_ext = 'gz'
                    # magiskboot compress tạo file: ramdisk-new.cpio.<comp_base>
                    comp_base = comp_ext.split('_')[0]
                    compressed_name = f"ramdisk-new.cpio.{comp_base}"
                    compressed_path = os.path.join(unpack_dir, compressed_name)

                    if os.path.isfile(compressed_path):
                        os.rename(compressed_path, ramdisk_cpio)
                        # Xóa file cpio chưa nén
                        raw_cpio = os.path.join(unpack_dir, "ramdisk-new.cpio")
                        if os.path.isfile(raw_cpio):
                            os.remove(raw_cpio)
                        print(f"[✓] Compressed: {compressed_name} → ramdisk.cpio")
                    else:
                        # Thử tìm bất kỳ file nào khớp pattern
                        found = False
                        for f_name in os.listdir(unpack_dir):
                            if f_name.startswith("ramdisk-new.cpio.") and f_name != "ramdisk-new.cpio":
                                os.rename(
                                    os.path.join(unpack_dir, f_name),
                                    ramdisk_cpio
                                )
                                raw_cpio = os.path.join(unpack_dir, "ramdisk-new.cpio")
                                if os.path.isfile(raw_cpio):
                                    os.remove(raw_cpio)
                                print(f"[✓] Compressed: {f_name} → ramdisk.cpio")
                                found = True
                                break
                        if not found:
                            print("[!] Compressed file not found, using raw cpio.")
                            os.rename(cpio_out, ramdisk_cpio)
            else:
                # Format unknown → dùng raw cpio
                ramdisk_cpio = os.path.join(unpack_dir, "ramdisk.cpio")
                if os.path.exists(ramdisk_cpio):
                    os.remove(ramdisk_cpio)
                if os.path.isfile(os.path.join(unpack_dir, "ramdisk-new.cpio")):
                    os.rename(
                        os.path.join(unpack_dir, "ramdisk-new.cpio"),
                        ramdisk_cpio
                    )
                    print("[✓] Using uncompressed ramdisk.")
                else:
                    print("[!] ramdisk-new.cpio not found!")
                    return False

            os.chdir(self.script_dir)

        # ── Step 3: magiskboot repack ─────────────────────────
        # MIO Kitchen:
        #   flag = "-n" if comp == "unknown" else ""
        #   call(['magiskboot', 'repack', flag, boot])
        flag = "-n" if comp == "unknown" else ""
        print(f"[*] Step 3: Repacking vendor_boot image...")
        os.chdir(unpack_dir)
        ret = self._call(
            [self.magiskboot, 'repack', flag, vendor_boot_img],
            cwd=unpack_dir
        )
        os.chdir(self.script_dir)

        if ret != 0:
            print("[!] magiskboot repack failed!")
            return False

        # ── Step 4: Copy new-boot.img → Build ─────────────────
        # MIO Kitchen: os.rename(f"{source}/new-boot.img", output_path + "/{name}.img")
        new_img = os.path.join(unpack_dir, "new-boot.img")
        if not os.path.isfile(new_img):
            print("[!] Error: new-boot.img was not generated.")
            return False

        if not os.path.exists(build_dir):
            os.makedirs(build_dir)

        target_path = os.path.join(build_dir, "vendor_boot.img")
        shutil.copy2(new_img, target_path)
        print(f"[✓] SUCCESS: Repacked image saved to {target_path}")
        return True


# ─── MAIN ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Vendor Boot Unpack/Repack Tool (MIO Kitchen style)"
    )
    parser.add_argument(
        "action", choices=["unpack", "repack"],
        help="Action to perform"
    )
    parser.add_argument(
        "--source", default="source_rom",
        help="Source directory containing vendor_boot.img (default: source_rom)"
    )
    parser.add_argument(
        "--unpack", default="rom-unpack",
        help="Unpack output directory (default: rom-unpack)"
    )
    parser.add_argument(
        "--build", default="Build",
        help="Build output directory (default: Build)"
    )

    args = parser.parse_args()
    tool = VendorBootTool()

    if args.action == "unpack":
        success = tool.unpack(args.source, args.unpack)
    elif args.action == "repack":
        success = tool.repack(args.unpack, args.build, args.source)
    else:
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
