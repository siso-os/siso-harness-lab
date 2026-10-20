// Prints the HALO v2 test files a PR diff touches, one per line, or the single word FULL when a shared file changed.
// Run from <repo>/v2 with SISO_CI_BASE set. A changed test runs; a changed source file runs its sibling <name>.test.* or,
// failing that, the tests in its own directory. Anything shared (deps, tsconfig, db, helpers, deploy) runs everything.
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
const git = (...a) => execFileSync('git', a, { encoding: 'utf8', maxBuffer: 1 << 26 }).split('\n').filter(Boolean);
const changed = git('diff', '--name-only', '--relative', '--no-renames', process.env.SISO_CI_BASE || 'HEAD~1', 'HEAD', '--', '.');
const all = git('ls-files', '--', '*.test.ts', '*.test.mjs');
const SHARED = /^(package(-lock)?\.json|tsconfig[^/]*\.json|\.npmrc|db\/|test-support|testing\/|.*\/(test-helpers?|testkit|fixtures?)\/)/;
const isTest = (p) => /\.test\.(ts|mjs)$/.test(p);
const out = new Set();
let full = false;
for (const p of changed) {
  if (SHARED.test(p) && !isTest(p)) { full = true; break; }
  if (isTest(p)) { if (existsSync(p)) out.add(p); continue; }
  if (!/\.(ts|tsx|mjs|js|json)$/.test(p)) continue;
  const sibling = p.replace(/\.(ts|tsx|mjs|js)$/, '.test.ts');
  const dir = p.includes('/') ? p.slice(0, p.lastIndexOf('/') + 1) : '';
  const near = all.filter((t) => t === sibling || t === sibling.replace(/\.ts$/, '.mjs') || (t.startsWith(dir) && !t.slice(dir.length).includes('/')));
  near.forEach((t) => out.add(t));
}
console.log(full ? 'FULL' : [...out].sort().join('\n'));
