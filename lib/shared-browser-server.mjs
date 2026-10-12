// Started detached by shared-browser.mjs. Owns one Chrome via playwright's launchServer,
// publishes its endpoint in the state file, and exits after SHOT_IDLE_MS (default 10 min)
// without a client heartbeat, so it can never become a forgotten memory hog.
import { createRequire } from 'node:module';
import fs from 'node:fs';

const [pwFile, stateFile, optsJson] = process.argv.slice(2);
const IDLE_MS = Number(process.env.SHOT_IDLE_MS || 10 * 60 * 1000);
const beat = stateFile.replace(/\.json$/, '.beat');
const pw = createRequire(import.meta.url)(pwFile);

const server = await pw.chromium.launchServer({ ...JSON.parse(optsJson), headless: true });
const tmp = `${stateFile}.${process.pid}`;
fs.writeFileSync(tmp, JSON.stringify({
  wsEndpoint: server.wsEndpoint(),
  pid: process.pid,
  chromePid: server.process().pid,
  started: new Date().toISOString(),
}));
fs.renameSync(tmp, stateFile);

let closing = false;
async function shutdown(code) {
  if (closing) return;
  closing = true;
  try {
    if (JSON.parse(fs.readFileSync(stateFile, 'utf8')).pid === process.pid) fs.rmSync(stateFile, { force: true });
  } catch {}
  await server.close().catch(() => {});
  process.exit(code);
}
server.process().on('exit', () => shutdown(1));
for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP']) process.on(sig, () => shutdown(0));
setInterval(() => {
  let last = 0;
  try { last = fs.statSync(beat).mtimeMs; } catch {}
  if (Date.now() - last > IDLE_MS) shutdown(0);
}, 30_000);
