import tempfile
import unittest
from pathlib import Path

import wk_manager_patcher


class WkManagerPatcherTests(unittest.TestCase):
    def test_smali_anchor_preserves_instruction_indentation(self):
        self.assertEqual(
            wk_manager_patcher._smali_anchor(
                """
                    invoke-static {}, Lfixture/Hook;->run()V

                    return-void
                """
            ),
            "    invoke-static {}, Lfixture/Hook;->run()V\n\n    return-void",
        )

    def test_trace_return_hook_allows_line_metadata(self):
        method = (
            "    invoke-static {v1, v2}, Landroid/os/Trace;->traceEnd(J)V\n"
            "\n"
            "    .line 42\n"
            "    return-object v3"
        )
        patched = wk_manager_patcher._insert_before_return_after_trace(
            method,
            "v1, v2",
            "v3",
            "    invoke-static {v3}, Lfixture/Hook;->run(Ljava/lang/Object;)V",
            "fixture",
        )
        self.assertIn(".line 42\n\n    invoke-static {v3}", patched)
        self.assertTrue(patched.endswith("    return-object v3"))

    def test_add_local_registers_supports_locals_and_registers(self):
        locals_method, locals_base = wk_manager_patcher._add_local_registers(
            ".method test()V\n    .locals 2\n    return-void\n.end method",
            3,
            parameter_words=1,
        )
        self.assertIn(".locals 5", locals_method)
        self.assertEqual(locals_base, 2)

        registers_method, registers_base = wk_manager_patcher._add_local_registers(
            ".method test()V\n    .registers 4\n    return-void\n.end method",
            2,
            parameter_words=1,
        )
        self.assertIn(".registers 6", registers_method)
        self.assertEqual(registers_base, 3)

    def test_edit_method_is_idempotent_and_fails_on_missing_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            decoded = Path(temp)
            smali = decoded / "smali" / "fixture" / "Target.smali"
            smali.parent.mkdir(parents=True)
            smali.write_text(
                ".class public Lfixture/Target;\n"
                ".method public test()V\n"
                "    .registers 1\n"
                "    return-void\n"
                ".end method\n",
                encoding="utf-8",
            )
            changed = wk_manager_patcher._patch_before(
                decoded,
                "fixture.Target",
                "test()V",
                "    return-void",
                "    invoke-static {}, Lfixture/Hook;->run()V",
                "Lfixture/Hook;->run",
            )
            self.assertTrue(changed)
            self.assertFalse(
                wk_manager_patcher._patch_before(
                    decoded,
                    "fixture.Target",
                    "test()V",
                    "    return-void",
                    "    invoke-static {}, Lfixture/Hook;->run()V",
                    "Lfixture/Hook;->run",
                )
            )
            with self.assertRaisesRegex(wk_manager_patcher.WkManagerPatchError, "expected one anchor"):
                wk_manager_patcher._patch_before(
                    decoded,
                    "fixture.Target",
                    "test()V",
                    "    missing-anchor",
                    "    nop",
                    "missing-marker",
                )

    def test_copy_stark_smali_targets_classes6(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            decoded = root / "decoded"
            stark = root / "STARK"
            source = stark / "com" / "wukong" / "manager" / "Hook.smali"
            source.parent.mkdir(parents=True)
            source.write_text(".class public Lcom/wukong/manager/Hook;\n", encoding="utf-8")
            self.assertEqual(wk_manager_patcher._copy_stark_smali(decoded, stark), 1)
            target = decoded / "smali_classes6" / "com" / "wukong" / "manager" / "Hook.smali"
            self.assertEqual(target.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertEqual(wk_manager_patcher._copy_stark_smali(decoded, stark), 0)


if __name__ == "__main__":
    unittest.main()
