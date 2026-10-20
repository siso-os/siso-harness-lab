import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, unlinkSync, rmdirSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

for (const [nodeStatus, pythonStatus] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
  test(`full suite runs both phases and preserves failures: node=${nodeStatus}, python=${pythonStatus}`, (t) => {
    const dir = mkdtempSync(join(tmpdir(), 'harness-full-suite-'));
    const log = join(dir, 'phases');
    t.after(() => {
      for (const name of ['node', 'python3', 'phases']) {
        const file = join(dir, name);
        if (existsSync(file)) unlinkSync(file);
      }
      rmdirSync(dir);
    });
    for (const [command, status] of [['node', nodeStatus], ['python3', pythonStatus]]) {
      writeFileSync(join(dir, command), `#!/bin/sh\nprintf '%s\\n' '${command}' >> "$PHASE_LOG"\nexit ${status}\n`, { mode: 0o755 });
    }
    const command = JSON.parse(readFileSync('package.json', 'utf8')).scripts.test;
    const result = spawnSync('/bin/sh', ['-c', command], {
      env: { ...process.env, PATH: `${dir}:${process.env.PATH}`, PHASE_LOG: log }, encoding: 'utf8',
    });
    assert.equal(result.status, nodeStatus || pythonStatus ? 1 : 0, result.stderr);
    assert.deepEqual(readFileSync(log, 'utf8').trim().split('\n'), ['node', 'python3']);
  });
}
