import fs from 'node:fs';
import path from 'node:path';

import {tool} from 'langchain';
import {z} from 'zod';

import {getSettings} from '../utils/config.js';
import {getLogger} from '../utils/logger.js';
import {resolveWorkspacePath, truncate} from '../utils/security.js';

const HUNK_FUZZ = 3;
const logger = getLogger('tools.fs');

type Hunk = {
	hint: number;
	oldLines: string[];
	newLines: string[];
	header: string;
};

function workspaceRoot(): string {
	const root = getSettings().workspace.root;
	return path.resolve(root ?? process.cwd());
}

function resolvePath(filePath: string): string {
	return resolveWorkspacePath(filePath, workspaceRoot());
}

function fsConfig() {
	return getSettings().tools.filesystem;
}

function readText(target: string): string {
	return fs.readFileSync(target, 'utf8').replace(/\r\n/g, '\n');
}

function writeText(target: string, content: string): void {
	fs.mkdirSync(path.dirname(target), {recursive: true});
	fs.writeFileSync(target, content.replace(/\r\n/g, '\n'), 'utf8');
}

function ensureFile(target: string, label: string): [boolean, string] {
	if (!fs.existsSync(target)) {
		return [false, `Error: '${label}' does not exist.`];
	}
	const stat = fs.statSync(target);
	if (!stat.isFile()) {
		return [false, `Error: '${label}' is not a file.`];
	}
	return [true, ''];
}

function splitLinesKeepEnds(text: string): string[] {
	if (text.length === 0) {
		return [];
	}
	const matches = text.match(/.*(?:\n|$)/g);
	if (!matches) {
		return [];
	}
	return matches.filter(line => line.length > 0);
}

function parsePatch(patch: string): Hunk[] {
	const hunks: Hunk[] = [];
	let current: Hunk | null = null;
	let noNewlineNext = false;

	const lines = splitLinesKeepEnds(patch);
	for (const rawLine of lines) {
		const line = rawLine.endsWith('\n')
			? rawLine.slice(0, -1)
			: rawLine;

		if (line.startsWith('--- ') || line.startsWith('+++ ')) {
			current = null;
			continue;
		}

		const m = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/.exec(line);
		if (m) {
			const oldStart = Number(m[1]);
			const oldCount = m[2] ? Number(m[2]) : 1;
			current = {
				hint: Math.max(0, oldStart - 1),
				oldLines: [],
				newLines: [],
				header: line,
			};
			if (oldCount === 0) {
				current.hint = oldStart;
			}
			hunks.push(current);
			noNewlineNext = false;
			continue;
		}

		if (!current) {
			continue;
		}

		if (line.startsWith('\\ No newline')) {
			noNewlineNext = true;
			continue;
		}

		const prefix = line[0];
		const content = line.slice(1) + '\n';

		if (noNewlineNext) {
			if (current.oldLines.length > 0) {
				current.oldLines[current.oldLines.length - 1]
          = current.oldLines[current.oldLines.length - 1].replace(/\n$/, '');
			}
			if (current.newLines.length > 0) {
				current.newLines[current.newLines.length - 1]
          = current.newLines[current.newLines.length - 1].replace(/\n$/, '');
			}
			noNewlineNext = false;
		}

		switch (prefix) {
			case ' ': {
				current.oldLines.push(content);
				current.newLines.push(content);

				break;
			}
			case '-': {
				current.oldLines.push(content);

				break;
			}
			case '+': {
				current.newLines.push(content);

				break;
			}
		// No default
		}
	}

	if (hunks.length === 0) {
		throw new Error('Patch contains no hunks - nothing to apply.');
	}

	return hunks;
}

function findHunkPosition(lines: string[], hunk: Hunk): number {
	const old = hunk.oldLines;
	const n = lines.length;
	const oldN = old.length;

	if (oldN === 0) {
		return Math.min(hunk.hint, n);
	}

	for (let offset = 0; offset <= HUNK_FUZZ; offset += 1) {
		const signs = offset === 0 ? [0] : [1, -1];
		for (const sign of signs) {
			const start = hunk.hint + offset * sign;
			if (start < 0 || start + oldN > n) {
				continue;
			}
			const slice = lines.slice(start, start + oldN);
			let match = true;
			for (let i = 0; i < oldN; i += 1) {
				if (slice[i] !== old[i]) {
					match = false;
					break;
				}
			}
			if (match) {
				return start;
			}
		}
	}

	const expectedPreview = old.slice(0, 5).join('').trimEnd();
	const startLine = Math.max(0, hunk.hint - HUNK_FUZZ) + 1;
	const endLine = Math.min(n, hunk.hint + HUNK_FUZZ + old.length) + 1;
	throw new Error(
		`Hunk ${JSON.stringify(hunk.header)} could not be applied.\n`
      + `  Searched lines ${startLine}-${endLine} (file has ${n} lines).\n`
      + '  Expected to find:\n'
      + expectedPreview
      	.split('\n')
      	.map(l => `    ${l}`)
      	.join('\n'),
	);
}

function applyHunks(content: string, hunks: Hunk[]): string {
	const lines = splitLinesKeepEnds(content);
	const positions: Array<[number, Hunk]> = [];
	for (const hunk of hunks) {
		const start = findHunkPosition(lines, hunk);
		positions.push([start, hunk]);
	}

	const sorted = [...positions].sort((a, b) => a[0] - b[0]);
	for (let i = 0; i < sorted.length - 1; i += 1) {
		const [aStart, aHunk] = sorted[i];
		const [bStart] = sorted[i + 1];
		const aEnd = aStart + aHunk.oldLines.length;
		if (bStart < aEnd) {
			throw new Error(
				`Hunks overlap: hunk starting at line ${aStart + 1} `
          + `ends at ${aEnd}, but next hunk starts at ${bStart + 1}.`,
			);
		}
	}

	const reverse = [...positions].sort((a, b) => b[0] - a[0]);
	for (const [start, hunk] of reverse) {
		lines.splice(start, hunk.oldLines.length, ...hunk.newLines);
	}

	return lines.join('');
}

type DiffOp = {type: 'equal' | 'insert' | 'delete'; line: string};

function computeDiffOps(oldLines: string[], newLines: string[]): DiffOp[] {
	const n = oldLines.length;
	const m = newLines.length;
	const dp: number[][] = Array.from({length: n + 1}, () =>
		new Array(m + 1).fill(0),
	);

	for (let i = n - 1; i >= 0; i -= 1) {
		for (let j = m - 1; j >= 0; j -= 1) {
			if (oldLines[i] === newLines[j]) {
				dp[i][j] = dp[i + 1][j + 1] + 1;
			} else {
				dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
			}
		}
	}

	const ops: DiffOp[] = [];
	let i = 0;
	let j = 0;
	while (i < n && j < m) {
		if (oldLines[i] === newLines[j]) {
			ops.push({type: 'equal', line: oldLines[i]});
			i += 1;
			j += 1;
		} else if (dp[i + 1][j] >= dp[i][j + 1]) {
			ops.push({type: 'delete', line: oldLines[i]});
			i += 1;
		} else {
			ops.push({type: 'insert', line: newLines[j]});
			j += 1;
		}
	}
	while (i < n) {
		ops.push({type: 'delete', line: oldLines[i++]});
	}
	while (j < m) {
		ops.push({type: 'insert', line: newLines[j++]});
	}
	return ops;
}

function buildUnifiedDiff(oldLines: string[], newLines: string[], filePath: string): string {
	const ops = computeDiffOps(oldLines, newLines);
	const context = 3;
	const hunks: Array<{oldStart: number; newStart: number; lines: DiffOp[]}> = [];

	let oldLine = 1;
	let newLine = 1;
	let buffer: DiffOp[] = [];
	let hunk: {oldStart: number; newStart: number; lines: DiffOp[]} | null = null;
	let trailingContext = 0;

	for (const op of ops) {
		if (op.type === 'equal') {
			if (hunk) {
				if (trailingContext < context) {
					hunk.lines.push(op);
					trailingContext += 1;
				} else {
					hunks.push(hunk);
					hunk = null;
					trailingContext = 0;
					buffer = [op];
				}
			} else {
				buffer.push(op);
				if (buffer.length > context) {
					buffer.shift();
				}
			}
			oldLine += 1;
			newLine += 1;
		} else {
			if (!hunk) {
				hunk = {
					oldStart: oldLine - buffer.length,
					newStart: newLine - buffer.length,
					lines: [...buffer],
				};
			}
			trailingContext = 0;
			hunk.lines.push(op);
			if (op.type === 'delete') {
				oldLine += 1;
			} else {
				newLine += 1;
			}
		}
	}

	if (hunk) {
		hunks.push(hunk);
	}

	if (hunks.length === 0) {
		return 'No changes.';
	}

	const output: string[] = [];
	output.push(`--- a/${filePath}`, `+++ b/${filePath}`);

	for (const h of hunks) {
		const oldCount = h.lines.filter(l => l.type !== 'insert').length;
		const newCount = h.lines.filter(l => l.type !== 'delete').length;
		output.push(
			`@@ -${h.oldStart},${oldCount} +${h.newStart},${newCount} @@`,
		);
		for (const line of h.lines) {
			const prefix = line.type === 'equal' ? ' ' : (line.type === 'delete' ? '-' : '+');
			output.push(prefix + line.line.replace(/\n$/, ''));
		}
	}

	return output.join('\n');
}

const lsTool = tool(
	async ({path: targetPath = '.'}: {path?: string}) => {
		try {
			logger.info(`ls path=${targetPath}`);
			const target = resolvePath(targetPath);
			if (!fs.existsSync(target)) {
				return `Error: '${targetPath}' does not exist.`;
			}
			if (!fs.statSync(target).isDirectory()) {
				return `Error: '${targetPath}' is not a directory.`;
			}

			const ignore = new Set(fsConfig().ignore_dirs);
			const entries = fs
				.readdirSync(target, {withFileTypes: true})
				.filter(d => !ignore.has(d.name))
				.map(d => ({
					name: d.name,
					isFile: d.isFile(),
					size: d.isFile() ? fs.statSync(path.join(target, d.name)).size : 0,
				}))
				.sort((a, b) => {
					if (a.isFile !== b.isFile) {
						return a.isFile ? 1 : -1;
					}
					return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
				});

			const lines = entries.map(e => {
				const prefix = e.isFile ? '      ' : '[DIR] ';
				const size = e.isFile ? ` (${e.size.toLocaleString()} B)` : '';
				return `${prefix}${e.name}${size}`;
			});
			return truncate(lines.join('\n') || '(empty)', fsConfig().max_output_length);
		} catch (err) {
			logger.error(`ls error path=${targetPath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'ls',
		description: 'List files and directories at the given path.',
		schema: z.object({
			path: z.string().optional().default('.').describe('Directory to list.'),
		}),
	},
);

const readFileTool = tool(
	async ({
		path: filePath,
		start_line,
		end_line,
	}: {
		path: string;
		start_line?: number;
		end_line?: number;
	}) => {
		const cfg = fsConfig();
		try {
			logger.info(`read_file path=${filePath}`);
			if (start_line !== undefined && start_line < 1) {
				return 'Error: start_line must be >= 1 (1-indexed).';
			}
			if (end_line !== undefined && end_line < 1) {
				return 'Error: end_line must be >= 1 (1-indexed).';
			}
			if (
				start_line !== undefined
        && end_line !== undefined
        && start_line > end_line
			) {
				return 'Error: start_line must be <= end_line.';
			}

			const target = resolvePath(filePath);
			const [ok, err] = ensureFile(target, filePath);
			if (!ok) {
				return err;
			}

			const stat = fs.statSync(target);
			if (stat.size > cfg.max_file_size_mb * 1024 * 1024) {
				return `Error: File exceeds the ${cfg.max_file_size_mb} MB read limit.`;
			}

			const content = readText(target);
			const lines = splitLinesKeepEnds(content);
			const s = start_line ? start_line - 1 : 0;
			const e = end_line ? Math.min(lines.length, end_line) : lines.length;
			const numbered = lines
				.slice(s, e)
				.map((line, idx) => `${String(idx + s + 1).padStart(5)} | ${line}`)
				.join('');
			return truncate(numbered, cfg.max_output_length);
		} catch (err) {
			logger.error(`read_file error path=${filePath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'read_file',
		description: 'Read a file with optional line-range slicing.',
		schema: z.object({
			path: z.string().describe('File path (relative to workspace).'),
			start_line: z.number().optional().describe('First line to read (1-indexed).'),
			end_line: z.number().optional().describe('Last line to read (1-indexed).'),
		}),
	},
);

const writeFileTool = tool(
	async ({path: filePath, content}: {path: string; content: string}) => {
		try {
			logger.info(`write_file path=${filePath} bytes=${content.length}`);
			const target = resolvePath(filePath);
			if (fs.existsSync(target)) {
				return (
					`Error: '${filePath}' already exists. `
          + 'Use apply_patch for partial edits or overwrite_file for a full rewrite.'
				);
			}
			writeText(target, content);
			return `Created '${filePath}'.`;
		} catch (err) {
			logger.error(`write_file error path=${filePath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'write_file',
		description: 'Create a new file. Fails if the file already exists.',
		schema: z.object({
			path: z.string().describe('Path of the new file to create.'),
			content: z.string().describe('Full content to write.'),
		}),
	},
);

const overwriteFileTool = tool(
	async ({path: filePath, content}: {path: string; content: string}) => {
		try {
			logger.info(`overwrite_file path=${filePath} bytes=${content.length}`);
			const target = resolvePath(filePath);
			const [ok, err] = ensureFile(target, filePath);
			if (!ok) {
				return err;
			}
			const current = readText(target);
			const newContent = content.replace(/\r\n/g, '\n');
			if (newContent === current) {
				return `No changes needed in '${filePath}'.`;
			}
			writeText(target, newContent);
			return `Overwrote '${filePath}'.`;
		} catch (err) {
			logger.error(`overwrite_file error path=${filePath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'overwrite_file',
		description: 'Replace an existing file\'s content entirely.',
		schema: z.object({
			path: z.string().describe('Path of the existing file to overwrite.'),
			content: z.string().describe('New full content for the file.'),
		}),
	},
);

const applyPatchTool = tool(
	async ({path: filePath, patch}: {path: string; patch: string}) => {
		try {
			logger.info(`apply_patch path=${filePath} bytes=${patch.length}`);
			const target = resolvePath(filePath);
			const [ok, err] = ensureFile(target, filePath);
			if (!ok) {
				return err;
			}

			const content = readText(target);
			let hunks: Hunk[];
			try {
				hunks = parsePatch(patch);
			} catch (err) {
				logger.error(`apply_patch parse error path=${filePath}`, err);
				return `Error parsing patch: ${(err as Error).message}`;
			}

			let updated: string;
			try {
				updated = applyHunks(content, hunks);
			} catch (err) {
				logger.error(`apply_patch apply error path=${filePath}`, err);
				return `Error applying patch: ${(err as Error).message}`;
			}

			if (updated === content) {
				return `Patch produced no changes in '${filePath}'.`;
			}
			writeText(target, updated);
			return `Patched '${filePath}' (${hunks.length} hunk(s) applied).`;
		} catch (err) {
			logger.error(`apply_patch error path=${filePath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'apply_patch',
		description:
      'Apply a unified diff patch to an existing file. All hunks succeed or no changes are made.',
		schema: z.object({
			path: z.string().describe('File to patch (relative to workspace).'),
			patch: z.string().describe('Unified diff patch to apply.'),
		}),
	},
);

const previewDiffTool = tool(
	async ({path: filePath, new_content}: {path: string; new_content: string}) => {
		try {
			logger.info(`preview_diff path=${filePath} bytes=${new_content.length}`);
			const target = resolvePath(filePath);
			const [ok, err] = ensureFile(target, filePath);
			if (!ok) {
				return err;
			}

			const oldLines = splitLinesKeepEnds(readText(target));
			const newLines = splitLinesKeepEnds(new_content.replace(/\r\n/g, '\n'));
			return buildUnifiedDiff(oldLines, newLines, filePath);
		} catch (err) {
			logger.error(`preview_diff error path=${filePath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'preview_diff',
		description: 'Show a unified diff between the current file and proposed new content.',
		schema: z.object({
			path: z.string().describe('Path of the file to compare.'),
			new_content: z.string().describe('Proposed full replacement content.'),
		}),
	},
);

const deleteFileTool = tool(
	async ({path: targetPath}: {path: string}) => {
		try {
			logger.info(`delete_file path=${targetPath}`);
			const target = resolvePath(targetPath);
			if (!fs.existsSync(target)) {
				return `Error: '${targetPath}' does not exist.`;
			}
			const stat = fs.statSync(target);
			if (stat.isDirectory()) {
				try {
					fs.rmdirSync(target);
					return `Deleted empty directory '${targetPath}'.`;
				} catch {
					return `Error: '${targetPath}' is not empty. Only empty directories can be deleted here.`;
				}
			}
			fs.unlinkSync(target);
			return `Deleted '${targetPath}'.`;
		} catch (err) {
			logger.error(`delete_file error path=${targetPath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'delete_file',
		description: 'Delete a file or an empty directory.',
		schema: z.object({
			path: z.string().describe('Path to the file or empty directory to delete.'),
		}),
	},
);

const grepSearchTool = tool(
	async ({
		pattern,
		path: searchPath = '.',
		max_matches = 100,
	}: {
		pattern: string;
		path?: string;
		max_matches?: number;
	}) => {
		const cfg = fsConfig();
		try {
			logger.info(`grep_search path=${searchPath} pattern=${pattern}`);
			const target = resolvePath(searchPath);
			if (!fs.existsSync(target)) {
				return `Error: '${searchPath}' does not exist.`;
			}
			let regex: RegExp;
			try {
				regex = new RegExp(pattern);
			} catch (err) {
				return `Error: Invalid regex - ${(err as Error).message}`;
			}
			const ws = workspaceRoot();
			const matches: string[] = [];

			const grepFile = (fp: string): boolean => {
				try {
					const lines = readText(fp).split('\n');
					for (const [i, line] of lines.entries()) {
						if (regex.test(line)) {
							const rel = path.relative(ws, fp);
							matches.push(`${rel}:${i + 1}: ${line}`);
							if (matches.length >= max_matches) {
								matches.push(`... [capped at ${max_matches} matches]`);
								return true;
							}
						}
					}
				} catch {
					// ignore binary or unreadable
				}
				return false;
			};

			const walk = (dir: string): boolean => {
				const entries = fs.readdirSync(dir, {withFileTypes: true});
				for (const entry of entries) {
					if (entry.isDirectory()) {
						if (cfg.ignore_dirs.has(entry.name)) {
							continue;
						}
						if (walk(path.join(dir, entry.name))) {
							return true;
						}
					} else if (entry.isFile() && grepFile(path.join(dir, entry.name))) {
						return true;
					}
				}
				return false;
			};

			if (fs.statSync(target).isFile()) {
				grepFile(target);
			} else {
				walk(target);
			}

			return matches.length > 0 ? matches.join('\n') : 'No matches found.';
		} catch (err) {
			logger.error(`grep_search error path=${searchPath}`, err);
			return `Error: ${(err as Error).message}`;
		}
	},
	{
		name: 'grep_search',
		description: 'Search for a regex pattern across all text files in a directory.',
		schema: z.object({
			pattern: z.string().describe('Regular expression pattern to search for.'),
			path: z.string().optional().default('.').describe('Directory or file to search.'),
			max_matches: z
				.number()
				.min(1)
				.max(500)
				.optional()
				.default(100)
				.describe('Maximum results to return.'),
		}),
	},
);

// Only include tools that do NOT collide with Deep Agents built-ins.
// Built-ins already provide: ls, read_file, write_file, edit_file, glob, grep.
export const FS_TOOLS = [
	overwriteFileTool,
	applyPatchTool,
	previewDiffTool,
	deleteFileTool,
	grepSearchTool,
];

// Export built-in-compatible tools in case you need them elsewhere.
export const FS_TOOLSET = {
	lsTool,
	readFileTool,
	writeFileTool,
	overwriteFileTool,
	applyPatchTool,
	previewDiffTool,
	deleteFileTool,
	grepSearchTool,
};
