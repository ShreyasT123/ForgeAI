import json
import logging
import time
from pathlib import Path
from typing import Any, Dict
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from opentelemetry import metrics

logger = logging.getLogger(__name__)

# --- Configuration ---
AUDIT_FILE = Path.cwd() / ".agent_audit" / "observability.jsonl"
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)

# --- Global Metrics ---
meter = metrics.get_meter("helius-agent")
tokens_counter = meter.create_counter("agent.tokens", description="LLM tokens used")
tool_calls_counter = meter.create_counter("agent.tool_calls", description="Tool invocations")

def _log_audit(event: str, data: Dict[str, Any]):
    try:
        entry = {"ts": time.time(), "event": event, **data}
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Audit failed: {e}")

class AuditTelemetryHandler(BaseCallbackHandler):
    """
    Native LangChain/LangGraph callback.
    No need to wrap functions; it hooks into the graph execution context.
    """
    def __init__(self, session_id: str = "default"):
        self.session_id = session_id
        self._tool_starts: Dict[UUID, float] = {}

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> None:
        self._tool_starts[run_id] = time.time()

    def on_tool_end(self, output: str, *, run_id: UUID, name: str, **kwargs: Any) -> None:
        start = self._tool_starts.pop(run_id, time.time())
        duration_ms = int((time.time() - start) * 1000)
        
        # OTel Metric
        tool_calls_counter.add(1, {"tool": name})
        
        # Local Audit
        _log_audit("tool.call", {
            "session_id": self.session_id,
            "tool": name,
            "duration_ms": duration_ms
        })

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        if not response.llm_output: return
        
        usage = response.llm_output.get("token_usage", {})
        total = usage.get("total_tokens", 0)
        model = response.llm_output.get("model_name", "unknown")

        # OTel Metric
        tokens_counter.add(total, {"model": model})
        
        # Local Audit
        _log_audit("llm.call", {
            "session_id": self.session_id,
            "model": model,
            "tokens": total
        })

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        _log_audit("tool.error", {"session_id": self.session_id, "error": str(error)})