# Implementation Plan: Deep Plan Mode (STATUS: CORE COMPLETE)

This plan outlines the steps to implement "Deep Plan Mode" in the Helius Agent, following the architecture described in the project's deep agent documentation.

## 1. Core Agent Enhancements
**Goal:** Support dual-mode operation (Fast vs. Deep) and advanced configuration.

- [x] **Define `AgentMode` Enum**:
    - `FAST`: Standard tool-calling loop with basic tools.
    - `DEEP`: Enhanced loop with planning, VFS, and subagents. (Implemented in `base.py`)
- [x] **Refactor `AgentConfig`**:
    - Add `mode: AgentMode`.
    - Add `subagents: List[SubAgentConfig]`.
    - Add `thinking: ThinkingConfig` (Implemented in `base.py`)
- [x] **Thinking Support**: Update `src/helius_agent/agents/base.py` to pass thinking parameters to supported LLM providers. (Implemented for Anthropic)

## 2. Planning & Task Decomposition
**Goal:** Enable the agent to break down complex tasks and track progress.

- [x] **Configure `TodoListMiddleware`**:
    - Integrate the built-in `TodoListMiddleware` into the agent's middleware pipeline. (Implemented in `base.py`)
- [x] **Built-in `write_todos` Tool**:
    - Use the built-in `write_todos` tool provided by the planning middleware. (Implemented in `planning.py`)
- [x] **System Prompt Integration**:
    - The default system prompt should already contain instructions for the planning tool. (Implemented via middleware injection)

## 3. Virtual Filesystem (VFS) & Backends
**Goal:** Use a pluggable backend system for file operations and context isolation.

- [x] **Implement `BackendProtocol`**: Define a standard interface for `ls`, `read`, `write`, `edit`, `glob`, and `grep`. (Implemented in `vfs.py`)
- [x] **Develop Built-in Backends**:
    - `LocalDiskBackend`: Operations on the host filesystem.
    - `StateBackend`: Store files in LangGraph state (ephemeral to the thread).
    - `StoreBackend`: Persistent cross-thread storage using a JSON store.
    - `CompositeBackend`: Route different paths (e.g., `/memories/`) to different backends. (All implemented in `vfs.py`)
- [x] **Refactor File Tools**: Update `src/helius_agent/tools/files.py` to delegate to the configured backend. (Completed)

## 4. Subagent Delegation
**Goal:** Enable "context isolation" by spawning specialized subagents.

- [x] **Implement `task` Tool**:
    - Allow the main agent to spawn a subagent with a specific prompt and toolset. (Stub implemented in `subagents.py`)
- [ ] **Subagent Configuration Registry**:
    - Support loading subagent definitions from `AGENTS.md` files. (PENDING Phase 2)

## 5. Long-term Memory
**Goal:** Persist preferences and patterns across conversations.

- [x] **Hybrid Storage Architecture**:
    - Use `CompositeBackend` to route `/memories/*` to a `StoreBackend`. (Architecture verified)
- [ ] **Memory Patterns**:
    - Implement "Self-improving instructions" by allowing the agent to edit `/memories/instructions.md`. (PENDING Prompt tuning)

## 6. Execution & Validation
- [x] **Deep Plan Test Suite**: Create tests for complex multi-step scenarios. (Verified in `tests/test_deepplan.py`)
- [x] **VFS Validation**: Ensure files written in a subagent's `StateBackend` correctly isolate context. (Verified)
- [x] **Memory Persistence**: Verify `/memories/` survive thread restarts. (Verified via `StoreBackend` test)

---
*This plan is a living document and should be updated as implementation progresses.*
