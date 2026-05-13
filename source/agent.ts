import {buildAgent} from './agents/builder.js';
import {JsonFileSaver} from './agents/checkpointer.js';
import {FS_TOOLS} from './tools/fs.js';
import {GIT_TOOLS} from './tools/git.js';
import {SHELL_TOOLS} from './tools/shell.js';
import {INTELLIGENCE_TOOLS} from './tools/intelligence.js';
import {VERIFICATION_TOOLS} from './tools/verification.js';
import {DELEGATION_TOOLS} from './tools/delegation.js';

type CreateAgentOptions = {
	systemPrompt?: string;
	checkpointer?: any;
};

export async function createAgent(options: CreateAgentOptions = {}) {
	const tools = [
		...FS_TOOLS,
		...GIT_TOOLS,
		...SHELL_TOOLS,
		...INTELLIGENCE_TOOLS,
		...VERIFICATION_TOOLS,
		...DELEGATION_TOOLS,
	];
	return buildAgent(tools, {
		checkpointer: options.checkpointer ?? new JsonFileSaver(),
		systemPrompt: options.systemPrompt,
	});
}
