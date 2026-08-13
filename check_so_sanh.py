import os
from pathlib import Path
from datetime import datetime
from difflib import SequenceMatcher, unified_diff

# ==========================
# 🧩 CẤU HÌNH — SỬA 3 DÒNG NÀY
# ==========================
DIR_A = r"C:\Users\KHANHSTARK\Downloads\Telegram Desktop\adb\ainur_jamesdsp\system\system_mod2"
DIR_B = r"C:\Users\KHANHSTARK\Downloads\Telegram Desktop\adb\ainur_jamesdsp\system\system"
LOG_PATH = r"C:\Android\App_mod\systemui_check\check_file\check_file11.txt"
# ==========================


def read_text_lines(p: Path):
    try:
        chunk = p.read_bytes()[:4096]
        if b"\x00" in chunk:
            return None
        return p.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None


def collect_paths(dir_a: Path, dir_b: Path):
    files_a = {f.relative_to(dir_a).as_posix(): f for f in dir_a.rglob("*") if f.is_file()}
    files_b = {f.relative_to(dir_b).as_posix(): f for f in dir_b.rglob("*") if f.is_file()}
    only_a = sorted(set(files_a) - set(files_b))
    only_b = sorted(set(files_b) - set(files_a))
    common = sorted(set(files_a) & set(files_b))
    return files_a, files_b, only_a, only_b, common


def diff_added_removed(lines_a, lines_b):
    sm = SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    removed, added = [], []
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag in ("delete", "replace"):
            for i in range(a0, a1):
                removed.append((i + 1, lines_a[i]))
        if tag in ("insert", "replace"):
            for j in range(b0, b1):
                added.append((j + 1, lines_b[j]))
    return removed, added


def compare_directories(dir_a: Path, dir_b: Path, log_path: Path):
    files_a, files_b, only_a, only_b, common = collect_paths(dir_a, dir_b)

    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"=== SO SÁNH NỘI DUNG ===\nA = {dir_a}\nB = {dir_b}\n")
        log.write(f"Thời gian: {datetime.now()}\n\n")

        for rel in only_a:
            log.write(f"[−] {rel} chỉ có trong A\n")
        for rel in only_b:
            log.write(f"[+] {rel} chỉ có trong B\n")

        for rel in common:
            pa = files_a[rel]
            pb = files_b[rel]
            lines_a = read_text_lines(pa)
            lines_b = read_text_lines(pb)

            if lines_a is None or lines_b is None:
                if pa.stat().st_size == pb.stat().st_size:
                    log.write(f"[=] {rel} (binary, giống kích thước)\n")
                else:
                    log.write(f"[≠] {rel} (binary khác)\n")
                continue

            if lines_a == lines_b:
                log.write(f"[=] {rel}\n")
                continue

            removed, added = diff_added_removed(lines_a, lines_b)
            log.write(f"[≠] {rel} — {len(removed)} dòng bị xóa, {len(added)} dòng được thêm\n")

            if removed:
                log.write("    --- REMOVED ---\n")
                for ln, text in removed[:30]:
                    log.write(f"    - A:{ln:>6} | {text}\n")
                if len(removed) > 30:
                    log.write(f"    ... (+{len(removed)-30} dòng nữa)\n")

            if added:
                log.write("    +++ ADDED +++\n")
                for ln, text in added[:30]:
                    log.write(f"    + B:{ln:>6} | {text}\n")
                if len(added) > 30:
                    log.write(f"    ... (+{len(added)-30} dòng nữa)\n")

            # Unified diff để xem ngữ cảnh
            diff = unified_diff(lines_a, lines_b, fromfile=f"a/{rel}", tofile=f"b/{rel}", lineterm="")
            log.write("\n".join(["    " + line for line in list(diff)[:50]]) + "\n\n")

    print(f"✅ Đã lưu kết quả tại: {log_path.resolve()}")


if __name__ == "__main__":
    dir_a = Path(DIR_A)
    dir_b = Path(DIR_B)
    log_file = Path(LOG_PATH)
    compare_directories(dir_a, dir_b, log_file)
