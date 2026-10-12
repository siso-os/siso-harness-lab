#!/usr/bin/env node
// Scoped, on-demand adoption/rollback for the TWO approved installed senders.
import { createHash } from 'node:crypto';
import { chmodSync, copyFileSync, constants, existsSync, lstatSync, mkdirSync, mkdtempSync, readFileSync, readlinkSync, renameSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const hash = data => createHash('sha256').update(data).digest('hex');
const source = fileURLToPath(new URL('./herdr-send.mjs', import.meta.url));
export function layout(home = homedir()) {
  return { targets: [join(home, '.claude/bin/herdr-send'), join(home, 'bin/herdr-send')],
    backupRoot: join(home, '.claude/backups'), releaseRoot: join(home, '.claude/lib/herdr-send') };
}
function pointsTo(path, target) {
  return lstatSync(path).isSymbolicLink() && readlinkSync(path) === target;
}
function replaceLink(path, target) {
  const temp = `${path}.new-${process.pid}`;
  symlinkSync(target, temp);
  try { renameSync(temp, path); } finally { if (existsSync(temp)) rmSync(temp); }
}
export function restore(manifestPath, paths = layout()) {
  const m = JSON.parse(readFileSync(manifestPath, 'utf8'));
  if (m.version !== 1 || JSON.stringify(m.originals.map(o => o.path)) !== JSON.stringify(paths.targets)) throw new Error('wrong rollback targets');
  for (const o of m.originals) {
    if (hash(readFileSync(o.backup)) !== o.sha256) throw new Error('backup hash mismatch');
    if (!pointsTo(o.path, m.release)) throw new Error('installed entrypoint changed; refusing overwrite');
  }
  for (const o of m.originals) {
    const temp = `${o.path}.restore-${process.pid}`;
    copyFileSync(o.backup, temp, constants.COPYFILE_EXCL); chmodSync(temp, o.mode); renameSync(temp, o.path);
    if (hash(readFileSync(o.path)) !== o.sha256) throw new Error('rollback readback failed');
  }
  return { status: 'restored', originals: m.originals.map(o => ({ path: o.path, sha256: o.sha256 })), retainedInactiveRelease: m.release };
}
export function install(paths = layout(), sourcePath = source) {
  const bytes = readFileSync(sourcePath), sha256 = hash(bytes);
  const release = join(paths.releaseRoot, `${sha256}.mjs`);
  if (paths.targets.every(p => existsSync(p) && pointsTo(p, release)) && hash(readFileSync(release)) === sha256) return { status: 'unchanged', release, sha256 };
  // Resolve BOTH preimages before changing either. No overwrite of an unknown
  // prior symlink/projection, and no secret/config capture in the backup.
  const originals = paths.targets.map(path => {
    const stat = lstatSync(path);
    if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('expected original regular sender: ' + path);
    return { path, mode: stat.mode & 0o777, sha256: hash(readFileSync(path)) };
  });
  mkdirSync(paths.backupRoot, { recursive: true, mode: 0o700 });
  const backup = mkdtempSync(join(paths.backupRoot, 'herdr-send-'));
  chmodSync(backup, 0o700);
  for (const [i, o] of originals.entries()) {
    o.backup = join(backup, `original-${i + 1}`);
    copyFileSync(o.path, o.backup, constants.COPYFILE_EXCL); chmodSync(o.backup, o.mode);
    if (hash(readFileSync(o.backup)) !== o.sha256) throw new Error('backup readback mismatch');
  }
  const manifest = { version: 1, source: sourcePath, sha256, release, originals };
  const manifestPath = join(backup, 'manifest.json');
  writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  writeFileSync(join(backup, 'MANIFEST.txt'), originals.map(o => `${o.path} -> ${o.backup} sha256=${o.sha256} mode=${o.mode.toString(8)}`).join('\n') + `\nNew core: ${release} sha256=${sha256}\nRollback: node ${fileURLToPath(import.meta.url)} --restore ${manifestPath}\n`, { flag: 'wx', mode: 0o600 });
  // The manifest and BOTH verified originals exist before any installed change.
  mkdirSync(paths.releaseRoot, { recursive: true, mode: 0o700 });
  if (!existsSync(release)) writeFileSync(release, bytes, { flag: 'wx', mode: 0o755 });
  if (hash(readFileSync(release)) !== sha256) throw new Error('release hash mismatch');
  const changed = [];
  try {
    for (const o of originals) {
      if (!lstatSync(o.path).isFile() || hash(readFileSync(o.path)) !== o.sha256) throw new Error('preimage changed before adoption');
      replaceLink(o.path, release); changed.push(o);
    }
    for (const o of originals) if (!pointsTo(o.path, release) || hash(readFileSync(o.path)) !== sha256) throw new Error('adoption readback mismatch');
  } catch (error) {
    for (const o of changed) {
      if (!pointsTo(o.path, release)) continue; // preserve a concurrent external edit
      const temp = `${o.path}.rollback-${process.pid}`;
      copyFileSync(o.backup, temp, constants.COPYFILE_EXCL); chmodSync(temp, o.mode); renameSync(temp, o.path);
    }
    throw error;
  }
  return { status: 'adopted', manifestPath, release, sha256, targets: paths.targets };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2);
    if (args.length === 1 && args[0] === '--apply') console.log(JSON.stringify(install()));
    else if (args.length === 2 && args[0] === '--restore') console.log(JSON.stringify(restore(resolve(args[1]))));
    else if (!args.length || (args.length === 1 && args[0] === '--dry-run')) console.log(JSON.stringify({ status: 'plan', ...layout(), source, sha256: hash(readFileSync(source)) }));
    else throw new Error('usage: install-herdr-send.mjs [--dry-run | --apply | --restore MANIFEST]');
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
