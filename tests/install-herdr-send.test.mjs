import test from 'node:test';
import assert from 'node:assert/strict';
import { chmodSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readlinkSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { install, layout, restore } from '../scripts/install-herdr-send.mjs';

test('both distinct originals survive adoption and exact rollback; both entrypoints run one core', t => {
  const home = mkdtempSync(join(tmpdir(), 'sender-install-')); t.after(() => rmSync(home, { recursive: true, force: true }));
  const paths = layout(home), original = ['#!/bin/sh\necho positional\n', '#!/bin/sh\necho flags\n'];
  paths.targets.forEach((p, i) => { mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, original[i]); chmodSync(p, i ? 0o700 : 0o755); });
  const result = install(paths);
  const manifest = JSON.parse(readFileSync(result.manifestPath));
  assert.equal(manifest.originals.length, 2);
  assert.ok(readFileSync(join(dirname(result.manifestPath), 'MANIFEST.txt'), 'utf8').includes('Rollback:'));
  for (const [i, p] of paths.targets.entries()) {
    assert.equal(readlinkSync(p), result.release);
    assert.equal(readFileSync(manifest.originals[i].backup, 'utf8'), original[i]);
    const cli = spawnSync(process.execPath, [p, '--help'], { encoding: 'utf8' });
    assert.equal(cli.status, 0, cli.stderr); assert.match(cli.stdout, /NOT processed/);
  }
  assert.equal(install(paths).status, 'unchanged');
  assert.equal(restore(result.manifestPath, paths).status, 'restored');
  paths.targets.forEach((p, i) => { assert.equal(readFileSync(p, 'utf8'), original[i]); assert.equal(lstatSync(p).mode & 0o777, i ? 0o700 : 0o755); });
});

test('rollback refuses tampered backup and preserves both current entrypoints', t => {
  const home = mkdtempSync(join(tmpdir(), 'sender-restore-')); t.after(() => rmSync(home, { recursive: true, force: true }));
  const paths = layout(home);
  for (const p of paths.targets) { mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, 'original'); }
  const result = install(paths), m = JSON.parse(readFileSync(result.manifestPath));
  writeFileSync(m.originals[0].backup, 'wrong');
  assert.throws(() => restore(result.manifestPath, paths), /backup hash/);
  for (const p of paths.targets) assert.equal(readlinkSync(p), result.release);
});
