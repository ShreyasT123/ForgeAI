import logging
import shlex
import subprocess
from pathlib import Path
from typing import List

from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langgraph.types import interrupt

logger = logging.getLogger(__name__)

# --- Configuration & Security ---
WORKSPACE_ROOT = Path.cwd().resolve()
MAX_OUTPUT_LENGTH = 50_000

# Strict categorization of Git subcommands
SAFE_CMDS = {
    "status", "log", "diff", "show", "branch", "checkout", "switch", 
    "add", "commit", "stash", "pull", "fetch", "rev-parse"
}
DANGEROUS_CMDS = {
    "reset", "merge", "rebase", "clean", "restore", "revert", "rm"
}

def _run_git(args: List[str]) -> str:
    """
    Executes a git command securely.
    shell=False ensures no bash injections (e.g. `git commit -m "m" && rm -rf /`) can execute.
    """
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            check=True
        )
        output = res.stdout.strip() or "Success (no output)"
        return output[:MAX_OUTPUT_LENGTH] + ("\n...[TRUNCATED]" if len(output) > MAX_OUTPUT_LENGTH else "")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() or e.stdout.strip()
        return f"Git Error (Exit Code {e.returncode}):\n{error_msg}"


# ---------------------------------------------------------------------------
# 1. SAFE GIT TOOL
# ---------------------------------------------------------------------------
class GitSafeArgs(BaseModel):
    command: str = Field(
        ..., 
        description="The git command to execute (omitting the word 'git'). Examples: 'status --porcelain', 'commit -m \"fix\"', 'diff'."
    )

@tool(args_schema=GitSafeArgs)
def git_safe_op(command: str) -> str:
    """
    Execute a safe, non-destructive Git command (e.g., status, add, commit, branch).
    Do NOT use this for reset, merge, or force pushing.
    """
    try:
        args = shlex.split(command)
        if not args:
            return "Error: Empty command provided."

        subcmd = args[0]
        
        # Check for force push flags
        is_force_push = subcmd == "push" and any(f in args for f in ("--force", "-f", "--force-with-lease"))

        if subcmd in DANGEROUS_CMDS or is_force_push:
            return f"Security Error: '{subcmd}' operations are dangerous. You MUST use the `git_dangerous_op` tool instead."
            
        if subcmd not in SAFE_CMDS and subcmd != "push":
            return f"Security Error: Unrecognized or unauthorized safe command '{subcmd}'."

        return _run_git(args)
        
    except ValueError as e: # Catch shlex unmatched quotes
        return f"Argument Parsing Error: {str(e)}"
    except Exception as e:
        return f"Tool Execution Error: {str(e)}"


# ---------------------------------------------------------------------------
# 2. DANGEROUS GIT TOOL (Requires HITL)
# ---------------------------------------------------------------------------
class GitDangerousArgs(BaseModel):
    command: str = Field(
        ..., 
        description="The dangerous git command to execute. Examples: 'reset --hard HEAD~1', 'merge feature-branch'."
    )
    reason: str = Field(
        ..., 
        description="A clear explanation for the human of WHY this destructive action is needed."
    )

@tool(args_schema=GitDangerousArgs)
def git_dangerous_op(command: str, reason: str) -> str:
    """
    Execute a destructive or history-altering Git command (e.g., reset, merge, rebase, push --force).
    This tool pauses execution and requests human approval.
    """
    try:
        args = shlex.split(command)
        if not args:
            return "Error: Empty command provided."

        # Trigger Human-In-The-Loop (LangGraph v1)
        # This halts graph execution and yields this payload to the client.
        response = interrupt({
            "action": "approve_git",
            "command": f"git {command}",
            "reason": reason
        })

        # When the graph resumes, it injects the human's response here.
        if not response.get("approved", False):
            return f"Error: The human denied permission to run `git {command}`. Please find an alternative approach or ask for clarification."

        return _run_git(args)
        
    except ValueError as e:
        return f"Argument Parsing Error: {str(e)}"
    except Exception as e:
        return f"Tool Execution Error: {str(e)}"

# Bundle for the agent
GIT_TOOLS =[git_safe_op, git_dangerous_op]