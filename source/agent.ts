import { buildAgent } from "./agents/builder.js";
import { JsonFileSaver } from "./agents/checkpointer.js";
import { FS_TOOLS } from "./tools/fs.js";
import { GIT_TOOLS } from "./tools/git.js";
import { SHELL_TOOLS } from "./tools/shell.js";
import { INTELLIGENCE_TOOLS } from "./tools/intelligence.js";
import { VERIFICATION_TOOLS } from "./tools/verification.js";
import { DELEGATION_TOOLS } from "./tools/delegation.js";

type CreateAgentOpts = {
  systemPrompt?: string;
  checkpointer?: any;
};

export async function createAgent(opts: CreateAgentOpts = {}) {
  const tools = [
    ...FS_TOOLS,
    ...GIT_TOOLS,
    ...SHELL_TOOLS,
    ...INTELLIGENCE_TOOLS,
    ...VERIFICATION_TOOLS,
    ...DELEGATION_TOOLS,
  ];
  return await buildAgent(tools, {
    checkpointer: opts.checkpointer ?? new JsonFileSaver(),
    systemPrompt: opts.systemPrompt,
  });
}
