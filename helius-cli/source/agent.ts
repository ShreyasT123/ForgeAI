import { buildAgent } from "./agents/builder.js";
import { JsonFileSaver } from "./agents/checkpointer.js";
import { FS_TOOLS } from "./tools/fs.js";
import { GIT_TOOLS } from "./tools/git.js";
import { SHELL_TOOLS } from "./tools/shell.js";

type CreateAgentOpts = {
  systemPrompt?: string;
  checkpointer?: any;
};

export async function createAgent(opts: CreateAgentOpts = {}) {
  return await buildAgent([...FS_TOOLS, ...GIT_TOOLS, ...SHELL_TOOLS], {
    checkpointer: opts.checkpointer ?? new JsonFileSaver(),
    systemPrompt: opts.systemPrompt,
  });
}
