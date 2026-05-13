#!/usr/bin/env node
import readline from 'node:readline/promises';
import {stdin as input, stdout as output} from 'node:process';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {render} from 'ink';
import React from 'react';

import App from './tui.js';
import {createAgent} from './agent.js';
import {runAgent} from './agents/runner.js';
import {SessionStore} from './agents/sessions.js';
import {configureLogging} from './utils/logging_setup.js';
import {getSettings} from './utils/config.js';

const RESUME_SENTINEL = '__latest__';

type ParsedArgs = {
	task: string | null;
	resume: string | null;
	newSession: boolean;
	listSessions: boolean;
	model: string | null;
	nonInteractive: boolean;
};

function parseArgs(argv: string[]): ParsedArgs {
	const out: ParsedArgs = {
		task: null,
		resume: null,
		newSession: false,
		listSessions: false,
		model: null,
		nonInteractive: false,
	};

	const taskParts: string[] = [];
	for (let i = 0; i < argv.length; i += 1) {
		const arg = argv[i];
		if (arg === '--resume') {
			const next = argv[i + 1];
			if (next && !next.startsWith('--')) {
				out.resume = next;
				i += 1;
			} else {
				out.resume = RESUME_SENTINEL;
			}
			continue;
		}
		if (arg === '--new') {
			out.newSession = true;
			continue;
		}
		if (arg === '--list-sessions') {
			out.listSessions = true;
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
		if (arg === '--non-interactive') {
			out.nonInteractive = true;
			continue;
		}

		if (arg.startsWith('-')) {
			// Unknown flag: ignore for now.
			continue;
		}
		taskParts.push(arg);
	}

	if (taskParts.length > 0) {
		out.task = taskParts.join(' ');
	}
	return out;
}

function listSessionsAndExit(): number {
	const store = new SessionStore();
	const sessions = [...store.list()];
	if (sessions.length === 0) {
		console.log('No saved sessions found under ~/.helius/sessions/');
		return 0;
	}
	console.log(`\n  Found ${sessions.length} session(s)\n`);
	store.printList();
	console.log('');
	return 0;
}

function resolveThreadId(resumeArg: string | null): string | null {
	if (!resumeArg) {
		return null;
	}

	if (resumeArg === RESUME_SENTINEL) {
		const cfg = new SessionStore().latestConfig();
		if (!cfg) {
			console.log('No saved sessions found - starting a new session instead.\n');
			return null;
		}
		const tid = (cfg as {configurable?: Record<string, unknown>}).configurable
			?.thread_id as string;
		console.log(`Resuming latest session: ${tid}`);
		return tid;
	}

	const store = new SessionStore();
	const info = store.get(resumeArg);
	if (!info) {
		console.log(
			`Session '${resumeArg}' not found - starting a new session instead.\n`,
		);
		return null;
	}
	console.log(
		`Resuming session: ${resumeArg} (${info.checkpoint_count} checkpoints)`,
	);
	return resumeArg;
}

async function promptForTask(): Promise<string | null> {
	const rl = readline.createInterface({input, output});
	try {
		const line = await rl.question('Enter your task: ');
		const task = line.trim();
		return task.length > 0 ? task : null;
	} finally {
		rl.close();
	}
}

async function runHeadless(args: ParsedArgs, threadId: string | null): Promise<number> {
	let task = args.task;
	if (!task) {
		task = await promptForTask();
	}
	if (!task) {
		console.log('No task provided. Exiting.');
		return 1;
	}

	const agent = await createAgent();

	const {result, threadId: usedTid} = await runAgent(task, {
		agent,
		threadId,
	});

	if (result) {
		console.log(
			`\nSession saved. Resume with:\n  helius-cli --resume ${usedTid} "<next task>"\n`,
		);
	}

	return result ? 0 : 1;
}

export async function runCli(
	argv: string[] = process.argv.slice(2),
): Promise<number | null> {
	const args = parseArgs(argv);

	if (args.listSessions) {
		return listSessionsAndExit();
	}

	const settings = getSettings();
	configureLogging(
		settings.observability.log_level,
		settings.observability.log_format,
	);

	if (args.model) {
		settings.agent.model = args.model;
	}
	if (args.nonInteractive) {
		settings.hitl.interactive = false;
	}

	const threadId = args.newSession ? null : resolveThreadId(args.resume);

	if (args.nonInteractive) {
		return runHeadless(args, threadId);
	}

	const {waitUntilExit} = render(<App resume={threadId}/>, {
		stdin: process.stdin,
		stdout: process.stdout,
	});
	await waitUntilExit();
	return 0;
}

const entry = process.argv[1] ? path.resolve(process.argv[1]) : null;
const self = fileURLToPath(import.meta.url);
if (entry && self === entry) {
	runCli().then(code => {
		if (typeof code === 'number') {
			process.exit(code);
		}
	});
}
