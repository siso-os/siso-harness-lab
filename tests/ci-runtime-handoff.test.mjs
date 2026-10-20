import { test } from 'node:test';
import { execFileSync } from 'node:child_process';

test('CI owner handoff: idle gates, local validation, rollback and inherited lock', () => {
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  execFileSync('python3', ['-B', 'tests/ci-runtime-handoff.test.py'], {
    env, timeout: 120_000, stdio: 'pipe',
  });
});
