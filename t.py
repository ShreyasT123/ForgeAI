# t.py
import os
import json
import subprocess
from pathlib import Path

import requests
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool
from langchain_mistralai import ChatMistralAI
load_dotenv()

REPO_PATH = Path(os.environ.get("REPO_PATH", ".")).resolve()
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # "ShreyasT123/ForgeAI"
DEFAULT_BASE_BRANCH = os.environ.get("BASE_BRANCH", "main")


# ---------------- Helper functions ----------------

def _run(cmd: list[str], cwd: Path = REPO_PATH) -> str:
    """Run a shell command and return stdout. Raises RuntimeError if the command fails."""
    result = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, shell=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return (result.stdout or result.stderr).strip()


def _safe_path(rel_path: str) -> Path:
    """Ensure the relative path stays inside the repo."""
    full = (REPO_PATH / rel_path).resolve()
    if REPO_PATH not in full.parents and full != REPO_PATH:
        raise ValueError(f"Path escapes repository root: {rel_path}")
    return full


# ---------------- Tools ----------------

@tool
def repo_status() -> str:
    """
    Get the current git branch and short status of the repository.
    
    Returns:
        JSON string containing:
            - branch: current branch name
            - status: short git status
    """
    branch = _run(["git", "branch", "--show-current"])
    status = _run(["git", "status", "--short"])
    return json.dumps({"branch": branch, "status": status}, indent=2)


@tool
def read_file(path: str) -> str:
    """
    Read the content of a file inside the repository.
    
    Args:
        path: Relative path to the file from the repository root.
    
    Returns:
        File content as a string.
    
    Raises:
        ValueError if the path is a directory.
    """
    full = _safe_path(path)
    if full.is_dir():
        raise ValueError(f"Path {path} is a directory, not a file.")
    if not full.exists():
        return ""  # file doesn't exist yet
    return full.read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> str:
    """
    Write content to a file inside the repository.
    
    Args:
        path: Relative path to the file from the repository root.
        content: Text content to write.
    
    Returns:
        Confirmation string.
    
    Raises:
        ValueError if the path is a directory.
    """
    full = _safe_path(path)
    if full.is_dir():
        raise ValueError(f"Cannot write to directory path {path}")
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    return f"written: {path}"


@tool
def create_branch(branch_name: str) -> str:
    """
    Create and switch to a new git branch.
    
    Args:
        branch_name: Name of the new branch.
    
    Returns:
        Confirmation string.
    """
    _run(["git", "checkout", "-b", branch_name])
    return f"checked out new branch: {branch_name}"


@tool
def git_add_commit(message: str) -> str:
    """
    Stage all changes and commit with a message.
    
    Args:
        message: Commit message.
    
    Returns:
        Confirmation string.
    """
    _run(["git", "add", "-A"])
    _run(["git", "commit", "-m", message])
    return f"committed: {message}"


@tool
def git_push(branch_name: str) -> str:
    """
    Push a branch to the remote repository.
    
    Args:
        branch_name: Branch name to push.
    
    Returns:
        Confirmation string.
    """
    _run(["git", "push", "-u", "origin", branch_name])
    return f"pushed: {branch_name}"


@tool
def create_pull_request(title: str, body: str, head_branch: str, base_branch: str = DEFAULT_BASE_BRANCH) -> str:
    """
    Create a pull request on GitHub from head_branch to base_branch.
    
    Args:
        title: PR title.
        body: PR body description.
        head_branch: Branch containing changes.
        base_branch: Branch to merge into (default: main).
    
    Returns:
        JSON string with PR details or error message if failed.
    """
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    if not GITHUB_TOKEN:
        return "GITHUB_TOKEN not set. Cannot create PR."
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body, "head": head_branch, "base": base_branch}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code not in (200, 201):
        return f"PR creation failed: {r.status_code} {r.text}"
    data = r.json()
    return json.dumps(
        {"pr_url": data.get("html_url"), "number": data.get("number"), "state": data.get("state")},
        indent=2,
    )


# ---------------- Initialize Gemini ----------------

llm = ChatMistralAI(model="mistral-large-latest")

agent = create_agent(
    model=llm,
    tools=[
        repo_status,
        read_file,
        write_file,
        create_branch,
        git_add_commit,
        git_push,
        create_pull_request,
    ],
    system_prompt=(
    "You are an AI coding assistant operating on a local ForgeAI git repository. "
    "Follow these rules strictly:\n"
    "1. Always inspect the repository state before making any changes.\n"
    "2. Use **only one feature branch** per task. Name the branch clearly based on the task.\n"
    "3. Only modify or create files inside the repository. Never write outside.\n"
    "4. Use `read_file` to check existing content before editing.\n"
    "5. Use `write_file` to create or update files safely.\n"
    "6. After completing changes, stage all changes and commit with a clear message.\n"
    "7. Push the branch to the remote via SSH.\n"
    "8. Use `create_pull_request` to open a PR from your branch to the main branch.\n"
    "9. Do not create extra branches or overwrite existing work.\n"
    "10. Confirm each step with clear messages before proceeding to the next.\n"
    "11. Never assume files exist; check first. If a file is missing, create it safely.\n"
    "12. Avoid leaving untracked or unsaved changes."
)
)

# ---------------- Example Task ----------------

if __name__ == "__main__":
    task = """
 Task:

1. Create a new file called `hello.mist.txt` in the root of the ForgeAI repository.
2. Add the following content to the file exactly as shown:
   "Hello from AI mist-agent v-mist"
3. Before writing, check if the file already exists:
   - If it exists, read its content using `read_file`.
   - Append the new message on a new line if the exact message is not already present.
   - If it does not exist, create it safely using `write_file`.
4. Create a **single feature branch** for this task named: `feature/hello-mist-update`.
5. Stage all changes and commit them with the message: `"Add hello.mist.txt with AI message"`.
6. Push the branch to the remote repository via SSH using `git_push`.
7. Create a **pull request** from `feature/hello-mist-update` to the `main` branch using `create_pull_request`.
   - PR title: `"Add hello.mist.txt via AI agent"`
   - PR body: `"This PR adds or updates hello.mist.txt with a greeting from the AI agent."`
8. Confirm each step after completion before moving to the next step.
9. **Do not** modify any files outside the repository or create extra branches.
10. After PR creation, return a JSON summary including:
    - Branch name
    - Commit message
    - PR URL
    - Status of file creation (new or updated)
    """
    result = agent.invoke({"messages": [{"role": "user", "content": task}]})
    print(result["messages"])