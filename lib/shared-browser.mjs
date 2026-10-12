// Preload used by `shot` (node --import). Makes playwright's chromium.launch() reuse one
// long-lived Chrome per playwright version instead of starting a new browser per script.
// A script's browser.close() then only disconnects and drops its own contexts.
// Anything the shared browser can't honour (custom args, proxy, headed) or any failure
// falls back to the script's own launch, so a run is never worse than without `shot`.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SHAREABLE = new Set(['channel', 'headless', 'timeout']);
const DIR = path.join(process.env.HEAVY_DIR || path.join(os.homedir(), '.cache/siso-heavy'), 'browser');
const SERVER = fileURLToPath(new URL('./shared-browser-server.mjs', import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function findPlaywright() {
  const from = process.argv[1] ? path.resolve(process.argv[1]) : path.join(process.cwd(), 'noop.js');
  try {
    const req = createRequire(from);
    const file = req.resolve('playwright');
    const version = JSON.parse(fs.readFileSync(path.join(path.dirname(file), 'package.json'), 'utf8')).version;
    return { pw: req('playwright'), file, version };
  } catch {
    return null; // not a playwright script
  }
}

function touch(file) {
  const t = new Date();
  try { fs.utimesSync(file, t, t); } catch { try { fs.writeFileSync(file, ''); } catch {} }
}

function readLive(state) {
  try {
    const s = JSON.parse(fs.readFileSync(state, 'utf8'));
    process.kill(s.pid, 0);
    return s.wsEndpoint;
  } catch {
    return null;
  }
}

async function ensureServer(pwFile, key, launchOpts) {
  const state = path.join(DIR, `${key}.json`);
  let ws = readLive(state);
  if (ws) return ws;
  fs.mkdirSync(DIR, { recursive: true });
  const lock = path.join(DIR, `${key}.lock`);
  let mine = false;
  try {
    fs.mkdirSync(lock);
    mine = true;
  } catch {
    try {
      if (Date.now() - fs.statSync(lock).mtimeMs > 60_000) {
        fs.rmSync(lock, { recursive: true, force: true });
        fs.mkdirSync(lock);
        mine = true;
      }
    } catch {}
  }
  if (mine) {
    touch(path.join(DIR, `${key}.beat`)); // a fresh server must not idle out before we connect
    const env = { ...process.env, NODE_OPTIONS: '' };
    spawn(process.execPath, [SERVER, pwFile, state, JSON.stringify(launchOpts)], { detached: true, stdio: 'ignore', env }).unref();
  }
  try {
    for (const deadline = Date.now() + 45_000; Date.now() < deadline; await sleep(200)) {
      ws = readLive(state);
      if (ws) return ws;
    }
    throw new Error('did not start within 45s');
  } finally {
    if (mine) fs.rmSync(lock, { recursive: true, force: true });
  }
}

function keepAlive(key, browser) {
  const beat = path.join(DIR, `${key}.beat`);
  touch(beat);
  const timer = setInterval(() => touch(beat), 20_000);
  timer.unref();
  browser.on('disconnected', () => { clearInterval(timer); touch(beat); });
}

const found = process.env.SHOT_OWN_BROWSER ? null : findPlaywright();
if (found) {
  const bt = found.pw.chromium;
  const ownLaunch = bt.launch.bind(bt);
  bt.launch = async function sharedLaunch(opts = {}) {
    const shareable = Object.keys(opts).every((k) => SHAREABLE.has(k)) && opts.headless !== false;
    if (!shareable) return ownLaunch(opts);
    const key = `pw${found.version}-${opts.channel || 'chromium'}`;
    let ws;
    try {
      ws = await ensureServer(found.file, key, opts.channel ? { channel: opts.channel } : {});
      const browser = await bt.connect(ws, { timeout: opts.timeout ?? 30_000 });
      keepAlive(key, browser);
      browser.sharedChrome = true;
      return browser;
    } catch (e) {
      const state = path.join(DIR, `${key}.json`);
      if (ws && readLive(state) === ws) fs.rmSync(state, { force: true }); // stale endpoint: next run starts fresh
      process.stderr.write(`shot: shared Chrome unavailable (${String(e.message).split('\n')[0]}); launching own\n`);
      return ownLaunch(opts);
    }
  };
  bt.launch.shared = true;
}
