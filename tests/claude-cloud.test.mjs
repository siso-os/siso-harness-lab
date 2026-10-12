import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const root = new URL("..", import.meta.url).pathname;
const py = code => execFileSync("python3", ["-c", code], { encoding: "utf8", env: { ...process.env, ...py.env } }).trim();
const loader = (name, file) => `import importlib.machinery as m, importlib.util as u, json
l=m.SourceFileLoader('${name}','${root}${file}');x=u.module_from_spec(u.spec_from_loader('${name}',l));l.exec_module(x)\n`;

test("claude-credits: a grant is any usage bucket with limit_dollars; samples only when it moves; a dead login is reported, not fatal", () => {
  const dir = mkdtempSync(path.join(tmpdir(), "ccred-"));
  py.env = { CLAUDE_CREDITS_STATE: dir };
  const out = py(loader("cc", "bin/claude-credits") + `
use = {"five_hour": {"utilization": 4}, "iguana_necktie": {"limit_dollars": 250, "used_dollars": 0.11, "remaining_dollars": 249.89,
       "resets_at": "2026-11-05T07:59:00+00:00", "locked_reason": None}, "extra_usage": {"is_enabled": False}}
def fetch(login, cfg):
    if login == "claude-siso-3": raise OSError("401")
    return ({"account": {"email": "a@b"}}, use)
rows = x.read_all(fetch)
print(json.dumps(rows))
print(len(x.sample(rows)), len(x.sample(rows)))
use["iguana_necktie"]["used_dollars"] = 0.5
print(len(x.sample(x.read_all(fetch))))
print([l.split('"used_usd": ')[1].split(",")[0] for l in open("${dir}/samples.jsonl")])
print(x.LOGINS)`).split("\n");
  const rows = JSON.parse(out[0]);
  assert.deepEqual(rows[0].grants, [{ bucket: "iguana_necktie", limit_usd: 250, used_usd: 0.11, left_usd: 249.89, ends: "2026-11-05T07:59:00+00:00", locked: null }]);
  assert.match(rows[1].error, /OSError/);
  assert.equal(out[1], "1 0", "the second sample of an unchanged figure is skipped");
  assert.equal(out[2], "1");
  assert.equal(out[3], "['0.11', '0.5']");
  assert.ok(!out[4].includes("'~/.claude'"), "plain claude (Fahmy's) is never read");
});

function repo(home, origin) {
  const r = path.join(home, "repo"); mkdirSync(r);
  execFileSync("git", ["init", "-q", r]);
  execFileSync("git", ["-C", r, "remote", "add", "origin", origin]);
  return r;
}

test("claude-cloud: starts through a pty, stamps the task and chain, logs the session; refuses plain claude and non-GitHub repos", () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccloud-"));
  const fake = path.join(home, "claude");
  writeFileSync(fake, `#!/bin/sh\n[ -t 0 ] || [ -t 1 ] || { echo "Error: --cloud requires an interactive terminal." >&2; exit 1; }\n` +
    `printf '%s' "$2" > "${home}/brief.txt"\necho "$CLAUDE_CONFIG_DIR" > "${home}/cfg.txt"\n` +
    `echo "Created cloud session: probe"\necho "View: https://claude.ai/code/session_01AbC?from=cli"\n`, { mode: 0o755 });
  const env = { ...process.env, CLAUDE_BIN: fake, CLAUDE_CLOUD_STATE: path.join(home, "cc"), SISO_TASK_STATE: path.join(home, "t"),
    CLAUDE_CLOUD_NO_SAMPLE: "1", CLAUDE_CLOUD_CREATE: "bundle" };  // the fallback path
  const run = (cwd, ...a) => spawnSync(`${root}bin/claude-cloud`, a, { env, cwd, encoding: "utf8" });
  const gh = repo(home, "git@github.com:sisodias/x.git");
  const r = run(gh, "--task", "so-022", "--alloc", "usd:5", "--chain", "opus:spec,cloud:run", "sweep the docs");
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /cloud session session_01AbC on claude-siso for so-022/);
  assert.match(readFileSync(path.join(home, "brief.txt"), "utf8"), /^TASK: so-022\nCHAIN: opus:spec,cloud:run\n\nsweep the docs[\s\S]*RETURN\nSTATUS:/);
  assert.match(readFileSync(path.join(home, "cfg.txt"), "utf8").trim(), /\.claude-siso$/);
  const mark = JSON.parse(readFileSync(path.join(home, "t", "marks.jsonl"), "utf8").trim());
  assert.deepEqual([mark.session, mark.task, mark.source, mark.alloc, mark.chain], ["session_01AbC", "so-022", "cloud", { usd: 5 }, ["opus:spec", "cloud:run"]]);
  const log = JSON.parse(readFileSync(path.join(home, "cc", "log.jsonl"), "utf8").trim());
  assert.deepEqual([log.session, log.login, log.url], ["session_01AbC", "claude-siso", "https://claude.ai/code/session_01AbC?from=cli"]);
  assert.equal(run(gh, "--login", "claude", "x").status, 2, "plain claude is refused");
  const local = path.join(home, "l"); mkdirSync(local); repo(local, "/tmp/somewhere.git");
  assert.equal(run(path.join(local, "repo"), "x").status, 2, "the cloud can only clone a GitHub origin");
});

test("ledger: each rise in the grant goes to the cloud sessions started before it (within 6 h); otherwise unattributed", () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccl-"));
  const cs = path.join(home, "cs"), cl = path.join(home, "cl"); mkdirSync(cs); mkdirSync(cl);
  const S = (at, used) => JSON.stringify({ at, login: "claude-siso", bucket: "iguana_necktie", used_usd: used, limit_usd: 250 });
  // 1 Oct: $1 before any session. 2 Oct 10:00 (+07): a manual probe took it to $1.5; session_a starts 12:00, session_b
  // 13:00; $3 at 16:00 (both running: $0.75 each); 3 Oct 20:00: $4, but both started > 6 h before: unattributed.
  writeFileSync(path.join(cs, "samples.jsonl"), [S("2026-10-01T05:00:00+00:00", 1), S("2026-10-02T03:00:00+00:00", 1.5),
    S("2026-10-02T04:59:00+00:00", 1.5), S("2026-10-02T09:00:00+00:00", 3), S("2026-10-03T13:00:00+00:00", 4)].join("\n") + "\n");
  writeFileSync(path.join(cl, "log.jsonl"), [
    { at: "2026-10-02T12:00:00+07:00", session: "session_a", login: "claude-siso", task: "so-022", alloc: { usd: 5 }, chain: ["opus:spec", "cloud:run"] },
    { at: "2026-10-02T13:00:00+07:00", session: "session_b", login: "claude-siso", task: null }].map(x => JSON.stringify(x)).join("\n") + "\n");
  py.env = { CLAUDE_CREDITS_STATE: cs, CLAUDE_CLOUD_STATE: cl, SPEND_LEDGER_DIR: home, TZ: "Asia/Ho_Chi_Minh" };
  const rows = JSON.parse(py(loader("sl", "bin/spend-ledger") + `print(json.dumps(x.cloud_rows({"2026-10-02", "2026-10-03"}, {})))`));
  const got = rows.map(r => [r.day, r.task, r.session, r.cost.grant_usd, r.attribution]);
  assert.deepEqual(got, [
    ["2026-10-02", "unattributed:cloud", null, 0.5, "none"],
    ["2026-10-02", "so-022", "session_a", 0.75, "stamped"],
    ["2026-10-02", "unattributed:cloud", "session_b", 0.75, "none"],
    ["2026-10-03", "unattributed:cloud", null, 1, "none"]]);
  assert.deepEqual(rows[1].chain, ["opus:spec", "cloud:run"]);
});

// A stand-in for the Claude Code sessions API: one session that can't push, and its events carrying a recover patch.
import http from "node:http";
import { spawn } from "node:child_process";
import { gzipSync } from "node:zlib";
function serve(routes) {
  return new Promise((res) => { const s = http.createServer((q, a) => { const k = Object.keys(routes).find((p) => q.url.startsWith(p)); a.statusCode = k ? 200 : 404; a.end(JSON.stringify(k ? routes[k] : {})); }).listen(0, "127.0.0.1", () => res(s)); });
}
function runCC(args, env, cwd) {
  return new Promise((res) => { const p = spawn(`${root}bin/claude-cloud`, args, { cwd, env: { ...process.env, ...env } }); let out = "", err = ""; p.stdout.on("data", (d) => (out += d)); p.stderr.on("data", (d) => (err += d)); p.on("close", (status) => res({ status, out, err })); });
}

test("claude-cloud status: each logged session's state, cost and what it waits on; flags a session that cannot push", async () => {
  const state = mkdtempSync(path.join(tmpdir(), "ccst-"));
  writeFileSync(path.join(state, "log.jsonl"), JSON.stringify({ at: "2026-10-03T00:17:42+07:00", session: "session_A", login: "claude-siso", task: "t-1" }) + "\n");
  const s = await serve({ "/v1/sessions/session_A?": { session_status: "idle", connection_status: "disconnected", github_access: "GITHUB_ACCESS_UNSPECIFIED",
    external_metadata: { usage: { cost_usd: 3.2281 }, current_branches: { "": "main" }, post_turn_summary: { status_category: "need_input", status_detail: "commit ready, push blocked", needs_action: "push branch cloud/t-1" } } } });
  const env = { CLAUDE_CLOUD_STATE: state, CLAUDE_CLOUD_API: `http://127.0.0.1:${s.address().port}`, CLAUDE_CLOUD_TOKEN: "x" };
  const r = await runCC(["status"], env); const j = await runCC(["status", "--json"], env); s.close();
  assert.equal(r.status, 0, r.err);
  assert.match(r.out, /t-1\s+idle\s+\$3\.23\s+need_input\s+commit ready, push blocked\s+CANNOT PUSH/);
  assert.match(r.out, /needs: push branch cloud\/t-1/);
  assert.equal(JSON.parse(j.out)[0].github, "GITHUB_ACCESS_UNSPECIFIED");
});

test("claude-cloud recover: reads the patch parts a session printed (events API), checks it, and puts its commits on a branch in a worktree", async () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccrec-"));
  const r0 = path.join(home, "repo"); mkdirSync(r0);
  const g = (...a) => execFileSync("git", ["-C", r0, ...a], { encoding: "utf8", env: { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" } }).trim();
  g("init", "-q", "-b", "main"); writeFileSync(path.join(r0, "a.txt"), "1\n"); g("add", "."); g("commit", "-qm", "base");
  const base = g("rev-parse", "HEAD");
  // the "cloud" commit, made in a scratch clone, then turned into a patch the way the session does
  const c = path.join(home, "cloud"); execFileSync("git", ["clone", "-q", r0, c]);
  writeFileSync(path.join(c, "a.txt"), "1\n2\n"); execFileSync("git", ["-C", c, "commit", "-qam", "cloud work"], { env: { ...process.env, GIT_AUTHOR_NAME: "Claude", GIT_AUTHOR_EMAIL: "c@c", GIT_COMMITTER_NAME: "Claude", GIT_COMMITTER_EMAIL: "c@c" } });
  const patch = execFileSync("git", ["-C", c, "format-patch", "--stdout", `${base}..HEAD`]);
  const b64 = gzipSync(patch, { level: 9 }).toString("base64").match(/.{1,76}/g).join("\n");
  const half = Math.ceil(b64.length / 2);
  const ev = [["aa", b64.slice(0, half)], ["ab", b64.slice(half)]].flatMap(([k, body], i) => [
    { message: { content: [{ type: "tool_use", id: `u${i}`, input: { command: `cat /tmp/recover-part-${k}` } }] } },
    { message: { content: [{ type: "tool_result", tool_use_id: `u${i}`, content: body + "\nShell cwd was reset to /x" }] } }]);
  ev.push({ message: { content: [{ type: "text", text: `PATCH READY 2 parts, base ${base}, branch cloud/t-9-thing` }] } });
  const state = mkdtempSync(path.join(tmpdir(), "ccst-"));
  writeFileSync(path.join(state, "log.jsonl"), JSON.stringify({ at: "x", session: "session_B", login: "claude-siso", task: "t-9" }) + "\n");
  const s = await serve({ "/v1/sessions/session_B/events": { data: ev, has_more: false } });
  const r = await runCC(["recover", "session_B"], { CLAUDE_CLOUD_STATE: state, CLAUDE_CLOUD_API: `http://127.0.0.1:${s.address().port}`, CLAUDE_CLOUD_TOKEN: "x", HOME: home }, r0);
  s.close();
  assert.equal(r.status, 0, r.out + r.err);
  assert.match(r.out, /recovered session_B onto cloud\/t-9-thing/);
  const wt = path.join(home, "SISO_Workspace/_data/worktrees/repo/cloud-t-9");
  assert.equal(readFileSync(path.join(wt, "a.txt"), "utf8"), "1\n2\n");
  assert.equal(execFileSync("git", ["-C", wt, "log", "-1", "--format=%an %s"], { encoding: "utf8" }).trim(), "Claude cloud work");
});

test("claude-cloud's start contract: push access checked first, push after every commit, a RETURN block always", () => {
  const src = readFileSync(`${root}bin/claude-cloud`, "utf8");
  assert.match(src, /git push --dry-run origin HEAD:refs\/heads\/cloud\/<task>/);
  assert.match(src, /Push the branch after EVERY commit/);
  assert.match(src, /ALWAYS, also when you fail or stop early/);
});

test("claude-cloud recover: an empty patch creates nothing; a session that says 'branch main' is recovered onto cloud/<task>", async () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccrec2-"));
  const r0 = path.join(home, "repo"); mkdirSync(r0);
  const env0 = { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" };
  execFileSync("git", ["-C", r0, "init", "-q", "-b", "main"]); writeFileSync(path.join(r0, "a.txt"), "1\n");
  execFileSync("git", ["-C", r0, "add", "."], { env: env0 }); execFileSync("git", ["-C", r0, "commit", "-qm", "base"], { env: env0 });
  const base = execFileSync("git", ["-C", r0, "rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  const evFor = (b64) => ({ data: [
    { message: { content: [{ type: "tool_use", id: "u0", input: { command: "cat /tmp/recover-part-aa" } }] } },
    { message: { content: [{ type: "tool_result", tool_use_id: "u0", content: b64 }] } },
    { message: { content: [{ type: "text", text: `PATCH READY 1 part, base ${base}, branch main` }] } }], has_more: false });
  const c = path.join(home, "cloud"); execFileSync("git", ["clone", "-q", r0, c]);
  writeFileSync(path.join(c, "b.txt"), "b\n"); execFileSync("git", ["-C", c, "add", "."], { env: env0 }); execFileSync("git", ["-C", c, "commit", "-qm", "on main"], { env: env0 });
  const full = gzipSync(execFileSync("git", ["-C", c, "format-patch", "--stdout", `${base}..HEAD`]), { level: 9 }).toString("base64");
  const state = mkdtempSync(path.join(tmpdir(), "ccst-"));
  writeFileSync(path.join(state, "log.jsonl"), JSON.stringify({ at: "x", session: "session_E", login: "claude-siso", task: "t-e" }) + "\n" + JSON.stringify({ at: "x", session: "session_M", login: "claude-siso", task: "t-m" }) + "\n");
  const s = await serve({ "/v1/sessions/session_E/events": evFor(gzipSync(Buffer.alloc(0)).toString("base64")), "/v1/sessions/session_M/events": evFor(full) });
  const env = { CLAUDE_CLOUD_STATE: state, CLAUDE_CLOUD_API: `http://127.0.0.1:${s.address().port}`, CLAUDE_CLOUD_TOKEN: "x", HOME: home };
  const e = await runCC(["recover", "session_E"], env, r0);
  const m = await runCC(["recover", "session_M"], env, r0);
  s.close();
  assert.equal(e.status, 0); assert.match(e.out, /made no commits/);
  assert.equal(execFileSync("git", ["-C", r0, "worktree", "list"], { encoding: "utf8" }).trim().split("\n").length, 2, "only the t-m worktree was made");
  assert.equal(m.status, 0, m.err); assert.match(m.out, /onto cloud\/t-m/);
  assert.equal(execFileSync("git", ["-C", r0, "rev-parse", "--abbrev-ref", "HEAD"], { encoding: "utf8" }).trim(), "main", "the checkout's main untouched");
});

test("claude-cloud start (default): creates the session via the API with the GitHub repo as its source, then sends the brief; logs mode api", async () => {
  const home = mkdtempSync(path.join(tmpdir(), "ccapi-"));
  const fake = path.join(home, "claude");
  writeFileSync(fake, `#!/bin/sh\nprintf '%s|%s|%s' "$1" "$3" "$4" > "${home}/send.txt"\necho sent\n`, { mode: 0o755 });
  let body = null;
  const s = await new Promise((res) => { const srv = http.createServer((q, a) => { let b = ""; q.on("data", (d) => (b += d)); q.on("end", () => {
    if (q.method === "POST") { body = JSON.parse(b); a.end(JSON.stringify({ id: "session_NEW", session_context: body.session_context })); } else a.end("{}"); }); }).listen(0, "127.0.0.1", () => res(srv)); });
  const gh = repo(home, "git@github.com:sisodias/x.git");
  const r = await runCC(["--task", "t-api", "build the thing"], { CLAUDE_BIN: fake, CLAUDE_CLOUD_STATE: path.join(home, "cc"), SISO_TASK_STATE: path.join(home, "t"),
    CLAUDE_CLOUD_NO_SAMPLE: "1", CLAUDE_CLOUD_API: `http://127.0.0.1:${s.address().port}`, CLAUDE_CLOUD_TOKEN: "x", CLAUDE_CLOUD_ENV: "env_T" }, gh);
  s.close();
  assert.equal(r.status, 0, r.err);
  assert.deepEqual(body.session_context.sources, [{ type: "git_repository", url: "https://github.com/sisodias/x", revision: "main" }]);
  assert.deepEqual(body.session_context.outcomes[0].git_info, { type: "github", repo: "sisodias/x", branches: ["cloud/t-api"] });
  assert.equal(body.environment_id, "env_T");
  const [p, flag, sid] = readFileSync(path.join(home, "send.txt"), "utf8").split("|");  // claude -p <brief> --cloud <sid>
  assert.equal(p, "-p"); assert.equal(flag, "--cloud"); assert.equal(sid, "session_NEW");
  assert.equal(JSON.parse(readFileSync(path.join(home, "cc", "log.jsonl"), "utf8").trim()).mode, "api");
});

test("claude-cloud start: when the API refuses the create, its reason is printed (3 Oct: a bare 'HTTP 400' hid 'GitHub repository access check failed')", async () => {
  const home = mkdtempSync(path.join(tmpdir(), "cc400-"));
  const fake = path.join(home, "claude"); writeFileSync(fake, "#!/bin/sh\nexit 1\n", { mode: 0o755 });
  const s = await new Promise((res) => { const srv = http.createServer((q, a) => { q.resume(); q.on("end", () => { a.statusCode = 400;
    a.end(JSON.stringify({ type: "error", error: { type: "invalid_request_error", message: "GitHub repository access check failed. Either you don't have access" } })); }); }).listen(0, "127.0.0.1", () => res(srv)); });
  const gh = repo(home, "git@github.com:sisodias/x.git");
  const r = await runCC(["--task", "t-400", "x"], { CLAUDE_BIN: fake, CLAUDE_CLOUD_STATE: path.join(home, "cc"), SISO_TASK_STATE: path.join(home, "t"),
    CLAUDE_CLOUD_NO_SAMPLE: "1", CLAUDE_CLOUD_API: `http://127.0.0.1:${s.address().port}`, CLAUDE_CLOUD_TOKEN: "x", CLAUDE_CLOUD_ENV: "env_T" }, gh);
  s.close();
  assert.match(r.err, /API create failed \(HTTP 400 for \/v1\/sessions: GitHub repository access check failed/);
});
