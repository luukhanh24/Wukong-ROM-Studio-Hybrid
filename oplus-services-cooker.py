import os

def patch_smali_file(file_path, patches):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    modified = False
    new_lines = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        
        # Check if line starts a method we want to patch
        for method_sig, insert_after, code, check_str in patches:
            if method_sig in line:
                # Find the insert_after point within this method
                method_end = False
                found_insertion = False
                j = i + 1
                temp_method_lines = []
                
                # Check if already patched
                already_patched = False
                
                while j < len(lines) and not method_end:
                    curr_line = lines[j]
                    if '.end method' in curr_line:
                        method_end = True
                    if check_str in curr_line:
                        already_patched = True
                    j += 1
                
                if already_patched:
                    # Skip patching this method
                    break
                
                # If not patched, find insertion point
                j = i + 1
                method_end = False
                while j < len(lines) and not method_end:
                    curr_line = lines[j]
                    new_lines.append(curr_line)
                    if insert_after in curr_line and not found_insertion:
                        new_lines.append("\n")
                        new_lines.extend([l + "\n" for l in code.splitlines()])
                        new_lines.append("\n")
                        found_insertion = True
                        modified = True
                    if '.end method' in curr_line:
                        method_end = True
                    j += 1
                i = j - 1 # Update outer loop index
                break
        i += 1

    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True
    return False

def patch_flexible_window_utils():
    file_path = os.path.join("framework-cooker", "oplus-services_unpack", "smali_classes2", "com", "android", "server", "wm", "FlexibleWindowUtils.smali")
    
    patches = [
        (
            '.method private static getUnSupportRatiosInFlexibleTask(Ljava/lang/String;)Ljava/lang/String;',
            '.param p0',
            '    const-string/jumbo v0, "black_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_b\n\n    const/4 v0, 0x0\n\n    return-object v0\n    \n    :cond_b',
            'black_window'
        ),
        (
            '.method public static isInMultiWindowFlexibleBlackList(Ljava/lang/String;)Z',
            '.param p0',
            '    const-string/jumbo v0, "black_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_b\n\n    const/4 v0, 0x0\n\n    return v0\n    \n    :cond_b',
            'black_window'
        ),
        (
            '.method public static isSupportFlexibleWindow(Landroid/content/Intent;Landroid/content/pm/ActivityInfo;)Z',
            '.param p1',
            '    const-string/jumbo v0, "black_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_b\n\n    const/4 v0, 0x1\n\n    return v0\n    \n    :cond_b',
            'black_window'
        ),
        (
            '.method public static isSupportFlexibleWindow(Lcom/android/server/wm/Task;)Z',
            '.param p0',
            '    const-string/jumbo v0, "black_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_b\n\n    const/4 v0, 0x1\n\n    return v0\n    \n    :cond_b',
            'black_window'
        ),
        (
            '.method public static isSupportFlexibleWindow(Ljava/lang/String;Ljava/lang/String;)Z',
            '.param p1',
            '    const-string/jumbo v0, "black_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_b\n\n    const/4 v0, 0x1\n\n    return v0\n    \n    :cond_b',
            'black_window'
        ),
        (
            '.method public static isSupportMultiMode()Z',
            '.registers',
            '    const-string/jumbo v0, "multi_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_b\n\n    const/4 v0, 0x1\n\n    return v0\n\n    .line 1655\n    :cond_b',
            'multi_window'
        )
    ]
    
    if patch_smali_file(file_path, patches):
        print(f"Patched FlexibleWindowUtils.smali")
    else:
        print(f"FlexibleWindowUtils.smali already patched or no changes made.")

def patch_flexible_window_manager_service():
    file_path = os.path.join("framework-cooker", "oplus-services_unpack", "smali_classes2", "com", "android", "server", "wm", "FlexibleWindowManagerService.smali")
    
    patches = [
        (
            '.method public getMaxWinNum(I)I',
            '.param p1',
            '    const-string/jumbo v0, "multi_window"\n\n    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n\n    move-result v0\n\n    if-eqz v0, :cond_c\n\n    const/16 v0, 0x10\n\n    return v0\n\n    :cond_c',
            'multi_window'
        )
    ]
    
    if patch_smali_file(file_path, patches):
        print(f"Patched FlexibleWindowManagerService.smali")
    else:
        print(f"FlexibleWindowManagerService.smali already patched or no changes made.")

def patch_startup_strategy():
    file_path = os.path.join("framework-cooker", "oplus-services_unpack", "smali_classes", "com", "android", "server", "am", "OplusAppStartupManager$OplusStartupStrategy.smali")
    
    patches = [
        (
            '.method private initFeature()V',
            'const-string/jumbo v2, "oplus.software.startup_strategy_restrict"',
            '    const-string/jumbo v2, "stark"',
            'stark'
        )
    ]
    
    # We need a different logic for replacement rather than insertion for this one
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    target = 'const-string/jumbo v2, "oplus.software.startup_strategy_restrict"'
    replacement = 'const-string/jumbo v2, "stark"'
    
    if target in content:
        content = content.replace(target, replacement)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Patched OplusAppStartupManager$OplusStartupStrategy.smali")
    elif replacement in content:
        print(f"OplusAppStartupManager$OplusStartupStrategy.smali already patched.")
    else:
        print(f"Target string not found in OplusAppStartupManager$OplusStartupStrategy.smali")

def patch_notification_service_ext():
    file_path = os.path.join("framework-cooker", "oplus-services_unpack", "smali_classes", "com", "android", "server", "notification", "OplusNotificationManagerServiceExtImpl.smali")
    
    patches = [
        (
            'invoke-static {}, Lcom/android/server/wm/FlexibleWindowUtils;->isDomesticRegion()Z',
            'move-result v2',
            '    const/4 v2, 0x0',
            'const/4 v2, 0x0' # Note: simplified check
        )
    ]
    
    if patch_smali_file(file_path, patches):
        print(f"Patched OplusNotificationManagerServiceExtImpl.smali")
    else:
        print(f"OplusNotificationManagerServiceExtImpl.smali already patched or no changes made.")

def patch_phone_window_manager_ext():
    file_path = os.path.join("framework-cooker", "oplus-services_unpack", "smali_classes2", "com", "android", "server", "policy", "PhoneWindowManagerExtImpl.smali")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Đoạn mã gốc cần tìm (lưu ý các dòng trống và khoảng trắng)
    target = """    invoke-static {}, Lcom/oplus/content/OplusFeatureConfigManager;->getInstacne()Lcom/oplus/content/OplusFeatureConfigManager;

    move-result-object v0

    const-string/jumbo v1, "oplus.software.speech_assist_for_breeno"

    invoke-virtual {v0, v1}, Lcom/oplus/content/OplusFeatureConfigManager;->hasFeature(Ljava/lang/String;)Z

    move-result v0"""

    # Đoạn mã thay thế
    replacement = """    const-string/jumbo v0, "gemini_button"

    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

    move-result v0

    if-eqz v0, :cond_b

    const/4 v0, 0x0

    goto :goto_c

    :cond_b
    const/4 v0, 0x1

    :goto_c"""

    if target in content:
        content = content.replace(target, replacement)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Patched PhoneWindowManagerExtImpl.smali (Gemini Button)")
    elif "gemini_button" in content:
        print(f"PhoneWindowManagerExtImpl.smali already patched.")
    else:
        print(f"Target code block not found in PhoneWindowManagerExtImpl.smali")

if __name__ == "__main__":
    patch_flexible_window_utils()
    patch_flexible_window_manager_service()
    patch_startup_strategy()
    patch_notification_service_ext()
    patch_phone_window_manager_ext()
