from __future__ import annotations


LITE_DEFAULT_MODS: list[str] = [
    "Global_props",
    "Cts_Gemini",
    "Fix_noti",
    "Fix_Metis",
    "Gapps",
    "Chat_bubbles",
    "Block_ota",
    "GlobalSearch",
    "WK_Installer",
]
PLUS_DEFAULT_EXCLUDED_MODS: set[str] = {"Gallery_mod_CN"}
SHARED_MOD_NAMES: frozenset[str] = frozenset({"WK_Manager", "WK_Installer"})
