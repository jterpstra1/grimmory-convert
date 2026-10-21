import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import convert

FAKE_CONVERTER = """
import shutil, sys
src, out = sys.argv[1], sys.argv[2]
if "broken" in src:
    print("conversion error: broken book", file=sys.stderr)
    sys.exit(1)
shutil.copyfile(src, out)
"""


class ConvertTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.lib = root / "books"
        self.lib.mkdir()
        fake = root / "fake_convert.py"
        fake.write_text(FAKE_CONVERTER)
        self.env = {
            "LIBRARY_DIR": str(self.lib),
            "STATE_DIR": str(root / "config"),
            "EBOOK_CONVERT": f"{sys.executable} {fake}",
            "DRY_RUN": "false",
            "TARGET_FORMATS": "azw3",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def book(self, rel, content="book"):
        p = self.lib / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def run_with(self, **env):
        old = os.environ.copy()
        os.environ.update(self.env)
        os.environ.update(env)
        try:
            convert.run_once(convert.Config.from_env())
        finally:
            os.environ.clear()
            os.environ.update(old)

    def files(self):
        return sorted(str(p.relative_to(self.lib)) for p in self.lib.rglob("*") if p.is_file())

    def test_converts_next_to_original(self):
        self.book("Author/Title/Title.epub")
        self.run_with()
        self.assertEqual(self.files(), ["Author/Title/Title.azw3", "Author/Title/Title.epub"])

    def test_dry_run_writes_nothing(self):
        self.book("Title.epub")
        self.run_with(DRY_RUN="true")
        self.assertEqual(self.files(), ["Title.epub"])

    def test_skips_existing_target_case_insensitive(self):
        self.book("Title.epub")
        self.book("title.AZW3", "original")
        self.run_with()
        self.assertEqual((self.lib / "title.AZW3").read_text(), "original")
        self.assertEqual(self.files(), ["Title.epub", "title.AZW3"])

    def test_multiple_targets_and_preferred_source(self):
        self.book("Title.epub", "from-epub")
        self.book("Title.mobi", "from-mobi")
        self.run_with(SOURCE_FORMATS="epub,mobi", TARGET_FORMATS="azw3,mobi,pdf")
        self.assertEqual((self.lib / "Title.azw3").read_text(), "from-epub")
        self.assertEqual((self.lib / "Title.pdf").read_text(), "from-epub")
        self.assertEqual((self.lib / "Title.mobi").read_text(), "from-mobi")

    def test_ignore_file_and_hidden_dirs_skipped(self):
        self.book("skip/.ignore")
        self.book("skip/A.epub")
        self.book(".hidden/B.epub")
        self.run_with()
        self.assertNotIn("skip/A.azw3", self.files())
        self.assertNotIn(".hidden/B.azw3", self.files())

    def test_failure_recorded_and_not_retried(self):
        self.book("broken.epub")
        self.book("good.epub")
        self.run_with()
        self.assertEqual(self.files(), ["broken.epub", "good.azw3", "good.epub"])
        failed = json.loads((Path(self.env["STATE_DIR"]) / "failed.json").read_text())
        self.assertIn("broken.epub::azw3", failed)
        self.assertIn("broken book", failed["broken.epub::azw3"])
        jobs = list(convert.find_jobs(self.config(), failed))
        self.assertEqual(jobs, [])

    def test_max_per_run(self):
        for n in range(3):
            self.book(f"B{n}.epub")
        self.run_with(MAX_PER_RUN="2")
        self.assertEqual(len([f for f in self.files() if f.endswith(".azw3")]), 2)
        self.run_with(MAX_PER_RUN="2")
        self.assertEqual(len([f for f in self.files() if f.endswith(".azw3")]), 3)

    def test_leftover_part_files_removed(self):
        self.book("Title.epub")
        self.book("Title.azw3" + convert.PART_SUFFIX, "half")
        self.run_with()
        self.assertEqual(self.files(), ["Title.azw3", "Title.epub"])
        self.assertEqual((self.lib / "Title.azw3").read_text(), "book")

    def test_part_symlink_not_followed(self):
        self.book("Title.epub")
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("untouched")
        target = self.lib / "Title.azw3"
        source, _, fmt = next(convert.find_jobs(self.config(), {}))
        target.with_name(target.name + convert.PART_SUFFIX).symlink_to(outside)
        convert.convert(self.config(), source, target, fmt)
        self.assertEqual(outside.read_text(), "untouched")
        self.assertFalse(target.is_symlink())
        self.assertEqual(target.read_text(), "book")

    def config(self):
        old = os.environ.copy()
        os.environ.update(self.env)
        try:
            return convert.Config.from_env()
        finally:
            os.environ.clear()
            os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
