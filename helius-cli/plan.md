# Transformation Plan: Helius "Industrial Grade"

This plan outlines the roadmap to transform `helius-cli` into a market-leading autonomous agent.

## Phase 1: Foundation & Tooling (Short Term)
*Goal: Replace custom, fragile logic with robust, high-performance tools.*

1.  **Upgrade Search:** Replace the custom `grep_search` with a high-performance `glob` + `content search` tool. Integrate `ripgrep` (if available) or an optimized JS library.
2.  **Robust Patching:** Switch from the custom `apply_patch` to a more resilient library (like `diff-match-patch`) or use `git apply` directly for more reliable code edits.
3.  **Project Indexing:** Implement a "Project Discovery" node that runs on startup. It should automatically read `README.md`, `package.json`, `tsconfig.json`, and `.gitignore` to build a mental map of the project.
4.  **Context Injection:** Automatically provide the agent with a summary of the current directory structure and key project files in the system prompt.

## Phase 2: Language Intelligence (Medium Term)
*Goal: Move from text manipulation to semantic code understanding.*

1.  **AST Tools:** Integrate `tree-sitter`. Add tools like `get_symbols_in_file`, `find_references`, and `get_class_hierarchy`.
2.  **LSP Integration:** (Optional/Advanced) Implement a basic LSP client to leverage existing language servers for type-checking and navigation.
3.  **Smart "Read":** Enhance `read_file` to be "intelligence-aware"—e.g., providing summaries of large files instead of just truncating them.

## Phase 3: Autonomous Loops & Verification (Medium Term)
*Goal: Enable the agent to guarantee the quality of its own work.*

1.  **Test Runner Tool:** Create a specialized tool that identifies the project's test runner and executes specific tests related to the changed files.
2.  **Verification Loop:** Implement a LangGraph cycle: `Edit` -> `Lint/TypeCheck` -> `Test` -> `Fix (if fail)`. The agent should not report "Done" until the verification loop passes.
3.  **Self-Correction Logic:** Train/Prompt the agent to interpret compiler/test errors and apply fixes autonomously.

## Phase 4: Meta-Recursive Orchestration (Completed/Expanding)
*Goal: Scaling to complex, cross-cutting enterprise tasks via self-recursive delegation.*

1.  **Meta-Recursive Delegation:** Implemented `delegate_task` tool. This allows HELIUS to spawn a new instance of itself via the CLI, providing a custom system prompt and model for specialized sub-tasks.
    - **Features:** Headless execution, JSON output parsing, environment isolation, and dynamic specialization.
2.  **Specialized Sub-Agents:** Pre-configured `Architect` and `Reviewer` roles are available via the standard `task` tool for common workflows.
3.  **Parallel Execution:** Future work to allow the parent agent to monitor multiple `delegate_task` background processes simultaneously.

## Phase 5: Polished Ecosystem (Ongoing)
1.  **Plugin System:** Allow users to define custom "skills" or "tools" in their `.helius` folder.
2.  **Observability Dashboard:** A web-based or more advanced TUI view for "Session Replay" and "Audit Trails."
3.  **CI/CD Integration:** A "Headless Mode" for running as a GitHub Action or in a CI pipeline to auto-fix PRs.
