import test from 'ava';
import path from 'node:path';
import { resolveWorkspacePath, safeTokenCompare, truncate } from '../source/utils/security.js';

test('resolveWorkspacePath resolves internal paths', t => {
  const root = process.cwd();
  const file = 'foo.txt';
  const resolved = resolveWorkspacePath(file, root);
  t.is(resolved, path.resolve(root, file));
});

test('resolveWorkspacePath throws on directory traversal', t => {
  const root = process.cwd();
  const file = '../../etc/passwd';
  t.throws(() => resolveWorkspacePath(file, root), {
    message: /Security violation/
  });
});

test('safeTokenCompare returns true for identical tokens', t => {
  t.true(safeTokenCompare('abc', 'abc'));
});

test('safeTokenCompare returns false for different tokens', t => {
  t.false(safeTokenCompare('abc', 'def'));
});

test('safeTokenCompare returns false for different length tokens', t => {
  t.false(safeTokenCompare('abc', 'abcd'));
});

test('safeTokenCompare returns false for null/undefined', t => {
  t.false(safeTokenCompare(null, 'abc'));
  t.false(safeTokenCompare('abc', undefined));
});

test('truncate truncates long strings', t => {
  const text = 'hello world';
  const truncated = truncate(text, 5);
  t.is(truncated, 'hello\n...[TRUNCATED]');
});

test('truncate does not truncate short strings', t => {
  const text = 'hello';
  const truncated = truncate(text, 10);
  t.is(truncated, 'hello');
});
