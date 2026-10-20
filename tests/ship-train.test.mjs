import { test } from 'node:test';
import { execFileSync } from 'node:child_process';
test('ship train: isolated parallel slots, disk guard, affected graph, shards, merge and exact green deploy', () => {
  const env = { ...process.env };
  delete env.NODE_TEST_CONTEXT;
  execFileSync('python3', ['-B', 'tests/ship-train.test.py'], { env, timeout: 120_000, stdio: 'pipe' });
});
