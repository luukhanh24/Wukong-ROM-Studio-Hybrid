import os

def patch_window_state():
    # Sử dụng đường dẫn tương đối từ vị trí file services_cooker.py
    file_path = os.path.join("framework-cooker", "services_unpack", "smali_classes3", "com", "android", "server", "wm", "WindowState.smali")
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    patch_added = False
    in_method = False

    patch_code = [
        '    const-string/jumbo v0, "disable_flag_secure"\n',
        '\n',
        '    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n',
        '\n',
        '    move-result v0\n',
        '\n',
        '    if-eqz v0, :cond_b\n',
        '\n',
        '    const/4 v0, 0x0\n',
        '\n',
        '    return v0\n',
        '   \n',
        '    :cond_b\n'
    ]

    for line in lines:
        new_lines.append(line)
        if '.method isSecureLocked()Z' in line:
            in_method = True
        elif in_method and '.registers' in line and not patch_added:
            # Check if patch already exists
            found_patch = False
            for j in range(1, 10):
                if lines.index(line) + j < len(lines) and 'disable_flag_secure' in lines[lines.index(line) + j]:
                    found_patch = True
                    break
            
            if not found_patch:
                new_lines.extend(patch_code)
                patch_added = True
            in_method = False
    
    if patch_added:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Patched WindowState.smali")
    else:
        print(f"WindowState.smali already patched or method not found.")

def patch_media_focus():
    file_path = os.path.join("framework-cooker", "services_unpack", "smali_classes", "com", "android", "server", "audio", "MediaFocusControl.smali")
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    method_sig = '.method protected requestAudioFocus(Landroid/media/AudioAttributes;ILandroid/os/IBinder;Landroid/media/IAudioFocusDispatcher;Ljava/lang/String;Ljava/lang/String;IIZIZ)I'
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    patch_added = False
    in_method = False
    last_param_index = -1

    patch_code = [
        '    const-string/jumbo v0, "multi_audio"\n',
        '\n',
        '    invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I\n',
        '\n',
        '    move-result v0\n',
        '\n',
        '    if-eqz v0, :cond_b\n',
        '\n',
        '    const/4 v0, 0x1\n',
        '\n',
        '    return v0\n',
        '\n',
        '    :cond_b\n'
    ]

    for i, line in enumerate(lines):
        new_lines.append(line)
        if method_sig in line:
            in_method = True
        elif in_method:
            if '.param' in line:
                last_param_index = len(new_lines) - 1
            elif last_param_index != -1 and not line.strip().startswith('.line') and line.strip() != '':
                # This is the line after all .params
                # Check if patch already exists
                found_patch = False
                for j in range(0, 10):
                    if i + j < len(lines) and 'multi_audio' in lines[i + j]:
                        found_patch = True
                        break
                
                if not found_patch:
                    # Insert patch after the last .param
                    new_lines.insert(last_param_index + 1, '\n')
                    for patch_line in reversed(patch_code):
                        new_lines.insert(last_param_index + 1, patch_line)
                    patch_added = True
                in_method = False
                last_param_index = -1
            elif '.end method' in line:
                in_method = False
                last_param_index = -1

    if patch_added:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"Patched MediaFocusControl.smali")
    else:
        print(f"MediaFocusControl.smali already patched or method not found.")

if __name__ == "__main__":
    patch_window_state()
    patch_media_focus()
