# HELIUS: Industrial Autonomous Code Engineer ☉

HELIUS is a production-grade autonomous agent built for high-stakes software engineering. It combines the power of **LangGraph** and **DeepAgents** with a robust, industrial-first architecture.

## 🚀 Key Features

- **Meta-Recursive Delegation:** HELIUS can spawn specialized sub-instances of itself to solve complex sub-problems with isolated context and custom models.
- **Symbol-Aware Intelligence:** Built-in semantic search for symbols (classes, functions, etc.) across multiple languages.
- **Autonomous Verification:** Proactive "Build-Test-Fix" loops ensure code quality and structural integrity.
- **Industrial Reliability:** Multi-model rotation and session persistence via checkpointing.
- **Human-in-the-Loop:** Strict security boundary enforcement with interactive approval for dangerous shell and git operations.

## 📦 Installation

```bash
npm install -g helius-cli
```

## 🛠 Usage

Start the interactive TUI:
```bash
helius
```

Run a single task:
```bash
helius "Refactor the authentication logic in source/utils/auth.ts"
```

## 🧩 Advanced: Specialized Subagents

HELIUS comes with pre-configured expert roles:
- **Architect:** For high-level design and dependency mapping.
- **Reviewer:** For auditing changes and running verification suites.

Example:
> "task architect: Design a new plugin system for the project"

## 🛡 Security

HELIUS enforces strict path isolation. It cannot access files outside the workspace root. All destructive operations (like `git reset` or `rm`) require explicit human approval.

## 📄 License

MIT
