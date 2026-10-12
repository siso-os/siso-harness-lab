import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const here = new URL("../bin/", import.meta.url).pathname;

// A fake HOME whose ~/.local/bin/claude reports the config folder and whether a token arrived (never its value), and a
// fake `security` that has a token for fuzeheritage only.
function fixture() {
  const home = mkdtempSync(path.join(tmpdir(), "one-home-"));
  mkdirSync(path.join(home, ".local", "bin"), { recursive: true });
  writeFileSync(path.join(home, ".local", "bin", "claude"), `#!/bin/sh\necho "dir=\${CLAUDE_CONFIG_DIR:-unset} token=\${CLAUDE_CODE_OAUTH_TOKEN:+set} account=\${SISO_ACCOUNT:-none}"\n`);
  chmodSync(path.join(home, ".local", "bin", "claude"), 0o755);
  const fb = path.join(home, "fakebin"); mkdirSync(fb);
  writeFileSync(path.join(fb, "security"), `#!/bin/sh\ncase "$*" in *"-a fuzeheritage"*) echo tok-fuze ;; *) exit 44 ;; esac\n`);
  chmodSync(path.join(fb, "security"), 0o755);
  const run = (launcher, env = {}, name = "PROBE") => spawnSync(path.join(here, launcher), ["-n", name], { encoding: "utf8",
    env: { PATH: `${fb}:/usr/bin:/bin`, HOME: home, SISO_FULL_BOOT: "1", CLAUDE_CODE_OAUTH_TOKEN: "inherited", ...env } });
  return { home, run };
}

test("defaults: claude-siso seats run from ~/.claude on fuzeheritage's token; streaming seats and SISO_ONE_HOME=0 keep the old folder; claude-siso-3 stays on its folder", () => {
  const f = fixture();
  let r = f.run("claude-siso");
  assert.equal(r.status, 0, r.stderr); assert.match(r.stdout, /dir=unset token=set account=fuzeheritage/);
  assert.ok(!r.stdout.includes("tok-fuze"), "the token value is never printed");
  for (const seat of ["STREAM-B", "STREAMING-CLAUDE", "OPS-BUILD"]) {
    r = f.run("claude-siso", {}, seat);
    assert.match(r.stdout, new RegExp(`dir=${f.home}/\\.claude-siso token= account=none`), seat);
  }
  r = f.run("claude-siso", { SISO_ONE_HOME: "0" });
  assert.match(r.stdout, new RegExp(`dir=${f.home}/\\.claude-siso token= account=none`));
  r = f.run("claude-siso-3");
  assert.match(r.stdout, new RegExp(`dir=${f.home}/\\.config/claude-siso-3 token= account=none`), "inherited token dropped too");
});

test("SISO_ONE_HOME=1 with no token for the account refuses (exit 3) before claude starts: never ~/.claude's own login (Fahmy's)", () => {
  const f = fixture();
  const r = f.run("claude-siso-3", { SISO_ONE_HOME: "1" });
  assert.equal(r.status, 3); assert.match(r.stderr, /no token for lordsisodia; run: claude-token-login lordsisodia/);
  assert.equal(r.stdout, "", "claude never started");
});

test("the stack plugin is passed to claude when its folder exists (lean and full boot), and not when it is absent", () => {
  const f = fixture();
  const plug = path.join(f.home, "plug");
  mkdirSync(path.join(plug, ".claude-plugin"), { recursive: true });
  writeFileSync(path.join(plug, ".claude-plugin", "plugin.json"), "{}");
  writeFileSync(path.join(f.home, ".local", "bin", "claude"), `#!/bin/sh\necho "$*"\n`);
  let r = f.run("claude-siso", { SISO_ONE_HOME: "0", SISO_STACK_PLUGIN: plug });
  assert.match(r.stdout, new RegExp(`--plugin-dir ${plug} `), "full boot");
  r = f.run("claude-siso-3", { SISO_ONE_HOME: "0", SISO_STACK_PLUGIN: plug, SISO_FULL_BOOT: "" });
  assert.match(r.stdout, new RegExp(`--plugin-dir ${plug} `), "lean boot");
  r = f.run("claude-siso", { SISO_ONE_HOME: "0", SISO_STACK_PLUGIN: path.join(f.home, "nope") });
  assert.doesNotMatch(r.stdout, /--plugin-dir/);
});
