// siso-ci: the failure parser and the repo list (no network, no GitHub calls).
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

test("siso-ci selftest parses failing tests from node, python, pytest, vitest and check scripts", () => {
  const out = execFileSync("python3", ["ci/siso-ci", "selftest"], { encoding: "utf8" });
  assert.match(out, /selftest ok/);
});

test("every repo in ci/repos.json has a test command (or runs only its branch's .siso-ci) and a known mode", () => {
  const repos = JSON.parse(readFileSync("ci/repos.json", "utf8"));
  for (const [repo, cfg] of Object.entries(repos)) {
    assert.match(repo, /^[\w.-]+\/[\w.-]+$/);
    assert.ok(cfg.test || cfg.branch_file === true, `${repo} has no test and no branch_file`);
    assert.ok(["all", "new-failures"].includes(cfg.mode), `${repo} mode ${cfg.mode}`);
    if (cfg.branches !== undefined) assert.ok(Array.isArray(cfg.branches) && cfg.branches.every((b) => typeof b === "string" && b), `${repo} branches`);
  }
});


test("CI bytecode suppression reaches child loaders", () => {
  const out = execFileSync("python3", ["-B", "-c", `
import os, pathlib, runpy, subprocess, sys, tempfile
os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
sys.path.insert(0, str(pathlib.Path("ci").resolve()))
runpy.run_path("ci/siso-ci", run_name="fixture_ci")
with tempfile.TemporaryDirectory() as tmp:
    source = pathlib.Path(tmp) / "child_module.py"
    source.write_text("value = 1\\n")
    child = "import importlib.machinery,sys; importlib.machinery.SourceFileLoader('child_module',sys.argv[1]).load_module()"
    subprocess.run([sys.executable, "-c", child, str(source)], check=True)
    assert not (pathlib.Path(tmp) / "__pycache__").exists(), "child recreated executable cache"
print("child loader wrote no bytecode")
`], { encoding: "utf8", timeout: 10000 });
  assert.match(out, /child loader wrote no bytecode/);
});
