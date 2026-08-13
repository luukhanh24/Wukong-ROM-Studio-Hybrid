import sys
import hashlib
import os

# Thêm đường dẫn tới thư mục chứa avbtool để import
sys.path.append(r"C:\Android\Auto_Build_WK\platform_external_avb-master")
import avbtool

def get_vbmeta_blob_hash(image_filename):
    if not os.path.exists(image_filename):
        print(f"File not found: {image_filename}")
        return

    # Sử dụng module của avbtool để phân tích cấu trúc img
    image = avbtool.ImageHandler(image_filename, read_only=True)
    avb = avbtool.Avb()
    
    # Bóc cấu trúc Header
    (footer, header, descriptors, _) = avb._parse_image(image)
    
    offset = 0
    if footer:
        offset = footer.vbmeta_offset
        
    # Tính toán kích thước của riêng khối VBMeta Blob
    size = (header.SIZE + header.authentication_data_block_size +
            header.auxiliary_data_block_size)
            
    # Đọc chính xác byte-range của cấu trúc vbmeta này
    image.seek(offset)
    vbmeta_blob = image.read(size)

    # Băm mã băm SHA256
    hasher = hashlib.sha256()
    hasher.update(vbmeta_blob)
    blob_hash = hasher.hexdigest()
    
    print(f"Hashed Vbmeta Blob of {os.path.basename(image_filename)}:")
    print(blob_hash)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1].strip('\"').strip('\'')
    else:
        target = input("Enter path to vbmeta.img: ").strip('\"').strip('\'')
    get_vbmeta_blob_hash(target)
