# Wukong ROM Studio

## Setup

```powershell
py -m pip install -r requirements.txt
```

Start the local dashboard with `RUN_UI.bat`. The Flask server binds only to
`127.0.0.1` and opens the dashboard in the default browser. `RUN.bat` remains
the legacy CLI entry point.

The optional WinUI 3 host uses the same dashboard and backend while mapping all
managed runtime data to `C:\WukongROMStudio`. See `desktop/README.md` for the
self-contained runtime and installer workflow. Source mode remains unchanged.

In New build, paste an absolute ROM ZIP path or use Browse ROM ZIP. Browse
opens the native system file picker, so ROMs can be selected from any drive.
The selected ROM directory is added to the local allowlist after validation.

## Lite, Debloat And MODs

`Lite` replaces the old `Standard` preset. It targets `Global_props`,
`Cts_Gemini`, `Fix_noti`, `Gapps`, `Chat_bubbles`, `Block_ota` and `GlobalSearch`
by default. `Plus` targets every
visible `MOD/ColorOS_700` child folder by default, while still reusing only
validated artifacts from a previous UI job.

The pipeline keeps every stage checkbox editable. Use Customize on the
`debloat` stage to edit relative removal paths, and Customize on `apply_mod`
to select multiple MOD folders. Files prefixed with `stark_` are interpreted
as line patches instead of copied verbatim. After a platform SELinux patch,
Studio refreshes `plat_sepolicy_and_mapping.sha256` as the SHA-256 digest of
`plat_sepolicy.cil`, written as 64 ASCII hex bytes plus one LF byte;
`Fix_noti` patches `oplus-services.jar` through
`bin/Windows/AMD64/apktool_3.0.2.jar`.

Android text files modified during a build are written with LF line endings.
This includes `build.prop`, init RC, SELinux CIL and repack metadata files.
Text files copied from a MOD, including XML, are normalized to LF while binary
artifacts such as APK files are copied byte-for-byte.

`Global_props` replaces the old standalone region/property pipeline stage. It
upserts the US timezone, region and locale in `my_product/build.prop`, and the
two requested Oplus camera properties in `vendor/build.prop`. These values are
applied only when `Global_props` is selected under `Apply MOD`.

`Fake_lock` uses a structured patch for `system/system/etc/init/hw/init.rc`.
The `wk` commands are injected into `on post-fs-data`, while Studio forces the
repack metadata for `system/system/bin/wk` to `0 2000 0755` and preserves both
`/system/bin/wk` SELinux aliases as `u:object_r:wk_exec:s0`.

`WK_Manager` applies a deterministic fail-fast patch manifest through
`wk_manager_patcher.py`. It patches `framework.jar`, `services.jar` and
`oplus-services.jar`, imports `STARK` classes into `smali_classes6`, preserves
the original JAR compression profile and refreshes the platform SELinux
checksum.
When a ROM version no longer matches an expected class, method or anchor, the
worker stops instead of packaging a partially patched ROM.

## Optional Telegram Notification

Credentials are read from environment variables or the ignored local file
`.wkstudio/telegram.env`. They are never shown in the dashboard:

```powershell
$env:WUKONG_TELEGRAM_BOT_TOKEN = "..."
$env:WUKONG_TELEGRAM_CHAT_ID = "..."
```

Local file format:

```text
WUKONG_TELEGRAM_BOT_TOKEN=...
WUKONG_TELEGRAM_CHAT_ID=...
WUKONG_TELEGRAM_PARSE_MODE=HTML
WUKONG_TELEGRAM_TIMEOUT=10
WUKONG_TELEGRAM_TIMEZONE=Asia/Bangkok
```

Send `/start` to the bot before configuring a private chat ID. Rotate any token
that was previously exposed or stored in source code before using this feature.

After sending `/start`, detect and save the private chat ID automatically:

```powershell
py configure_telegram.py
```

## JAR MOD Dependency

There is no standalone `framework_patch` pipeline stage. JAR patching runs only
when a selected MOD needs it. `Fix_noti` and `WK_Manager` require:

```text
bin/Windows/AMD64/apktool_3.0.2.jar
Java
```

`WK_Manager` additionally requires its `STARK` smali assets. Diagnostics shows
the apktool path, and preflight blocks only builds that select an affected MOD.

## Runtime Data

Small Studio runtime files live under `.wkstudio/`: SQLite state, job specs and
logs. Each UI build workspace is created directly under the project root with
the sanitized `version_name` read from `META-INF/com/android/metadata`, matching
the legacy CLI layout.

Studio writes a `.wkstudio-workspace.json` ownership marker before using a
version workspace. Existing project folders without that marker are never
overwritten or deleted. After `package_zip` produces a ZIP that passes final
validation, Studio removes the complete version workspace to release disk
space. Failed or cancelled workspaces remain available for diagnostics and
validated Resume jobs.
