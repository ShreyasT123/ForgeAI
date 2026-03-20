import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.tools.files import (
    edit_file as apply_diff,
    ls,
    edit_lines,
    insert_at_line,
    read_file,
    write_file,
    delete_file,
    set_backend
)
from helius_agent.tools.vfs import LocalDiskBackend


class TestFileTools(unittest.TestCase):
    """Test suite for file manipulation tools"""

    def setUp(self):
        """Create a temporary directory for testing"""
        self.test_dir = tempfile.mkdtemp()
        self._old_repo_root = os.getenv("REPO_ROOT")
        os.environ["REPO_ROOT"] = self.test_dir
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
        # Ensure VFS is set to this temp dir
        set_backend(LocalDiskBackend(root_dir=self.test_dir))

    def tearDown(self):
        """Clean up temporary directory"""
        os.chdir(self.original_cwd)
        if self._old_repo_root is None:
            os.environ.pop("REPO_ROOT", None)
        else:
            os.environ["REPO_ROOT"] = self._old_repo_root
        shutil.rmtree(self.test_dir)

    def create_test_file(self, filename, content):
        """Helper to create a test file"""
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filename

    # Tests for read_file
    def test_read_file_success(self):
        """Test reading an existing file"""
        content = "Hello, World!\nThis is a test file."
        filename = self.create_test_file("test.txt", content)

        result = read_file.invoke({"path": filename})
        # read_file now returns numbered lines
        self.assertIn("Hello, World!", result)
        self.assertIn("1 |", result)

    def test_read_file_not_found(self):
        """Test reading a non-existent file"""
        result = read_file.invoke({"path": "nonexistent.txt"})
        self.assertIn("Error", result)
        self.assertIn("not found", result.lower())

    # Tests for write_file
    def test_write_file_new(self):
        """Test writing to a new file"""
        filename = "new.txt"
        content = "New file content"

        result = write_file.invoke({"path": filename, "content": content})
        self.assertIn("Successfully wrote", result)

        with open(os.path.join(self.test_dir, filename), "r") as f:
            self.assertEqual(f.read(), content)

    def test_write_file_creates_directory(self):
        """Test that write_file creates parent directories"""
        filename = os.path.join("subdir", "file.txt")
        content = "Content in subdirectory"

        result = write_file.invoke({"path": filename, "content": content})
        self.assertIn("Successfully wrote", result)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, filename)))

    # Tests for apply_diff (edit_file)
    def test_apply_diff_success(self):
        """Test applying a diff successfully"""
        original = """def hello():
    print("Hello")
    return True"""

        filename = self.create_test_file("code.py", original)

        search = '    print("Hello")'
        replace = '    print("Hello, World!")'

        result = apply_diff.invoke(
            {"path": filename, "old_string": search, "new_string": replace}
        )

        self.assertIn("Successfully updated", result)

        with open(os.path.join(self.test_dir, filename), "r") as f:
            content = f.read()
            self.assertIn("Hello, World!", content)
            self.assertNotIn('print("Hello")\n', content)

    # Tests for insert_at_line
    def test_insert_at_line_middle(self):
        """Test inserting in the middle of a file"""
        original = "Line 1\nLine 2\nLine 3"
        filename = self.create_test_file("lines.txt", original)

        result = insert_at_line.invoke(
            {"path": filename, "line_number": 2, "content": "Inserted Line"}
        )

        self.assertIn("Successfully inserted", result)

        with open(os.path.join(self.test_dir, filename), "r") as f:
            lines = f.readlines()
            self.assertEqual(lines[1].strip(), "Inserted Line")

    # Tests for edit_lines
    def test_edit_lines_range(self):
        """Test editing multiple lines"""
        original = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        filename = self.create_test_file("lines.txt", original)

        result = edit_lines.invoke(
            {
                "path": filename,
                "start_line": 2,
                "end_line": 4,
                "new_content": "Replaced Lines",
            }
        )

        self.assertIn("Successfully edited", result)

        with open(os.path.join(self.test_dir, filename), "r") as f:
            lines = f.readlines()
            # Range 2-4 is 3 lines. Replaced by 1 line. Total should be 5-3+1 = 3
            self.assertEqual(len(lines), 3)
            self.assertIn("Replaced Lines", lines[1])

    # Tests for ls (was list_files)
    def test_ls_all(self):
        """Test listing all files in a directory"""
        self.create_test_file("file1.txt", "")
        self.create_test_file("file2.py", "")

        result = ls.invoke({"path": "."})

        self.assertIn("file1.txt", result)
        self.assertIn("file2.py", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
