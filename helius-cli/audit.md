# helius-cli Code Audit Report

**Date:** May 12, 2026
**Project:** helius-cli (Helius Code)
**Status:** Functional Prototype / Alpha

## 1. Executive Summary
`helius-cli` is a well-structured autonomous code agent built on a modern stack (`LangGraph`, `DeepAgents`, `Ink`). It features a polished terminal interface, robust security primitives (path isolation, HITL), and industrial-grade reliability features (LLM rotation, session check-pointing). While the foundation is solid, it currently lacks the "killer" features of high-end autonomous agents like Claude-Code: deep language intelligence (AST/LSP), project-wide semantic indexing, and autonomous verification loops.

## 2. Technical Architecture
- **Framework:** Leverages `deepagents` as an orchestration layer over `LangGraph`. This provides a clean graph-based state management system.
- **Reliability:** The `RotatingChatModel` is a standout feature, providing resilience against rate limits and model-specific failures through round-robin or fallback strategies.
- **Persistence:** Session persistence via `JsonFileSaver` is implemented, allowing long-running tasks to survive restarts.
- **UI:** The `Ink`-based TUI is exceptionally polished, offering a mascot-driven, "human-centric" experience that is rare in CLI tools.

## 3. Tooling & Security
- **Security Primitives:** Excellent work on `resolveWorkspacePath`. Boundary enforcement is strict and prevents directory traversal.
- **HITL (Human-In-The-Loop):** A robust interrupt system for "dangerous" commands (shell/git) is in place.
- **FS Tools:** Basic operations (`ls`, `read`, `write`, `delete`) are present. `apply_patch` is custom-implemented, which is prone to failure on complex diffs. `grep_search` is a sequential JS implementation, which will bottleneck on large codebases.
- **Git Tools:** Well-defined safe vs. dangerous operations.

## 4. Identified Weaknesses & Gaps
- **Language Intelligence:** The agent treats code as raw text. It lacks AST (Abstract Syntax Tree) awareness or LSP (Language Server Protocol) integration. It cannot "understand" imports, class hierarchies, or symbol definitions without manual searching.
- **Context Injection:** The agent starts with zero project-specific context (other than what the user provides). It doesn't automatically ingest `README.md`, `package.json`, or architecture docs.
- **Tool Sophistication:** `grep_search` and `apply_patch` are "homegrown" and lack the performance/robustness of industry standards (like `ripgrep` or `git apply`).
- **Autonomous Verification:** There is no built-in loop for the agent to "verify" its own work (e.g., run tests, check types, and self-correct) without explicit user instruction.
- **Testing:** The internal test suite is minimal, covering only basic security primitives.

## 5. Potential for "Claude-Code Killer" Status
To reach industrial-grade maturity, the project must move from being a "file manipulator" to a "code engineer." This requires:
1.  **Semantic Context:** Automatic project indexing.
2.  **Structural Understanding:** AST/Symbol-based navigation.
3.  **Proactive Validation:** Automatic build/test/fix loops.
4.  **Performance:** Optimized native tooling for search and indexing.
