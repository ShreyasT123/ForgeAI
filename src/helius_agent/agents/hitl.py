import logging
import os
from typing import Any, Dict, Optional

from langgraph.types import Command

logger = logging.getLogger(__name__)

# HITL_BYPASS_TOKEN environment variable enables secure bypassing in CI/CD.
HITL_BYPASS_ENV = os.getenv("HITL_BYPASS_TOKEN")


def _auto_resume_payload(approve: bool, reason: str = None) -> Dict[str, Any]:
    """Format the payload for resuming an agent after an interrupt."""
    if approve:
        return {
            "decisions": [{"type": "approve", "message": reason or "auto-approved"}]
        }
    else:
        return {"decisions": [{"type": "reject", "message": reason or "rejected"}]}


def handle_hitl_interrupt(agent: Any, config: Dict[str, Any], interactive: bool = True) -> Any:
    """
    Inspect agent state for interrupts and handle them via bypass token or user input.

    - If config contains hitl.bypass==True and the provided token matches HITL_BYPASS_TOKEN -> auto approve.
    - Else if interactive -> prompt user to approve/reject via stdin.
    - Else -> return a structured error (hitl_required).

    Returns:
      - The result of agent.invoke(Command(resume=...)) if resolved.
      - A status dict if rejected or if manual intervention is required.
    """
    state = agent.get_state(config)
    if not getattr(state, "tasks", None):
        return {"status": "no_tasks"}

    # find first task with interrupts
    task = state.tasks[0]
    if not getattr(task, "interrupts", None):
        return {"status": "no_interrupts"}

    interrupt_value = task.interrupts[0].value
    # Action request payload shape usually contains action_requests
    action_requests = interrupt_value.get("action_requests", [{}])
    action_request = action_requests[0] if action_requests else {}

    logger.info("HITL Interrupt found for tool: %s", action_request.get("name"))

    # Check bypass config: config["hitl"] = {"bypass": True, "bypass_token": "TOKEN"}
    hitl_cfg = (config or {}).get("hitl") or {}
    bypass_flag = bool(hitl_cfg.get("bypass"))
    provided_token = hitl_cfg.get("bypass_token")

    # Secure bypass: environment token must be set and must match provided_token
    if bypass_flag:
        if not HITL_BYPASS_ENV:
            logger.warning(
                "Bypass requested but no HITL_BYPASS_TOKEN set in environment. Denying."
            )
        elif provided_token and provided_token == HITL_BYPASS_ENV:
            logger.info("Bypass token validated. Auto-approving the action.")
            resume_payload = _auto_resume_payload(True, reason="bypassed-by-token")
            return agent.invoke(Command(resume=resume_payload), config)
        else:
            logger.warning("Bypass token mismatch. Falling back to interactive/deny.")

    # Interactive approval
    if interactive:
        print("\n=== HUMAN-IN-THE-LOOP INTERRUPT ===")
        print(f"Tool: {action_request.get('name')}")
        print(f"Args: {action_request.get('args')}")
        user_in = (
            input("\nApprove action? (y = approve / n = reject): ").strip().lower()
        )
        if user_in == "y":
            resume_payload = _auto_resume_payload(True)
            return agent.invoke(Command(resume=resume_payload), config)
        else:
            resume_payload = _auto_resume_payload(False, reason="rejected-by-user")
            agent.invoke(Command(resume=resume_payload), config)
            return {"status": "rejected-by-user"}
    else:
        # Non-interactive and bypass not available -> signal caller to decide
        return {
            "error": "hitl_required",
            "action_request": {
                "name": action_request.get("name"),
                "args": action_request.get("args"),
            },
        }


__all__ = ["handle_hitl_interrupt", "HITL_BYPASS_ENV"]
