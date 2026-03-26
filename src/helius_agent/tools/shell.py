import os
import platform
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langgraph.types import interrupt

# --- Security Configuration ---
WORKSPACE_ROOT = Path.cwd().resolve()

# Strict allowlist: Only these root executables can be invoked.
ALLOWLIST = frozenset({
    "pwd", "ls", "dir", "echo", "cat", "type", "uname", "whoami", "hostname",
    "git", "python", "python3", "pip", "pytest", "uv","node", "npm", "npx", "yarn", "tsc",
    "java", "javac", "go", "gcc", "g++", "rustc", "cargo", "make", "cmake", "docker",
    "grep", "find", "sort", "head", "tail", "clear", "cls"
})

# Dangerous subset: Allowed, but ALWAYS trigger Human-In-The-Loop.
DANGEROUS = frozenset({
    "rm", "del", "rmdir",  
})

# In-memory tracking for background jobs (like `npm run dev`)
_ACTIVE_JOBS: Dict[str, subprocess.Popen] = {}
_JOB_LOGS: Dict[str, List[str]] = {}

# --- Internal Helpers ---
def _resolve_cwd(cwd: Optional[str]) -> Path:
    """Ensure the target directory is strictly within REPO_ROOT."""
    target = (WORKSPACE_ROOT / cwd).resolve() if cwd else WORKSPACE_ROOT
    if not target.is_relative_to(WORKSPACE_ROOT):
        raise ValueError(f"Security Error: cwd '{cwd}' escapes the repository root.")
    target.mkdir(parents=True, exist_ok=True)
    return target

def _get_resource_limits_fn():
    """Apply CPU and File Descriptor limits on Unix systems to prevent fork bombs."""
    if platform.system().lower() == "windows":
        return None
    try:
        import resource
        def preexec():
            # Limit to 120 seconds of pure CPU time
            resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
            try:
                _, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
            except Exception:
                pass
        return preexec
    except ImportError:
        return None

def _windows_resource_monitor(proc: subprocess.Popen, cpu_limit: int = 120):
    """Fallback CPU monitor for Windows background processes."""
    try:
        import psutil
        p = psutil.Process(proc.pid)
        while proc.poll() is None:
            cpu_times = p.cpu_times()
            if (cpu_times.user + cpu_times.system) > cpu_limit:
                for child in p.children(recursive=True):
                    child.kill()
                p.kill()
                return
            time.sleep(2)
    except Exception:
        pass # Fail gracefully if psutil is missing

def _capture_background_logs(job_id: str, stream, prefix: str):
    """Continuously read background logs into memory."""
    for line in iter(stream.readline, ''):
        if line:
            _JOB_LOGS[job_id].append(f"[{prefix}] {line.strip()}")
            # Keep only the last 500 lines to prevent OOM
            if len(_JOB_LOGS[job_id]) > 500:
                _JOB_LOGS[job_id] = _JOB_LOGS[job_id][-500:]

# --- 1. CORE RUN COMMAND TOOL ---
class RunCmdArgs(BaseModel):
    command: str = Field(..., description="The shell command to execute.")
    cwd: Optional[str] = Field(default=None, description="Relative working directory.")
    background: bool = Field(default=False, description="Set to True for long-running servers (e.g. 'npm start').")

@tool(args_schema=RunCmdArgs)
def run_command(command: str, cwd: Optional[str] = None, background: bool = False) -> str:
    """Execute a shell command securely. Use background=True for servers."""
    try:
        args = shlex.split(command, posix=platform.system().lower() != "windows")
        if not args:
            return "Error: Empty command."

        executable = args[0].lower()

        # 1. Allowlist Check
        if executable not in ALLOWLIST:
            return f"Security Error: Command '{executable}' is not in the allowlist."

        # 2. HITL Check for Dangerous Commands
        if executable in DANGEROUS:
            response = interrupt({
                "action": "approve_command",
                "command": command,
                "reason": f"'{executable}' is flagged as a potentially dangerous operation."
            })
            if not response.get("approved", False):
                return "Error: Human denied permission to execute this command."

        # 3. Path & Executable Resolution
        run_cwd = _resolve_cwd(cwd)
        
        # Windows requires resolving to .cmd or .exe if shell=False
        resolved_exe = shutil.which(args[0])
        if not resolved_exe:
            return f"Error: Executable '{args[0]}' not found in PATH."
        args[0] = resolved_exe

        # 4. Background Execution
        if background:
            job_id = uuid.uuid4().hex[:8]
            _JOB_LOGS[job_id] =[]
            
            proc = subprocess.Popen(
                args, cwd=str(run_cwd),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, shell=False, preexec_fn=_get_resource_limits_fn()
            )
            
            _ACTIVE_JOBS[job_id] = proc
            
            # Start daemon threads to capture logs
            threading.Thread(target=_capture_background_logs, args=(job_id, proc.stdout, "OUT"), daemon=True).start()
            threading.Thread(target=_capture_background_logs, args=(job_id, proc.stderr, "ERR"), daemon=True).start()
            
            if platform.system().lower() == "windows":
                threading.Thread(target=_windows_resource_monitor, args=(proc,), daemon=True).start()

            return f"Started background job '{job_id}'. PID: {proc.pid}. Use `manage_background_job` to view logs or stop it."

        # 5. Foreground Execution
        result = subprocess.run(
            args, cwd=str(run_cwd),
            capture_output=True, text=True,
            timeout=120, shell=False, preexec_fn=_get_resource_limits_fn()
        )
        
        output = f"Exit Code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        return output[:50000] + ("\n...[TRUNCATED]" if len(output) > 50000 else "")

    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        return f"Execution Error: {str(e)}"

# --- 2. BACKGROUND JOB MANAGER TOOL ---
class ManageJobArgs(BaseModel):
    job_id: str = Field(..., description="The ID of the background job.")
    action: str = Field(..., description="'logs' to view recent output, 'kill' to stop the job.")

@tool(args_schema=ManageJobArgs)
def manage_background_job(job_id: str, action: str) -> str:
    """Read logs or kill a running background process."""
    if job_id not in _ACTIVE_JOBS:
        return f"Error: Job '{job_id}' not found. It may have already exited."

    proc = _ACTIVE_JOBS[job_id]
    
    if action == "logs":
        status = "RUNNING" if proc.poll() is None else f"EXITED ({proc.returncode})"
        logs = "\n".join(_JOB_LOGS[job_id][-50:]) # Send last 50 lines to LLM
        return f"Job Status: {status}\nRecent Logs:\n{logs or '(No output yet)'}"
        
    elif action == "kill":
        if proc.poll() is not None:
            return f"Job already exited with code {proc.returncode}."
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        
        del _ACTIVE_JOBS[job_id]
        del _JOB_LOGS[job_id]
        return f"Successfully killed background job '{job_id}'."
        
    return "Error: Invalid action. Use 'logs' or 'kill'."

# Bundle for DeepAgents
SHELL_TOOLS = [run_command, manage_background_job]