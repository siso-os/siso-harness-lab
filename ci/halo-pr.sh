#!/bin/sh
# HALO PR gate, owned by the runner (ci/repos.json "pr_script"): what a halo/v2 PR must pass, in about 30-60 s warm.
# The repo's own .siso-ci stays the full gate for the branch and the ship train (it also runs build:model, a deploy step).
# Differences from .siso-ci: npm ci is skipped when v2/package-lock.json is unchanged (node_modules keeps a hash marker, with
# a clone cache under the work root for lockfile changes); typecheck, typecheck:model, check:model and the tests run in
# parallel; every test file gets 30 s (--test-timeout); at 100 s the files still running are named, and the runner kills
# the job at its 120 s cap. Per-step seconds are printed as "[siso-ci-step] <name> <s>s".
cd v2 || exit 1
N22=${SISO_CI_NODE22:-$HOME/.local/opt/node-22/bin}
[ -x "$N22/node" ] || { echo "siso-ci: no Node 22 at $N22 on this runner"; exit 1; }
export PATH="$N22:$PATH"
export LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
export PG_BIN=/opt/homebrew/opt/postgresql@16/bin CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CACHE=${SISO_CI_NM_CACHE:-$HOME/.cache/siso-ci/node_modules}
T0=$(date +%s)
step_done() { echo "[siso-ci-step] $1 $(( $(date +%s) - $2 ))s"; }

# 1. dependencies, keyed by the lockfile hash
s=$(date +%s)
KEY=$( (cat package-lock.json; node -v; uname -m) | shasum | cut -c1-16 )
if [ -f node_modules/.siso-lock-key ] && [ "$(cat node_modules/.siso-lock-key)" = "$KEY" ]; then
  echo "[siso-ci] node_modules already match the lockfile ($KEY): npm ci skipped"
else
  mkdir -p "$CACHE"
  if [ -d "$CACHE/$KEY/node_modules" ]; then
    echo "[siso-ci] restoring node_modules from the cache ($KEY)"
    mkdir -p "$CACHE/_old" && [ -d node_modules ] && mv node_modules "$CACHE/_old/nm-$$-$(date +%s)"
    cp -Rc "$CACHE/$KEY/node_modules" node_modules || exit 1
  else
    echo "[siso-ci] lockfile changed ($KEY): npm ci"
    npm ci --no-audit --no-fund || exit 1
    echo "$KEY" > node_modules/.siso-lock-key
    mkdir -p "$CACHE/$KEY" && cp -Rc node_modules "$CACHE/$KEY/node_modules"
    # keep the 3 newest cache entries; the rest are moved aside (nothing is deleted)
    mkdir -p "$CACHE/_old"; ls -t "$CACHE" | grep -v '^_old$' | tail -n +4 | while read -r k; do mv "$CACHE/$k" "$CACHE/_old/$k-$(date +%s)"; done
  fi
  echo "$KEY" > node_modules/.siso-lock-key
fi
step_done deps "$s"

# 2. everything else in parallel; each prints its own seconds
OUT=$(mktemp -d)
run() { # name command...
  n=$1; shift; s=$(date +%s)
  "$@" > "$OUT/$n.log" 2>&1; c=$?
  echo "$c" > "$OUT/$n.code"; echo "$(( $(date +%s) - s ))" > "$OUT/$n.secs"
}
# which tests: the files the diff touches (FULL when a shared file changed)
export TMPDIR=/tmp/hv2; mkdir -p "$TMPDIR"   # short: Postgres' unix socket path must stay under 103 characters
# the repo's own picker when it has one (v2/ci/changed-tests.mjs: importers too, a migration runs only the db tests, and the
# whole suite only for the harness), else this runner's directory picker
if [ -f ci/changed-tests.mjs ]; then PICK=$(node ci/changed-tests.mjs) || PICK=FULL
else PICK=$(node "$(dirname "$0")/halo-affected.mjs") || PICK=FULL; fi
FLAGS=$(node -p "require('./package.json').scripts.test" | sed 's/ "[^"]*"//g')
case "$FLAGS" in "node --test"*) ;; *) echo "siso-ci: v2 npm test is not 'node --test ...' any more; update ci/halo-pr.sh"; exit 1;; esac
FLAGS=$(echo "$FLAGS" | sed 's/^node --test /node --test --test-timeout=30000 /')
if [ "$PICK" = FULL ]; then
  CAP=300; echo "[siso-ci] a shared file changed: full suite (cap ${CAP}s)"
  TESTCMD=$(node -p "require('./package.json').scripts.test" | sed 's/^node --test /node --test --test-timeout=30000 /')
elif [ -z "$PICK" ]; then
  CAP=120; echo "[siso-ci] no test file touched by this diff: typecheck and model checks only"; TESTCMD=true
else
  CAP=120; echo "[siso-ci] $(echo "$PICK" | wc -l | tr -d ' ') test file(s) touched by this diff:"; echo "$PICK" | sed 's/^/  /'
  TESTCMD="$FLAGS $(echo "$PICK" | sed 's/.*/"&"/' | tr '\n' ' ')"
fi
run typecheck npm run typecheck & P="$!"
run typecheck-model npm run typecheck:model & P="$P $!"
run check-model npm run check:model & P="$P $!"
run test sh -c "$TESTCMD" & P="$P $!"
# at CAP-20 s name the test files still running, at CAP kill the job: a hang is attributed, never a silent pending
( sleep $((CAP - 20)); echo "[siso-ci] JOB CAP NEAR: still running:" >&2; ps -axo command | grep -E '\.test\.(ts|mjs)' | grep -v grep | sed 's/^/[siso-ci] HUNG /' >&2
  sleep 20; echo "[siso-ci] JOB CAP ${CAP}s: killing" >&2; kill -TERM 0 ) &
WD=$!
wait $P
kill $WD 2>/dev/null
rc=0
for n in typecheck typecheck-model check-model test; do
  c=$(cat "$OUT/$n.code" 2>/dev/null || echo 1)
  echo "[siso-ci-step] $n $(cat "$OUT/$n.secs" 2>/dev/null || echo ?)s exit $c"
  if [ "$c" != 0 ]; then rc=1; echo "---- $n log tail ----"; tail -n 60 "$OUT/$n.log"; fi
done
[ $rc = 0 ] && grep -E '^# (tests|pass|fail|cancelled)' "$OUT/test.log" | tr '\n' ' ' && echo
echo "[siso-ci-step] total $(( $(date +%s) - T0 ))s"
exit $rc
