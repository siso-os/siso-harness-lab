# Automatic fresh SISO Code seats

`seat-fresh-t3 SEAT` now executes configuration read → launch → verify replacement
configuration/workspace and initial-run acceptance → atomically update the seat
map (keeping `previous_thread`) → archive old thread and verify its archive.
The boot message points to HANDOFF/AGENTS and specific old-thread reads, plus the
last completed assistant message. Private boot text is never logged on a live run.
`--dry-run` retains the print-only MCP plan; `--adopt` retains the legacy guarded
manual adoption path for older plans.

`seat-fresh-t3 --all-long` rotates local seats **over 800** turn items. Every
rotation requires no active or queued run and a latest run with status
`completed` and a completion timestamp. Running, waiting, failed, interrupted,
never-run, archived and deleted sources are skipped. Agent Zero (by name and
thread `2233dd6b-bf45-4985-b462-4879c470babc`) is excluded from automatic rotation.
`fleet-check` still flags LONG inclusively at 800; automatic rotation begins at
801, following Shaan's “passes 800” requirement.

## Existing authenticated channel

The server's supported local CLI `auth pairing create --json --base-dir ...`
issues a five-minute one-time grant. The command captures its output privately,
registers an MCP OAuth client, approves using that grant, and exchanges a PKCE
code for an MCP client bearer token through `/oauth/mcp/*`. The CLI uses the
server's existing auth control plane; this script neither reads signing keys
nor modifies SQLite. Auth source: SISO Code's `cli/auth.ts`,
`auth/mcpOAuthHttp.ts`, `auth/McpOAuth.ts` and `auth/EnvironmentAuth.ts`.
Provider-session tokens are in-memory/thread-bound; ACP credentials are absent
from a normal launchd environment, so they cannot support the scheduled job.

Only loopback HTTP origins from `userdata/server-runtime.json` are accepted.
The bearer token is cached mode 600 at
`~/.local/state/agent-base/seat-fresh-auth.json` until expiry; bodies and secrets
are withheld from errors and logs. No browser or new auth bypass is used.
The existing installed CLI lives at `~/.local/share/siso-code/app/t3/dist/bin.mjs`;
the scheduler uses `~/.local/bin/node` to invoke it.

## Recovery and concurrency

A process lock serializes rotation invocations. Before the non-idempotent
launch, a mode-600 journal (`t3-seats.json.fresh.json`) records the old thread
and a unique marker appended to the boot message. It then records the returned
new ID. A lost launch response is reconciled by that marker in the read-only
message projection. An ambiguous outcome never causes a second launch.
Preparation, verification or archive errors retain the journal; the next run
continues the same rotation, even after the seat map has already moved.
A replacement with failed preparation or mismatched settings is left available
for diagnosis; its source is preserved. A never-accepted ambiguous launch stays
pending rather than risking a duplicate.

The seat-map writer takes its existing advisory lock, reads the latest map,
compares the expected old ID, preserves other seats/metadata, then atomically
replaces the file. Writers ignoring that lock can race the final compare/write.
The source is checked for idle state again immediately before launch, adoption
and archive. The server API offers no atomic idle-and-archive command; a new
human message arriving after the last check remains a narrow external race.

## Installation and verification

Run `bin/seat-fresh-t3-install` from the merged checkout. It copies the command
into a revisioned bundle, writes a SHA-256 receipt, atomically switches the PATH
launcher, and bootstraps `~/Library/LaunchAgents/com.siso.seat-fresh-t3.plist`.
The job runs immediately and every 900 seconds; stdout/stderr go to
`~/.local/state/agent-base/seat-fresh.log`. RunAtLoad catches eligible seats after
login. Agent Zero is never rotated by this job.

`heavy -- node --test tests/fleet-check.test.mjs tests/seat-fresh-auto.test.mjs`
checks existing fleet/dry-run/adoption contracts and failure-injected rotations:
active/queued/failed guards, exact settings, 800/801, Agent Zero exclusion,
lost-launch recovery, archive retry, map preservation and operation order.
Live proof must additionally observe a naturally idle LONG seat and its old
archive/new map IDs; the test suite never launches a live seat.
