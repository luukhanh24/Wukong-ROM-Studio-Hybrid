#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

SEARCH_DIRS=("images" "firmware-update")
CHECKSUM_FILE="$SCRIPT_DIR/wukong_md5_hashes.txt"

LOCAL_FASTBOOT="$SCRIPT_DIR/bin/macos/fastboot"
LOCAL_ADB="$SCRIPT_DIR/bin/macos/adb"
lines=()
while IFS= read -r line || [ -n "$line" ]; do
    lines+=("$line")
done < "$SCRIPT_DIR/info.txt"

to_lower() { printf "%s" "$1" | tr '[:upper:]' '[:lower:]'; }

calc_md5() {
    local file="$1"
    if command -v md5sum >/dev/null 2>&1; then
        md5sum "$file" | awk '{print $1}'
    elif command -v md5 >/dev/null 2>&1; then
        md5 -q "$file"
    elif command -v openssl >/dev/null 2>&1; then
        openssl md5 "$file" | awk '{print $NF}'
    else
        echo ""
        return 1
    fi
}

show_progress() {
    local status="$1"
    local filename="$2"
    local percent=$((progress_current * 100 / progress_total))
    local filled=$(((progress_current * 20 + progress_total - 1) / progress_total))
    local empty=$((20 - filled))
    local filled_bar empty_bar color

    printf -v filled_bar '%*s' "$filled" ''
    printf -v empty_bar '%*s' "$empty" ''
    filled_bar="${filled_bar// /#}"
    empty_bar="${empty_bar// /-}"

    case "$status" in
        OK) color='\033[92m' ;;
        CHECK) color='\033[96m' ;;
        *) color='\033[91m' ;;
    esac

    printf "\r\033[2K%b[%s%s] %d%% (%d/%d) [%s] %s\033[0m" \
        "$color" "$filled_bar" "$empty_bar" "$percent" \
        "$progress_current" "$progress_total" "$status" "$filename"
}
countdown() {
    local seconds=$1
    echo ""
    local i
    for (( i=seconds; i>0; i-- )); do
        printf "  Waiting... %d \r" "$i"
        sleep 1
    done
    printf "                  \r"
    echo ""
}

if [ -f "$LOCAL_FASTBOOT" ]; then
    FASTBOOT="$LOCAL_FASTBOOT"
    chmod +x "$FASTBOOT"
elif command -v fastboot >/dev/null 2>&1; then
    FASTBOOT="$(command -v fastboot)"
else
    echo "Error: fastboot not found in bin/macos/ or system PATH."
    exit 1
fi

if [ -f "$LOCAL_ADB" ]; then
    ADB="$LOCAL_ADB"
    chmod +x "$ADB"
elif command -v adb >/dev/null 2>&1; then
    ADB="$(command -v adb)"
else
    echo "Error: adb not found in bin/macos/ or system PATH."
    exit 1
fi

clear
echo -e "\033[97;41m                                                                \033[0m"
echo -e "\033[97;41m    .d88b.  d8b   db d88888b d8888b. db      db    db .d8888.   \033[0m"
echo -e "\033[97;41m   .8P  Y8. 888o  88 88'     88 \`8D 88      88    88 88'  YP   \033[0m"
echo -e "\033[97;41m   88    88 88V8o 88 88ooooo 88oodD' 88      88    88\`8bo.     \033[0m"
echo -e "\033[97;41m   88    88 88 V8o88 88~~~~~ 88~~~   88      88    88  \`Y8b.   \033[0m"
echo -e "\033[97;41m  \`8b  d8' 88  V888 88.     88      88booo. 88b  d88 db   8D   \033[0m"
echo -e "\033[97;41m   \`Y88P'  VP   V8P Y88888P 88      Y88888P ~Y8888P'\`8888Y'   \033[0m"
echo -e "\033[97;41m                                                                \033[0m"
echo -e "\033[30;107m=========================== Wukong ============================\033[0m"
echo -e "\033[30;107m  Author: https://t.me/Kswukong                                \033[0m"
echo -e "\033[30;107m  Support group: https://t.me/OnePlus_Ace5_Port                \033[0m"
echo ""
echo ""
echo ""
echo "Devices : ${lines[0]}"
echo "Version : ${lines[1]}"
echo "Region  : ${lines[2]}"
echo "Wukong  ${lines[3]}  ${lines[4]}"
echo ""

echo -e "\033[96m1. Check path.\033[0m"
echo "Working dir: $PWD"
if [[ "$PWD" =~ \  ]]; then
    echo -e "\033[91m[!] Warning: The current path contains spaces.\033[0m"
else
    echo -e "\033[92m[OK] Done.\033[0m"
fi

echo -e "\033[96m2. Check image file integrity.\033[0m"
echo "Please wait..."
error_count=0
rec=0
if [ ! -f "$CHECKSUM_FILE" ]; then
    echo -e "\033[91m[!] Checksum file not found: $CHECKSUM_FILE\033[0m"
    read -p "Press Enter to exit..."
    exit 1
fi

if ! command -v md5sum >/dev/null 2>&1 && ! command -v md5 >/dev/null 2>&1 && ! command -v openssl >/dev/null 2>&1; then
    echo -e "\033[91m[!] No MD5 tool found (need md5sum or md5 or openssl).\033[0m"
    read -p "Press Enter to exit..."
    exit 1
fi

progress_total=0
while IFS= read -r checksum_line || [ -n "$checksum_line" ]; do
    checksum_line="${checksum_line%$'\r'}"
    [ -z "$checksum_line" ] && continue
    progress_total=$((progress_total + 1))
done < "$CHECKSUM_FILE"
progress_current=0
echo "Files to verify: $progress_total"

while IFS= read -r line || [ -n "$line" ]; do
    line="$(printf "%s" "$line" | tr -d '\r')"
    [ -z "$line" ] && continue

    expected_md5="$(printf "%s" "$line" | awk '{print $1}')"
    filename="$(printf "%s" "$line" | cut -d ' ' -f 2-)"
    filename="$(printf "%s" "$filename" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

    progress_current=$((progress_current + 1))
    show_progress "CHECK" "$filename"

    found_path=""
    for dir in "${SEARCH_DIRS[@]}"; do
        if [ -f "$dir/$filename" ]; then
            found_path="$dir/$filename"
            break
        fi
    done

    if [ -z "$found_path" ]; then
        error_count=$((error_count + 1))
        show_progress "MISSING" "$filename"
        printf '\n'
    else
        current_md5="$(calc_md5 "$found_path")"
        if [ -z "$current_md5" ]; then
            error_count=$((error_count + 1))
            show_progress "FAILED" "$filename"
            printf '\n'
        elif [ "$(to_lower "$expected_md5")" != "$(to_lower "$current_md5")" ]; then
            error_count=$((error_count + 1))
            show_progress "MISMATCH" "$filename"
            printf '\n'
        else
            show_progress "OK" "$filename"
        fi
    fi
done < "$CHECKSUM_FILE"
printf '\n'

if [ "$error_count" -eq 0 ]; then
    echo -e "\033[92m[OK] Done.\033[0m"
else
    echo -e "\033[91m[!] Warning: Detected $error_count corrupt or missing file(s)\033[0m"
    read -p "Press Enter to exit..."
    exit 1
fi

echo -e "\033[96m3. Check bootloader status.\033[0m"
echo "Waiting for device..."

while true; do
    status="$("$FASTBOOT" getvar is-userspace 2>&1)"
    if echo "$status" | grep -q "is-userspace: no"; then
        echo -e "\033[92m[OK] Your device is currently in Bootloader mode.\033[0m"
        break
    else
        echo -e "\033[91m[!] Your device is currently in FastbootD mode.\033[0m"
        "$FASTBOOT" reboot bootloader
        sleep 5
    fi
done

echo ""
echo "--------------------------------------------------------"
echo "#   y = Format data      #   n = Keep data             #"
echo "--------------------------------------------------------"
read -p "Your choice (y/n): " format_choice
format_choice="$(to_lower "$format_choice")"

echo ""
echo "--------------------------------------------------------"
echo "#   y = Flash firmware   #   n = Skip firmware image   #"
echo "--------------------------------------------------------"
read -p "Your choice (y/n): " fw_choice
fw_choice="$(to_lower "$fw_choice")"
echo ""

if [ -f "images/OrangeFox.img" ]; then
    "$FASTBOOT" flash recovery_a images/OrangeFox.img || { echo -e "\033[91m[!] Flash OrangeFox error\033[0m"; exit 1; }
    "$FASTBOOT" flash recovery_b images/OrangeFox.img || { echo -e "\033[91m[!] Flash OrangeFox error\033[0m"; exit 1; }
elif [ -f "images/TWRP.img" ]; then
    "$FASTBOOT" flash recovery_a images/TWRP.img || { echo -e "\033[91m[!] Flash TWRP error\033[0m"; exit 1; }
    "$FASTBOOT" flash recovery_b images/TWRP.img || { echo -e "\033[91m[!] Flash TWRP error\033[0m"; exit 1; }
else
    echo "Neither OrangeFox.img nor TWRP.img was found in the images folder."
    rec=$((rec + 1))
fi

if [ "$fw_choice" = "y" ]; then
    "$FASTBOOT" reboot fastboot
    echo ""
    countdown 15

    if compgen -G "firmware-update/*.img" > /dev/null; then
        for img in firmware-update/*.img; do
            part_name="$(basename "$img" .img)"
            echo "Flashing $part_name..."
            "$FASTBOOT" flash --slot=all "$part_name" "$img" || { echo -e "\033[91m[!] Flash $part_name error\033[0m"; exit 1; }
        done
    else
        echo "No images found in firmware-update folder."
    fi
fi
"$FASTBOOT" flash vbmeta_a images/vbmeta.img || { echo -e "\033[91m[!] Flash vbmeta error\033[0m"; exit 1; }
"$FASTBOOT" flash vbmeta_b images/vbmeta.img || { echo -e "\033[91m[!] Flash vbmeta error\033[0m"; exit 1; }
"$FASTBOOT" flash vbmeta_system_a images/vbmeta_system.img || { echo -e "\033[91m[!] Flash vbmeta_system error\033[0m"; exit 1; }
"$FASTBOOT" flash vbmeta_system_b images/vbmeta_system.img || { echo -e "\033[91m[!] Flash vbmeta_system error\033[0m"; exit 1; }
"$FASTBOOT" flash vbmeta_vendor_a images/vbmeta_vendor.img || { echo -e "\033[91m[!] Flash vbmeta_vendor error\033[0m"; exit 1; }
"$FASTBOOT" flash vbmeta_vendor_b images/vbmeta_vendor.img || { echo -e "\033[91m[!] Flash vbmeta_vendor error\033[0m"; exit 1; }
"$FASTBOOT" flash dtbo_a images/dtbo.img || { echo -e "\033[91m[!] Flash dtbo error\033[0m"; exit 1; }
"$FASTBOOT" flash dtbo_b images/dtbo.img || { echo -e "\033[91m[!] Flash dtbo error\033[0m"; exit 1; }
"$FASTBOOT" flash boot_a images/boot.img || { echo -e "\033[91m[!] Flash boot error\033[0m"; exit 1; }
"$FASTBOOT" flash boot_b images/boot.img || { echo -e "\033[91m[!] Flash boot error\033[0m"; exit 1; }
"$FASTBOOT" flash init_boot_a images/init_boot.img || { echo -e "\033[91m[!] Flash init_boot error\033[0m"; exit 1; }
"$FASTBOOT" flash init_boot_b images/init_boot.img || { echo -e "\033[91m[!] Flash init_boot error\033[0m"; exit 1; }
"$FASTBOOT" flash vendor_boot_a images/vendor_boot.img || { echo -e "\033[91m[!] Flash vendor_boot error\033[0m"; exit 1; }
"$FASTBOOT" flash vendor_boot_b images/vendor_boot.img || { echo -e "\033[91m[!] Flash vendor_boot error\033[0m"; exit 1; }
"$FASTBOOT" flash vendor_boot images/vendor_boot.img || { echo -e "\033[91m[!] Flash vendor_boot error\033[0m"; exit 1; }
if [ "$rec" -eq 1 ]; then
    "$FASTBOOT" flash recovery_a images/recovery.img || { echo -e "\033[91m[!] Flash recovery error\033[0m"; exit 1; }
    "$FASTBOOT" flash recovery_b images/recovery.img || { echo -e "\033[91m[!] Flash recovery error\033[0m"; exit 1; }
fi
if [ "$format_choice" = "y" ] && [ "$fw_choice" = "y" ]; then
    "$FASTBOOT" erase frp || { echo -e "\033[91m[!] Erase frp error\033[0m"; exit 1; }
fi
if [[ "$fw_choice" == "y" ]]; then
    "$FASTBOOT" reboot bootloader
    echo ""
    countdown 15
	"$FASTBOOT" flash modem_a images/modem.img || { echo -e "\033[91m[!] Flash modem error\033[0m"; exit 1; }
	"$FASTBOOT" flash modem_b images/modem.img || { echo -e "\033[91m[!] Flash modem error\033[0m"; exit 1; }
fi

if [ "$format_choice" = "y" ] && [ "$fw_choice" = "n" ]; then
    "$FASTBOOT" reboot fastboot
    echo ""
    countdown 15
    "$FASTBOOT" erase frp
    "$FASTBOOT" reboot bootloader
    echo ""
    countdown 15
fi

"$FASTBOOT" erase super || { echo -e "\033[91m[!] Erase super error\033[0m"; exit 1; }
"$FASTBOOT" flash super images/super.img || { echo -e "\033[91m[!] Flash super error\033[0m"; exit 1; }
"$FASTBOOT" set_active a
echo ""

if [ "$format_choice" = "y" ]; then
    echo "Formatting system, please wait."
    "$FASTBOOT" -w
    "$FASTBOOT" reboot
else
    if [ "$rec" -eq 0 ]; then
        echo "Wipe cache, please wait."
        "$FASTBOOT" reboot recovery
        countdown 60

        echo "Waiting for ADB recovery..."
        while true; do
            if "$ADB" devices 2>/dev/null | grep -q "recovery"; then
                echo -e "\033[92m[OK] Your device is currently in Recovery mode.\033[0m"
                break
            else
                sleep 5
            fi
        done

        "$ADB" shell rm -rf \
            /data/cache/* \
            /data/resource-cache/* \
            /data/system/package_cache/* \
            /data/dalvik-cache/arm/* \
            /data/dalvik-cache/arm64/* \
            /data/data/*/app_track_sslcache/* \
            /data/data/*/app_pccache/* \
            /data/data/*/app_tmpcache/* \
            /data/data/*/cache/* \
            /data/data/*/app_cache/* \
            /data/data/*/code_cache/* \
            /data/user_de/*/*/cache/* \
            /data/user_de/*/*/code_cache/* \
            /data/system/dropbox/* 2>/dev/null

        echo "Keep data."
        "$ADB" reboot
    fi
    
fi

echo ""
read -p "Done. Press Enter to exit..."
