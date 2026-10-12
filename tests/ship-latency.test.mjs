import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const bin = new URL("../scripts/ship-latency.py", import.meta.url).pathname;

// main: base (deploy 1) -> merge of lane A (A built 10:00, merged 10:10) -> merge of lane B (B built 10:05, merged 10:30);
// deploy 2 at 11:00. Expected: A built->merged 10, merged->live 50; B 25 and 30.
test("ship-latency: built, merged (first first-parent commit holding it) and live per lane commit; medians", () => {
  const repo = mkdtempSync(path.join(tmpdir(), "latency-"));
  const day = "2026-10-02";
  const t = hm => `${day}T${hm}:00+07:00`;
  const g = (env, ...a) => execFileSync("git", ["-C", repo, ...a], { env: { ...process.env, GIT_AUTHOR_DATE: env, GIT_COMMITTER_DATE: env,
    GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" }, encoding: "utf8" }).trim();
  g(t("09:00"), "init", "-q", "-b", "main");
  writeFileSync(path.join(repo, "f"), "0"); g(t("09:00"), "add", "f"); g(t("09:00"), "commit", "-qm", "base");
  const base = g(t("09:00"), "rev-parse", "HEAD");
  g(t("09:00"), "checkout", "-qb", "a"); writeFileSync(path.join(repo, "a"), "1"); g(t("10:00"), "add", "a"); g(t("10:00"), "commit", "-qm", "lane A");
  g(t("09:00"), "checkout", "-q", "main"); g(t("09:00"), "checkout", "-qb", "b"); writeFileSync(path.join(repo, "b"), "1"); g(t("10:05"), "add", "b"); g(t("10:05"), "commit", "-qm", "lane B");
  g(t("10:10"), "checkout", "-q", "main"); g(t("10:10"), "merge", "-q", "--no-ff", "-m", "merge A", "a");
  g(t("10:30"), "merge", "-q", "--no-ff", "-m", "merge B", "b");
  const tip = g(t("10:30"), "rev-parse", "HEAD");
  const dep = path.join(repo, "deploys.txt");
  writeFileSync(dep, `# test\n${base} 09:30\n${tip} 11:00\n`);
  const r = spawnSync("python3", [bin, "--repo", repo, "--deploys", dep, "--day", day, "--json"], { encoding: "utf8", env: { ...process.env, TZ: "Asia/Bangkok" } });
  assert.equal(r.status, 0, r.stderr);
  const { summary, items } = JSON.parse(r.stdout);
  const a = items.find(i => i.subject === "lane A"), b = items.find(i => i.subject === "lane B");
  assert.deepEqual([a.built_to_merged, a.merged_to_live, a.built_to_live], [10, 50, 60]);
  assert.deepEqual([b.built_to_merged, b.merged_to_live, b.built_to_live], [25, 30, 55]);
  assert.equal(summary.items, 2); assert.equal(summary.median_built_to_live, 57.5); assert.equal(summary.over_20_min, 2);
});
