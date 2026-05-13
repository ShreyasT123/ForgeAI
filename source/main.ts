import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

import {createAgent} from './agent.js';
import {runAgent} from './agents/runner.js';
import {configureLogging} from './utils/logging_setup.js';
import {getSettings} from './utils/config.js';

type ParsedArgs = {
	task: string | null;
	systemPrompt: string | null;
	systemPromptFile: string | null;
	model: string | null;
	threadId: string | null;
	json: boolean;
};

function parseArgs(argv: string[]): ParsedArgs {
	const out: ParsedArgs = {
		task: null,
		systemPrompt: null,
		systemPromptFile: null,
		model: null,
		threadId: null,
		json: false,
	};

	const taskParts: string[] = [];
	for (let i = 0; i < argv.length; i += 1) {
		const arg = argv[i];
		if (arg === '--task') {
			const next = argv[i + 1];
			if (next && !next.startsWith('--')) {
				out.task = next;
				i += 1;
			}
			continue;
		}
		if (arg === '--system-prompt') {
			const next = argv[i + 1];
			if (next && !next.startsWith('--')) {
				out.systemPrompt = next;
				i += 1;
			}
			continue;
		}
		if (arg === '--system-prompt-file') {
			const next = argv[i + 1];
			if (next && !next.startsWith('--')) {
				out.systemPromptFile = next;
				i += 1;
			}
			continue;
		}
		if (arg === '--model') {
			const next = argv[i + 1];
			if (next && !next.startsWith('--')) {
				out.model = next;
				i += 1;
			}
			continue;
		}
		if (arg === '--thread-id') {
			const next = argv[i + 1];
			if (next && !next.startsWith('--')) {
				out.threadId = next;
				i += 1;
			}
			continue;
		}
		if (arg === '--json') {
			out.json = true;
			continue;
		}
		if (arg.startsWith('-')) {
			continue;
		}
		taskParts.push(arg);
	}

	if (!out.task && taskParts.length > 0) {
		out.task = taskParts.join(' ');
	}
	return out;
}

function loadSystemPromptFromFile(filePath: string): string {
	if (!fs.existsSync(filePath)) {
		throw new Error(`System prompt file not found: ${filePath}`);
	}
	return fs.readFileSync(filePath, 'utf8').trim();
}

export async function main(argv: string[] = process.argv.slice(2)): Promise<number> {
	const args = parseArgs(argv);

	const settings = getSettings();
	if (!args.json) {
		configureLogging(
			settings.observability.log_level,
			settings.observability.log_format,
		);
	}

	if (args.model) {
		settings.agent.model = args.model;
	}

	if (!args.task) {
		if (!args.json) {
			console.log('No task provided. Use --task "..." or pass the task as args.');
		}
		return 1;
	}

	let systemPrompt: string | undefined;
	if (args.systemPromptFile) {
		try {
			systemPrompt = loadSystemPromptFromFile(args.systemPromptFile);
		} catch (err) {
			if (!args.json) {
				console.log(`Error: ${(err as Error).message}`);
			}
			return 1;
		}
	} else if (args.systemPrompt) {
		systemPrompt = args.systemPrompt;
	}

	const agent = await createAgent({systemPrompt});

	const {result} = await runAgent(args.task, {
		agent,
		threadId: args.threadId ?? null,
		// Pass a silent presenter if JSON is requested to avoid TUI-like output in recursion
		presenter: args.json ? {present() {
			throw new Error('HITL not supported in JSON/Recursive mode.');
		}} : undefined,
	});

	if (args.json) {
		console.log(JSON.stringify({
			success: Boolean(result),
			threadId: args.threadId,
			result: result ? (result.messages as any[])?.at(-1)?.content : null,
		}));
	}

	return result ? 0 : 1;
}

const entry = process.argv[1] ? path.resolve(process.argv[1]) : null;
const self = fileURLToPath(import.meta.url);
if (entry && self === entry) {
	main().then(code => process.exit(code));
}
