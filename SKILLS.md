# Helius Agent Skills Registry

This repository implements the **Skills Pattern** for progressive disclosure of domain knowledge.

## Core Principles
- **Prompt-driven specialization**: Skills are specialized prompts that augment agent behavior.
- **On-demand loading**: The agent uses `list_skills` and `load_skill` to fetch context only when relevant.
- **Reference awareness**: Skills can be registered dynamically via the `register_skill` tool.

## Available Skills

### [sql_expert](skills/sql_expert.md)
Expertise in writing optimized PostgreSQL and SQLite queries, using CTEs, and performance tuning.

### [react_patterns](skills/react_patterns.md)
Modern React (v18+) and TypeScript best practices, focusing on hooks and robust component architecture.

---
*To add a new skill, create a markdown file in the `skills/` directory or use the `register_skill` tool.*
