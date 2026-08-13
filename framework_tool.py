import os
import sys
import subprocess
import zipfile
import shutil
import argparse
import re
from pathlib import Path

class FrameworkTool:
    def __init__(self, jar_or_dir, tools_dir=None, base_out="framework-cooker"):
        self.work_dir = Path(__file__).parent
        path = Path(jar_or_dir)
        if not path.is_absolute():
            path = self.work_dir / path

        # Locate tools
        if tools_dir:
            self.tools_dir = Path(tools_dir).absolute()
        else:
            self.tools_dir = self.work_dir / "framework_mod_v3"
            
        self.baksmali_jar = self.tools_dir / "baksmali.jar"
        self.smali_jar = self.tools_dir / "smali.jar"
        
        if path.is_file():
            # If input is a JAR file, create a dedicated folder inside base_out
            self.jar_path = path
            self.unpack_dir = self.work_dir / base_out / (path.stem + "_unpack")
        else:
            # If input is a directory, assume it's the unpack directory
            self.unpack_dir = path
            self.jar_path = None
            
        self.source_info_file = self.unpack_dir / ".source"

        # Try to resolve original JAR path from .source if it wasn't provided or if we're in a directory context
        if self.unpack_dir.exists() and self.source_info_file.exists() and self.jar_path is None:
            try:
                with open(self.source_info_file, "r") as f:
                    source_path = Path(f.read().strip())
                    if source_path.exists():
                        self.jar_path = source_path
            except:
                pass

    def check_tools(self):
        for jar in [self.baksmali_jar, self.smali_jar]:
            if not jar.exists():
                print(f"[!] Error: {jar.name} not found at {jar}")
                return False
        return True

    def unpack(self):
        if self.jar_path is None or not self.jar_path.is_file():
            print(f"[!] Error: {self.jar_path} is not a valid file.")
            return False

        print(f"[*] Unpacking {self.jar_path}...")
        if self.unpack_dir.exists():
            shutil.rmtree(self.unpack_dir)
        self.unpack_dir.mkdir(parents=True, exist_ok=True)

        # Save source path
        with open(self.source_info_file, "w") as f:
            f.write(str(self.jar_path))

        try:
            # 1. Extract all contents
            print(f"[*] Extracting all contents to {self.unpack_dir.name}...")
            with zipfile.ZipFile(self.jar_path, 'r') as zip_ref:
                zip_ref.extractall(self.unpack_dir)

            # 2. Find ALL .dex files
            dex_files = list(self.unpack_dir.glob("*.dex"))
            if not dex_files:
                print("[!] No DEX files found in JAR.")
                return False

            print(f"[*] Disassembling {len(dex_files)} DEX files found...")
            # Sort dex files (classes.dex, classes2.dex...)
            def dex_sort_key(f):
                name = f.stem
                if name == "classes": return 0
                match = re.search(r'(\d+)', name)
                return int(match.group(1)) if match else 999

            dex_files.sort(key=dex_sort_key)

            for dex in dex_files:
                # Name smali folders correctly: smali_classes, smali_classes2...
                stem = dex.stem
                folder_name = f"smali_{stem}" if stem != "classes" else "smali_classes"
                smali_out = self.unpack_dir / folder_name
                
                print(f"    - {dex.name} -> {smali_out.name}")
                cmd = ["java", "-Xmx2G", "-jar", str(self.baksmali_jar), "d", str(dex), "-o", str(smali_out)]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode != 0:
                    print(f"      [!] Error disassembling {dex.name}:\n{res.stderr}")
                    return False
                # Optionally remove original dex to avoid confusion? No, keep it for now.

            print(f"[*] SUCCESS: Unpacked {len(dex_files)} classes to {self.unpack_dir}")
            return True
        except Exception as e:
            print(f"[!] Unpack failed: {e}")
            return False

    def repack(self):
        if self.jar_path is None or not self.jar_path.exists():
            # Try to recover from .source if user passed the cooker dir
            if self.source_info_file.exists():
                with open(self.source_info_file, "r") as f:
                    self.jar_path = Path(f.read().strip())
            
        if self.jar_path is None or not self.jar_path.exists():
            print(f"[!] Error: Could not determine target JAR path.")
            return False

        print(f"[*] Target JAR: {self.jar_path}")
        
        try:
            # 1. Clear old DEX files in root to prepare for new ones
            for dex in self.unpack_dir.glob("*.dex"):
                dex.unlink()

            # 2. Detect ALL smali directories
            smali_dirs = [d for d in self.unpack_dir.iterdir() if d.is_dir() and (d.name.startswith("smali") or (d / "android").exists() or (d / "com").exists())]
            # Actually, let's stick to name-based detection but be more inclusive
            smali_dirs = [d for d in self.unpack_dir.iterdir() if d.is_dir() and d.name.startswith("smali")]
            
            if not smali_dirs:
                print("[!] No smali folders found for repacking.")
                return False

            def natural_key(string_):
                return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_.name)]
            smali_dirs.sort(key=natural_key)

            print(f"[*] Assembling {len(smali_dirs)} smali directories...")
            for smali_dir in smali_dirs:
                name = smali_dir.name
                # Mapping logic:
                # smali or smali_classes -> classes.dex
                # smali_classes2 -> classes2.dex
                # smali_anything -> anything.dex
                if name in ["smali", "smali_classes"]:
                    dex_name = "classes.dex"
                elif name.startswith("smali_"):
                    dex_name = name[6:] + ".dex"
                else:
                    dex_name = name + ".dex" # Fallback
                
                dex_out = self.unpack_dir / dex_name
                print(f"    - {smali_dir.name} -> {dex_name}", end=" ", flush=True)
                
                cmd = ["java", "-Xmx2G", "-jar", str(self.smali_jar), "a", str(smali_dir), "-o", str(dex_out), "--api", "33"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                
                if res.returncode != 0 or not dex_out.exists():
                    print(f"\n[!] Failed to assemble {dex_name}. Error:\n{res.stderr}")
                    return False
                print(f"({os.path.getsize(dex_out)} bytes)")
                
            # 3. Create backup (Disabled by user request)
            # backup_jar = self.jar_path.with_suffix(".jar.bak")
            # if not backup_jar.exists():
            #     shutil.copy2(self.jar_path, backup_jar)
            #     print(f"[*] Created backup: {backup_jar.name}")

            # 4. ZIP everything back
            print(f"[*] Building final JAR...")
            with zipfile.ZipFile(self.jar_path, 'w', zipfile.ZIP_DEFLATED) as new_zip:
                for root, dirs, files in os.walk(self.unpack_dir):
                    rel_root = Path(root).relative_to(self.unpack_dir)
                    # Exclude smali source folders
                    if any(part.startswith("smali") for part in rel_root.parts):
                        continue
                    
                    for file in files:
                        # Exclude metadata and backups
                        if file == ".source" or file.endswith(".jar.bak"):
                            continue
                            
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.unpack_dir)
                        new_zip.write(file_path, arcname)
            
            print(f"[*] SUCCESS: Updated JAR at {self.jar_path}")
            return True
        except Exception as e:
            print(f"\n[!] Repack failed: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Tool to unpack/repack ALL classes in framework.jar")
    parser.add_argument("action", choices=["unpack", "repack"])
    parser.add_argument("jar", help="Path to JAR file or cooker directory")
    parser.add_argument("-o", "--out", default="framework-cooker", help="Output folder name")
    
    args = parser.parse_args()
    tool = FrameworkTool(args.jar, base_out=args.out)
    if not tool.check_tools():
        return 1
    return 0 if getattr(tool, args.action)() else 1

if __name__ == "__main__":
    raise SystemExit(main())
