import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync, readlinkSync, symlinkSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../bin/", import.meta.url).pathname;

// A fake HOME with two installed versions; each fake binary prints which version ran and the account env it got.
function fixture() {
  const home = realpathSync(mkdtempSync(path.join(tmpdir(), "cwrap-")));
  for (const v of ["2.1.9", "2.1.10"]) {
    const d = path.join(home, ".local/share/claude/versions"); mkdirSync(d, { recursive: true });
    writeFileSync(path.join(d, v), `#!/bin/sh\necho "v=${v} cfg=\${CLAUDE_CONFIG_DIR:-unset} tok=\${CLAUDE_CODE_OAUTH_TOKEN:+set}"\n`, { mode: 0o755 });
  }
  const run = (tool, env = {}) => spawnSync(path.join(bin, tool), ["auth", "status"], { encoding: "utf8",
    env: { PATH: "/usr/bin:/bin", HOME: home, ...env } }).stdout.trim();
  return { home, run };
}

test("plain claude: no account chosen -> lordsisodia (~/.config/claude-siso-3), newest version; anything chosen passes through", () => {
  const f = fixture();
  assert.equal(f.run("claude"), `v=2.1.10 cfg=${f.home}/.config/claude-siso-3 tok=`, "never ~/.claude's own login (Fahmy's); fuzeheritage is off for Claude Code since 3 Oct");
  assert.equal(f.run("claude", { SISO_CLAUDE_DEFAULT: "/x/other" }), "v=2.1.10 cfg=/x/other tok=");
  assert.equal(f.run("claude", { CLAUDE_CONFIG_DIR: "/x/claude-siso-3" }), "v=2.1.10 cfg=/x/claude-siso-3 tok=");
  assert.equal(f.run("claude", { CLAUDE_CODE_OAUTH_TOKEN: "t" }), "v=2.1.10 cfg=unset tok=set", "one-home token sessions untouched");
});

test("claude-fahmy is the only way to Fahmy's login: it clears every account choice", () => {
  const f = fixture();
  assert.equal(f.run("claude-fahmy", { CLAUDE_CONFIG_DIR: "/x/claude-siso", CLAUDE_CODE_OAUTH_TOKEN: "t" }), "v=2.1.10 cfg=unset tok=");
});

test("a SISO launch puts the wrapper back when an update made ~/.local/bin/claude a plain symlink again", () => {
  const f = fixture();
  mkdirSync(path.join(f.home, ".local/bin"), { recursive: true });
  symlinkSync(path.join(f.home, ".local/share/claude/versions/2.1.10"), path.join(f.home, ".local/bin/claude"));
  const r = spawnSync("bash", ["-c", `source ${bin}one-home.sh`], { encoding: "utf8", env: { PATH: "/usr/bin:/bin", HOME: f.home } });
  assert.equal(r.status, 0, r.stderr);
  assert.equal(readlinkSync(path.join(f.home, ".local/bin/claude")), path.join(bin, "claude").replace(/\/$/, ""));
});
