from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from tools.content_cache_key import SHARED_PACKS, content_cache_key
from wukong.artifacts import prepare_artifact


class BuildOptimizationTests(unittest.TestCase):
    def test_prepared_artifact_reuses_digest_only_while_file_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rom.zip"
            path.write_bytes(b"first")
            hasher = Mock(side_effect=lambda p: hashlib.sha256(p.read_bytes()).hexdigest())
            prepared = prepare_artifact(path, hasher=hasher)
            self.assertIs(prepare_artifact(path, prepared, hasher=hasher), prepared)
            self.assertEqual(hasher.call_count, 1)
            path.write_bytes(b"other")  # same size; content identity must invalidate
            updated = prepare_artifact(path, prepared, hasher=hasher)
            self.assertNotEqual(prepared.sha256, updated.sha256)
            self.assertEqual(hasher.call_count, 2)

    def test_changes_during_hashing_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rom.zip"
            path.write_bytes(b"original")
            def mutate(p):
                p.write_bytes(b"changed")
                return "f" * 64
            with self.assertRaisesRegex(RuntimeError, "changed"):
                prepare_artifact(path, hasher=mutate)

    def test_cache_ignores_unrelated_packs_and_tracks_dependencies_and_tools(self):
        index = {"packs": [{"id": name, "files": [{"path": "a", "sha256": "a" * 64, "sizeBytes": 1}]} for name in [*SHARED_PACKS, "MOD/selected", "MOD/other"]]}
        key = content_cache_key(index, "selected", b"tools-v1")
        changed = copy.deepcopy(index)
        changed["packs"][-1]["files"][0]["sha256"] = "b" * 64
        self.assertEqual(key, content_cache_key(changed, "selected", b"tools-v1"))
        changed["packs"][0]["files"][0]["sha256"] = "c" * 64
        self.assertNotEqual(key, content_cache_key(changed, "selected", b"tools-v1"))
        self.assertNotEqual(key, content_cache_key(index, "selected", b"tools-v2"))
