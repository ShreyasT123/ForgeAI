import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from helius_agent.tools.shell import (  # noqa: E402
    run_command,
    get_command_status,
    get_command_output,
)


def _wait(job_id: str, interval: float = 1.0, max_wait: float = 300.0) -> None:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        status = json.loads(get_command_status.invoke({"job_id": job_id}))
        if status.get("status") == "finished":
            return
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not finish in time")


def main() -> None:
    init = json.loads(
        run_command.invoke({"cmd": ["npm", "init", "-y"], "background": True})
    )
    print("init:", init)
    job_id = init["job_id"]
    _wait(job_id, interval=1.0, max_wait=120.0)
    print("init output:", get_command_output.invoke({"job_id": job_id}))

    install = json.loads(
        run_command.invoke({"cmd": ["npm", "install", "react"], "background": True})
    )
    print("install:", install)
    job_id = install["job_id"]
    _wait(job_id, interval=2.0, max_wait=600.0)
    print("install output:", get_command_output.invoke({"job_id": job_id}))


if __name__ == "__main__":
    main()
