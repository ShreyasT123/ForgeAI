import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.tools.shell import (  # noqa: E402
    run_command,
    get_command_status,
    get_command_output,
)


class TestShellBackground(unittest.TestCase):
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

    def test_background_command(self):
        result = run_command.invoke(
            {"cmd": ["python", "-c", "print('hello')"], "background": True}
        )
        data = json.loads(result)
        self.assertIn("job_id", data)

        job_id = data["job_id"]
        # poll for completion
        for _ in range(50):
            status = json.loads(get_command_status.invoke({"job_id": job_id}))
            if status.get("status") == "finished":
                break
            time.sleep(1)

        output = json.loads(get_command_output.invoke({"job_id": job_id}))
        self.assertIn("hello", output.get("stdout", ""))

    def test_background_npm_init_install(self):
        if os.getenv("RUN_NPM_TESTS", "0") != "1":
            self.skipTest("Set RUN_NPM_TESTS=1 to enable npm integration test")

        init_result = run_command.invoke(
            {"cmd": ["npm", "init", "-y"], "background": True}
        )
        init_data = json.loads(init_result)
        init_job_id = init_data["job_id"]

        for _ in range(200):
            status = json.loads(get_command_status.invoke({"job_id": init_job_id}))
            if status.get("status") == "finished":
                break
            time.sleep(1)
        else:
            self.fail("npm init did not finish in time")

        pkg = Path(self.test_dir) / "package.json"
        self.assertTrue(pkg.exists())

        install_result = run_command.invoke(
            {"cmd": ["npm", "install", "meow"], "background": True}
        )
        install_data = json.loads(install_result)
        install_job_id = install_data["job_id"]

        for _ in range(600):
            status = json.loads(get_command_status.invoke({"job_id": install_job_id}))
            if status.get("status") == "finished":
                break
            time.sleep(0.2)
        else:
            self.fail("npm install did not finish in time")

        node_modules = Path(self.test_dir) / "node_modules" / "react"
        self.assertTrue(node_modules.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
