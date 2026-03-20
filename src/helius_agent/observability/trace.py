"""trace_agent.py

OpenTelemetry-based observability helper for your LangChain agent runtime.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# OpenTelemetry imports
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    from opentelemetry.trace import TracerProvider
except Exception as e:
    raise ImportError(
        "OpenTelemetry packages not found. Install opentelemetry-api, opentelemetry-sdk, "
        "and opentelemetry-exporter-otlp to enable observability. Error: {}".format(e)
    )


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _get_repo_root() -> Path:
    return Path(os.getenv("REPO_ROOT", ".")).resolve()


def _get_audit_file() -> Path:
    audit_dir = _get_repo_root() / ".agent_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return audit_dir / "observability.jsonl"


# Default config from env
OTEL_COLLECTOR = os.getenv(
    "OTEL_COLLECTOR_ENDPOINT",
    os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
)
SERVICE_NAME = os.getenv("SERVICE_NAME", "agent")
ENABLE_CONSOLE_EXPORT = os.getenv("ENABLE_OTEL_CONSOLE", "0") == "1"


# Global instruments (populated by init_observability)
_tracer = None
_meter = None
_tokens_counter = None
_tool_calls_counter = None
_invocation_histogram = None


def _append_audit(entry: Dict[str, Any], retries: int = 3) -> None:
    """Append entry to audit file with basic retry logic."""
    last_exc = None
    for i in range(retries):
        try:
            timestamp = time.time()
            entry_out = {"ts": timestamp, **entry}
            with open(_get_audit_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry_out, ensure_ascii=False) + "\n")
            return
        except (IOError, OSError) as e:
            last_exc = e
            time.sleep(0.1 * (i + 1))
    
    logger.warning("Failed to write audit entry after %d retries: %s", retries, last_exc)


def init_observability(
    collector_endpoint: Optional[str] = None, service_name: Optional[str] = None
):
    """Initialize tracer and meter with OTLP exporters."""
    global _tracer, _meter, _tokens_counter, _tool_calls_counter, _invocation_histogram

    collector = collector_endpoint or OTEL_COLLECTOR
    svc = service_name or SERVICE_NAME

    # Resource attributes
    resource = Resource.create({"service.name": svc})

    # Tracing
    tracer_provider = SDKTracerProvider(resource=resource)
    otlp_span_exporter = OTLPSpanExporter(endpoint=collector)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_span_exporter))
    if ENABLE_CONSOLE_EXPORT:
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)
    _tracer = trace.get_tracer(__name__)

    # Metrics
    metric_exporter = OTLPMetricExporter(endpoint=collector)
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(svc)

    # Instruments
    _tokens_counter = _meter.create_counter(
        "agent.tokens", description="tokens used by agent invocations"
    )
    _tool_calls_counter = _meter.create_counter(
        "agent.tool_calls", description="number of tool calls"
    )
    try:
        _invocation_histogram = _meter.create_histogram(
            "agent.invocation.duration_ms", description="invocation latency (ms)"
        )
    except Exception:
        _invocation_histogram = None

    logger.info(
        "Observability initialized. OTLP collector=%s, service_name=%s", collector, svc
    )
    _append_audit(
        {"event": "observability.initialized", "collector": collector, "service": svc}
    )

    return _tracer, _meter


def _redact_args(args: Any) -> str:
    """Deterministically hash tool args to avoid storing secrets in telemetry/audit."""
    try:
        j = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        j = str(args)
    return hashlib.sha256(j.encode("utf-8")).hexdigest()


def instrument_agent_invocation(
    user_id: Optional[str],
    session_id: Optional[str],
    run_fn: Callable[[Any], Any],
    **attrs,
) -> Any:
    """Wrap a full agent invocation."""
    global _tracer, _invocation_histogram
    if _tracer is None:
        # Auto-init with defaults if not already done
        init_observability()

    attrs = {**attrs}
    if user_id:
        attrs["user.id"] = user_id
    if session_id:
        attrs["session.id"] = session_id

    t0 = time.time()
    with _tracer.start_as_current_span("agent.invocation", attributes=attrs) as span:
        try:
            result = run_fn(span)
            return result
        except Exception as e:
            span.record_exception(e)
            span.set_attribute("agent.status", "error")
            raise
        finally:
            dur_ms = int((time.time() - t0) * 1000)
            try:
                if _invocation_histogram is not None:
                    _invocation_histogram.record(dur_ms)
                else:
                    span.set_attribute("agent.duration_ms", dur_ms)
            except Exception:
                logger.exception("Failed to record invocation duration")
            _append_audit(
                {
                    "event": "agent.invocation.finished",
                    "duration_ms": dur_ms,
                    "user": user_id,
                    "session": session_id,
                }
            )


def instrument_llm_call(
    model_name: str,
    prompt: str,
    llm_call_fn: Callable[[str], Any],
    span: Optional[Any] = None,
) -> Any:
    """Instrument a single LLM call."""
    global _tracer, _tokens_counter
    if _tracer is None:
        init_observability()

    attrs = {"model.name": model_name, "prompt.length": len(prompt)}
    with _tracer.start_as_current_span("llm.call", attributes=attrs) as llm_span:
        t0 = time.time()
        try:
            resp, usage = llm_call_fn(prompt)
            prompt_tokens = int(usage.get("prompt_tokens", 0))
            completion_tokens = int(usage.get("completion_tokens", 0))
            total_tokens = int(
                usage.get("total_tokens", prompt_tokens + completion_tokens)
            )

            llm_span.set_attribute("tokens.prompt", prompt_tokens)
            llm_span.set_attribute("tokens.completion", completion_tokens)
            llm_span.set_attribute("tokens.total", total_tokens)
            llm_span.set_attribute("model.name", model_name)

            try:
                _tokens_counter.add(total_tokens, {"model": model_name})
            except Exception:
                logger.exception("Failed to add tokens metric")

            return resp, usage
        except Exception as e:
            llm_span.record_exception(e)
            llm_span.set_attribute("llm.status", "error")
            raise
        finally:
            llm_span.set_attribute("llm.duration_ms", int((time.time() - t0) * 1000))


def instrument_tool_call(
    tool_name: str, args: Any, tool_fn: Callable[..., Any], span: Optional[Any] = None
) -> Any:
    """Instrument a tool call."""
    global _tracer, _tool_calls_counter
    if _tracer is None:
        init_observability()

    args_hash = _redact_args(args)
    attrs = {"tool.name": tool_name, "tool.args_hash": args_hash}
    with _tracer.start_as_current_span("tool.call", attributes=attrs) as tool_span:
        t0 = time.time()
        try:
            if isinstance(args, dict):
                out = tool_fn(**args)
            elif isinstance(args, (list, tuple)):
                out = tool_fn(*args)
            else:
                out = tool_fn(args)

            tool_span.set_attribute("tool.status", "ok")
            return out
        except Exception as e:
            tool_span.record_exception(e)
            tool_span.set_attribute("tool.status", "error")
            raise
        finally:
            dur_ms = int((time.time() - t0) * 1000)
            tool_span.set_attribute("tool.duration_ms", dur_ms)
            try:
                _tool_calls_counter.add(1, {"tool": tool_name})
            except Exception:
                logger.exception("Failed to increment tool_calls_counter")
            _append_audit(
                {
                    "event": "tool.call",
                    "tool": tool_name,
                    "args_hash": args_hash,
                    "duration_ms": dur_ms,
                }
            )


def wrap_agent_invoke(
    agent_invoke_fn: Callable[[Dict], Any], user_id: Optional[str] = None
):
    """Return a wrapped invoke function that instruments the agent invocation."""

    def wrapped_invoke(payload: Dict, *args, **kwargs):
        session_id = None
        if isinstance(payload, dict):
            cfg = payload.get("config") or payload.get("configurable") or {}
            session_id = cfg.get("thread_id") or cfg.get("session_id")

        def run_fn(parent_span):
            return agent_invoke_fn(payload, *args, **kwargs)

        return instrument_agent_invocation(
            user_id=user_id, session_id=session_id, run_fn=run_fn
        )

    return wrapped_invoke
