import logging
import os
from typing import Any, Dict, Optional

from langgraph.types import Command

logger = logging.getLogger(__name__)

# Secure CI/CD bypass token
HITL_BYPASS_ENV = os.getenv("HITL_BYPASS_TOKEN")

def handle_hitl_interrupt(agent: Any, config: Dict[str, Any], interactive: bool = True) -> Optional[Any]:
    """
    Processes pending Human-In-The-Loop (HITL) interrupts in the LangGraph state.
    
    Args:
        agent: The compiled LangGraph / DeepAgent.
        config: The LangGraph config dict (must contain thread_id).
        interactive: Whether to prompt via CLI if no bypass token is provided.
        
    Returns:
        The new graph state after resumption, or None if no interrupts were pending.
    """
    state = agent.get_state(config)
    
    # 1. Check if the graph is actually paused on an interrupt
    if not state.next or not state.tasks:
        return None
        
    task = state.tasks[0]
    if not task.interrupts:
        return None

    # 2. Extract the payload yielded by the tool's `interrupt({...})` call
    interrupt_payload = task.interrupts[0].value
    
    # Supports both our custom tools and generic action requests
    cmd_name = interrupt_payload.get("command") or interrupt_payload.get("name") or "Unknown Action"
    reason = interrupt_payload.get("reason") or "No justification provided by agent."

    logger.info("HITL Interrupt paused execution for tool: %s", cmd_name)

    # 3. Check for CI/CD Bypass Token via LangGraph's standard 'configurable' dict
    configurable = config.get("configurable", {})
    provided_token = configurable.get("hitl_bypass_token")

    if provided_token:
        if not HITL_BYPASS_ENV:
            logger.warning("Bypass requested but HITL_BYPASS_TOKEN is not set in environment.")
        elif provided_token == HITL_BYPASS_ENV:
            logger.info("✅ Bypass token validated. Auto-approving dangerous action.")
            return agent.invoke(Command(resume={"approved": True}), config)
        else:
            logger.warning("❌ Bypass token mismatch! Falling back to interactive mode.")

    # 4. Interactive CLI Approval
    if interactive:
        print("\n" + "="*60)
        print("🛑 HUMAN-IN-THE-LOOP AUTHORIZATION REQUIRED 🛑")
        print(f"Requested Action : {cmd_name}")
        print(f"Agent's Reason   : {reason}")
        print("="*60)
        
        user_in = input("\nApprove execution? (y/N): ").strip().lower()
        is_approved = user_in in ('y', 'yes')
        
        if is_approved:
            logger.info("Human approved the action.")
        else:
            logger.info("Human rejected the action.")
            
        # Resume the graph, passing the boolean decision back to the tool
        return agent.invoke(Command(resume={"approved": is_approved}), config)

    # 5. Non-interactive & No bypass -> Force Reject
    # We MUST resume the graph with a rejection. If we just return an error string, 
    # the graph remains indefinitely suspended and the agent loop breaks.
    logger.error("HITL required but interactive mode is off and no valid bypass token provided. Auto-rejecting.")
    return agent.invoke(Command(resume={"approved": False, "error": "interactive_mode_disabled"}), config)

__all__ =["handle_hitl_interrupt", "HITL_BYPASS_ENV"]