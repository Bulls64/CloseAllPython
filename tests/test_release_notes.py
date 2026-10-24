import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / ".github" / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## 2.1.0 (2026-11-02)

- Two

## 2.0.1 (2026-11-01)

- One fix

## 2.0.0 (2026-11-01)

- Big

---

# Journal

## 2.1.0 (2026-11-02)

- Deux

## 2.0.1 (2026-11-01)

- Un correctif

## 2.0.0 (2026-11-01)

- Gros
"""


class ReleaseNotesTests(unittest.TestCase):
    def test_one_version_without_the_published_list(self):
        notes = release_notes.notes("2.1.0", text=CHANGELOG)
        self.assertIn("- Two", notes)
        self.assertNotIn("One fix", notes)
        self.assertNotIn("####", notes)
        self.assertLess(notes.index("- Two"), notes.index("### Modifications"))
        self.assertIn("- Deux", notes)

    def test_versions_never_released_are_included(self):
        notes = release_notes.notes("2.1.0", ["v2.0.0", "v1.9.0", "latest"], text=CHANGELOG)
        self.assertLess(notes.index("#### 2.1.0"), notes.index("#### 2.0.1"))
        self.assertIn("One fix", notes)
        self.assertIn("Un correctif", notes)
        self.assertNotIn("Big", notes)   # already in the notes of 2.0.0

    def test_rerun_after_publication(self):
        # The release of 2.1.0 itself is already in the list: it is not "the previous one".
        notes = release_notes.notes("2.1.0", ["v2.1.0", "v2.0.1"], text=CHANGELOG)
        self.assertNotIn("One fix", notes)

    def test_missing_entry(self):
        with self.assertRaises(SystemExit):
            release_notes.notes("3.0.0", text=CHANGELOG)

    def test_real_changelog_has_every_version_in_both_languages(self):
        found = release_notes.entries((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        for version, bodies in found.items():
            self.assertEqual(len(bodies), 2, version)


if __name__ == "__main__":
    unittest.main()
