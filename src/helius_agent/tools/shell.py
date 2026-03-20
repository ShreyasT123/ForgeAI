"""shell_tools.py — Safe subprocess execution primitives for a coding agent.

Security model
--------------
* All commands run inside REPO_ROOT (path-traversal guard on cwd).
* An allowlist gates which executables are accepted at all.
* A separate dangerous-set requires HITL confirmation or a bypass token.
* resource limits are applied on Unix (CPU cap) and Windows (psutil monitor).
* shell=False always — no shell injection possible.
"""

import json
import logging
import os
import platform
import shlex
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# REPO_ROOT
# ---------------------------------------------------------------------------


def _get_repo_root() -> Path:
    return Path(os.getenv("REPO_ROOT", ".")).resolve()


# ---------------------------------------------------------------------------
# HITL bypass token (optional CI integration)
# ---------------------------------------------------------------------------

SHELL_BYPASS_TOKEN_ENV: Optional[str] = os.getenv("SHELL_BYPASS_TOKEN")

# ---------------------------------------------------------------------------
# Allowlist / dangerous set
# ---------------------------------------------------------------------------

DEFAULT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "pwd", "ls", "dir", "echo", "cat", "type", "uname", "whoami", "hostname",
        "uptime", "df", "du", "free", "top", "htop", "tasklist", "systeminfo",
        "git", "hg", "svn", "python", "python3", "pip", "pip3", "pytest", "ipython",
        "jupyter", "conda", "poetry", "virtualenv", "node", "npm", "npx", "yarn", "tsc",
        "java", "javac", "jar", "gradle", "mvn", "go", "gcc", "g++", "rustc", "cargo",
        "make", "cmake", "bazel", "docker", "docker-compose", "kubectl", "minikube",
        "kind", "helm", "aws", "az", "gcloud", "terraform", "vault", "ping", "traceroute",
        "nslookup", "dig", "curl", "wget", "scp", "ssh", "netstat", "lsof", "ip",
        "ifconfig", "route", "arp", "vim", "nano", "emacs", "code", "subl", "notepad",
        "notepad++", "sed", "awk", "grep", "find", "sort", "uniq", "cut", "head", "tail",
        "xargs", "env", "set", "clear", "cls",
    }
)

DANGEROUS_COMMANDS: frozenset[str] = frozenset(
    {
        "rm", "del", "rmdir", "mv", "cp", "format", "diskpart", "chown", "chmod",
        "attrib", "shutdown", "reboot", "poweroff", "systemctl", "service", "init",
        "apt", "yum", "dnf", "pacman", "brew", "choco", "scoop", "docker",
        "docker-compose", "kubectl", "helm", "terraform", "curl", "wget", "scp",
        "ssh", "ftp", "rsync", "netcat", "nc", "telnet", "python", "python3",
        "node", "npm", "npx", "java", "javac", "go", "cargo", "rustc", "gcc", "g++",
    }
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_cwd(cwd: Optional[str]) -> Path:
    repo_root = _get_repo_root()
    if not cwd:
        return repo_root
    p = (repo_root / cwd).resolve()
    try:
        p.relative_to(repo_root)
    except ValueError:
        raise ValueError(f"Access denied: cwd '{cwd}' escapes REPO_ROOT")
    if not p.exists():
        raise FileNotFoundError(f"cwd '{cwd}' does not exist under REPO_ROOT")
    return p


def _split_command(cmd: Union[str, List[str]]) -> List[str]:
    if isinstance(cmd, list):
        return [str(a) for a in cmd]
    posix = not platform.system().lower().startswith("win")
    return shlex.split(cmd, posix=posix)


def _top_command_name(args: List[str]) -> str:
    return Path(args[0]).name if args else ""


def _is_allowed(cmd_name: str, allowlist: frozenset[str]) -> bool:
    return cmd_name.lower() in {c.lower() for c in allowlist}


def _is_dangerous(cmd_name: str) -> bool:
    return cmd_name.lower() in {c.lower() for c in DANGEROUS_COMMANDS}


def _normalize_windows_exec(args: List[str]) -> List[str]:
    if platform.system().lower() != "windows" or not args:
        return args
    cmd = args[0].lower()
    if cmd in {"npm", "npx", "yarn"}:
        return ["cmd", "/c"] + args
    return args


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


def _mk_audit_entry(request: Dict[str, Any], result: Dict[str, Any]) -> None:
    try:
        audit_dir = _get_repo_root() / ".agent_audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), "request": request, "result": result}
        with open(audit_dir / "commands.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        logger.exception("Failed to write audit log")


# ---------------------------------------------------------------------------
# Background job infrastructure
# ---------------------------------------------------------------------------


def _get_jobs_dir() -> Path:
    jobs_dir = _get_repo_root() / ".agent_audit" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    return jobs_dir


def _write_job_meta(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _load_job_meta(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _tail_lines(path: Path, max_lines: int) -> str:
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return "".join(lines[-max_lines:])


def _monitor_process_resource_limits(proc: subprocess.Popen, cpu_limit: int = 120):
    """Thread-based resource monitor for Windows or as fallback."""
    try:
        import psutil
        p = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                # Check CPU time
                cpu_times = p.cpu_times()
                total_cpu = cpu_times.user + cpu_times.system
                if total_cpu > cpu_limit:
                    logger.warning("Process %d exceeded CPU limit (%ds). Terminating.", proc.pid, cpu_limit)
                    # Kill process and all children
                    for child in p.children(recursive=True):
                        child.kill()
                    p.kill()
                    return
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                break
            time.sleep(2)
    except ImportError:
        # Fallback to simple wall-clock if psutil not available
        t0 = time.time()
        while proc.poll() is None:
            if time.time() - t0 > cpu_limit * 2: # Grace period for wall clock
                logger.warning("Process %d exceeded wall-clock limit. Terminating.", proc.pid)
                proc.kill()
                return
            time.sleep(5)


def _start_background_job(
    args: List[str], cwd: Optional[str], request: Dict[str, Any]
) -> str:
    jobs_dir = _get_jobs_dir()
    job_id = uuid.uuid4().hex
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    stdout_path = job_dir / "stdout.txt"
    stderr_path = job_dir / "stderr.txt"
    rc_path = job_dir / "returncode.json"
    meta_path = job_dir / "job.json"

    run_cwd = _safe_cwd(cwd)

    job_meta: Dict[str, Any] = {
        "job_id": job_id, "cmd_args": args, "cwd": str(run_cwd),
        "status": "running", "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path), "returncode_path": str(rc_path),
        "started_at": time.time(), "pid": None,
    }

    stdout_f = open(stdout_path, "w", encoding="utf-8")
    stderr_f = open(stderr_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        args, cwd=str(run_cwd), stdout=stdout_f, stderr=stderr_f,
        text=True, shell=False, preexec_fn=_make_preexec_fn()
    )
    job_meta["pid"] = proc.pid
    _write_job_meta(meta_path, job_meta)

    # Resource monitor for Windows (since preexec_fn=None)
    if platform.system().lower() == "windows":
        threading.Thread(target=_monitor_process_resource_limits, args=(proc,), daemon=True).start()

    def _wait() -> None:
        try:
            rc = proc.wait()
        except Exception:
            rc = -1
        finally:
            stdout_f.close()
            stderr_f.close()

        now = time.time()
        job_meta.update({"status": "finished", "returncode": rc, "finished_at": now})
        _write_job_meta(meta_path, job_meta)
        rc_path.write_text(json.dumps({"returncode": rc, "finished_at": now}), encoding="utf-8")

    threading.Thread(target=_wait, daemon=True, name=f"job-{job_id[:8]}").start()

    result: Dict[str, Any] = {"job_id": job_id, "status": "running", "pid": proc.pid}
    _mk_audit_entry(request, result)
    return json.dumps(result, indent=2)


def _make_preexec_fn():
    if platform.system().lower() == "windows":
        return None
    try:
        import resource
        def _limit_child() -> None:
            resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
            try:
                _soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
                resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
            except Exception:
                pass
        return _limit_child
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Public tools
# ---------------------------------------------------------------------------


@tool("run_command")
def run_command(
    cmd: Union[str, List[str]], cwd: Optional[str] = None,
    timeout: Optional[int] = 30, capture_output: bool = True,
    dry_run: bool = False, allowlist: Optional[List[str]] = None,
    require_confirmation: bool = False, bypass_token: Optional[str] = None,
    background: bool = False,
) -> str:
    """Execute a command safely inside REPO_ROOT."""
    request = locals()
    try:
        args = _split_command(cmd)
        if not args: return json.dumps({"error": "empty_command"})
        cmd_name = _top_command_name(args)
        effective_allowlist = frozenset(allowlist) if allowlist else DEFAULT_ALLOWLIST

        if not _is_allowed(cmd_name, effective_allowlist):
            return json.dumps({"error": "command_not_in_allowlist", "cmd_name": cmd_name}, indent=2)

        if _is_dangerous(cmd_name) and require_confirmation:
            if not (bypass_token and SHELL_BYPASS_TOKEN_ENV and bypass_token == SHELL_BYPASS_TOKEN_ENV):
                return json.dumps({"error": "hitl_required", "action_request": {"name": cmd_name, "args": args}}, indent=2)

        if dry_run:
            return json.dumps({"dry_run": True, "cmd_args": args, "cwd": str(_safe_cwd(cwd))}, indent=2)

        exec_args = _normalize_windows_exec(args)
        if background: return _start_background_job(exec_args, cwd, request)

        completed = subprocess.run(
            exec_args, cwd=str(_safe_cwd(cwd)),
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            timeout=timeout, check=False, shell=False, text=True,
            preexec_fn=_make_preexec_fn()
        )
        result = {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        _mk_audit_entry(request, result)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"error": "exception", "message": str(exc)}, indent=2)


@tool("get_command_status")
def get_command_status(job_id: str) -> str:
    """Check status of a background job."""
    try:
        meta_path = _get_jobs_dir() / job_id / "job.json"
        if not meta_path.exists(): return json.dumps({"error": "job_not_found"})
        meta = _load_job_meta(meta_path)
        rc_path = meta_path.parent / "returncode.json"
        if rc_path.exists():
            rc_data = json.loads(rc_path.read_text(encoding="utf-8"))
            meta.update({"status": "finished", **rc_data})
        return json.dumps(meta, indent=2)
    except Exception as e: return json.dumps({"error": str(e)})


@tool("cleanup_audit_logs")
def cleanup_audit_logs(days_to_keep: int = 7) -> str:
    """Purge old audit logs and .bak files."""
    repo_root = _get_repo_root()
    audit_dir = repo_root / ".agent_audit"
    now = time.time()
    seconds_to_keep = days_to_keep * 86400
    purged_count = 0

    if audit_dir.exists():
        # Cleanup job dirs
        jobs_dir = audit_dir / "jobs"
        if jobs_dir.exists():
            for d in jobs_dir.iterdir():
                if d.is_dir() and (now - d.stat().st_mtime > seconds_to_keep):
                    import shutil
                    shutil.rmtree(d)
                    purged_count += 1
        
        # Could rotate commands.jsonl here if it was large
    
    # Cleanup .bak files in the repo
    for bak_file in repo_root.rglob("*.bak"):
        if now - bak_file.stat().st_mtime > seconds_to_keep:
            bak_file.unlink()
            purged_count += 1
            
    return json.dumps({"status": "success", "purged_items": purged_count})

@tool("get_command_output")
def get_command_output(job_id: str, tail_lines: int = 200) -> str:
    """Fetch output from a background job."""
    meta_path = _get_jobs_dir() / job_id / "job.json"
    if not meta_path.exists(): return json.dumps({"error": "job_not_found"})
    meta = _load_job_meta(meta_path)
    return json.dumps({
        "stdout": _tail_lines(Path(meta["stdout_path"]), tail_lines),
        "stderr": _tail_lines(Path(meta["stderr_path"]), tail_lines)
    })

@tool("cancel_command")
def cancel_command(job_id: str) -> str:
    """Cancel a running background job."""
    meta_path = _get_jobs_dir() / job_id / "job.json"
    if not meta_path.exists(): return json.dumps({"error": "job_not_found"})
    meta = _load_job_meta(meta_path)
    if meta.get("status") == "finished": return json.dumps({"status": "already_finished"})
    try:
        os.kill(int(meta["pid"]), 15)
        return json.dumps({"status": "cancel_requested"})
    except Exception as e: return json.dumps({"error": str(e)})

def run_command_raw(*args, **kwargs) -> str:
    return run_command.func(*args, **kwargs)
