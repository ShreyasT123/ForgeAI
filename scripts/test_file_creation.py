import os
import shutil
from pathlib import Path
import sys

# Ensure the local src/ directory is in the path so we can import helius_agent
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.tools.vfs import LocalDiskBackend
from helius_agent.tools.files import set_backend, write_file, ls, read_file

# 1. Setup a clean test directory
test_dir = PROJECT_ROOT / "temp_test_workspace"
if test_dir.exists():
    shutil.rmtree(test_dir)
test_dir.mkdir()

print(f"--- Setting up LocalDiskBackend at {test_dir.absolute()} ---")

# 2. Configure the tools to use this directory as the root
# We use virtual_mode=True to ensure paths are trapped inside this folder
backend = LocalDiskBackend(root_dir=str(test_dir), virtual_mode=True)
set_backend(backend)

# 3. Use the tool to create a code file
# This is exactly what the Agent sends:
print("\n[Action] Creating hello.py...")
result = write_file.invoke({
    "path": "hello.py", 
    "content": "def say_hello():\n    print('Hello from Helius VFS!')\n\nif __name__ == '__main__':\n    say_hello()"
})
print(f"[Result] {result}")

# 4. Verify using the 'ls' tool
print("\n[Action] Listing files in workspace via ls tool...")
files = ls.invoke({"path": "."})
print(f"[Result] Available files:\n{files}")

# 5. Verify the file actually exists on the REAL disk
real_path = test_dir / "hello.py"
print(f"\n[Verification] Checking real path on disk: {real_path}")
if real_path.exists():
    print("✅ SUCCESS: File exists on disk.")
    print("--- Content ---")
    print(real_path.read_text())
else:
    print("❌ FAILURE: File was not found on disk.")

# Cleanup instruction
print(f"\nTest folder remains at: {test_dir}")
print("Run 'rm -r temp_test_workspace' to clean up manually.")
