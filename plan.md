# Helius CLI: Technical Audit & Enhancement Plan

This document outlines the professional audit and implementation plan for the Helius CLI, based on the Deep Agents, LangChain, and LangGraph skill architectures.

## 1. Framework & Architecture (`framework-selection`)
**Status:** The current architecture correctly utilizes **Deep Agents** as the top-level orchestrator (`createDeepAgent`). This is the correct choice for an agent that needs planning, filesystem management, and subagent delegation.
**Enhancement Plan:**
- Continue using Deep Agents for the main orchestrator.
- For highly specialized, fixed-workflow tasks (like complex code validation loops), consider compiling strict LangGraph graphs and passing them as tools or subagents.
- Ensure that the agent configuration relies on built-in Deep Agents middleware (TodoList, Filesystem, SubAgent) rather than redundant custom implementations.

## 2. Memory & Persistence (`deep-agents-memory` & `langgraph-persistence`)
**Status:** Currently uses `FilesystemBackend` for the workspace. Uses `JsonFileSaver` or `MemorySaver` for checkpoints. Does not utilize long-term cross-session memory (`StoreBackend`).
**Enhancement Plan:**
- **Hybrid Storage:** Implement `CompositeBackend` in `builder.ts` to route temporary files to `StateBackend` and persistent cross-session memory to `StoreBackend` (e.g., `/memories/`).
- **Store Instance:** Attach a `Store` instance (e.g., an `InMemoryStore` or persistent alternative) to `createDeepAgent(store=...)` to allow cross-thread memory.
- **Production Checkpointer:** Transition from `MemorySaver`/`JsonFileSaver` to `PostgresSaver` or a robust SQLite checkpointer for production deployments to ensure session durability and time-travel capability.
- **Time Travel:** Expose LangGraph's `getStateHistory` and `updateState` features in the CLI (`cli.tsx`) to allow users to fork and resume from previous checkpoints.

## 3. Subagents & Orchestration (`deep-agents-orchestration`)
**Status:** Defines `architect` and `reviewer` subagents in `builder.ts`. However, custom subagents do *not* inherit skills or tools from the main agent by default.
**Enhancement Plan:**
- **Explicit Skills:** Add `skills: ['./.helius/skills']` to the configuration objects for the `architect` and `reviewer` subagents.
- **Explicit Tools:** Explicitly assign relevant tools to each subagent (e.g., `VERIFICATION_TOOLS` for `reviewer`, `INTELLIGENCE_TOOLS` for `architect`) so they aren't restricted to base capabilities.
- **Stateless Execution:** Ensure instructions passed via `delegate_task` provide the complete context, as subagents are stateless.

## 4. Human-In-The-Loop (HITL) (`langgraph-human-in-the-loop` & `langchain-middleware`)
**Status:** The `run_command` tool in `shell.ts` manually invokes `interrupt()` for dangerous commands. `handleHitlInterrupt` in `hitl.ts` correctly processes the interrupt and resumes via `Command({ resume: payload })`.
**Enhancement Plan:**
- **Centralized HITL:** Migrate tool-level interrupts to Deep Agents' native `interruptOn` configuration in `builder.ts` (e.g., `interruptOn: { run_command: { allowedDecisions: ["approve", "edit", "reject"] } }`). This standardizes HITL policies without embedding them inside tool logic.
- **Idempotency:** Verify that any logic executed prior to an `interrupt()` in a custom tool is completely idempotent, as LangGraph will re-execute the node upon resumption.
- **Thread Consistency:** Ensure `thread_id` is consistently passed during `resume` operations.

## 5. Tool & Schema Definitions (`langchain-fundamentals`)
**Status:** Tools use the `@langchain/core/tools` `tool()` wrapper with Zod schemas.
**Enhancement Plan:**
- Audit all tool descriptions to ensure they are exhaustive. The LLM relies on precise descriptions to know *when* and *how* to use them.
- Standardize the usage of `write_todos` by explicitly instructing the agent in the system prompt to utilize it for tasks > 2 steps.

## 6. UI Implementation (`tui.tsx`)
**Status:** An Ink-based React terminal UI that streams message states but lacks visibility into sub-agent operations or structured planning.
**Enhancement Plan:**
- **Stream Planner Output:** Update `tui.tsx` to listen to the `values` or `updates` stream mode from `agent.stream()`, rather than just awaiting `invoke()`. This will allow real-time display of the Todo list (`write_todos` state) to the user.
- **Subagent Visibility:** Render active subagents visually (e.g., "Architect is planning...") by tracking `__interrupt__` or tool call events for `delegate_task`.

## Next Steps
1. Refactor `builder.ts` to implement `CompositeBackend` and `Store`.
2. Add explicit skills and tools to subagents.
3. Migrate manual `interrupt()` calls to `interruptOn`.
4. Update `tui.tsx` to use `agent.stream()` for real-time state visualization.
