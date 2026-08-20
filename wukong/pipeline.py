from __future__ import annotations


PIPELINE_STEP_DEFINITIONS: tuple[tuple[str, str, bool], ...] = (
    ("inspect_rom", "Inspect ROM", True),
    ("extract_payload", "Extract payload", True),
    ("unpack_partitions", "Unpack partitions", True),
    ("debloat", "Remove bloatware", False),
    ("apply_mod", "Apply MOD", False),
    ("sync_configs", "Sync fs_config and SELinux contexts", True),
    ("repack_partitions", "Repack partitions", True),
    ("repack_super", "Repack super.img", True),
    ("patch_vbmeta", "Patch vbmeta", False),
    ("patch_vendor_boot", "Patch vendor_boot", False),
    ("package_zip", "Package ROM ZIP", True),
    ("notify_telegram", "Send Telegram notification", False),
)
PIPELINE_STEP_NAMES = frozenset(item[0] for item in PIPELINE_STEP_DEFINITIONS)
DEFAULT_PIPELINE_STEPS = frozenset(
    {
        "inspect_rom",
        "extract_payload",
        "unpack_partitions",
        "debloat",
        "apply_mod",
        "sync_configs",
        "repack_partitions",
        "repack_super",
        "patch_vbmeta",
        "package_zip",
    }
)
CHECKPOINT_PIPELINE_STEPS = frozenset(
    {
        "extract_payload",
        "unpack_partitions",
        "sync_configs",
        "repack_partitions",
        "repack_super",
        "patch_vbmeta",
        "patch_vendor_boot",
    }
)
