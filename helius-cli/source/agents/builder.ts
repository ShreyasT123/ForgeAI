import { createDeepAgent, FilesystemBackend } from "deepagents";
import { ChatGoogleGenerativeAI } from "@langchain/google-genai";
import { ChatGroq } from "@langchain/groq";
import { MemorySaver } from "@langchain/langgraph";

import { getSettings, loadSystemPrompt } from "../utils/config.js";
import { getLogger } from "../utils/logger.js";

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
  const prompt = opts.systemPrompt ?? loadSystemPrompt(settings);
  const saver = opts.checkpointer ?? new MemorySaver();
  const rootDir = settings.workspace.root ?? process.cwd();

  logger.info(
    `Building agent | model='${settings.agent.model}' tools=${tools.length}`
  );

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
    systemPrompt: prompt,
    checkpointer: saver,
    // Skill source paths are relative to the backend root in the JS docs.
    skills: ["./.helius/skills"],
  });

  return agent;
}
