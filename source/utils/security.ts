/**
 * Shared security primitives used across all tools.
 * Import from here — never duplicate these.
 */

import path from 'node:path';
import crypto from 'node:crypto';

// ── Path Security ───────────────────────────────────────────────────────────

/**
 * Resolve `filepath` relative to `workspaceRoot` with strict boundary enforcement.
 *
 * Prevents directory traversal attacks like '../../etc/passwd'.
 */
export function resolveWorkspacePath(
	filepath: string,
	workspaceRoot: string,
): string {
	const root = path.resolve(workspaceRoot);
	const target = path.resolve(root, filepath);

	// Ensure target is inside root
	const relative = path.relative(root, target);

	if (
		relative.startsWith('..')
    || path.isAbsolute(relative)
	) {
		throw new Error(
			`Security violation: '${filepath}' resolves to '${target}', `
      + `which is outside the workspace boundary '${root}'.`,
		);
	}

	return target;
}

// ── Constant-Time Token Comparison ──────────────────────────────────────────

/**
 * Constant-time string comparison to prevent timing attacks.
 */
export function safeTokenCompare(
	provided: string | null | undefined,
	expected: string | null | undefined,
): boolean {
	if (!provided || !expected) {
		return false;
	}

	const a = Buffer.from(provided, 'utf8');
	const b = Buffer.from(expected, 'utf8');

	// Must be same length for timingSafeEqual
	if (a.length !== b.length) {
		return false;
	}

	return crypto.timingSafeEqual(a, b);
}

// ── String Truncation ───────────────────────────────────────────────────────

/**
 * Trim a string to maxLength characters, appending a marker if trimmed.
 */
export function truncate(
	text: string,
	maxLength: number,
	marker = '\n...[TRUNCATED]',
): string {
	if (text.length <= maxLength) {
		return text;
	}
	return text.slice(0, maxLength) + marker;
}
