# PR gate policy: only what the diff touches (17 Oct 2026)

Shaan, 17 Oct: "can we cut down on these checks? These checks take the piss ... from first principles, we don't even need to do these checks. These checks are 80% of our build and we just waste ... so much time on these fucking checks". So: **a PR gate (`siso-ci/pr`, and HALO's alias `siso-ci/affected`) runs only the tests its diff touches, and no full suite blocks a merge or a ship.** SISO Code runs `vp test run --changed <merge-base>` (vitest's own import graph); a diff of only docs runs nothing and passes at once (no install, no heavy ticket); only the lockfile or root config runs its full suite. Harness-lab maps a changed file to the tests of the same name and to itself; a path no test names runs nothing. HALO's PR gate was already affected-only (`halo-pr.sh`). The HALO train ships a head whose PRs were all green and no longer runs the full suite first; the full suite runs once a night (or after 40 new commits) as `siso-ci/nightly`, report-only: on red, the red-main bisect names the first bad landing and files an issue, and nothing is reverted, merged or blocked (`ship-train REPO BRANCH --nightly`, run by the coordinator beside the train; set by `train.suite: "nightly"`). Status names are unchanged, so merge rules keep working. The price is a bug caught a day later by the nightly run instead of before the merge; Shaan chose iteration speed.

# PR affected-test selection

`ci/repos.json` is the runner-owned mapping. `test` remains the full command.
PRs alone opt into `affected`: `command` receives a shell-quoted, deduplicated
list of explicit test files. `test_globs` inventories the full suite's test files
for receipts; `rules` map changed `paths` globs to explicit `tests` filenames.
`shared` adds repo-specific full-suite triggers. Globs use Python fnmatch (a `*`
can include `/`); overlapping rules are unioned, not first-match wins.

The first mappings cover the harness's independent read-gate and test-filter
hooks and their tests. Repos with a `changed` command, `by_name` or `unmapped: skip` (see above) no longer fall back to full on unknown paths; others stay full until mapped (`ignore` still skips docs-only diffs). Do not add a broad source glob without reviewing all its consumers.
`.siso-ci` overrides continue to run their full command; they do not inherit a
central mapping for a different suite. SISO Code's PR gate uses `affected.changed` (`--changed <merge-base>`); main and the full fallback keep the full command, which never uses `--changed`.

Selection fetches the exact PR base and diffs merge-base..head. Rename endpoints
both count. Unknown paths, shared/config/dependency files, missing/deleted mapped
tests, invalid/empty maps and unavailable history all run the original full
command. Setup always runs. Empty selections never become a passing no-test run, except `ignore`d docs paths and `unmapped: skip` repos (mode `skip`, test `true`).
Main/watched-branch pushes, recovery and baseline comparisons use the full
command; a PR status cannot skip a watched-branch run. Tests written in `.siso-ci`
must themselves be full-suite commands.

The log, GitHub status and `state.json` record subset/full; state additionally
records reason, selected/total **test-file counts**, names and elapsed test time.
Counts describe scheduled files, not test cases or completed files: a failing
full command may stop before later suites. Runner output supplies test-case
counts. 

Check: `heavy -- node --test tests/ci-affected.test.mjs tests/siso-ci.test.mjs tests/red-main.test.mjs`.
The affected integration suite uses real Git repositories and runs Node tests,
covering subset, union, shared/config/unknown fallbacks, missing history, renames,
deletions, malformed maps, base advance, `.siso-ci`, main status isolation and
restoring the PR head for the new-failures retry.
