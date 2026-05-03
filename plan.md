# Helius CLI: MAANG-Level Architecture & Design Plan

To elevate `helius-cli` to a MAANG-tier software standard, the architecture must evolve to prioritize **modularity, testability, security, and scalability**. 

This plan proposes transitioning to a **Clean Architecture (Ports and Adapters)** model, incorporating robust GoF (Gang of Four) design patterns, and introducing advanced engineering features (excluding RAG) to create a resilient, extensible agentic CLI.

---

## 1. Architectural Paradigm: Clean / Hexagonal Architecture

The current codebase mixes infrastructure (file I/O, shell execution, LangChain specific classes) with the application logic (agent orchestration). We will decouple these layers to make the system modular and highly testable.

### Proposed Directory Structure
```text
source/
├── core/                  # Pure TypeScript, NO infrastructure dependencies
│   ├── domain/            # Entities, Interfaces (ITool, ILLMProvider, IWorkspace)
│   └── use-cases/         # Agent workflows, Session management logic
├── infrastructure/        # Implementations of core interfaces
│   ├── llm/               # LangChain wrappers, Groq/OpenAI adapters
│   ├── execution/         # Shell execution (Host, Docker)
│   ├── persistence/       # SQLite / File-based checkpointers
│   └── telemetry/         # OpenTelemetry tracing
├── presentation/          # User interfaces
│   ├── cli/               # Headless entry points
│   └── tui/               # React Ink components & Event listeners
└── main.ts                # Composition Root (Dependency Injection setup)
```

**Why?** This ensures that if you switch from LangChain to another framework, or from Host execution to Docker, the core agent logic remains completely untouched.

---

## 2. Core Design Patterns to Implement

### A. Dependency Injection (DI)
Instead of importing `getSettings()` or `getLogger()` globally in every file, dependencies should be injected. We will implement a Composition Root (using a lightweight DI container like `tsyringe` or manual injection).
* **Benefit:** Absolute testability. You can inject an `InMemoryFileSystem` and a `MockLLM` to test the entire agent loop in milliseconds without touching the disk or network.

### B. Observer Pattern (Event-Driven Agent Streaming)
The current TUI waits for the agent to finish its run (`await agent.invoke(...)`) while displaying a static spinner. 
* **Implementation:** Expose an `EventEmitter` or RxJS `Observable` from the Agent Runner. The agent will emit events like `THOUGHT_GENERATED`, `TOOL_START`, `TOOL_END`, and `CHUNK_RECEIVED`.
* **Benefit:** The React Ink TUI can subscribe to these events and render a beautiful, real-time streaming interface (similar to ChatGPT or Claude), drastically improving perceived latency and UX.

### C. Strategy Pattern (Execution Contexts)
Abstract the `shell.ts` execution into an `ICommandExecutor` interface. Implement multiple strategies:
1. `HostExecutorStrategy` (Current behavior)
2. `DockerSandboxStrategy` (Executes commands inside an ephemeral container)
* **Benefit:** Seamlessly switch security contexts based on configuration or task risk level without changing tool logic.

### D. Command Pattern (Tool Execution)
Wrap tool executions in a Command object that defines `execute()`, `undo()`, and `validate()`. 
* **Benefit:** This allows the agent to safely rollback filesystem changes if a multi-step refactor fails halfway through.

---

## 3. Proposed New Features (Excluding RAG)

### 1. Isolated Sandbox Execution (Docker Workspace)
**Feature:** Instead of executing `run_command` on the user's host machine, the CLI mounts the workspace into an ephemeral Docker container and runs commands there.
* **Why:** Running arbitrary LLM-generated shell commands on a host machine is a massive security risk. MAANG-level agent tools (like GitHub Copilot Workspace or Devin) utilize strict sandboxing.

### 2. Multi-Agent Orchestration (Supervisor Pattern)
**Feature:** Transition from a single generic agent to a multi-agent system using LangGraph's Supervisor pattern.
* **Why:** A single prompt context becomes diluted. We will introduce:
  - **Planner Agent:** Breaks down the user's request.
  - **Coder Agent:** Writes the code.
  - **Reviewer Agent:** Critiques the code and checks for vulnerabilities.
  - **Runner Agent:** Executes tests and captures errors.

### 3. Persistent Background Job Daemon
**Feature:** Replace the in-memory `ACTIVE_JOBS` map in `shell.ts` with a lightweight local daemon (e.g., using a local SQLite database or a persistent background Node process).
* **Why:** Currently, if the CLI is closed (Ctrl+C), all background jobs are orphaned. A daemon ensures background tasks (like spinning up a dev server) survive CLI restarts and can be re-attached to later.

### 4. Dynamic Skill / Plugin Ecosystem
**Feature:** Implement an extension architecture where users can drop `.ts` or `.js` files into a `.helius/plugins/` directory. The CLI dynamically loads these as new tools at runtime.
* **Why:** Extensibility. Users can write custom internal tooling (e.g., specific deployment scripts) without modifying the core CLI codebase.

### 5. Advanced Observability (OpenTelemetry)
**Feature:** Instrument the application with OpenTelemetry.
* **Why:** Logs aren't enough for complex agent reasoning. Tracing allows you to visualize exactly how long the LLM took to respond, how long a tool took to run, and the exact state transitions of the LangGraph state machine.

---

## 4. Software Engineering Best Practices

### 1. Strict Type Enforcement
- Enable `strict: true` and `noImplicitAny: true` in `tsconfig.json`.
- Eradicate the use of `any` across the codebase. Use LangChain's built-in types (e.g., `CompiledStateGraph`, `BaseMessage`) or define strict generic constraints.

### 2. Automated Testing Pyramid
- **Unit Tests:** Test all utility functions (`security.ts`, custom diff parsers) extensively. Use property-based testing (e.g., `fast-check`) for parsing logic.
- **Integration Tests:** Use a mocked LLM interface to test if the agent correctly calls the `write_file` tool when prompted.
- **E2E Tests:** Execute the CLI as a child process with predefined inputs to verify end-to-end functionality.

### 3. Safe State Migrations
- The current `JsonFileSaver` assumes the state schema will never change.
- **Improvement:** Introduce schema versioning in the checkpoint JSON. If the LangGraph state schema changes in a future update, implement migration functions to upgrade older checkpoints instead of crashing or losing session history.
