import { test } from 'node:test';
import { execFileSync } from 'node:child_process';

test('red-main integration: bisect, safe revert, land, issue and failure gates', () => {
  const output = execFileSync('python3', ['-B', 'tests/red-main.test.py'], {
    encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 180_000,
  });
  console.log(output.trim());
});
