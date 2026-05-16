import fs from 'node:fs';
import {spawn, spawnSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import path from 'node:path';

import {tool} from 'langchain';
import {z} from 'zod';

import {getSettings} from '../utils/config.js';
import {getLogger} from '../utils/logger.js';
import {resolveWorkspacePath, truncate} from '../utils/security.js';

const ACTIVE_JOBS = new Map<string, ReturnType<typeof spawn>>();
const JOB_LOGS = new Map<string, string[]>();
const logger = getLogger('tools.shell');

function workspaceRoot(): string {
	const root = getSettings().workspace.root;
	return path.resolve(root ?? process.cwd());
}

function resolveCwd(cwd?: string | null): string {
	const ws = workspaceRoot();
	const target = cwd ? resolveWorkspacePath(cwd, ws) : ws;
	fsEnsureDir(target);
	return target;
}

function fsEnsureDir(dirPath: string): void {
	try {
		fs.mkdirSync(dirPath, {recursive: true});
	} catch {
		// ignore
	}
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

function executableExists(cmd: string): boolean {
	const hasSep = cmd.includes('/') || cmd.includes('\\');
	if (hasSep) {
		return fs.existsSync(cmd);
	}
	const envPath = process.env.PATH ?? '';
	const exts = process.platform === 'win32'
		? (process.env.PATHEXT ?? '.EXE;.CMD;.BAT').split(';')
		: [''];
	for (const dir of envPath.split(path.delimiter)) {
		for (const ext of exts) {
			const full = path.join(dir, process.platform === 'win32' ? cmd + ext : cmd);
			if (fs.existsSync(full)) {
				return true;
			}
		}
	}
	return false;
}

function streamLogs(jobId: string, data: Buffer, prefix: string, maxLines: number): void {
	const text = data.toString('utf8');
	const lines = text.split(/\r?\n/).filter(l => l.length > 0);
	if (!JOB_LOGS.has(jobId)) {
		JOB_LOGS.set(jobId, []);
	}
	const buf = JOB_LOGS.get(jobId)!;
	for (const line of lines) {
		buf.push(`[${prefix}] ${line}`);
		if (buf.length > maxLines) {
			buf.splice(0, buf.length - maxLines);
		}
	}
}

const runCommandTool = tool(
	async ({
		command,
		cwd,
		background = false,
	}: {
		command: string;
		cwd?: string;
		background?: boolean;
	}) => {
		const cfg = getSettings().tools.shell;
		logger.info(`run_command cmd=${command} cwd=${cwd ?? '.'} bg=${background}`);
		let args: string[];
		try {
			args = splitArgs(command);
		} catch (err) {
			logger.error('run_command arg parse error', err);
			return `Argument parsing error: ${(err as Error).message}`;
		}

		if (args.length === 0) {
			return 'Error: Empty command.';
		}
		const executable = path.basename(args[0]).toLowerCase();

		if (!cfg.allowlist.has(executable) && !cfg.dangerous.has(executable)) {
			logger.warn(`run_command blocked executable=${executable}`);
			return (
				`Security Error: '${executable}' is not in the allowlist. `
        + 'Add it to .helius/settings.yaml -> tools.shell.allowlist if it\'s safe.'
			);
		}

		if (!executableExists(args[0])) {
			logger.warn(`run_command missing executable=${args[0]}`);
			return `Setup error: Executable '${args[0]}' not found in PATH.`;
		}

		let runCwd: string;
		try {
			runCwd = resolveCwd(cwd);
		} catch (err) {
			return `Setup error: ${(err as Error).message}`;
		}

		if (background) {
			const jobId = randomUUID().slice(0, 8);
			const maxLines = cfg.max_background_log_lines;
			const proc = spawn(args[0], args.slice(1), {
				cwd: runCwd,
				stdio: ['ignore', 'pipe', 'pipe'],
			});
			ACTIVE_JOBS.set(jobId, proc);
			JOB_LOGS.set(jobId, []);

			proc.stdout?.on('data', data => {
				streamLogs(jobId, data, 'OUT', maxLines);
			});
			proc.stderr?.on('data', data => {
				streamLogs(jobId, data, 'ERR', maxLines);
			});
			proc.on('close', () => {
				// Keep logs, but remove active job
				ACTIVE_JOBS.delete(jobId);
			});

			logger.info(`run_command background started id=${jobId} pid=${proc.pid}`);
			return `Background job started. ID='${jobId}', PID=${proc.pid}. Use manage_background_job to track it.`;
		}

		try {
			const result = spawnSync(args[0], args.slice(1), {
				cwd: runCwd,
				encoding: 'utf8',
				timeout: cfg.timeout_seconds * 1000,
			});
			logger.info(`run_command done code=${result.status ?? 'null'}`);
			if ((result.error as NodeJS.ErrnoException | undefined)?.code === 'ETIMEDOUT') {
				return `Error: Timed out after ${cfg.timeout_seconds}s.`;
			}
			const output
        = `Exit Code: ${result.status ?? 'null'}\n`
        + `STDOUT:\n${result.stdout ?? ''}\n`
        + `STDERR:\n${result.stderr ?? ''}`;
			return truncate(output, cfg.max_output_length);
		} catch (err) {
			logger.error('run_command exec error', err);
			return `Execution error: ${(err as Error).message}`;
		}
	},
	{
		name: 'run_command',
		description:
      'Execute a shell command securely inside the workspace. Supports background jobs.',
		schema: z.object({
			command: z.string().describe('Shell command to execute.'),
			cwd: z
				.string()
				.optional()
				.describe('Working directory relative to workspace root.'),
			background: z
				.boolean()
				.optional()
				.default(false)
				.describe('Spawn as a background process.'),
		}),
	},
);

const manageBackgroundJobTool = tool(
	async ({job_id, action}: {job_id: string; action: string}) => {
		logger.info(`manage_background_job id=${job_id} action=${action}`);
		const proc = ACTIVE_JOBS.get(job_id);
		if (!proc) {
			return `Error: No active job '${job_id}'. It may have already exited.`;
		}

		const code = proc.exitCode;
		const status = code === null ? 'RUNNING' : `EXITED (code ${code})`;

		if (action === 'status') {
			return `Job '${job_id}': ${status}`;
		}
		if (action === 'logs') {
			const logs = JOB_LOGS.get(job_id) ?? [];
			const recent = logs.slice(-50).join('\n') || '(no output yet)';
			return `Job '${job_id}': ${status}\n\n${recent}`;
		}
		if (action === 'kill') {
			if (code !== null) {
				return `Job '${job_id}' already exited with code ${code}.`;
			}
			proc.kill();
			ACTIVE_JOBS.delete(job_id);
			JOB_LOGS.delete(job_id);
			return `Killed background job '${job_id}'.`;
		}

		return 'Error: Unknown action. Valid: \'status\', \'logs\', \'kill\'.';
	},
	{
		name: 'manage_background_job',
		description: 'Inspect or terminate a background process started by run_command.',
		schema: z.object({
			job_id: z.string().describe('Job ID returned by run_command.'),
			action: z.string().describe('\'status\' | \'logs\' | \'kill\''),
		}),
	},
);

export const SHELL_TOOLS = [runCommandTool, manageBackgroundJobTool];
