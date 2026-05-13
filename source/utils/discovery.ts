import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {getSettings} from './config.js';

export type ProjectSummary = {
	name: string;
	version: string;
	description: string;
	mainTech: string[];
	entryPoints: string[];
	structure: string;
};

export async function discoverProject(): Promise<ProjectSummary> {
	const settings = getSettings();
	const searchRoots = [
		settings.workspace.root,
		process.cwd(),
		path.dirname(fileURLToPath(import.meta.url)),
	].filter((root): root is string => typeof root === 'string' && root.length > 0);

	let rootDir = searchRoots[0] ?? process.cwd();
	let pkgPath = '';

	for (const root of searchRoots) {
		let current = root;
		let depth = 0;
		while (depth < 4) {
			const candidate = path.join(current, 'package.json');
			if (fs.existsSync(candidate)) {
				pkgPath = candidate;
				rootDir = current;
				break;
			}
			const parent = path.dirname(current);
			if (parent === current) {
				break;
			}
			current = parent;
			depth++;
		}
		if (pkgPath) {
			break;
		}
	}

	let pkg: any = {};
	if (pkgPath && fs.existsSync(pkgPath)) {
		try {
			pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
		} catch {
			// ignore
		}
	}

	const deps = Object.keys(pkg.dependencies ?? {});
	const devDeps = Object.keys(pkg.devDependencies ?? {});
	const tech = [...new Set([...deps, ...devDeps])].filter(t =>
		['typescript', 'react', 'langchain', 'next', 'express', 'fastify', 'ink'].includes(t) || t.startsWith('@langchain/'),
	);

	const entryPoints = [];
	if (pkg.main) {
		entryPoints.push(pkg.main);
	}
	if (pkg.bin) {
		if (typeof pkg.bin === 'string') {
			entryPoints.push(pkg.bin);
		} else {
			entryPoints.push(...Object.values(pkg.bin as Record<string, string>));
		}
	}

	// Basic structure scan (top 2 levels)
	const structure = scanDir(rootDir, 0, 2);

	return {
		name: pkg.name ?? 'unknown-project',
		version: pkg.version ?? '0.0.0',
		description: pkg.description ?? '',
		mainTech: tech,
		entryPoints,
		structure,
	};
}

function scanDir(dir: string, depth: number, maxDepth: number): string {
	if (depth > maxDepth) {
		return '';
	}
	try {
		const entries = fs.readdirSync(dir, {withFileTypes: true});
		let out = '';
		const indent = '  '.repeat(depth);

		const sorted = entries.sort((a, b) => {
			if (a.isDirectory() === b.isDirectory()) {
				return a.name.localeCompare(b.name);
			}
			return a.isDirectory() ? -1 : 1;
		});

		for (const entry of sorted) {
			if (entry.name.startsWith('.') || entry.name === 'node_modules' || entry.name === 'dist') {
				continue;
			}

			if (entry.isDirectory()) {
				out += `${indent}📁 ${entry.name}/\n`;
				// Only recurse if it's a very shallow scan (depth 0)
				if (depth === 0) {
					out += scanDir(path.join(dir, entry.name), depth + 1, maxDepth);
				}
			} else {
				out += `${indent}📄 ${entry.name}\n`;
			}
		}
		return out;
	} catch {
		return '';
	}
}

export function formatProjectSummary(s: ProjectSummary): string {
	return `
Project: ${s.name} (v${s.version})
Description: ${s.description}
Main Tech: ${s.mainTech.join(', ') || 'Not detected'}
Entry Points: ${s.entryPoints.join(', ') || 'Not detected'}

Structure:
${s.structure}
`.trim();
}
