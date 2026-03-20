# Implementation Plan: Helius Agent Improvements

This plan outlines the steps to improve the repository structure, code quality, and robustness of the Helius Agent system, addressing findings from the initial audit.

## 1. Repository Restructuring
**Goal:** Clean up the project root and organize source code and tests more logically.

- [ ] **Create `pyproject.toml`**: Define project metadata, dependencies, and tool configurations (pytest, black, ruff).
- [ ] **Cleanup Root**: 
    - Move `hello.txt` to a `data/` or `examples/` directory.
    - Remove or move `src/helius_agent/t.py` to `scripts/` or `tests/manual/`.
- [ ] **Modularize Tools**: Group tools in `src/helius_agent/tools/` into sub-packages if they grow further (e.g., `system/`, `vcs/`, `filesystem/`).
- [ ] **Standardize Tests**: Ensure all tests in `tests/` follow a consistent naming convention and use a shared test base/fixtures.

## 2. Code Robustness & Abstraction
**Goal:** Improve flexibility and reliability of the agent's core components.

- [ ] **LLM Provider Abstraction**:
    - Refactor `src/helius_agent/agents/base.py` to support multiple LLM providers (Mistral, OpenAI, Anthropic, Gemini) via a registry or factory pattern.
    - Use environment variables to determine the default provider.
- [ ] **Enhanced Error Handling**:
    - Improve resilience in `observability/trace.py` to prevent silent failures in audit logging.
    - Add retries or fallback mechanisms for critical telemetry/audit operations.
- [ ] **Type Safety**: Add type hints to all tool functions and internal helpers to improve IDE support and catch bugs early.

## 3. Security & Resource Management
**Goal:** Extend safety features to more environments and improve maintenance.

- [ ] **Windows Resource Limiting**:
    - Research and implement CPU/Memory limits for Windows using `psutil` or Windows Job Objects to parity Unix `preexec_fn` functionality.
- [ ] **Audit & Backup Maintenance**:
    - Implement a `MaintenanceTool` or background task to:
        - Rotate and compress old audit logs in `.agent_audit/`.
        - Purge old `.bak` files older than a configurable number of days.
- [ ] **Path Traversal Edge Cases**: Audit `_safe_path` for more complex symbolic link scenarios or case-insensitive filesystem issues on Windows/macOS.

## 4. Observability & Developer Experience
**Goal:** Improve visibility into agent actions and ease of development.

- [ ] **Local Audit Viewer**: Create a simple CLI script or dashboard to visualize the `.agent_audit/commands.jsonl` log.
- [ ] **Improved Logging**: Standardize log formats across all modules for better grep-ability and ingestion into external log managers.
- [ ] **Documentation**: Update README with clear instructions on how to add new tools, configure HITL, and interpret audit logs.

## 5. Timeline & Milestones
- **Phase 1 (Infrastructure)**: `pyproject.toml`, root cleanup, LLM abstraction.
- **Phase 2 (Robustness)**: Error handling, type safety, Windows resource limits.
- **Phase 3 (Maintenance)**: Audit rotation, backup purging, documentation.

---
*This plan is a living document and should be updated as implementation progresses.*
