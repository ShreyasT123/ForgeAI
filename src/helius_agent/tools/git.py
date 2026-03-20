"""git_workflow_tools.py — Generic Git workflow primitives for a coding agent.

Design goals
------------
* No language/linter coupling — pure Git operations only.
* Dangerous operations (force-push, reset, merge) require HITL confirmation
  unless a bypass token is provided.
* run_command handles REPO_ROOT containment; we don't re-implement it here.

Bug fixes vs original
---------------------
* BRANCH_RE was r"^[\\w./-]+$" (double-escaped → matched literal backslash-w).
  Fixed to r"^[\w./-]+$".
* re.split used r"[\\n,]+" (literal \\n, not newline).
  Fixed to r"[\n,]+".
"""


import json
import logging
import re
import os
import requests
from typing import Optional

from langchain.tools import tool

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

try:
    from helius_agent.tools.shell import run_command_raw as run_command
except Exception:

    def run_command(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError(
            "run_command is not available — provide helius_agent.tools.shell."
        )


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

# Fixed: was r"^[\\w./-]+$" which matched literal backslash-w, not word chars
_BRANCH_RE = re.compile(r"^[\w./\-]+$")
# Refs (tags, commit SHAs, HEAD~n) can include ^ ~ : but keep it conservative
_REF_RE = re.compile(r"^[\w./\-~^@{}]+$")


def _valid_branch(name: str) -> bool:
    if not name or not _BRANCH_RE.match(name):
        return False
    if name.startswith("/") or name.endswith("/"):
        return False
    if ".." in name:
        return False
    return True


def _valid_ref(ref: str) -> bool:
    return bool(ref and _REF_RE.match(ref))


def _split_paths(paths: str) -> list[str]:
    """Split a comma- or newline-separated path string into a list.

    Fixed: original used r"[\\n,]+" which splits on literal backslash-n.
    """
    return [p.strip() for p in re.split(r"[\n,]+", paths) if p.strip()]


def _parse(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {"text": raw}


def _err(msg: str, **kw) -> str:
    return json.dumps({"error": msg, **kw}, indent=2)


# ---------------------------------------------------------------------------
# Read-only / inspection tools
# ---------------------------------------------------------------------------


@tool(
    "git_status", description="Run `git status --porcelain -b` and return the output."
)
def git_status() -> str:
    return run_command(
        ["git", "status", "--porcelain", "-b"], cwd=".", capture_output=True
    )


@tool(
    "git_repo_summary",
    description="Get a structured summary of the current branch and repo status (JSON).",
)
def git_repo_summary() -> str:
    """
    Get the current git branch and short status of the repository.
    """
    try:
        branch = run_command(["git", "branch", "--show-current"], cwd=".", capture_output=True).strip()
        status = run_command(["git", "status", "--short"], cwd=".", capture_output=True).strip()
        return json.dumps({"branch": branch, "status": status}, indent=2)
    except Exception as e:
        return _err(str(e))


@tool("git_branches", description="List local branches (git branch -vv).")
def git_branches() -> str:
    return run_command(["git branch -vv"], cwd=".", capture_output=True, shell=True)


@tool(
    "git_log",
    description="Show a compact git log. n controls how many commits to show.",
)
def git_log(n: int = 20) -> str:
    if n < 1 or n > 500:
        return _err("n must be between 1 and 500")
    return run_command(
        ["git", "log", "-n", str(n), "--oneline", "--decorate"],
        cwd=".",
        capture_output=True,
    )


@tool(
    "git_diff",
    description="Show git diff — working tree vs index, vs a ref, or for a specific path.",
)
def git_diff(
    path: Optional[str] = None,
    cached: bool = False,
    ref: Optional[str] = None,
) -> str:
    if ref and not _valid_ref(ref):
        return _err("invalid_ref", ref=ref)
    args = ["git", "diff"]
    if cached:
        args.append("--cached")
    if ref:
        args.append(ref)
    if path:
        args += ["--", path]
    return run_command(args, cwd=".", capture_output=True)


@tool(
    "git_show",
    description="Show a commit, tag, or file at a given ref (git show <ref>).",
)
def git_show(ref: str = "HEAD", path: Optional[str] = None) -> str:
    if not _valid_ref(ref):
        return _err("invalid_ref", ref=ref)
    args = ["git", "show", "--stat", ref]
    if path:
        args += ["--", path]
    return run_command(args, cwd=".", capture_output=True)


# ---------------------------------------------------------------------------
# Branch management
# ---------------------------------------------------------------------------


@tool(
    "git_create_branch",
    description="Create and check out a new branch (optionally from a base ref).",
)
def git_create_branch(branch: str, base: Optional[str] = None) -> str:
    if not _valid_branch(branch):
        return _err("invalid_branch_name", branch=branch)
    if base and not _valid_ref(base):
        return _err("invalid_base_ref", base=base)
    cmd = ["git", "checkout", "-b", branch] + ([base] if base else [])
    return run_command(cmd, cwd=".", capture_output=True)


@tool("git_checkout", description="Check out an existing branch.")
def git_checkout(branch: str) -> str:
    if not _valid_branch(branch):
        return _err("invalid_branch_name", branch=branch)
    return run_command(["git", "checkout", branch], cwd=".", capture_output=True)


# ---------------------------------------------------------------------------
# Staging / committing
# ---------------------------------------------------------------------------


@tool(
    "git_add",
    description="Stage files. Accepts a comma- or newline-separated list of paths.",
)
def git_add(paths: str) -> str:
    path_list = _split_paths(paths)
    if not path_list:
        return _err("no_paths_provided")
    return run_command(["git", "add"] + path_list, cwd=".", capture_output=True)


@tool(
    "git_commit",
    description="Commit staged changes. Set amend=True to amend the last commit.",
)
def git_commit(message: str, amend: bool = False) -> str:
    if not message or not message.strip():
        return _err("empty_commit_message")
    args = ["git", "commit", "-m", message.strip()]
    if amend:
        args.append("--amend")
    return run_command(args, cwd=".", capture_output=True)


@tool("git_add_commit", description="Stage changes and commit in a single operation. Use paths='-A' to stage all.")
def git_add_commit(paths: str, message: str) -> str:
    if not message or not message.strip():
        return _err("empty_commit_message")
    
    if paths in ("-A", ".", "all"):
        add_args = ["git", "add", "-A"]
    else:
        path_list = _split_paths(paths)
        if not path_list:
            return _err("no_paths_provided")
        add_args = ["git", "add"] + path_list
        
    add_out = run_command(add_args, cwd=".", capture_output=True)
    commit_out = run_command(
        ["git", "commit", "-m", message.strip()], cwd=".", capture_output=True
    )
    return json.dumps({"add": _parse(add_out), "commit": _parse(commit_out)}, indent=2)


# ---------------------------------------------------------------------------
# Remote operations (dangerous — require confirmation by default)
# ---------------------------------------------------------------------------


@tool(
    "git_pull",
    description="Pull from remote. Defaults to rebase to keep history linear.",
)
def git_pull(
    remote: str = "origin",
    branch: Optional[str] = None,
    rebase: bool = True,
) -> str:
    if branch and not _valid_branch(branch):
        return _err("invalid_branch_name", branch=branch)
    args = ["git", "pull"]
    if rebase:
        args.append("--rebase")
    args.append(remote)
    if branch:
        args.append(branch)
    return run_command(args, cwd=".", capture_output=True)


@tool(
    "git_push",
    description=(
        "Push branch to remote. "
        "Force push requires confirmation unless bypass_token is supplied."
    ),
)
def git_push(
    remote: str = "origin",
    branch: Optional[str] = None,
    force: bool = False,
    require_confirmation: bool = True,
    bypass_token: Optional[str] = None,
) -> str:
    target = branch or "HEAD"
    if branch and not _valid_branch(branch):
        return _err("invalid_branch_name", branch=branch)
    args = ["git", "push", remote, target]
    if force:
        args.insert(2, "--force-with-lease")  # safer than --force
    return run_command(
        args,
        cwd=".",
        capture_output=True,
        require_confirmation=require_confirmation and force,
        bypass_token=bypass_token,
    )


@tool(
    "git_pull_request",
    description="Create a pull request on GitHub. Requires GITHUB_TOKEN and GITHUB_REPO env vars.",
)
def git_pull_request(title: str, body: str, head: str, base: str = "main") -> str:
    """
    Create a pull request on GitHub from head branch to base branch.
    """
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        return _err("GITHUB_TOKEN or GITHUB_REPO not set")
    
    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in (200, 201):
            data = response.json()
            return json.dumps({
                "pr_url": data.get("html_url"),
                "number": data.get("number"),
                "state": data.get("state")
            }, indent=2)
        else:
            return _err(f"PR creation failed: {response.status_code}", details=response.text)
    except Exception as e:
        return _err(f"Request failed: {str(e)}")


# ---------------------------------------------------------------------------
# Stash
# ---------------------------------------------------------------------------


@tool("git_stash", description="Stash or pop the working-tree changes.")
def git_stash(action: str = "push", message: Optional[str] = None) -> str:
    if action not in {"push", "pop", "list", "drop"}:
        return _err(
            "invalid_stash_action",
            action=action,
            allowed=["push", "pop", "list", "drop"],
        )
    args = ["git", "stash", action]
    if action == "push" and message:
        args += ["-m", message]
    return run_command(args, cwd=".", capture_output=True)


# ---------------------------------------------------------------------------
# Destructive operations (always require confirmation)
# ---------------------------------------------------------------------------


@tool(
    "git_reset",
    description="Reset the repository. DANGEROUS — requires HITL confirmation by default.",
)
def git_reset(
    mode: str = "--mixed",
    ref: str = "HEAD",
    require_confirmation: bool = True,
    bypass_token: Optional[str] = None,
) -> str:
    if mode not in {"--hard", "--soft", "--mixed"}:
        return _err("invalid_reset_mode", mode=mode)
    if not _valid_ref(ref):
        return _err("invalid_ref", ref=ref)
    return run_command(
        ["git", "reset", mode, ref],
        cwd=".",
        capture_output=True,
        require_confirmation=require_confirmation,
        bypass_token=bypass_token,
    )


@tool(
    "git_merge",
    description=(
        "Merge another branch into the current one. "
        "Non-fast-forward merges require HITL confirmation by default."
    ),
)
def git_merge(
    branch: str,
    no_ff: bool = False,
    require_confirmation: bool = True,
    bypass_token: Optional[str] = None,
) -> str:
    if not _valid_branch(branch):
        return _err("invalid_branch_name", branch=branch)
    args = ["git", "merge"]
    if no_ff:
        args.append("--no-ff")
    args.append(branch)
    return run_command(
        args,
        cwd=".",
        capture_output=True,
        require_confirmation=require_confirmation,
        bypass_token=bypass_token,
    )


__all__ = [
    "git_status",
    "git_repo_summary",
    "git_branches",
    "git_log",
    "git_diff",
    "git_show",
    "git_create_branch",
    "git_checkout",
    "git_add",
    "git_commit",
    "git_add_commit",
    "git_pull",
    "git_push",
    "git_pull_request",
    "git_stash",
    "git_reset",
    "git_merge",
]
