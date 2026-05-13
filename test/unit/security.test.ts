import path from 'node:path';
import test from 'ava';
import {resolveWorkspacePath, safeTokenCompare, truncate} from '../../source/utils/security.js';

test('resolveWorkspacePath prevents traversal', t => {
	const root = path.resolve('/tmp/helius');
	t.throws(() => resolveWorkspacePath('../etc/passwd', root), {
		message: /Security violation/,
	});
});

test('resolveWorkspacePath allows valid paths', t => {
	const root = path.resolve(process.cwd());
	const target = resolveWorkspacePath('source/main.ts', root);
	t.true(target.startsWith(root));
	t.true(target.endsWith('main.ts'));
});

test('safeTokenCompare works', t => {
	t.true(safeTokenCompare('secret', 'secret'));
	t.false(safeTokenCompare('secret', 'wrong'));
	t.false(safeTokenCompare('secret', 'longer-secret'));
	t.false(safeTokenCompare(null as any, 'secret'));
});

test('truncate works', t => {
	const long = 'a'.repeat(100);
	const truncated = truncate(long, 10, '...[T]');
	t.is(truncated, 'aaaaaaaaaa...[T]');
	t.is(truncate('short', 10), 'short');
});
