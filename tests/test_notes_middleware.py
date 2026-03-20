import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.agents.base import AgentConfig, build_agent  # noqa: E402
from helius_agent.tools.notes import create_note  # noqa: E402


class TestNotesMiddleware(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self._old_repo_root = os.getenv("REPO_ROOT")
        os.environ["REPO_ROOT"] = self.test_dir

    def tearDown(self):
        if self._old_repo_root is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self._old_repo_root
        for p in Path(self.test_dir).rglob("*"):
            if p.is_file():
                p.unlink()
        for p in sorted(Path(self.test_dir).rglob("*"), reverse=True):
            if p.is_dir():
                p.rmdir()

    def test_system_prompt_includes_notes(self):
        create_note.invoke({"title": "Style", "content": "Use small functions."})
        config = AgentConfig(model="fake")
        # build_agent will try to init real LLM; we only validate prompt logic indirectly
        # by checking that notes are loaded and would be appended via middleware utility.
        from helius_agent.agents.notes_middleware import NotesSystemPromptMiddleware

        prompt = NotesSystemPromptMiddleware().apply_to_system_prompt("Base prompt")
        self.assertIn("Use small functions", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
