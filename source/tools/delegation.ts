import {spawnSync} from 'node:child_process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {z} from 'zod';
import {tool} from 'langchain';
import {getSettings} from '../utils/config.js';
import {getLogger} from '../utils/logger.js';

const logger = getLogger('tools.delegation');

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const delegateTaskTool = tool(
	async ({task, systemPrompt, model}) => {
		logger.info(`delegating task: ${task.slice(0, 50)}...`);

		// We assume the compiled entry point is at dist/main.js or we can use ts-node for development
		// Since we are likely running in a compiled environment:
		const mainJs = path.resolve(__dirname, '..', 'main.js');

		const args = ['--task', task, '--json'];
		if (systemPrompt) {
			args.push('--system-prompt', systemPrompt);
		}
		if (model) {
			args.push('--model', model);
		}

		try {
			// Use 'node' to run the main.js
			const result = spawnSync('node', [mainJs, ...args], {
				encoding: 'utf8',
				env: {...process.env, HELIUS_SILENT: 'true'}, // Hint for silent mode
			});

			if (result.status !== 0) {
				return `Delegation failed (exit ${result.status}):\n${result.stderr || result.stdout}`;
			}

			try {
				const parsed = JSON.parse(result.stdout.trim());
				if (parsed.success) {
					return `Specialized agent response:\n${parsed.result}`;
				}
				return `Specialized agent failed to complete the task:\n${parsed.result}`;
			} catch {
				return `Raw output from specialized agent:\n${result.stdout}`;
			}
		} catch (err) {
			return `Error during delegation: ${(err as Error).message}`;
		}
	},
	{
		name: 'delegate_task',
		description: 'Spawns a specialized HELIUS agent instance to handle a sub-task with its own system prompt and model. Perfect for isolation or specialized analysis.',
		schema: z.object({
			task: z.string().describe('The specific task for the specialized agent.'),
			systemPrompt: z.string().describe('The specialized system instructions for this sub-task.'),
			model: z.string().optional().describe('Override the model for this sub-task.'),
		}),
	},
);

export const DELEGATION_TOOLS = [delegateTaskTool];
