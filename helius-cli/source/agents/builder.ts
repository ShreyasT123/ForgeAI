import { createDeepAgent, FilesystemBackend } from "deepagents";
import { ChatGoogleGenerativeAI } from "@langchain/google-genai";
import { ChatGroq } from "@langchain/groq";
import { MemorySaver } from "@langchain/langgraph";

import { getSettings, loadSystemPrompt } from "../utils/config.js";
import { getLogger } from "../utils/logger.js";
import { discoverProject, formatProjectSummary } from "../utils/discovery.js";

type AnyTool = unknown;

const logger = getLogger("agents.builder");

export async function buildAgent(
  tools: AnyTool[],
  opts: {
    checkpointer?: any;
    systemPrompt?: string;
  } = {}
) {
  const settings = getSettings();
  const basePrompt = opts.systemPrompt ?? loadSystemPrompt(settings);
  const saver = opts.checkpointer ?? new MemorySaver();
  const rootDir = settings.workspace.root ?? process.cwd();

  logger.info(
    `Building agent | model='${settings.agent.model}' tools=${tools.length}`
  );

  // Phase 1: Project Discovery
  const discovery = await discoverProject();
  const projectSummary = formatProjectSummary(discovery);
  
  const systemPrompt = `
${basePrompt}

# Project Context
${projectSummary}

# Industrial Engineering Mandate
- You are HELIUS, an elite autonomous engineer. You do not just "report" on tasks; you execute them to completion.
- **Conversational Awareness:** Be helpful and descriptive. Explain your plan before starting and summarize your actions once finished. Do NOT just say "Task completed."
- **Environment & Scope:** You are running on Windows. Ensure all shell commands are compatible with PowerShell or CMD. By default, all operations (file creation, command execution, etc.) MUST be performed within the current working directory (CWD).
- **Tool-First Execution:** If a task requires creating files, installing packages, or running commands, you MUST use the appropriate tools. Never assume a task is done until you have verified the results on disk.
- **Planning:** Use 'write_todos' for any task involving more than two steps.
- **Verification:** Always run 'ls' or 'read_file' after creating/editing to confirm the state. Use the 'verify' tool to run tests/lints.
- **Recursion:** For highly specialized sub-problems, use 'delegate_task' to spawn a specialist.

# Personality & Voice
- You are HELIUS, a highly capable and friendly engineering partner.
- Use a professional yet conversational tone.
- When a task is complex, share your excitement or your engineering rationale.
- Always conclude with a detailed summary of what you achieved and any next steps the user should consider.
- If you encounter an obstacle, explain it clearly and propose a workaround rather than just failing.
`.trim();

  const agent = await createDeepAgent({
    backend: new FilesystemBackend({
      rootDir,
      virtualMode: true,
    }),
    model: (() => {
      const modelStr = settings.agent.model;
      if (modelStr.startsWith("groq:")) {
        return new ChatGroq({
          model: modelStr.replace("groq:", ""),
          apiKey: settings.groq_api_key ?? undefined,
        });
      }
      // Default to Google GenAI
      const modelName = modelStr.includes(":") ? modelStr.split(":")[1] : modelStr;
      return new ChatGoogleGenerativeAI({
        model: modelName,
        apiKey: settings.google_api_key ?? undefined,
      });
    })(),
    tools: tools as any,
    systemPrompt,
    checkpointer: saver,
    // Skill source paths are relative to the backend root in the JS docs.
    skills: ["./.helius/skills"],
    subagents: [
      {
        name: "architect",
        description: "Specializes in high-level design, mapping dependencies, and planning complex changes.",
        systemPrompt: "You are a software architect. Your goal is to map out changes and ensure architectural consistency. Use search_symbols and ls to understand the project structure before proposing a plan.",
      },
      {
        name: "reviewer",
        description: "Specializes in auditing changes, running tests, and ensuring code quality.",
        systemPrompt: "You are a meticulous code reviewer. Your goal is to verify that changes are correct, follow style guides, and don't introduce regressions. Use the verify tool extensively.",
      }
    ]
  });

  return agent;
}
