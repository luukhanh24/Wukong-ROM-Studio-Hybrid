from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.merge_source_probe import merge_source_probe
from wukong.models import BuildRecipe, Identity, JobManifest
from wukong.orchestrator import HybridOrchestrator, InMemoryJobStore
from wukong.source_probe import inspect_local_rom_metadata


class MergeSourceProbeTests(unittest.TestCase):
    def test_merges_safe_rom_metadata_and_size_without_persisting_resolved_url(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recipe_path = Path(root, "recipe.json")
            probe_path = Path(root, "probe.json")
            recipe_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "task": "build",
                        "device": "PKG110",
                        "source": {
                            "kind": "https",
                            "uri": "https://component-ota-cn.allawntech.com/downloadCheck?id=fixture",
                            "metadata": {"provider": "oplus", "version": "stale"},
                        },
                        "execution": {"target": "github-auto"},
                    }
                ),
                encoding="utf-8",
            )
            probe_path.write_text(
                json.dumps(
                    {
                        "provider": "oplus",
                        "filename": "rom.zip",
                        "resolvedHost": "gauss-compota-c-cn.allawnfs.com",
                        "sizeBytes": 8_680_370_027,
                        "productName": "PKG110",
                        "version": "PKG110_16.0.10.500(CN01)",
                        "androidVersion": "16",
                        "securityPatch": "2026-08-01",
                        "buildDate": "2026-08-11 09:38:18",
                        "deepInspected": True,
                        "resolvedUrl": "https://signed.example/rom.zip?Signature=secret",
                        "signedUrlExpiresAt": 1_787_758_724,
                        "unknownNested": {"secret": "must-not-survive"},
                    }
                ),
                encoding="utf-8",
            )

            merged = merge_source_probe(recipe_path, probe_path)
            parsed = BuildRecipe.from_dict(merged)
            persisted = json.loads(recipe_path.read_text(encoding="utf-8"))

            self.assertEqual(parsed.source.size_bytes, 8_680_370_027)
            self.assertEqual(
                parsed.source.metadata,
                {
                    "provider": "oplus",
                    "filename": "rom.zip",
                    "resolvedHost": "gauss-compota-c-cn.allawnfs.com",
                    "productName": "PKG110",
                    "version": "PKG110_16.0.10.500(CN01)",
                    "androidVersion": "16",
                    "securityPatch": "2026-08-01",
                    "buildDate": "2026-08-11 09:38:18",
                    "deepInspected": "true",
                },
            )
            serialized = json.dumps(persisted)
            self.assertNotIn("resolvedUrl", serialized)
            self.assertNotIn("signedUrlExpiresAt", serialized)
            self.assertNotIn("unknownNested", serialized)
            self.assertNotIn("Signature=secret", serialized)

    def test_submission_carries_rom_metadata_into_terminal_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            recipe = BuildRecipe.from_dict(
                {
                    "schemaVersion": 1,
                    "task": "build",
                    "device": "PKG110",
                    "source": {
                        "kind": "https",
                        "uri": "https://downloads.example/rom.zip",
                        "metadata": {
                            "version": "PKG110_16.0.10.500(CN01)",
                            "androidVersion": "16",
                            "securityPatch": "2026-08-01",
                            "buildDate": "2026-08-11 09:38:18",
                        },
                    },
                    "execution": {"target": "github-auto"},
                }
            )
            orchestrator = HybridOrchestrator(
                store=InMemoryJobStore(),
                workspace_root=Path(root),
            )

            manifest = orchestrator.prepare_submission(
                recipe,
                Identity("actions", "100", "user"),
                job_id="metadata-job",
            )
            restored = JobManifest.from_dict(manifest.to_dict())

            self.assertEqual(restored.rom_metadata, recipe.source.metadata)

    def test_local_rom_inspection_recovers_terminal_fields_after_download(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            rom = Path(root, "rom.zip")
            with zipfile.ZipFile(rom, "w") as archive:
                archive.writestr(
                    "META-INF/com/android/metadata",
                    "\n".join(
                        (
                            "oplus-product-name=PKG110",
                            "pre-device=OP5D2BL1",
                            "oplus-version-name=PKG110_16.0.10.500(CN01)",
                            "post-sdk-level=36",
                            "post-security-patch-level=2026-08-01",
                            "post-timestamp=1786433898",
                            "ota-type=AB",
                        )
                    ),
                )

            metadata = inspect_local_rom_metadata(rom)

            self.assertEqual(metadata["version"], "PKG110_16.0.10.500(CN01)")
            self.assertEqual(metadata["androidVersion"], "16")
            self.assertEqual(metadata["securityPatch"], "2026-08-01")
            self.assertEqual(metadata["buildDate"], "2026-08-11 07:38:18")
            self.assertEqual(metadata["deepInspected"], "true")


if __name__ == "__main__":
    unittest.main()
