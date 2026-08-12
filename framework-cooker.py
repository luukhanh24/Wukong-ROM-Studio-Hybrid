import os
import shutil
import re
from pathlib import Path

# Paths - Adjusted to the new folder structure
BASE_DIR = Path(__file__).resolve().parent
COOKER_DIR = BASE_DIR / "framework-cooker" / "framework_unpack"
STARK_DIR = BASE_DIR / "STARK" / "kaorios"
CUSTOM_CLASSES_DIR = COOKER_DIR / "smali_classes6"

def find_file(root_dir, filename):
    """Recursively find a file in the directory."""
    if not root_dir.exists():
        return None
    for root, dirs, files in os.walk(root_dir):
        if filename in files:
            return Path(os.path.join(root, filename))
    return None

def patch_file(file_path, patches):
    """
    Applies multiple patches to a single file.
    patches: list of (method_pattern, inject_code, position, unique_check)
    """
    if not file_path:
        return
    if not file_path.exists():
        print(f"[!] Warning: File {file_path} not found.")
        return

    print(f"[*] Patching {file_path.relative_to(COOKER_DIR)}...")
    content = file_path.read_text(encoding="utf-8")
    any_ok = False

    for pattern, inject_code, position, unique_check in patches:
        match = re.search(pattern, content, flags=re.DOTALL | re.MULTILINE)
        if not match:
            # Simplified match if complex fails
            simplified_pattern = pattern.replace(r'(?:whitelist\s+|blacklist\s+|greylist\s+|greylist-max-o\s+)?', '')
            match = re.search(simplified_pattern, content, flags=re.DOTALL | re.MULTILINE)
            if not match:
                print(f"    [!] Could not find method matching pattern: {pattern[:40]}...")
                continue

        method_body = match.group(0)
        
        # Check if already patched
        if unique_check in method_body:
            print(f"    [-] Skipping a patch in {file_path.name} (already present by '{unique_check}')")
            continue

        new_method_body = method_body

        if position == "above_return":
            ret_pattern = r'(return-object v\d+|return v\d+|return-void|return p\d+)'
            ret_matches = list(re.finditer(ret_pattern, method_body))
            if ret_matches:
                last_ret = ret_matches[-1]
                target = last_ret.group(1)
                new_method_body = method_body[:last_ret.start()] + inject_code + "\n\n    " + target + method_body[last_ret.end():]

        elif position == "below_registers":
            reg_pattern = r'(\.registers \d+)'
            if re.search(reg_pattern, method_body):
                new_method_body = re.sub(reg_pattern, r'\1\n    ' + inject_code, method_body)

        elif position == "replace_body":
            # Keep method header and end, replace inside
            header_match = re.search(r'(\.method.*?\.registers \d+)', method_body, flags=re.DOTALL)
            if header_match:
                new_method_body = header_match.group(1) + "\n\n    " + inject_code + "\n.end method"

        elif position == "below_pattern":
            target_pattern, code_to_inject = inject_code
            if target_pattern in method_body:
                new_method_body = method_body.replace(target_pattern, target_pattern + "\n\n    " + code_to_inject)

        if new_method_body != method_body:
            content = content.replace(method_body, new_method_body)
            any_ok = True

    if any_ok:
        file_path.write_text(content, encoding="utf-8")
        print(f"    [+] Successfully updated {file_path.name}")

def main():
    print("=== framework-cooker logic starting ===")
    
    # 1. Copy custom files (into framework_unpack so they get repacked with framework.jar)
    if COOKER_DIR.exists():
        # kaorios files
        target_kaorios_dir = CUSTOM_CLASSES_DIR / "com/android/internal/util/kaorios"
        if STARK_DIR.exists():
            print(f"[*] Copying kaorios Smali files to framework_unpack...")
            os.makedirs(target_kaorios_dir, exist_ok=True)
            for item in STARK_DIR.iterdir():
                if item.is_file():
                    shutil.copy2(item, target_kaorios_dir)
            print("[*] Successfully copied kaorios files.")

        # SettingsHelper.smali from STARK
        settings_src = BASE_DIR / "STARK" / "SettingsHelper.smali"
        settings_dest = COOKER_DIR / "smali_classes/android/preference/SettingsHelper.smali"
        if settings_src.exists():
            print(f"[*] Copying SettingsHelper.smali to framework_unpack/android.preference...")
            os.makedirs(settings_dest.parent, exist_ok=True)
            shutil.copy2(settings_src, settings_dest)
            print("[*] Successfully copied SettingsHelper.smali.")
    else:
        print("[!] Warning: framework_unpack not found. Custom classes not copied.")

    # 2. Patch files (Searching recursively in all of framework-cooker)
    
    # ApplicationPackageManager
    file_path = find_file(COOKER_DIR, "ApplicationPackageManager.smali")
    patch_file(file_path, [
        (
            r'\.method\s+public\s+(?:whitelist\s+|blacklist\s+|greylist\s+|greylist-max-o\s+)?hasSystemFeature\(Ljava/lang/String;\)Z.*?.end method',
            '''const/4 v0, 0x0

    invoke-virtual {p0, p1, v0}, Landroid/app/ApplicationPackageManager;->hasSystemFeature(Ljava/lang/String;I)Z

    move-result p0

    :try_start_kousei
    invoke-static {p0, p1}, Lcom/android/internal/util/kaorios/KaoriPropsUtils;->KaoriFeatureBlock(ZLjava/lang/String;)Z

    move-result p0
    :try_end_kaorios
    .catchall {:try_start_kousei .. :try_end_kaorios} :catchall_kaorios

    :catchall_kaorios
    return p0''',
            "replace_body", "KaoriFeatureBlock"
        ),
        (
            r'\.method\s+public\s+(?:whitelist\s+|blacklist\s+|greylist\s+|greylist-max-o\s+)?hasSystemFeature\(Ljava/lang/String;I\)Z.*?.end method',
            '''invoke-static {}, Landroid/app/ActivityThread;->currentPackageName()Ljava/lang/String;
            
    move-result-object v0
            
    :try_start_kaori_override
    iget-object v1, p0, Landroid/app/ApplicationPackageManager;->mContext:Landroid/app/ContextImpl;
            
    invoke-static {v1, p1, v0}, Lcom/android/internal/util/kaorios/KaoriFeatureOverrides;->getOverride(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/Boolean;
            
    move-result-object v0
    :try_end_kaori_override
    .catchall {:try_start_kaori_override .. :try_end_kaori_override} :catchall_kaori_override
            
    goto :goto_kaori_override
            
    :catchall_kaori_override
    const/4 v0, 0x0
            
    :goto_kaori_override
    if-eqz v0, :cond_kaori_override
            
    invoke-virtual {v0}, Ljava/lang/Boolean;->booleanValue()Z
            
    move-result p0
            
    return p0
            
    :cond_kaori_override''',
            "below_registers", "KaoriFeatureOverrides"
        )
    ])

    # Instrumentation
    file_path = find_file(COOKER_DIR, "Instrumentation.smali")
    patch_file(file_path, [
        (
            r'\.method\s+public\s+static\s+whitelist\s+newApplication\(Ljava/lang/Class;Landroid/content/Context;\)Landroid/app/Application;.*?.end method',
            'invoke-static {p1}, Lcom/android/internal/util/kaorios/KaoriPropsUtils;->KaoriProps(Landroid/content/Context;)V',
            "above_return", "KaoriProps("
        ),
        (
            r'\.method\s+public\s+whitelist\s+newApplication\(Ljava/lang/ClassLoader;Ljava/lang/String;Landroid/content/Context;\)Landroid/app/Application;.*?.end method',
            'invoke-static {p3}, Lcom/android/internal/util/kaorios/KaoriPropsUtils;->KaoriProps(Landroid/content/Context;)V',
            "above_return", "KaoriProps("
        )
    ])

    # KeyStore2
    file_path = find_file(COOKER_DIR, "KeyStore2.smali")
    patch_file(file_path, [
        (
            r'\.method\s+public\s+blacklist\s+getKeyEntry\(Landroid/system/keystore2/KeyDescriptor;\)Landroid/system/keystore2/KeyEntryResponse;.*?.end method',
            '''invoke-static {v0}, Lcom/android/internal/util/kaorios/KaoriKeyboxHooks;->KaoriGetKeyEntry(Landroid/system/keystore2/KeyEntryResponse;)Landroid/system/keystore2/KeyEntryResponse;

    move-result-object v0''',
            "above_return", "KaoriGetKeyEntry"
        )
    ])

    # AndroidKeyStoreSpi
    file_path = find_file(COOKER_DIR, "AndroidKeyStoreSpi.smali")
    patch_file(file_path, [
        (
            r'\.method\s+public\s+(?:whitelist\s+test-api\s+)?engineGetCertificateChain\(Ljava/lang/String;\)\[Ljava/security/cert/Certificate;.*?.end method',
            'invoke-static {}, Lcom/android/internal/util/kaorios/KaoriPropsUtils;->KaoriGetCertificateChain()V',
            "below_registers", "KaoriGetCertificateChain()V"
        ),
        (
            r'\.method\s+public\s+(?:whitelist\s+test-api\s+)?engineGetCertificateChain\(Ljava/lang/String;\)\[Ljava/security/cert/Certificate;.*?.end method',
            ('const/4 v4, 0x0\n\n    aput-object v2, v3, v4', '''invoke-static {v3}, Lcom/android/internal/util/kaorios/KaoriKeyboxHooks;->KaoriGetCertificateChain([Ljava/security/cert/Certificate;)[Ljava/security/cert/Certificate;

    move-result-object v3'''),
            "below_pattern", "KaoriGetCertificateChain([L"
        )
    ])

    print("=== framework-cooker logic completed ===")

if __name__ == "__main__":
    main()
