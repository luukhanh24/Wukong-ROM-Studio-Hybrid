import os
import sys
import struct
import shutil


def patch_vbmeta(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found -> {file_path}")
        return False

    print(f"Checking {file_path}...")
    
    try:
        # Tạo thư mục Build nếu chưa có
        build_dir = "Build"
        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
            print(f"Created directory: {build_dir}")

        # Đọc nội dung file
        with open(file_path, "rb") as f:
            data = bytearray(f.read())

        # Check AVB Magic
        if data[0:4] != b'AVB0':
            print("Error: Not a valid AVB vbmeta image (Magic 'AVB0' not found).")
            return False

        # AVB VBMeta header flags are at offset 120 (0x78)
        # AVB uses Big-Endian (network byte order)
        old_flags = struct.unpack(">I", data[120:124])[0]
        
        # Bit 0: DISABLE_VERITY (0x01)
        # Bit 1: DISABLE_VERIFICATION (0x02)
        new_flags = old_flags | 0x03
        
        if old_flags == new_flags:
            print(f"VBMeta already has dm-verity and dm-verification disabled (Flags: 0x{old_flags:08x}).")
        else:
            # Ghi flag mới vào data buffer
            new_flags_raw = struct.pack(">I", new_flags)
            data[120:124] = new_flags_raw
            print(f"Patched successfully:")
            print(f"  Old Flags: 0x{old_flags:08x}")
            print(f"  New Flags: 0x{new_flags:08x}")

        # Xuất file ra thư mục Build
        output_name = os.path.basename(file_path)
        output_path = os.path.join(build_dir, output_name)
        
        with open(output_path, "wb") as f:
            f.write(data)
        
        print(f"Saved patched image to: {output_path}")
        print("dm-verity and dm-verification are now DISABLED in the output file.")
        return True

    except Exception as e:
        print(f"An error occurred: {e}")
        return False

if __name__ == "__main__":
    target_file = "vbmeta.img"
    
    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    
    if not os.path.exists(target_file):
        # Hãy thử tìm trong các thư mục phổ biến
        paths_to_check = [
            os.path.join("rom-unpack", "vbmeta.img"),
            os.path.join("rom-unpack", "config", "vbmeta.img"),
            os.path.join("source_rom", "vbmeta.img")
        ]
        for p in paths_to_check:
            if os.path.exists(p):
                target_file = p
                break

    raise SystemExit(0 if patch_vbmeta(target_file) else 1)
