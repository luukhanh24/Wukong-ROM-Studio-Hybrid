from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from textwrap import dedent
from typing import Callable


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_STARK_DIR = ROOT_DIR / "STARK"


class WkManagerPatchError(RuntimeError):
    pass


def _write_text_lf(path: Path, content: str) -> None:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(normalized.encode("utf-8"))


@dataclass
class PatchReport:
    jar: str
    patchedMethods: int = 0
    importedSmali: int = 0


def _code(value: str) -> str:
    return dedent(value).strip("\n")


def _smali_anchor(value: str) -> str:
    return "\n".join(f"    {line}" if line else "" for line in _code(value).splitlines())


def _find_smali(decoded: Path, class_name: str) -> Path:
    relative = Path(*class_name.split(".")).with_suffix(".smali")
    matches = [
        path
        for path in decoded.rglob(relative.name)
        if tuple(path.parts[-len(relative.parts) :]) == relative.parts
    ]
    if len(matches) != 1:
        raise WkManagerPatchError(
            f"{class_name}: expected one smali file, found {len(matches)}"
        )
    return matches[0]


def _method_pattern(signature: str) -> re.Pattern[str]:
    return re.compile(
        r"(?ms)^\.method[^\n]*" + re.escape(signature) + r"[ \t]*\n.*?^\.end method[ \t]*$"
    )


def _method_name_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        r"(?ms)^\.method[^\n]*\s" + re.escape(name) + r"\([^)]*\)[^\n]*\n.*?^\.end method[ \t]*$"
    )


def _edit_method(
    decoded: Path,
    class_name: str,
    signature: str,
    marker: str,
    editor: Callable[[str], str],
) -> bool:
    path = _find_smali(decoded, class_name)
    content = path.read_text(encoding="utf-8")
    matches = list(_method_pattern(signature).finditer(content))
    if len(matches) != 1:
        raise WkManagerPatchError(
            f"{class_name}.{signature}: expected one method, found {len(matches)}"
        )
    method = matches[0].group(0)
    if marker in method:
        return False
    updated = editor(method)
    if updated == method:
        raise WkManagerPatchError(f"{class_name}.{signature}: patch made no change")
    _write_text_lf(path, content[: matches[0].start()] + updated + content[matches[0].end() :])
    return True


def _edit_method_by_name(
    decoded: Path,
    class_name: str,
    method_name: str,
    marker: str,
    editor: Callable[[str], str],
) -> bool:
    path = _find_smali(decoded, class_name)
    content = path.read_text(encoding="utf-8")
    matches = list(_method_name_pattern(method_name).finditer(content))
    if len(matches) != 1:
        raise WkManagerPatchError(
            f"{class_name}.{method_name}: expected one method, found {len(matches)}"
        )
    method = matches[0].group(0)
    if marker in method:
        return False
    updated = editor(method)
    if updated == method:
        raise WkManagerPatchError(f"{class_name}.{method_name}: patch made no change")
    _write_text_lf(path, content[: matches[0].start()] + updated + content[matches[0].end() :])
    return True


def _replace_once(content: str, anchor: str, replacement: str, label: str) -> str:
    count = content.count(anchor)
    if count != 1:
        raise WkManagerPatchError(f"{label}: expected one anchor, found {count}")
    return content.replace(anchor, replacement, 1)


def _insert_before(content: str, anchor: str, snippet: str, label: str) -> str:
    return _replace_once(content, anchor, snippet + "\n\n" + anchor, label)


def _insert_after(content: str, anchor: str, snippet: str, label: str) -> str:
    return _replace_once(content, anchor, anchor + "\n\n" + snippet, label)


def _insert_after_regex(content: str, pattern: str, snippet: str, label: str) -> str:
    matches = list(re.finditer(pattern, content, flags=re.MULTILINE))
    if len(matches) != 1:
        raise WkManagerPatchError(f"{label}: expected one regex anchor, found {len(matches)}")
    match = matches[0]
    return content[: match.end()] + "\n\n" + snippet + content[match.end() :]


def _patch_gemini_button_in_register_settings(method: str) -> str:
    gap = r"(?:(?:[ \t]*\n)|(?:[ \t]*\.line[^\n]*\n))*"
    pattern = re.compile(
        r"(?m)"
        r"^[ \t]*invoke-static \{\}, "
        r"Lcom/oplus/content/OplusFeatureConfigManager;->getInsta(?:cne|nce)"
        r"\(\)Lcom/oplus/content/OplusFeatureConfigManager;[ \t]*\n"
        + gap
        + r"[ \t]*move-result-object (?P<manager>[vp][0-9]+)[ \t]*\n"
        + gap
        + r"[ \t]*const-string(?:/jumbo)? (?P<feature>[vp][0-9]+), "
        + re.escape('"oplus.software.speech_assist_for_breeno"')
        + r"[ \t]*\n"
        + gap
        + r"[ \t]*invoke-virtual \{(?P=manager), (?P=feature)\}, "
        r"Lcom/oplus/content/OplusFeatureConfigManager;->hasFeature"
        r"\(Ljava/lang/String;\)Z[ \t]*\n"
        + gap
        + r"[ \t]*move-result (?P<result>[vp][0-9]+)[ \t]*$"
    )
    matches = list(pattern.finditer(method))
    if len(matches) != 1:
        raise WkManagerPatchError(
            f"PhoneWindowManagerExtImpl registerSettingsForOplusLocked gemini button: "
            f"expected one speech assist feature probe, found {len(matches)}"
        )
    result_register = matches[0].group("result")
    replacement = _code(
        f"""
            const-string/jumbo {result_register}, "gemini_button"

            invoke-static {{{result_register}}}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

            move-result {result_register}

            if-eqz {result_register}, :cond_wk_gemini_button

            const/4 {result_register}, 0x0

            goto :goto_wk_gemini_button

            :cond_wk_gemini_button
            const/4 {result_register}, 0x1

            :goto_wk_gemini_button
        """
    )
    return method[: matches[0].start()] + replacement + method[matches[0].end() :]


def _insert_before_return_after_trace(
    content: str,
    trace_registers: str,
    return_register: str,
    snippet: str,
    label: str,
) -> str:
    pattern = re.compile(
        rf"(?m)"
        rf"(^[ \t]*invoke-static \{{{re.escape(trace_registers)}\}}, "
        rf"Landroid/os/Trace;->traceEnd\(J\)V[ \t]*\n"
        rf"(?:(?:[ \t]*\n)|(?:[ \t]*\.line [^\n]+\n))*)"
        rf"([ \t]*return-object {re.escape(return_register)}[ \t]*$)"
    )
    matches = list(pattern.finditer(content))
    if len(matches) != 1:
        raise WkManagerPatchError(f"{label}: expected one anchor, found {len(matches)}")
    match = matches[0]
    return (
        content[: match.start()]
        + match.group(1)
        + "\n"
        + snippet
        + "\n\n"
        + match.group(2)
        + content[match.end() :]
    )


def _replace_method(
    decoded: Path,
    class_name: str,
    signature: str,
    marker: str,
    replacement: str,
) -> bool:
    return _edit_method(decoded, class_name, signature, marker, lambda _method: replacement)


def _add_local_registers(method: str, count: int, parameter_words: int) -> tuple[str, int]:
    locals_match = re.search(r"(?m)^([ \t]*)\.locals ([0-9]+)[ \t]*$", method)
    if locals_match:
        base = int(locals_match.group(2))
        updated = (
            method[: locals_match.start()]
            + f"{locals_match.group(1)}.locals {base + count}"
            + method[locals_match.end() :]
        )
        return updated, base
    registers_match = re.search(r"(?m)^([ \t]*)\.registers ([0-9]+)[ \t]*$", method)
    if not registers_match:
        raise WkManagerPatchError("method has no .locals or .registers directive")
    registers = int(registers_match.group(2))
    base = registers - parameter_words
    if base < 0:
        raise WkManagerPatchError("method register count is lower than its parameter count")
    updated = (
        method[: registers_match.start()]
        + f"{registers_match.group(1)}.registers {registers + count}"
        + method[registers_match.end() :]
    )
    return updated, base


def _patch_before(
    decoded: Path,
    class_name: str,
    signature: str,
    anchor: str,
    snippet: str,
    marker: str,
) -> bool:
    return _edit_method(
        decoded,
        class_name,
        signature,
        marker,
        lambda method: _insert_before(method, anchor, snippet, f"{class_name}.{signature}"),
    )


def _patch_after(
    decoded: Path,
    class_name: str,
    signature: str,
    anchor: str,
    snippet: str,
    marker: str,
) -> bool:
    return _edit_method(
        decoded,
        class_name,
        signature,
        marker,
        lambda method: _insert_after(method, anchor, snippet, f"{class_name}.{signature}"),
    )


def _patch_after_directive(
    decoded: Path,
    class_name: str,
    signature: str,
    directive_pattern: str,
    snippet: str,
    marker: str,
) -> bool:
    return _edit_method(
        decoded,
        class_name,
        signature,
        marker,
        lambda method: _insert_after_regex(
            method,
            directive_pattern,
            snippet,
            f"{class_name}.{signature}",
        ),
    )


def _copy_stark_smali(decoded: Path, stark_dir: Path) -> int:
    if not stark_dir.is_dir():
        raise WkManagerPatchError(f"STARK directory is missing: {stark_dir}")
    destination = decoded / "smali_classes6"
    imported = 0
    for source in sorted(stark_dir.rglob("*.smali")):
        relative = source.relative_to(stark_dir)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.read_bytes() == source.read_bytes():
            continue
        if target.exists():
            raise WkManagerPatchError(f"STARK target already exists with different content: {target}")
        shutil.copy2(source, target)
        imported += 1
    if imported == 0 and not destination.is_dir():
        raise WkManagerPatchError("No STARK smali files were imported")
    return imported


def patch_framework_decoded(decoded: Path, stark_dir: Path = DEFAULT_STARK_DIR) -> dict[str, int | str]:
    report = PatchReport(jar="framework.jar")
    report.patchedMethods += _patch_before(
        decoded,
        "android.app.ApplicationPackageManager",
        "hasSystemFeature(Ljava/lang/String;I)Z",
        "    iget-boolean v1, p0, Landroid/app/ApplicationPackageManager;->mUseSystemFeaturesCache:Z",
        _code(
            """
                invoke-static {p1, p2}, Lcom/wukong/manager/WukongPackageManagerHook;->maybeOverride(Ljava/lang/String;I)Ljava/lang/Boolean;

                move-result-object v0

                if-eqz v0, :cond_wk

                invoke-virtual {v0}, Ljava/lang/Boolean;->booleanValue()Z

                move-result v1

                return v1

                :cond_wk
            """
        ),
        "WukongPackageManagerHook;->maybeOverride",
    )
    report.patchedMethods += _patch_before(
        decoded,
        "android.app.Instrumentation",
        "newApplication(Ljava/lang/Class;Landroid/content/Context;)Landroid/app/Application;",
        "    return-object v0",
        "    invoke-static {p1}, Lcom/wukong/manager/WukongInstrumentationHook;->onApplicationAttached(Landroid/content/Context;)V",
        "WukongInstrumentationHook;->onApplicationAttached",
    )
    report.patchedMethods += _patch_before(
        decoded,
        "android.app.Instrumentation",
        "newApplication(Ljava/lang/ClassLoader;Ljava/lang/String;Landroid/content/Context;)Landroid/app/Application;",
        "    return-object v0",
        "    invoke-static {p3}, Lcom/wukong/manager/WukongInstrumentationHook;->onApplicationAttached(Landroid/content/Context;)V",
        "WukongInstrumentationHook;->onApplicationAttached",
    )

    def patch_content_provider_call(method: str) -> str:
        updated, local = _add_local_registers(method, 3, parameter_words=6)
        identity, value, owner = (f"v{local + offset}" for offset in range(3))
        first = _code(
            f"""
                invoke-static {{p1, p2, p3, p4}}, Lcom/wukong/manager/WukongHmaPolicyBridge;->shouldExecuteSettingsCallAsManager(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)Z

                move-result v0

                if-eqz v0, :cond_wk

                const-string v0, "call: "

                const-wide/16 v1, 0x40

                invoke-static {{v1, v2, v0, p2}}, Landroid/content/ContentProvider;->-$$Nest$smtraceBegin(JLjava/lang/String;Ljava/lang/String;)V

                iget-object v0, p0, Landroid/content/ContentProvider$Transport;->this$0:Landroid/content/ContentProvider;

                invoke-virtual {{v0}}, Landroid/content/ContentProvider;->clearCallingIdentity()Landroid/content/ContentProvider$CallingIdentity;

                move-result-object {identity}

                :try_start_wk
                iget-object {value}, p0, Landroid/content/ContentProvider$Transport;->mInterface:Landroid/content/ContentInterface;

                invoke-interface {{{value}, p2, p3, p4, p5}}, Landroid/content/ContentInterface;->call(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)Landroid/os/Bundle;

                move-result-object {value}
                :try_end_wk
                .catchall {{:try_start_wk .. :try_end_wk}} :catchall_wk

                iget-object {owner}, p0, Landroid/content/ContentProvider$Transport;->this$0:Landroid/content/ContentProvider;

                invoke-virtual {{{owner}, {identity}}}, Landroid/content/ContentProvider;->restoreCallingIdentity(Landroid/content/ContentProvider$CallingIdentity;)V

                invoke-static {{v1, v2}}, Landroid/os/Trace;->traceEnd(J)V

                return-object {value}

                :catchall_wk
                move-exception {value}

                iget-object {owner}, p0, Landroid/content/ContentProvider$Transport;->this$0:Landroid/content/ContentProvider;

                invoke-virtual {{{owner}, {identity}}}, Landroid/content/ContentProvider;->restoreCallingIdentity(Landroid/content/ContentProvider$CallingIdentity;)V

                invoke-static {{v1, v2}}, Landroid/os/Trace;->traceEnd(J)V

                throw {value}

                :cond_wk
            """
        )
        updated = _insert_after(
            updated,
            "    invoke-static {p5, v0}, Landroid/os/Bundle;->setDefusable(Landroid/os/Bundle;Z)Landroid/os/Bundle;",
            first,
            "ContentProvider.Transport.call manager path",
        )
        return _insert_before_return_after_trace(
            updated,
            "v1, v2",
            "v3",
            _code(
                """
                    invoke-static {p1, p2, p3, p4, v3}, Lcom/wukong/manager/WukongHmaPolicyBridge;->maybeSpoofSettingsCall(Ljava/lang/Object;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)Landroid/os/Bundle;

                    move-result-object v3
                """
            ),
            "ContentProvider.Transport.call spoof return",
        )

    report.patchedMethods += _edit_method(
        decoded,
        "android.content.ContentProvider$Transport",
        "call(Landroid/content/AttributionSource;Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Landroid/os/Bundle;)Landroid/os/Bundle;",
        "WukongHmaPolicyBridge;->shouldExecuteSettingsCallAsManager",
        patch_content_provider_call,
    )

    def patch_content_provider_query(method: str) -> str:
        return _insert_before_return_after_trace(
            method,
            "v2, v3",
            "v1",
            _code(
                """
                    invoke-static {p1, p2, v1}, Lcom/wukong/manager/WukongHmaPolicyBridge;->maybeSpoofSettingsQuery(Ljava/lang/Object;Landroid/net/Uri;Landroid/database/Cursor;)Landroid/database/Cursor;

                    move-result-object v1
                """
            ),
            "ContentProvider.Transport.query spoof return",
        )

    report.patchedMethods += _edit_method(
        decoded,
        "android.content.ContentProvider$Transport",
        "query(Landroid/content/AttributionSource;Landroid/net/Uri;[Ljava/lang/String;Landroid/os/Bundle;Landroid/os/ICancellationSignal;)Landroid/database/Cursor;",
        "WukongHmaPolicyBridge;->maybeSpoofSettingsQuery",
        patch_content_provider_query,
    )
    report.patchedMethods += _edit_method(
        decoded,
        "android.security.keystore2.AndroidKeyStoreKeyPairGeneratorSpi",
        "generateKeyPair()Ljava/security/KeyPair;",
        "WukongFrameworkBridge;->maybeGenerateKey",
        lambda method: _insert_after(
            _insert_after(
                method,
                _smali_anchor(
                    """
                        invoke-direct {p0}, Landroid/security/keystore2/AndroidKeyStoreKeyPairGeneratorSpi;->constructKeyGenerationArguments()Ljava/util/Collection;

                        move-result-object v10
                    """
                ),
                _code(
                    """
                        move v13, v5

                        invoke-static/range {v8 .. v13}, Lcom/wukong/manager/WukongFrameworkBridge;->maybeGenerateKey(Landroid/system/keystore2/KeyDescriptor;Landroid/system/keystore2/KeyDescriptor;Ljava/util/Collection;I[BI)Landroid/system/keystore2/KeyMetadata;

                        move-result-object v0

                        if-nez v0, :cond_wk
                    """
                ),
                "AndroidKeyStoreKeyPairGeneratorSpi pre-generate",
            ),
            _smali_anchor(
                """
                    invoke-virtual/range {v7 .. v12}, Landroid/security/KeyStoreSecurityLevel;->generateKey(Landroid/system/keystore2/KeyDescriptor;Landroid/system/keystore2/KeyDescriptor;Ljava/util/Collection;I[B)Landroid/system/keystore2/KeyMetadata;

                    move-result-object v0
                """
            ),
            "    :cond_wk",
            "AndroidKeyStoreKeyPairGeneratorSpi post-generate",
        ),
    )
    report.patchedMethods += _replace_method(
        decoded,
        "android.security.keystore2.AndroidKeyStorePublicKey",
        "getCertificate()[B",
        "WukongFrameworkBridge;->maybePatchCertificate",
        _code(
            """
                .method public blacklist getCertificate()[B
                    .registers 4

                    invoke-virtual {p0}, Landroid/security/keystore2/AndroidKeyStoreKey;->getUserKeyDescriptor()Landroid/system/keystore2/KeyDescriptor;

                    move-result-object v0

                    if-eqz v0, :cond_0

                    iget-object v0, v0, Landroid/system/keystore2/KeyDescriptor;->alias:Ljava/lang/String;

                    goto :goto_0

                    :cond_0
                    const/4 v0, 0x0

                    :goto_0
                    iget-object v1, p0, Landroid/security/keystore2/AndroidKeyStorePublicKey;->mCertificate:[B

                    iget-object v2, p0, Landroid/security/keystore2/AndroidKeyStorePublicKey;->mCertificateChain:[B

                    invoke-static {v0, v1, v2}, Lcom/wukong/manager/WukongFrameworkBridge;->maybePatchCertificate(Ljava/lang/String;[B[B)[B

                    move-result-object v0

                    return-object v0
                .end method
            """
        ),
    )
    report.patchedMethods += _replace_method(
        decoded,
        "android.security.keystore2.AndroidKeyStorePublicKey",
        "getCertificateChain()[B",
        "WukongFrameworkBridge;->maybePatchCertificateChain",
        _code(
            """
                .method public blacklist getCertificateChain()[B
                    .registers 4

                    invoke-virtual {p0}, Landroid/security/keystore2/AndroidKeyStoreKey;->getUserKeyDescriptor()Landroid/system/keystore2/KeyDescriptor;

                    move-result-object v0

                    if-eqz v0, :cond_0

                    iget-object v0, v0, Landroid/system/keystore2/KeyDescriptor;->alias:Ljava/lang/String;

                    goto :goto_0

                    :cond_0
                    const/4 v0, 0x0

                    :goto_0
                    iget-object v1, p0, Landroid/security/keystore2/AndroidKeyStorePublicKey;->mCertificate:[B

                    iget-object v2, p0, Landroid/security/keystore2/AndroidKeyStorePublicKey;->mCertificateChain:[B

                    invoke-static {v0, v1, v2}, Lcom/wukong/manager/WukongFrameworkBridge;->maybePatchCertificateChain(Ljava/lang/String;[B[B)[B

                    move-result-object v0

                    return-object v0
                .end method
            """
        ),
    )
    report.patchedMethods += _patch_after(
        decoded,
        "android.security.keystore2.AndroidKeyStoreSpi",
        "getKeyMetadata(Ljava/lang/String;)Landroid/system/keystore2/KeyEntryResponse;",
        "    invoke-virtual {v1, v0}, Landroid/security/KeyStore2;->getKeyEntry(Landroid/system/keystore2/KeyDescriptor;)Landroid/system/keystore2/KeyEntryResponse;",
        _code(
            """
                move-result-object v1

                invoke-static {p1, v1}, Lcom/wukong/manager/WukongFrameworkBridge;->maybePatchKeyEntryResponse(Ljava/lang/String;Landroid/system/keystore2/KeyEntryResponse;)Landroid/system/keystore2/KeyEntryResponse;
            """
        ),
        "WukongFrameworkBridge;->maybePatchKeyEntryResponse",
    )
    report.patchedMethods += _patch_after(
        decoded,
        "android.security.keystore2.AndroidKeyStoreSpi",
        "engineGetKey(Ljava/lang/String;[C)Ljava/security/Key;",
        "    invoke-static {v0, p1, v1}, Landroid/security/keystore2/AndroidKeyStoreProvider;->loadAndroidKeyStoreKeyFromKeystore(Landroid/security/KeyStore2;Ljava/lang/String;I)Landroid/security/keystore2/AndroidKeyStoreKey;",
        _code(
            """
                move-result-object v0

                invoke-static {p1, v0}, Lcom/wukong/manager/WukongFrameworkBridge;->maybeSwapLoadedKey(Ljava/lang/String;Ljava/security/Key;)Ljava/security/Key;
            """
        ),
        "WukongFrameworkBridge;->maybeSwapLoadedKey",
    )
    report.patchedMethods += _replace_method(
        decoded,
        "android.security.KeyStore2",
        "deleteKey(Landroid/system/keystore2/KeyDescriptor;)V",
        "WukongFrameworkBridge;->deleteKey",
        _code(
            """
                .method public blacklist deleteKey(Landroid/system/keystore2/KeyDescriptor;)V
                    .registers 3
                    .annotation system Ldalvik/annotation/Throws;
                        value = {
                            Landroid/security/KeyStoreException;
                        }
                    .end annotation

                    invoke-static {}, Landroid/os/StrictMode;->noteDiskWrite()V

                    invoke-static {p1}, Lcom/wukong/manager/WukongFrameworkBridge;->deleteKey(Landroid/system/keystore2/KeyDescriptor;)Z

                    move-result v0

                    if-nez v0, :cond_0

                    new-instance v0, Landroid/security/KeyStore2$$ExternalSyntheticLambda4;

                    invoke-direct {v0, p1}, Landroid/security/KeyStore2$$ExternalSyntheticLambda4;-><init>(Landroid/system/keystore2/KeyDescriptor;)V

                    invoke-virtual {p0, v0}, Landroid/security/KeyStore2;->handleRemoteExceptionWithRetry(Landroid/security/KeyStore2$CheckedRemoteRequest;)Ljava/lang/Object;

                    :cond_0
                    return-void
                .end method
            """
        ),
    )
    report.patchedMethods += _replace_method(
        decoded,
        "android.security.KeyStore2",
        "getKeyEntry(Landroid/system/keystore2/KeyDescriptor;)Landroid/system/keystore2/KeyEntryResponse;",
        "WukongFrameworkBridge;->preGetKeyEntry",
        _code(
            """
                .method public blacklist getKeyEntry(Landroid/system/keystore2/KeyDescriptor;)Landroid/system/keystore2/KeyEntryResponse;
                    .registers 3
                    .annotation system Ldalvik/annotation/Throws;
                        value = {
                            Landroid/security/KeyStoreException;
                        }
                    .end annotation

                    invoke-static {}, Landroid/os/StrictMode;->noteDiskRead()V

                    invoke-static {p1}, Lcom/wukong/manager/WukongFrameworkBridge;->preGetKeyEntry(Landroid/system/keystore2/KeyDescriptor;)Landroid/system/keystore2/KeyEntryResponse;

                    move-result-object v0

                    if-nez v0, :cond_0

                    new-instance v0, Landroid/security/KeyStore2$$ExternalSyntheticLambda8;

                    invoke-direct {v0, p1}, Landroid/security/KeyStore2$$ExternalSyntheticLambda8;-><init>(Landroid/system/keystore2/KeyDescriptor;)V

                    invoke-virtual {p0, v0}, Landroid/security/KeyStore2;->handleRemoteExceptionWithRetry(Landroid/security/KeyStore2$CheckedRemoteRequest;)Ljava/lang/Object;

                    move-result-object v0

                    check-cast v0, Landroid/system/keystore2/KeyEntryResponse;

                    invoke-static {p1, v0}, Lcom/wukong/manager/WukongFrameworkBridge;->postGetKeyEntry(Landroid/system/keystore2/KeyDescriptor;Landroid/system/keystore2/KeyEntryResponse;)Landroid/system/keystore2/KeyEntryResponse;

                    move-result-object v0

                    :cond_0
                    return-object v0
                .end method
            """
        ),
    )
    report.importedSmali = _copy_stark_smali(decoded, stark_dir)
    return asdict(report)


def patch_services_decoded(decoded: Path) -> dict[str, int | str]:
    report = PatchReport(jar="services.jar")
    before_patches = [
        (
            "com.android.server.accessibility.AccessibilityManagerService",
            "addClient(Landroid/view/accessibility/IAccessibilityManagerClient;I)J",
            "    iget-object v0, p0, Lcom/android/server/accessibility/AccessibilityManagerService;->mServiceExt:Lcom/android/server/accessibility/IAccessibilityManagerServiceExt;",
            """
                invoke-static {}, Landroid/os/Binder;->getCallingUid()I

                move-result v0

                invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->shouldHideAccessibilityForUid(I)Z

                move-result v0

                if-eqz v0, :cond_wk

                const-wide/16 v0, 0x0

                return-wide v0

                :cond_wk
            """,
            "WukongHmaPolicyBridge;->shouldHideAccessibilityForUid",
        ),
        (
            "com.android.server.accessibility.AccessibilityManagerService",
            "getEnabledAccessibilityServiceList(II)Ljava/util/List;",
            "    iget-object v0, p0, Lcom/android/server/accessibility/AccessibilityManagerService;->mLock:Ljava/lang/Object;",
            """
                invoke-static {}, Landroid/os/Binder;->getCallingUid()I

                move-result v0

                invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->shouldHideAccessibilityForUid(I)Z

                move-result v0

                if-eqz v0, :cond_wk

                invoke-static {}, Ljava/util/Collections;->emptyList()Ljava/util/List;

                move-result-object v0

                return-object v0

                :cond_wk
            """,
            "WukongHmaPolicyBridge;->shouldHideAccessibilityForUid",
        ),
    ]
    for class_name, signature, anchor, snippet, marker in before_patches:
        report.patchedMethods += _patch_before(decoded, class_name, signature, anchor, _code(snippet), marker)
    report.patchedMethods += _edit_method(
        decoded,
        "com.android.server.am.ActivityManagerService",
        "forceStopPackage(Ljava/lang/String;IILjava/lang/String;)V",
        "WukongHmaPolicyBridge;->isManagerCallerUid",
        lambda method: _insert_before(
            _insert_after(
                method,
                _smali_anchor(
                    """
                        invoke-virtual {v1, v0}, Lcom/android/server/am/ActivityManagerService;->checkCallingPermission(Ljava/lang/String;)I

                        move-result v0
                    """
                ),
                _code(
                    """
                        if-eqz v0, :cond_wk

                        invoke-static {}, Landroid/os/Binder;->getCallingUid()I

                        move-result v0

                        invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->isManagerCallerUid(I)Z

                        move-result v0
                    """
                ),
                "ActivityManagerService.forceStopPackage permission",
            ),
            _smali_anchor(
                """
                    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

                    move-result v4
                """
            ),
            "    :cond_wk",
            "ActivityManagerService.forceStopPackage label",
        ),
    )
    report.patchedMethods += _patch_before(
        decoded,
        "com.android.server.am.ActivityManagerService",
        "systemReady(Ljava/lang/Runnable;Lcom/android/server/utils/TimingsTraceAndSlog;)V",
        _smali_anchor(
            """
                iget-object v0, v1, Lcom/android/server/am/ActivityManagerService;->mActivityManagerServiceExt:Lcom/android/server/am/IActivityManagerServiceExt;

                iget-object v3, v1, Lcom/android/server/am/ActivityManagerService;->mUiContext:Landroid/content/Context;
            """
        ),
        _code(
            """
                iget-object v0, v1, Lcom/android/server/am/ActivityManagerService;->mContext:Landroid/content/Context;

                invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->registerPolicySyncReceiver(Landroid/content/Context;)V
            """
        ),
        "WukongHmaPolicyBridge;->registerPolicySyncReceiver",
    )
    below_register_patches = [
        (
            "com.android.server.pm.AppsFilterBase",
            "shouldFilterApplication(Lcom/android/server/pm/snapshot/PackageDataSnapshot;ILjava/lang/Object;Lcom/android/server/pm/pkg/PackageStateInternal;I)Z",
            """
                if-eqz p4, :cond_wk

                invoke-interface {p4}, Lcom/android/server/pm/pkg/PackageState;->getPackageName()Ljava/lang/String;

                move-result-object v0

                invoke-interface {p4}, Lcom/android/server/pm/pkg/PackageState;->isSystem()Z

                move-result v2

                invoke-static {p2, v0, v2}, Lcom/wukong/manager/WukongHmaPolicyBridge;->shouldHidePackageForUid(ILjava/lang/String;Z)Z

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x1

                return v0

                :cond_wk
            """,
        ),
        (
            "com.android.server.pm.ComputerEngine",
            "getApplicationInfoInternal(Ljava/lang/String;JII)Landroid/content/pm/ApplicationInfo;",
            """
                const/4 v0, 0x0

                invoke-static {p4, p1, v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->shouldHidePackageForUid(ILjava/lang/String;Z)Z

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x0

                return-object v0

                :cond_wk
            """,
        ),
        (
            "com.android.server.pm.ComputerEngine",
            "getPackageInfoInternal(Ljava/lang/String;JJII)Landroid/content/pm/PackageInfo;",
            """
                const/4 v0, 0x0

                invoke-static {p6, p1, v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->shouldHidePackageForUid(ILjava/lang/String;Z)Z

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x0

                return-object v0

                :cond_wk
            """,
        ),
    ]
    for class_name, signature, snippet in below_register_patches:
        report.patchedMethods += _patch_after_directive(
            decoded,
            class_name,
            signature,
            r"^[ \t]*\.(?:registers|locals) [0-9]+[ \t]*$",
            _code(snippet),
            "WukongHmaPolicyBridge;->shouldHidePackageForUid",
        )
    report.patchedMethods += _replace_method(
        decoded,
        "com.android.server.power.PowerManagerService$BinderService",
        "reboot(ZLjava/lang/String;Z)V",
        "WukongHmaPolicyBridge;->isManagerCallerUid",
        _code(
            """
                .method public reboot(ZLjava/lang/String;Z)V
                    .registers 8

                    const/4 v2, 0x0

                    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

                    move-result v0

                    invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->isManagerCallerUid(I)Z

                    move-result v0

                    if-nez v0, :cond_0

                    iget-object v0, p0, Lcom/android/server/power/PowerManagerService$BinderService;->this$0:Lcom/android/server/power/PowerManagerService;

                    invoke-static {v0}, Lcom/android/server/power/PowerManagerService;->-$$Nest$fgetmContext(Lcom/android/server/power/PowerManagerService;)Landroid/content/Context;

                    move-result-object v0

                    const-string v1, "android.permission.REBOOT"

                    invoke-virtual {v0, v1, v2}, Landroid/content/Context;->enforceCallingOrSelfPermission(Ljava/lang/String;Ljava/lang/String;)V

                    :cond_0
                    const-string v0, "recovery"

                    invoke-virtual {v0, p2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

                    move-result v0

                    if-nez v0, :cond_1

                    const-string v0, "recovery-update"

                    invoke-virtual {v0, p2}, Ljava/lang/Object;->equals(Ljava/lang/Object;)Z

                    move-result v0

                    if-eqz v0, :cond_2

                    :cond_1
                    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

                    move-result v0

                    invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->isManagerCallerUid(I)Z

                    move-result v0

                    if-nez v0, :cond_2

                    iget-object v0, p0, Lcom/android/server/power/PowerManagerService$BinderService;->this$0:Lcom/android/server/power/PowerManagerService;

                    invoke-static {v0}, Lcom/android/server/power/PowerManagerService;->-$$Nest$fgetmContext(Lcom/android/server/power/PowerManagerService;)Landroid/content/Context;

                    move-result-object v0

                    const-string v1, "android.permission.RECOVERY"

                    invoke-virtual {v0, v1, v2}, Landroid/content/Context;->enforceCallingOrSelfPermission(Ljava/lang/String;Ljava/lang/String;)V

                    :cond_2
                    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

                    move-result v0

                    invoke-static {v0, p2}, Lcom/android/server/power/ShutdownCheckPoints;->recordCheckPoint(ILjava/lang/String;)V

                    invoke-static {}, Landroid/os/Binder;->clearCallingIdentity()J

                    move-result-wide v0

                    :try_start_0
                    iget-object v2, p0, Lcom/android/server/power/PowerManagerService$BinderService;->this$0:Lcom/android/server/power/PowerManagerService;

                    const/4 v3, 0x1

                    invoke-static {v2, v3, p1, p2, p3}, Lcom/android/server/power/PowerManagerService;->-$$Nest$mshutdownOrRebootInternal(Lcom/android/server/power/PowerManagerService;IZLjava/lang/String;Z)V
                    :try_end_0
                    .catchall {:try_start_0 .. :try_end_0} :catchall_0

                    invoke-static {v0, v1}, Landroid/os/Binder;->restoreCallingIdentity(J)V

                    nop

                    return-void

                    :catchall_0
                    move-exception v2

                    invoke-static {v0, v1}, Landroid/os/Binder;->restoreCallingIdentity(J)V

                    throw v2
                .end method
            """
        ),
    )
    report.patchedMethods += _replace_method(
        decoded,
        "com.android.server.power.PowerManagerService$BinderService",
        "shutdown(ZLjava/lang/String;Z)V",
        "WukongHmaPolicyBridge;->isManagerCallerUid",
        _code(
            """
                .method public shutdown(ZLjava/lang/String;Z)V
                    .registers 8

                    const/4 v2, 0x0

                    invoke-static {}, Landroid/os/Binder;->getCallingUid()I

                    move-result v0

                    invoke-static {v0}, Lcom/wukong/manager/WukongHmaPolicyBridge;->isManagerCallerUid(I)Z

                    move-result v0

                    if-nez v0, :cond_0

                    iget-object v0, p0, Lcom/android/server/power/PowerManagerService$BinderService;->this$0:Lcom/android/server/power/PowerManagerService;

                    invoke-static {v0}, Lcom/android/server/power/PowerManagerService;->-$$Nest$fgetmContext(Lcom/android/server/power/PowerManagerService;)Landroid/content/Context;

                    move-result-object v0

                    const-string v1, "android.permission.REBOOT"

                    invoke-virtual {v0, v1, v2}, Landroid/content/Context;->enforceCallingOrSelfPermission(Ljava/lang/String;Ljava/lang/String;)V

                    :cond_0
                    invoke-static {}, Landroid/os/Binder;->getCallingPid()I

                    move-result v0

                    invoke-static {v0, p2}, Lcom/android/server/power/ShutdownCheckPoints;->recordCheckPoint(ILjava/lang/String;)V

                    invoke-static {}, Landroid/os/Binder;->clearCallingIdentity()J

                    move-result-wide v0

                    :try_start_0
                    iget-object v2, p0, Lcom/android/server/power/PowerManagerService$BinderService;->this$0:Lcom/android/server/power/PowerManagerService;

                    const/4 v3, 0x0

                    invoke-static {v2, v3, p1, p2, p3}, Lcom/android/server/power/PowerManagerService;->-$$Nest$mshutdownOrRebootInternal(Lcom/android/server/power/PowerManagerService;IZLjava/lang/String;Z)V
                    :try_end_0
                    .catchall {:try_start_0 .. :try_end_0} :catchall_0

                    invoke-static {v0, v1}, Landroid/os/Binder;->restoreCallingIdentity(J)V

                    nop

                    return-void

                    :catchall_0
                    move-exception v2

                    invoke-static {v0, v1}, Landroid/os/Binder;->restoreCallingIdentity(J)V

                    throw v2
                .end method
            """
        ),
    )
    simple_directive_patches = [
        (
            "com.android.server.devicepolicy.DevicePolicyCacheImpl",
            "isScreenCaptureAllowed(I)Z",
            r'^[ \t]*\.param p1, "userHandle".*$',
            """
                const-string/jumbo v0, "disable_flag_secure"

                invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x1

                return v0

                :cond_wk
            """,
            "disable_flag_secure",
        ),
        (
            "com.android.server.devicepolicy.DevicePolicyManagerService",
            "getScreenCaptureDisabled(Landroid/content/ComponentName;IZ)Z",
            r'^[ \t]*\.param p3, "parent".*$',
            """
                const-string/jumbo v0, "disable_flag_secure"

                invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x0

                return v0

                :cond_wk
            """,
            "disable_flag_secure",
        ),
        (
            "com.android.server.wm.DisplayContent",
            "hasSecureWindowOnScreen()Z",
            r"^[ \t]*\.(?:registers|locals) [0-9]+[ \t]*$",
            """
                const-string/jumbo v0, "disable_flag_secure"

                invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x0

                return v0

                :cond_wk
            """,
            "disable_flag_secure",
        ),
        (
            "com.android.server.wm.WindowManagerService",
            "notifyScreenshotListeners(I)Ljava/util/List;",
            r"^[ \t]*\.end annotation[ \t]*$",
            """
                const-string/jumbo v0, "disable_flag_secure"

                invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                new-instance v0, Ljava/util/ArrayList;

                invoke-direct {v0}, Ljava/util/ArrayList;-><init>()V

                return-object v0

                :cond_wk
            """,
            "disable_flag_secure",
        ),
        (
            "com.android.server.wm.WindowState",
            "isSecureLocked()Z",
            r"^[ \t]*\.(?:registers|locals) [0-9]+[ \t]*$",
            """
                const-string/jumbo v0, "disable_flag_secure"

                invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x0

                return v0

                :cond_wk
            """,
            "disable_flag_secure",
        ),
        (
            "com.android.server.audio.MediaFocusControl",
            "requestAudioFocus(Landroid/media/AudioAttributes;ILandroid/os/IBinder;Landroid/media/IAudioFocusDispatcher;Ljava/lang/String;Ljava/lang/String;IIZIZ)I",
            r'^[ \t]*\.param p11, "permissionOverridesCheck".*$',
            """
                const-string/jumbo v0, "multi_audio"

                invoke-static {v0}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                const/4 v0, 0x1

                return v0

                :cond_wk
            """,
            "multi_audio",
        ),
    ]
    for class_name, signature, directive, snippet, marker in simple_directive_patches:
        report.patchedMethods += _patch_after_directive(
            decoded, class_name, signature, directive, _code(snippet), marker
        )
    return asdict(report)


def patch_oplus_services_decoded(decoded: Path) -> dict[str, int | str]:
    report = PatchReport(jar="oplus-services.jar")
    simple_patches = [
        ("com.android.server.wm.IOplusWindowManagerServiceEx", "dumpWindowsForScreenShot(Ljava/io/PrintWriter;Ljava/lang/String;[Ljava/lang/String;)Z", r'^[ \t]*\.param p3, "args".*$', "disable_flag_secure", "0x1", "return v0"),
        ("com.android.server.wm.OplusLongshotMainWindow", "hasSecure()Z", r"^[ \t]*\.(?:registers|locals) [0-9]+[ \t]*$", "disable_flag_secure", "0x0", "return v0"),
        ("com.android.server.wm.OplusWindowDumpUtils", "isSecureWindow(Lcom/android/server/wm/WindowState;)Z", r'^[ \t]*\.param p1, "w".*$', "disable_flag_secure", "0x0", "return v0"),
        ("com.android.server.wm.OplusWindowManagerServiceEx", "dumpWindowsForScreenShot(Ljava/io/PrintWriter;Ljava/lang/String;[Ljava/lang/String;)Z", r'^[ \t]*\.param p3, "args".*$', "disable_flag_secure", "0x1", "return v0"),
        ("com.android.server.wm.FlexibleWindowUtils", "getUnSupportRatiosInFlexibleTask(Ljava/lang/String;)Ljava/lang/String;", r'^[ \t]*\.param p0, "packageName".*$', "black_window", "0x0", "return-object v0"),
        ("com.android.server.wm.FlexibleWindowUtils", "isInMultiWindowFlexibleBlackList(Ljava/lang/String;)Z", r'^[ \t]*\.param p0, "packageName".*$', "black_window", "0x0", "return v0"),
        ("com.android.server.wm.FlexibleWindowUtils", "isSupportFlexibleWindow(Landroid/content/Intent;Landroid/content/pm/ActivityInfo;)Z", r'^[ \t]*\.param p1, "activityInfo".*$', "black_window", "0x1", "return v0"),
        ("com.android.server.wm.FlexibleWindowUtils", "isSupportFlexibleWindow(Lcom/android/server/wm/Task;)Z", r'^[ \t]*\.param p0, "task".*$', "black_window", "0x1", "return v0"),
        ("com.android.server.wm.FlexibleWindowUtils", "isSupportFlexibleWindow(Ljava/lang/String;Ljava/lang/String;)Z", r'^[ \t]*\.param p1, "componentName".*$', "black_window", "0x1", "return v0"),
        ("com.android.server.wm.FlexibleWindowManagerService", "getMaxWinNum(I)I", r'^[ \t]*\.param p1, "scenario".*$', "multi_window", "0x10", "return v0"),
        ("com.android.server.wm.FlexibleWindowUtils", "isSupportMultiMode()Z", r"^[ \t]*\.(?:registers|locals) [0-9]+[ \t]*$", "multi_window", "0x1", "return v0"),
    ]
    for class_name, signature, directive, setting, value, result in simple_patches:
        literal = "const/16" if value == "0x10" else "const/4"
        snippet = _code(
            f"""
                const-string/jumbo v0, "{setting}"

                invoke-static {{v0}}, Landroid/preference/SettingsHelper;->getIntofSettings(Ljava/lang/String;)I

                move-result v0

                if-eqz v0, :cond_wk

                {literal} v0, {value}

                {result}

                :cond_wk
            """
        )
        report.patchedMethods += _patch_after_directive(
            decoded, class_name, signature, directive, snippet, setting
        )
    report.patchedMethods += _edit_method_by_name(
        decoded,
        "com.android.server.policy.PhoneWindowManagerExtImpl",
        "registerSettingsForOplusLocked",
        '"gemini_button"',
        _patch_gemini_button_in_register_settings,
    )
    return asdict(report)


PATCHERS: dict[str, Callable[[Path], dict[str, int | str]]] = {
    "framework": patch_framework_decoded,
    "services": patch_services_decoded,
    "oplus-services": patch_oplus_services_decoded,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch decoded WK_Manager framework smali trees")
    parser.add_argument("jar", choices=sorted(PATCHERS))
    parser.add_argument("decoded", type=Path)
    parser.add_argument("--stark-dir", type=Path, default=DEFAULT_STARK_DIR)
    args = parser.parse_args()
    if args.jar == "framework":
        report = patch_framework_decoded(args.decoded.resolve(), args.stark_dir.resolve())
    else:
        report = PATCHERS[args.jar](args.decoded.resolve())
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
