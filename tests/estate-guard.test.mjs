// estate-guard: blocks new workspace-root entries, new visible folders in ~, and worktrees outside _data/worktrees.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { homedir } from 'node:os';
import { join } from 'node:path';

const HOOK = new URL('../hooks/estate-guard.mjs', import.meta.url).pathname;
const W = join(homedir(), 'SISO_Workspace');
const run = (payload) => spawnSync('node', [HOOK], { input: typeof payload === 'string' ? payload : JSON.stringify(payload) }).status;
const bash = (command, cwd = W) => run({ tool_name: 'Bash', cwd, tool_input: { command } });

test('blocks a new folder at the workspace root', () => assert.equal(bash('mkdir -p newthing/sub'), 2));
test('blocks it after another command too', () => assert.equal(bash('cd x && mkdir ~/SISO_Workspace/stray-folder', '/tmp'), 2));
test('allows a folder inside a district', () => assert.equal(bash('mkdir -p SISO_Agency/apps/new-app'), 0));
test('blocks a new visible folder in ~', () => assert.equal(bash('mkdir my-project', homedir()), 2));
test('allows a tool dotfolder in ~', () => assert.equal(bash('mkdir -p .newtool/config', homedir()), 0));
test('blocks a worktree beside the repo', () => assert.equal(bash('git worktree add -b feat/x ../app-feat', join(W, 'SISO_Agency/apps/siso-internal')), 2));
test('blocks a worktree in /tmp via git -C', () => assert.equal(bash('git -C repo worktree add /tmp/wt main', '/x'), 2));
test('allows a worktree in the one place', () => assert.equal(bash('git -C SISO_Agency worktree add ~/SISO_Workspace/_data/worktrees/siso-agency/lane main'), 0));
test('blocks writing a new file at the root', () => assert.equal(run({ tool_name: 'Write', cwd: W, tool_input: { file_path: join(W, 'NOTES.md') } }), 2));
test('allows writing inside a district', () => assert.equal(run({ tool_name: 'Write', cwd: W, tool_input: { file_path: join(W, 'SISO_Agency/NOTES.md') } }), 0));
test('the escape hatch passes', () => assert.equal(bash('mkdir newthing # estate-guard: allow'), 0));
test('mkdir as an argument is not a command', () => assert.equal(bash('echo mkdir newthing'), 0));
test('a variable path passes (cannot know)', () => assert.equal(bash('mkdir -p "$TMPDIR/x"'), 0));
test('bad input passes', () => assert.equal(run('garbage'), 0));
