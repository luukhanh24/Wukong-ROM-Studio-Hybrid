from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "content-packs" / "index.json"
MOD_ROOT = ROOT / "MOD"
STARK_ROOT = ROOT / "STARK"
MARKER = MOD_ROOT / ".wukong-test-fixture"
SHARED_WK_ROOT = STARK_ROOT / "WK_Manager"
SHARED_WK_MARKER = SHARED_WK_ROOT / ".wukong-test-fixture"


TEXT_FIXTURES = {
    "WK_Manager/system/system/etc/selinux/stark_plat_sepolicy.cil": """+(type wukong_manager_app)
+(type wukong_manager_app_userfaultfd)
+(typetransition wukong_manager_app wukong_manager_app anon_inode \"[userfaultfd]\" wukong_manager_app_userfaultfd)
+(allow wukong_manager_app wukong_manager_app_userfaultfd (anon_inode (ioctl read create)))
+(allow wukong_manager_app wukong_manager_app (anon_inode (ioctl read create)))
+(allow priv_app proc_stat (file (ioctl read getattr lock map open watch watch_reads)))
+(allow priv_app vendor_sysfs_kgsl_gpubusy (file (ioctl read getattr lock map open watch watch_reads)))
""",
    "WK_Manager/system/system/etc/selinux/stark_plat_seapp_contexts": "-user=_app isPrivApp=true name=com.wukong.manager domain=wukong_manager_app type=privapp_data_file levelFrom=all\n",
    "WK_Manager/system/system/etc/init/hw/stark_init.rc": """+on post-fs-data
+    chmod 0444 /sys/class/kgsl/kgsl-3d0/gpuclk
+    chmod 0444 /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq
+    chmod 0444 /sys/devices/platform/soc/3d00000.qcom,kgsl-3d0/kgsl/kgsl-3d0/clock_mhz
+    chmod 0444 /sys/devices/platform/soc/3d00000.qcom,kgsl-3d0/devfreq/3d00000.qcom,kgsl-3d0/cur_freq
+
+on property:sys.boot_completed=1
+    chmod 0444 /sys/class/kgsl/kgsl-3d0/gpuclk
+    chmod 0444 /sys/class/kgsl/kgsl-3d0/devfreq/cur_freq
+    chmod 0444 /sys/devices/platform/soc/3d00000.qcom,kgsl-3d0/kgsl/kgsl-3d0/clock_mhz
+    chmod 0444 /sys/devices/platform/soc/3d00000.qcom,kgsl-3d0/devfreq/3d00000.qcom,kgsl-3d0/cur_freq
""",
    "Fake_lock/system/system/etc/init/hw/stark_init.rc": """+on post-fs-data
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.boot.vbmeta.device_state locked
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.secureboot.lockstate locked
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.bootloader OP5D2BL1-locked
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.product.brand_for_attestation OnePlus
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.product.manufacturer_for_attestation OnePlus
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.boot.vbmeta.invalidate_on_error yes
+    exec u:r:init:s0 root root -- /system/bin/wk -n ro.boot.vbmeta.device /dev/block/by-name/vbmeta_a
""",
    "Fake_lock/system/system/etc/selinux/stark_plat_file_contexts": "+/system/bin/wk u:object_r:wk_exec:s0\n+/system/system/bin/wk u:object_r:wk_exec:s0\n",
    "Fake_lock/system/system/etc/selinux/stark_plat_sepolicy.cil": "+(allow init wk_exec (file (read getattr map execute open execute_no_trans entrypoint)))\n",
    "Global_props/my_product/stark_build.prop": "!persist.sys.timezone=America/New_York\n!persist.sys.oplus.region=US\n!ro.product.locale=en-US\n",
}

SHARED_WK_POWER_TEXT_FIXTURES = {
    "system/system/etc/init/wukong-system-powerd.rc": """service wukong-system-powerd /system/bin/wukong-system-powerd
    class late_start
    disabled
    user system
    group system everybody
    socket wukong_system_power stream 0660 system everybody u:object_r:wukong_system_power_socket:s0

on property:sys.boot_completed=1
    start wukong-system-powerd
""",
    "system/system/etc/selinux/stark_plat_seapp_contexts": (
        "+user=_app isPrivApp=true name=com.wukong.manager "
        "domain=wukong_manager_app type=privapp_data_file levelFrom=user\n"
    ),
    "system/system/etc/selinux/stark_plat_file_contexts": (
        "+/system/bin/wukong-system-powerd u:object_r:wukong_system_powerd_exec:s0\n"
        "+/system/system/bin/wukong-system-powerd u:object_r:wukong_system_powerd_exec:s0\n"
        "+/dev/socket/wukong_system_power u:object_r:wukong_system_power_socket:s0\n"
    ),
    "system/system/etc/selinux/stark_plat_sepolicy.cil": (
        "+(type wukong_system_powerd)\n"
        "+(type wukong_system_powerd_exec)\n"
        "+(type wukong_system_power_socket)\n"
        "+(allow wukong_manager_app wukong_system_powerd (unix_stream_socket (connectto)))\n"
    ),
}
SHARED_WK_POWER_TEXT_FIXTURES["system/system/etc/init/hw/stark_init.rc"] = TEXT_FIXTURES[
    "WK_Manager/system/system/etc/init/hw/stark_init.rc"
]


def main() -> int:
    if MOD_ROOT.exists() and not MARKER.is_file():
        raise SystemExit(
            f"Refusing to modify an existing content directory without the fixture marker: {MOD_ROOT}"
        )
    if SHARED_WK_ROOT.exists() and not SHARED_WK_MARKER.is_file():
        raise SystemExit(
            "Refusing to modify an existing shared content directory without the "
            f"fixture marker: {SHARED_WK_ROOT}"
        )
    MOD_ROOT.mkdir(parents=True, exist_ok=True)
    MARKER.write_text("Generated placeholders only; never use for ROM builds.\n", encoding="utf-8")
    SHARED_WK_ROOT.mkdir(parents=True, exist_ok=True)
    SHARED_WK_MARKER.write_text(
        "Generated placeholders only; never use for ROM builds.\n", encoding="utf-8"
    )
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    count = 0
    for pack in payload["packs"]:
        target = str(pack["target"])
        if not target.startswith("MOD/"):
            continue
        version = target.split("/", 1)[1]
        for entry in pack["files"]:
            relative = str(entry["path"])
            path = MOD_ROOT / version / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            text = TEXT_FIXTURES.get(relative)
            if text is None:
                path.write_bytes(b"fixture\n")
            else:
                path.write_text(text, encoding="utf-8", newline="\n")
            count += 1
    shared = SHARED_WK_ROOT
    for relative, text in SHARED_WK_POWER_TEXT_FIXTURES.items():
        path = shared / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        count += 1
    daemon = shared / "system" / "system" / "bin" / "wukong-system-powerd"
    daemon.parent.mkdir(parents=True, exist_ok=True)
    elf = bytearray(64)
    elf[:6] = b"\x7fELF\x02\x01"
    elf[18:20] = (183).to_bytes(2, "little")
    daemon.write_bytes(elf)
    count += 1
    print(f"Materialized {count} private-content test placeholders under {MOD_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
