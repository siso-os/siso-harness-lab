import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
test('ci retention: oldest-first prune selection, locks, recent units and receipts kept', () => {
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  execFileSync('python3', ['-B', 'tests/ci-retention.test.py'], { env, timeout: 60_000, stdio: 'pipe' });
});
