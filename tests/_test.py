"""test_all_tools.py — Comprehensive test suite for the Helius agent tool layer.

Coverage
--------
* shell_tools  : allowlist, HITL, dry_run, background jobs (happy + cancel)
* file_tools   : path traversal, MAX_READ_BYTES, all CRUD ops, search_in_files
* git_workflow : regex fix (branch/path splitting), validation, safe wrappers
* skills_tools : thread safety, register/unregister, FS loading, list/load tools
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import List
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Module bootstrap — resolve src path regardless of CWD
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ---------------------------------------------------------------------------
# Shared test helper
# ---------------------------------------------------------------------------


class _RepoRootMixin:
    """Set and tear down a temporary REPO_ROOT for isolation."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self._old_repo_root = os.getenv("REPO_ROOT")
        os.environ["REPO_ROOT"] = str(self.test_dir)

    def tearDown(self):
        if self._old_repo_root is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self._old_repo_root
        # Best-effort cleanup
        for p in sorted(self.test_dir.rglob("*"), reverse=True):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                pass
        try:
            self.test_dir.rmdir()
        except Exception:
            pass


# ===========================================================================
# shell_tools tests
# ===========================================================================


class TestShellTools(_RepoRootMixin, unittest.TestCase):

    def _import(self):
        # Re-import every test so REPO_ROOT env is respected
        import importlib
        import helius_agent.tools.shell as m

        importlib.reload(m)
        return m

    def test_empty_command_rejected(self):
        m = self._import()
        result = json.loads(m.run_command.invoke({"cmd": []}))
        self.assertEqual(result.get("error"), "empty_command")

    def test_command_not_in_allowlist(self):
        m = self._import()
        result = json.loads(m.run_command.invoke({"cmd": ["bash", "-c", "id"]}))
        self.assertEqual(result.get("error"), "command_not_in_allowlist")
        self.assertEqual(result.get("cmd_name"), "bash")

    def test_dry_run(self):
        m = self._import()
        result = json.loads(
            m.run_command.invoke({"cmd": ["python", "-c", "pass"], "dry_run": True})
        )
        self.assertTrue(result.get("dry_run"))
        self.assertIn("cmd_args", result)

    def test_hitl_required_without_token(self):
        m = self._import()
        result = json.loads(
            m.run_command.invoke(
                {"cmd": ["python", "-c", "pass"], "require_confirmation": True}
            )
        )
        self.assertEqual(result.get("error"), "hitl_required")

    def test_hitl_bypassed_with_valid_token(self):
        m = self._import()
        token = "test-secret-token"
        with patch.dict(os.environ, {"SHELL_BYPASS_TOKEN": token}):
            import importlib

            importlib.reload(m)
            result = json.loads(
                m.run_command.invoke(
                    {
                        "cmd": ["python", "-c", "pass"],
                        "require_confirmation": True,
                        "bypass_token": token,
                    }
                )
            )
        self.assertNotIn("error", result)
        self.assertEqual(result.get("returncode"), 0)

    def test_cwd_escape_rejected(self):
        m = self._import()
        result = json.loads(
            m.run_command.invoke({"cmd": ["python", "-c", "pass"], "cwd": "../../etc"})
        )
        self.assertEqual(result.get("error"), "security_error")

    def test_foreground_command_stdout(self):
        m = self._import()
        result = json.loads(
            m.run_command.invoke({"cmd": ["python", "-c", "print('helius')"]})
        )
        self.assertEqual(result.get("returncode"), 0)
        self.assertIn("helius", result.get("stdout", ""))

    def test_background_job_lifecycle(self):
        m = self._import()
        result = json.loads(
            m.run_command.invoke(
                {"cmd": ["python", "-c", "print('bg-hello')"], "background": True}
            )
        )
        self.assertIn("job_id", result)
        self.assertEqual(result["status"], "running")
        job_id = result["job_id"]

        for _ in range(50):
            status = json.loads(m.get_command_status.invoke({"job_id": job_id}))
            if status.get("status") == "finished":
                break
            time.sleep(0.2)
        else:
            self.fail("background job did not finish in time")

        output = json.loads(m.get_command_output.invoke({"job_id": job_id}))
        self.assertIn("bg-hello", output.get("stdout", ""))

    def test_background_job_cancel_already_finished(self):
        m = self._import()
        result = json.loads(
            m.run_command.invoke({"cmd": ["python", "-c", "pass"], "background": True})
        )
        job_id = result["job_id"]
        for _ in range(50):
            if (
                json.loads(m.get_command_status.invoke({"job_id": job_id})).get(
                    "status"
                )
                == "finished"
            ):
                break
            time.sleep(0.2)
        cancel = json.loads(m.cancel_command.invoke({"job_id": job_id}))
        self.assertEqual(cancel.get("status"), "already_finished")

    def test_get_status_unknown_job(self):
        m = self._import()
        result = json.loads(m.get_command_status.invoke({"job_id": "nonexistent-id"}))
        self.assertEqual(result.get("error"), "job_not_found")

    def test_audit_log_written(self):
        m = self._import()
        m.run_command.invoke({"cmd": ["python", "-c", "pass"]})
        audit_log = self.test_dir / ".agent_audit" / "commands.jsonl"
        self.assertTrue(audit_log.exists())
        entry = json.loads(audit_log.read_text().strip().splitlines()[0])
        self.assertIn("request", entry)
        self.assertIn("result", entry)


# ===========================================================================
# file_tools tests
# ===========================================================================


class TestFileTools(_RepoRootMixin, unittest.TestCase):

    def _mod(self):
        import importlib
        import helius_agent.tools.files as m

        importlib.reload(m)
        return m

    # Security ---------------------------------------------------------------

    def test_path_traversal_blocked(self):
        m = self._mod()
        result = m.read_file.invoke({"filepath": "../../etc/passwd"})
        self.assertIn("Error", result)

    def test_path_traversal_via_symlink_style(self):
        m = self._mod()
        # /tmp/../tmp/../../etc is caught by resolve()
        result = m.read_file.invoke({"filepath": "../outside.txt"})
        self.assertIn("Error", result)

    def test_max_read_bytes_enforced(self):
        m = self._mod()
        big_file = self.test_dir / "big.txt"
        # Write a file exceeding the tiny limit
        with patch.object(m, "MAX_READ_BYTES", 10):
            big_file.write_text("A" * 11, encoding="utf-8")
            result = m.read_file.invoke({"filepath": "big.txt"})
        self.assertIn("Error", result)
        self.assertIn("MAX_READ_BYTES", result)

    # read_file --------------------------------------------------------------

    def test_read_nonexistent(self):
        m = self._mod()
        result = m.read_file.invoke({"filepath": "ghost.py"})
        self.assertIn("Error", result)

    def test_read_directory(self):
        m = self._mod()
        result = m.read_file.invoke({"filepath": "."})
        self.assertIn("Error", result)

    def test_read_full(self):
        m = self._mod()
        (self.test_dir / "hello.txt").write_text(
            "line1\nline2\nline3\n", encoding="utf-8"
        )
        result = m.read_file.invoke({"filepath": "hello.txt"})
        self.assertIn("line2", result)

    def test_read_line_range(self):
        m = self._mod()
        (self.test_dir / "r.txt").write_text("a\nb\nc\nd\n", encoding="utf-8")
        result = m.read_file.invoke(
            {"filepath": "r.txt", "start_line": 2, "end_line": 3}
        )
        self.assertIn("b", result)
        self.assertIn("c", result)
        self.assertNotIn("a", result)
        self.assertNotIn("d", result)

    def test_read_invalid_range(self):
        m = self._mod()
        (self.test_dir / "small.txt").write_text("a\nb\n", encoding="utf-8")
        result = m.read_file.invoke(
            {"filepath": "small.txt", "start_line": 5, "end_line": 10}
        )
        self.assertIn("Error", result)

    # create / write / delete ------------------------------------------------

    def test_create_file(self):
        m = self._mod()
        result = m.create_file.invoke({"filepath": "new.txt", "content": "hello"})
        self.assertIn("Created", result)
        self.assertEqual((self.test_dir / "new.txt").read_text(), "hello")

    def test_create_file_refuses_overwrite(self):
        m = self._mod()
        (self.test_dir / "exists.txt").write_text("original")
        result = m.create_file.invoke({"filepath": "exists.txt", "content": "new"})
        self.assertIn("Error", result)
        self.assertEqual((self.test_dir / "exists.txt").read_text(), "original")

    def test_write_file_creates_backup(self):
        m = self._mod()
        (self.test_dir / "f.txt").write_text("v1", encoding="utf-8")
        m.write_file.invoke({"filepath": "f.txt", "content": "v2"})
        self.assertEqual((self.test_dir / "f.txt").read_text(), "v2")
        self.assertTrue((self.test_dir / "f.txt.bak").exists())

    def test_write_file_atomic(self):
        """Verify NamedTemporaryFile + os.replace leaves no .tmp on success."""
        m = self._mod()
        m.write_file.invoke({"filepath": "atom.txt", "content": "data"})
        tmps = list(self.test_dir.glob("*.tmp"))
        self.assertEqual(tmps, [])

    def test_delete_file(self):
        m = self._mod()
        (self.test_dir / "del.txt").write_text("bye")
        result = m.delete_file.invoke({"filepath": "del.txt"})
        self.assertIn("Deleted", result)
        self.assertFalse((self.test_dir / "del.txt").exists())

    def test_delete_file_creates_backup(self):
        m = self._mod()
        (self.test_dir / "bak_del.txt").write_text("original")
        m.delete_file.invoke({"filepath": "bak_del.txt"})
        self.assertTrue((self.test_dir / "bak_del.txt.bak").exists())

    def test_delete_nonexistent(self):
        m = self._mod()
        result = m.delete_file.invoke({"filepath": "missing.txt"})
        self.assertIn("Error", result)

    # apply_diff / insert_at_line / edit_lines --------------------------------

    def test_apply_diff(self):
        m = self._mod()
        (self.test_dir / "d.txt").write_text("foo bar baz", encoding="utf-8")
        result = m.apply_diff.invoke(
            {"filepath": "d.txt", "search_block": "bar", "replace_block": "QUX"}
        )
        self.assertIn("Applied", result)
        self.assertIn("QUX", (self.test_dir / "d.txt").read_text())

    def test_apply_diff_block_not_found(self):
        m = self._mod()
        (self.test_dir / "d2.txt").write_text("abc", encoding="utf-8")
        result = m.apply_diff.invoke(
            {"filepath": "d2.txt", "search_block": "xyz", "replace_block": "AAA"}
        )
        self.assertIn("Error", result)

    def test_apply_diff_dry_run(self):
        m = self._mod()
        (self.test_dir / "dr.txt").write_text("hello world")
        result = m.apply_diff.invoke(
            {
                "filepath": "dr.txt",
                "search_block": "world",
                "replace_block": "earth",
                "dry_run": True,
            }
        )
        self.assertIn("DRY RUN", result)
        self.assertEqual((self.test_dir / "dr.txt").read_text(), "hello world")

    def test_insert_at_line(self):
        m = self._mod()
        (self.test_dir / "ins.txt").write_text("line1\nline3\n", encoding="utf-8")
        m.insert_at_line.invoke(
            {"filepath": "ins.txt", "line_number": 2, "content": "line2"}
        )
        lines = (self.test_dir / "ins.txt").read_text().splitlines()
        self.assertEqual(lines, ["line1", "line2", "line3"])

    def test_edit_lines(self):
        m = self._mod()
        (self.test_dir / "el.txt").write_text("a\nb\nc\n", encoding="utf-8")
        m.edit_lines.invoke(
            {"filepath": "el.txt", "start_line": 2, "end_line": 2, "new_content": "B"}
        )
        lines = (self.test_dir / "el.txt").read_text().splitlines()
        self.assertEqual(lines, ["a", "B", "c"])

    # list_files / search_in_files -------------------------------------------

    def test_list_files(self):
        m = self._mod()
        (self.test_dir / "a.py").touch()
        (self.test_dir / "b.py").touch()
        result = m.list_files.invoke({"directory": ".", "pattern": "*.py"})
        self.assertIn("a.py", result)
        self.assertIn("b.py", result)

    def test_list_files_nonexistent_dir(self):
        m = self._mod()
        result = m.list_files.invoke({"directory": "ghost_dir"})
        self.assertIn("Error", result)

    def test_search_in_files(self):
        m = self._mod()
        (self.test_dir / "src.py").write_text(
            "def hello():\n    pass\n", encoding="utf-8"
        )
        result = m.search_in_files.invoke({"pattern": "def hello", "directory": "."})
        self.assertIn("src.py", result)
        self.assertIn("def hello", result)

    def test_search_in_files_no_match(self):
        m = self._mod()
        (self.test_dir / "empty.txt").write_text("nothing here", encoding="utf-8")
        result = m.search_in_files.invoke({"pattern": "XXXXXX"})
        self.assertIn("No matches", result)

    def test_search_in_files_invalid_regex(self):
        m = self._mod()
        result = m.search_in_files.invoke({"pattern": "["})
        self.assertIn("Error", result)
        self.assertIn("regex", result.lower())


# ===========================================================================
# git_workflow_tools tests (unit — mocked run_command)
# ===========================================================================


class TestGitWorkflowTools(unittest.TestCase):
    """Unit tests that mock run_command so no real git repo is needed."""

    def _mod(self):
        import importlib
        import helius_agent.tools.git as m

        importlib.reload(m)
        return m

    def _patch(self, m, return_value='{"returncode": 0, "stdout": "ok", "stderr": ""}'):
        return patch.object(m, "run_command", return_value=return_value)

    # Regex fix verification -------------------------------------------------

    def test_branch_re_accepts_valid_names(self):
        m = self._mod()
        for name in ["main", "feature/my-feature", "fix_123", "release-1.0"]:
            self.assertTrue(m._valid_branch(name), f"Expected valid: {name}")

    def test_branch_re_rejects_invalid_names(self):
        m = self._mod()
        for name in ["", "feat; rm -rf /", "feat$(id)", "../../../etc"]:
            self.assertFalse(m._valid_branch(name), f"Expected invalid: {name}")

    def test_split_paths_handles_newlines(self):
        m = self._mod()
        result = m._split_paths("src/a.py\nsrc/b.py,src/c.py")
        self.assertEqual(result, ["src/a.py", "src/b.py", "src/c.py"])

    def test_split_paths_handles_literal_backslash_n(self):
        """Original bug: \\n in regex meant literal backslash-n, not newline."""
        m = self._mod()
        # The fixed version splits on actual newline chars
        result = m._split_paths("a.py\nb.py")
        self.assertEqual(len(result), 2)

    # Validation errors returned without calling run_command -----------------

    def test_create_branch_invalid_name(self):
        m = self._mod()
        result = json.loads(m.git_create_branch.invoke({"branch": "feat; rm -rf /"}))
        self.assertEqual(result.get("error"), "invalid_branch_name")

    def test_checkout_invalid_name(self):
        m = self._mod()
        result = json.loads(m.git_checkout.invoke({"branch": "../../evil"}))
        self.assertEqual(result.get("error"), "invalid_branch_name")

    def test_commit_empty_message(self):
        m = self._mod()
        result = json.loads(m.git_commit.invoke({"message": "   "}))
        self.assertEqual(result.get("error"), "empty_commit_message")

    def test_git_add_no_paths(self):
        m = self._mod()
        result = json.loads(m.git_add.invoke({"paths": "  ,  "}))
        self.assertEqual(result.get("error"), "no_paths_provided")

    def test_reset_invalid_mode(self):
        m = self._mod()
        result = json.loads(m.git_reset.invoke({"mode": "--destroy"}))
        self.assertEqual(result.get("error"), "invalid_reset_mode")

    def test_stash_invalid_action(self):
        m = self._mod()
        result = json.loads(m.git_stash.invoke({"action": "obliterate"}))
        self.assertEqual(result.get("error"), "invalid_stash_action")

    # Happy-path (mocked) ----------------------------------------------------

    def test_git_status_calls_run_command(self):
        m = self._mod()
        with self._patch(m) as mock_rc:
            m.git_status.invoke({})
            mock_rc.assert_called_once()
            args = mock_rc.call_args[0][0]
            self.assertEqual(args[:2], ["git", "status"])

    def test_git_push_force_passes_force_with_lease(self):
        m = self._mod()
        with self._patch(m) as mock_rc:
            m.git_push.invoke(
                {"branch": "main", "force": True, "require_confirmation": False}
            )
            args = mock_rc.call_args[0][0]
            self.assertIn("--force-with-lease", args)

    def test_git_add_commit_calls_both(self):
        m = self._mod()
        with self._patch(m) as mock_rc:
            m.git_add_commit.invoke({"paths": "src/x.py", "message": "fix: stuff"})
            self.assertEqual(mock_rc.call_count, 2)
            first_cmd = mock_rc.call_args_list[0][0][0]
            second_cmd = mock_rc.call_args_list[1][0][0]
            self.assertIn("add", first_cmd)
            self.assertIn("commit", second_cmd)

    def test_git_log_rejects_large_n(self):
        m = self._mod()
        result = json.loads(m.git_log.invoke({"n": 9999}))
        self.assertEqual(result.get("error"), "n must be between 1 and 500")


# ===========================================================================
# skills_tools tests
# ===========================================================================


class TestSkillsTools(unittest.TestCase):

    def setUp(self):
        from helius_agent.tools.skills import SkillRegistry

        self.registry = SkillRegistry()

    # Validation -------------------------------------------------------------

    def test_register_empty_name_raises(self):
        with self.assertRaises(ValueError):
            self.registry.register("", "desc", "content")

    def test_register_empty_description_raises(self):
        with self.assertRaises(ValueError):
            self.registry.register("skill", "", "content")

    def test_register_none_content_raises(self):
        with self.assertRaises(ValueError):
            self.registry.register("skill", "desc", None)

    def test_register_duplicate_raises_without_overwrite(self):
        self.registry.register("s", "d", "c")
        with self.assertRaises(ValueError):
            self.registry.register("s", "d2", "c2")

    def test_register_duplicate_allowed_with_overwrite(self):
        self.registry.register("s", "d", "c1")
        self.registry.register("s", "d", "c2", overwrite=True)
        self.assertEqual(self.registry.get("s").content, "c2")

    # CRUD -------------------------------------------------------------------

    def test_register_and_get(self):
        self.registry.register(
            "rust", "Rust patterns", "use idiomatic Rust", tags=["lang"]
        )
        skill = self.registry.get("rust")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.name, "rust")
        self.assertEqual(skill.tags, ("lang",))

    def test_unregister(self):
        self.registry.register("tmp", "tmp", "tmp")
        removed = self.registry.unregister("tmp")
        self.assertTrue(removed)
        self.assertIsNone(self.registry.get("tmp"))

    def test_unregister_nonexistent_returns_false(self):
        self.assertFalse(self.registry.unregister("ghost"))

    def test_list_all(self):
        self.registry.register("a", "desc", "c")
        self.registry.register("b", "desc", "c")
        self.assertEqual(len(self.registry.list_all()), 2)

    def test_search(self):
        self.registry.register("python-patterns", "Python best practices", "PEP8 etc")
        self.registry.register("rust-patterns", "Rust idioms", "use Arc<>")
        results = self.registry.search("python")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].name, "python-patterns")

    # Thread safety ----------------------------------------------------------

    def test_concurrent_register(self):
        """Concurrent registrations must not corrupt the registry."""
        errors: List[Exception] = []

        def worker(i: int) -> None:
            try:
                self.registry.register(f"skill-{i}", f"desc {i}", f"content {i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Errors during concurrent register: {errors}")
        self.assertEqual(len(self.registry), 100)

    # Filesystem loading -----------------------------------------------------

    def test_load_from_directory(self):
        from helius_agent.tools.skills import load_skills_from_directory

        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "myskill.md").write_text(
                "# My skill\nDo something cool\n", encoding="utf-8"
            )
            (Path(td) / "another.md").write_text("Another skill\n", encoding="utf-8")
            (Path(td) / "ignored.json").write_text("{}")  # wrong extension
            count = load_skills_from_directory(td, overwrite=True)
        self.assertEqual(count, 2)

    def test_load_from_nonexistent_dir_raises(self):
        from helius_agent.tools.skills import load_skills_from_directory

        with self.assertRaises(FileNotFoundError):
            load_skills_from_directory("/no/such/dir")

    # LangChain tool behaviour -----------------------------------------------

    def test_load_skill_not_found(self):
        from helius_agent.tools.skills import _REGISTRY, load_skill

        # Temporarily clear the module-level registry for this test
        original = dict(_REGISTRY._skills)
        _REGISTRY._skills.clear()
        try:
            result = load_skill.invoke({"skill_name": "ghost"})
            self.assertIn("not found", result)
        finally:
            _REGISTRY._skills.update(original)

    def test_load_skill_returns_content(self):
        from helius_agent.tools.skills import _REGISTRY, load_skill, register_skill

        register_skill("test-skill", "A test skill", "## Rule 1\nDo X.", overwrite=True)
        result = load_skill.invoke({"skill_name": "test-skill"})
        self.assertIn("test-skill", result)
        self.assertIn("Do X.", result)

    def test_list_skills_tool(self):
        from helius_agent.tools.skills import (
            _REGISTRY,
            list_skills_tool,
            register_skill,
        )

        register_skill("visible-skill", "Shows up in list", "content", overwrite=True)
        result = list_skills_tool.invoke({})
        self.assertIn("visible-skill", result)

    def test_list_skills_tool_with_query(self):
        from helius_agent.tools.skills import (
            _REGISTRY,
            list_skills_tool,
            register_skill,
        )

        register_skill("django-patterns", "Django patterns", "ORM tips", overwrite=True)
        register_skill("react-patterns", "React patterns", "hooks", overwrite=True)
        result = list_skills_tool.invoke({"query": "django"})
        self.assertIn("django-patterns", result)
        self.assertNotIn("react-patterns", result)

    def test_load_skill_empty_name(self):
        from helius_agent.tools.skills import load_skill

        result = load_skill.invoke({"skill_name": ""})
        self.assertIn("Error", result)


# ===========================================================================
# Shell background integration (npm-gated)
# ===========================================================================


class TestShellNpmIntegration(_RepoRootMixin, unittest.TestCase):

    @unittest.skipUnless(os.getenv("RUN_NPM_TESTS") == "1", "Set RUN_NPM_TESTS=1")
    def test_npm_init_and_install(self):
        import importlib
        import helius_agent.tools.shell as m

        importlib.reload(m)

        init = json.loads(
            m.run_command.invoke({"cmd": ["npm", "init", "-y"], "background": True})
        )
        job_id = init["job_id"]
        for _ in range(200):
            if (
                json.loads(m.get_command_status.invoke({"job_id": job_id})).get(
                    "status"
                )
                == "finished"
            ):
                break
            time.sleep(1)
        else:
            self.fail("npm init timed out")

        self.assertTrue((self.test_dir / "package.json").exists())

        install = json.loads(
            m.run_command.invoke(
                {"cmd": ["npm", "install", "is-odd"], "background": True}
            )
        )
        iid = install["job_id"]
        for _ in range(300):
            if (
                json.loads(m.get_command_status.invoke({"job_id": iid})).get("status")
                == "finished"
            ):
                break
            time.sleep(0.5)
        else:
            self.fail("npm install timed out")

        self.assertTrue((self.test_dir / "node_modules" / "is-odd").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
