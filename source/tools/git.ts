import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import path from 'node:path';

import {tool} from 'langchain';
import {interrupt} from '@langchain/langgraph';
import {z} from 'zod';

import {getSettings} from '../utils/config.js';
import {getLogger} from '../utils/logger.js';
import {truncate} from '../utils/security.js';

const logger = getLogger('tools.git');

function workspaceRoot(): string {
	const root = getSettings().workspace.root;
	return path.resolve(root ?? process.cwd());
}

function splitArgs(command: string): string[] {
	const args: string[] = [];
	let current = '';
	let quote: '\'' | '"' | null = null;
	let escape = false;
	for (const ch of command) {
		if (escape) {
			current += ch;
			escape = false;
			continue;
		}
		if (ch === '\\' && quote !== '\'') {
			escape = true;
			continue;
		}
		if (ch === '\'' || ch === '"') {
			if (quote === ch) {
				quote = null;
			} else if (!quote) {
				quote = ch;
			} else {
				current += ch;
			}
			continue;
		}
		if (!quote && /\s/.test(ch)) {
			if (current.length > 0) {
				args.push(current);
				current = '';
			}
			continue;
		}
		current += ch;
	}
	if (current.length > 0) {
		args.push(current);
	}
	return args;
}

function runGit(args: string[]): string {
	try {
		logger.info(`git ${args.join(' ')}`);
		const result = spawnSync('git', args, {
			cwd: workspaceRoot(),
			encoding: 'utf8',
		});
		if (result.error) {
			return `Git error: ${result.error.message}`;
		}
		if (result.status !== 0) {
			const err = (result.stderr || result.stdout || '').trim();
			return `Git error (exit ${result.status}):\n${err}`;
		}
		return truncate((result.stdout || '').trim() || '(no output)', 50_000);
	} catch (err) {
		logger.error('git error', err);
		return `Git error: ${(err as Error).message}`;
	}
}

const gitSafeOp = tool(
	async ({command}: {command: string}) => {
		const cfg = getSettings().tools.git;
		let args: string[];
		try {
			args = splitArgs(command);
		} catch (err) {
			return `Argument parsing error: ${(err as Error).message}`;
		}
		if (args.length === 0) {
			return 'Error: Empty command.';
		}
		logger.info(`git_safe_op cmd=${command}`);

		const subcmd = args[0].toLowerCase();
		if (
			subcmd === 'push'
      && args.some(f => f === '--force' || f === '-f' || f === '--force-with-lease')
		) {
			return 'Error: Force-push is destructive. Use `git_dangerous_op` with a justification.';
		}
		if (cfg.dangerous_commands.has(subcmd)) {
			return `Error: '${subcmd}' is destructive. Use \`git_dangerous_op\` instead.`;
		}
		if (!cfg.safe_commands.has(subcmd) && subcmd !== 'push') {
			return `Error: Unrecognized git subcommand '${subcmd}'.`;
		}
		return runGit(args);
	},
	{
		name: 'git_safe_op',
		description: 'Execute a safe, non-destructive git command.',
		schema: z.object({
			command: z
				.string()
				.describe('Git subcommand and flags (omit the word \'git\').'),
		}),
	},
);

const gitDangerousOp = tool(
	async ({command, reason}: {command: string; reason: string}) => {
		let args: string[];
		try {
			args = splitArgs(command);
		} catch (err) {
			return `Argument parsing error: ${(err as Error).message}`;
		}
		if (args.length === 0) {
			return 'Error: Empty command.';
		}
		logger.info(`git_dangerous_op cmd=${command} reason=${reason}`);

		const response = interrupt({
			action: 'approve_git',
			command: `git ${command}`,
			reason,
		}) as Record<string, unknown>;

		if (!response?.approved) {
			logger.warn(`git_dangerous_op denied cmd=${command}`);
			return `Denied. Reason: ${String(response?.reason ?? 'None given')}. Find an alternative approach.`;
		}

		const edited = response?.edited_command as string | undefined;
		if (edited) {
			try {
				const cleaned = edited.startsWith('git ')
					? edited.slice(4)
					: edited;
				args = splitArgs(cleaned);
			} catch (err) {
				return `Argument parsing error in edited command: ${(err as Error).message}`;
			}
		}

		return runGit(args);
	},
	{
		name: 'git_dangerous_op',
		description: 'Execute a destructive git command (requires human approval).',
		schema: z.object({
			command: z
				.string()
				.describe('Destructive git command (without \'git\').'),
			reason: z
				.string()
				.describe('Clear justification for why this operation is necessary.'),
		}),
	},
);

const gitApplyPatchTool = tool(
	async ({patch}: {patch: string}) => {
		logger.info('git_apply_patch started');
		const ws = workspaceRoot();
		const tmpPath = path.join(ws, `.helius_tmp_${randomUUID().slice(0, 8)}.patch`);

		try {
			fs.writeFileSync(tmpPath, patch, 'utf8');
			const result = spawnSync('git', ['apply', '--whitespace=fix', tmpPath], {
				cwd: ws,
				encoding: 'utf8',
			});

			if (result.status !== 0) {
				const err = (result.stderr || result.stdout || 'Unknown error').trim();
				return `Git apply failed:\n${err}`;
			}

			return 'Patch applied successfully via git apply.';
		} catch (err) {
			logger.error('git_apply_patch error', err);
			return `Error: ${(err as Error).message}`;
		} finally {
			if (fs.existsSync(tmpPath)) {
				fs.unlinkSync(tmpPath);
			}
		}
	},
	{
		name: 'git_apply_patch',
		description: 'Apply a unified diff patch using \'git apply\'. More robust than manual patching.',
		schema: z.object({
			patch: z.string().describe('The unified diff patch to apply.'),
		}),
	},
);

export const GIT_TOOLS = [gitSafeOp, gitDangerousOp, gitApplyPatchTool];
