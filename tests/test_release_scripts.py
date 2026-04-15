from pathlib import Path
import tempfile
import unittest

from scripts import release_common


class ReleaseCommonTests(unittest.TestCase):
    def test_project_version_reads_matching_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text('{"version":"1.2.3"}\n', encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nversion = "1.2.3"\n', encoding="utf-8")

            self.assertEqual(release_common.project_version(root), "1.2.3")

    def test_project_version_rejects_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text('{"version":"1.2.3"}\n', encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nversion = "2.0.0"\n', encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                release_common.project_version(root)

        self.assertIn("version mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
