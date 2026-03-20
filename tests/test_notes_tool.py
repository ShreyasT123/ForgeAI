import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.tools.notes import (  # noqa: E402
    create_note,
    read_note,
    list_notes,
    update_note,
    delete_note,
)


class TestNotesTool(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self._old_repo_root = os.getenv("REPO_ROOT")
        os.environ["REPO_ROOT"] = self.test_dir

    def tearDown(self):
        if self._old_repo_root is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self._old_repo_root
        # cleanup
        for p in Path(self.test_dir).rglob("*"):
            if p.is_file():
                p.unlink()
        for p in sorted(Path(self.test_dir).rglob("*"), reverse=True):
            if p.is_dir():
                p.rmdir()

    def test_create_note(self):
        result = create_note.invoke(
            {"title": "Coding Style", "content": "# Style\nUse small functions."}
        )
        self.assertIn("Saved note", result)
        note_path = Path(self.test_dir) / ".helius-code" / "Coding-Style.md"
        self.assertTrue(note_path.exists())
        self.assertIn("Use small functions", note_path.read_text(encoding="utf-8"))

    def test_create_note_no_overwrite(self):
        create_note.invoke({"title": "Patterns", "content": "A"})
        result = create_note.invoke({"title": "Patterns", "content": "B"})
        self.assertIn("already exists", result)

    def test_read_list_update_delete(self):
        create_note.invoke({"title": "Guides", "content": "V1"})
        self.assertIn("Guides.md", list_notes.invoke({}))

        self.assertEqual("V1", read_note.invoke({"title": "Guides"}))

        update_note.invoke({"title": "Guides", "content": "V2"})
        self.assertEqual("V2", read_note.invoke({"title": "Guides"}))

        delete_note.invoke({"title": "Guides"})
        self.assertIn("No notes", list_notes.invoke({}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
