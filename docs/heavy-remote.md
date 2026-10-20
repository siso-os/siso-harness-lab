# Opt-in Mini execution

```sh
heavy --on mini --cwd /absolute/path/to/mini/worktree -- npm test
```

This runs the command in the explicitly named **Mini checkout**, via SSH host
`mac-mini`. The sender dispatches before creating its local pool or registering a
waiter. The Mini runs `$HOME/SISO_Workspace/SISO_Agents/siso-harness-lab/bin/heavy`
and uses its existing local slots and FIFO. Existing `heavy -- COMMAND`, status,
hold and release behavior is unchanged.

Requirements: working noninteractive SSH authentication and trusted host key for
`mac-mini`, Python 3 and the canonical heavy executable on the Mini, an existing
absolute remote directory, and the command's tools/dependencies already present.
The remote PATH adds `~/.local/bin`, `/opt/homebrew/bin` and `/usr/local/bin`.
No repository sync, dependency installation, checkout update or environment copy
occurs. Check remote source revision yourself before choosing a worktree.

Arguments are individually shell-quoted. stdin, stdout and stderr remain attached;
SSH runs without a TTY. The exit code is the payload's exit code, or SSH's failure
code (typically 255); these can overlap. SSH connection establishment is limited
to eight seconds and one attempt, with batch authentication. Running commands have
no imposed timeout. Missing SSH returns 127; bad routing syntax returns 2. Any
connection, directory or remote command failure exits without a local fallback.
Shell expansion and pipelines require an explicit payload such as `sh -c '...'`.
Local control flags do not control the remote pool. Existing in-flight commands
are unaffected.

## Standalone activation by the owner

Only the sending machine needs the new CLI. The Mini's existing local `heavy`
suffices. After obtaining the reviewed commit, extract `bin/heavy` from that exact
commit to a temporary file, then install it under an unused name such as
`~/.local/bin/heavy-remote-20261016` with mode 755. Invoke that name with the options
above. This avoids replacing a symlink or modifying a shared checkout; remove the
new file to roll back. The delivery receipt supplies exact pinned commands.
No live installation or restart was performed by this branch.

## Verification and measurement scope

Run on the Mini through its canonical heavy:

```sh
~/SISO_Workspace/SISO_Agents/siso-harness-lab/bin/heavy -- python3 -B tests/heavy.test.py
~/SISO_Workspace/SISO_Agents/siso-harness-lab/bin/heavy -- python3 -B tests/heavy-remote.test.py
```

Nine existing local admission/FIFO tests and six remote tests pass. The SSH mock
executes the actual remote shell command and a separate copy of heavy in an
isolated HOME. It verifies argument boundaries (including empty strings, quotes,
newlines and shell metacharacters), all three streams, payload exit 23, remote
pool creation, unchanged sender ticket, and failure without local execution.
Placement fixture before/after: sender payload executions **1 → 0**, remote
payload executions **0 → 1**. This is a process-placement fixture, not a measured
laptop CPU, memory or whole-load improvement.

Real SSH smoke evidence is in
`../.agents/runs/2026-10-16-eff-astra-builds/live-smoke.json`: Mini-to-itself SSH
using a temporary `mac-mini` alias to localhost, the assigned checkout as cwd,
remote canonical pool slot 1, payload result 42 and exit 7, stderr preserved,
and no sender pool created. The test harness occupied slot 0 under the required
Mini test wrapper; the remote CLI independently acquired slot 1. This proves the
real SSH producer/consumer path on the Mini. Laptop-to-Mini authentication and
live laptop performance were not tested, and no laptop was contacted.
