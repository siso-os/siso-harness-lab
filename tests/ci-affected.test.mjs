import { test } from 'node:test';
import { execFileSync } from 'node:child_process';

test('affected CI: real Git diffs, executed subsets, full fallbacks and main/PR isolation', () => {
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT; // fixture starts a real nested node test runner
  console.log(execFileSync('python3', ['-B', 'tests/ci-affected.test.py'], {
    encoding: 'utf8', timeout: 120_000, env,
  }).trim());
});
